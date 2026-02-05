# controller/agent_loop.py
"""
Core agent loop: LLM → parse → gate → execute → ledger.

This is the main entry point for the multi-purpose agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rfsn.ledger import AppendOnlyLedger
from rfsn.types import ProposedAction, WorldSnapshot
from rfsn.policy import AgentPolicy, DEFAULT_POLICY

from controller.prompts import SYSTEM_PROMPT, user_prompt
from controller.context_builder import build_context, ContextConfig
from controller.action_io import parse_llm_json, ProposalError, validate_tool_args
from controller.agent_gate import agent_gate
from controller.tool_router import route_action, ExecutionContext
from controller.llm_client import LLMClient, LLMConfig


@dataclass
class AgentConfig:
    """Configuration for the agent loop."""
    max_steps: int = 6
    context_cfg: ContextConfig = None  # type: ignore
    llm_cfg: LLMConfig = None  # type: ignore
    require_reply_each_turn: bool = True
    
    def __post_init__(self):
        if self.context_cfg is None:
            self.context_cfg = ContextConfig()
        if self.llm_cfg is None:
            self.llm_cfg = LLMConfig()


@dataclass
class AgentResult:
    """Result of an agent turn."""
    message: str
    steps_taken: int
    actions_proposed: int
    actions_allowed: int
    actions_denied: int


def _state_snapshot(world: Any) -> Any:
    """Get a stable snapshot for ledger."""
    if hasattr(world, "to_state_snapshot"):
        return world.to_state_snapshot()
    return world


def _append_to_ledger(
    ledger: AppendOnlyLedger | None,
    *,
    world: Any,
    action: ProposedAction,
    decision: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append entry to ledger (if provided)."""
    if ledger is None:
        return
    
    try:
        ledger.append(
            state=_state_snapshot(world),
            action=action,
            decision=decision,
        )
    except Exception:
        # Don't break agent loop if ledger fails
        pass


def run_agent_turn(
    *,
    user_text: str,
    chat_history: list[tuple[str, str]],
    world: WorldSnapshot | Any,
    policy: AgentPolicy | None = None,
    ledger: AppendOnlyLedger | None = None,
    exec_ctx: ExecutionContext | None = None,
    memory: Any | None = None,
    cfg: AgentConfig | None = None,
) -> AgentResult:
    """
    Execute one user turn through the agent loop.
    
    Args:
        user_text: User's input message
        chat_history: Previous (role, text) pairs
        world: Current world state (for gate)
        policy: Agent policy (defaults to DEFAULT_POLICY)
        ledger: Optional ledger for logging
        exec_ctx: Execution context for tools
        memory: Optional memory store
        cfg: Agent configuration
    
    Returns:
        AgentResult with message and stats
    """
    if cfg is None:
        cfg = AgentConfig()
    if policy is None:
        policy = DEFAULT_POLICY
    if exec_ctx is None:
        exec_ctx = ExecutionContext(session_id="default")
    
    llm = LLMClient(cfg.llm_cfg)
    
    local_history = list(chat_history)
    final_message: str | None = None
    
    actions_proposed = 0
    actions_allowed = 0
    actions_denied = 0
    
    for step in range(cfg.max_steps):
        # Build context
        context_block = build_context(
            chat_history=local_history,
            user_text=user_text,
            memory=memory,
            cfg=cfg.context_cfg,
        )
        
        prompt = user_prompt(user_text=user_text, context_block=context_block)
        
        # Get LLM response
        try:
            raw = llm.complete_json(system=SYSTEM_PROMPT, user=prompt)
        except Exception as e:
            _append_to_ledger(
                ledger,
                world=world,
                action=ProposedAction(kind="error", payload={"type": "llm_call"}, justification="LLM call failed"),
                decision=f"error:llm_call:{e}",
            )
            return AgentResult(
                message=f"LLM call failed: {e}",
                steps_taken=step,
                actions_proposed=actions_proposed,
                actions_allowed=actions_allowed,
                actions_denied=actions_denied,
            )
        
        # Parse JSON
        try:
            proposal = parse_llm_json(raw)
        except ProposalError as e:
            _append_to_ledger(
                ledger,
                world=world,
                action=ProposedAction(kind="error", payload={"type": "parse"}, justification="Parse failed"),
                decision=f"error:parse:{e}",
                extra={"raw_head": raw[:500]},
            )
            return AgentResult(
                message="I couldn't parse the model output. Try a simpler request.",
                steps_taken=step + 1,
                actions_proposed=actions_proposed,
                actions_allowed=actions_allowed,
                actions_denied=actions_denied,
            )
        
        # Process each proposed action
        for action in proposal.actions:
            actions_proposed += 1
            
            # Ensure justification exists
            if not action.justification:
                action = ProposedAction(
                    kind=action.kind,
                    payload=action.payload,
                    justification=f"Auto: {action.kind}",
                )
            
            # Gate check
            decision = agent_gate(world, action, policy=policy)
            
            _append_to_ledger(
                ledger,
                world=world,
                action=action,
                decision=decision.decision if hasattr(decision, 'decision') else ("allow" if decision.allowed else "deny"),
                extra={"reason": decision.reason, "step": step},
            )
            
            if not decision.allowed:
                actions_denied += 1
                continue
            
            actions_allowed += 1
            
            # Execute based on action kind
            if action.kind == "message_send":
                msg = str(action.payload.get("message", ""))
                final_message = msg
                local_history.append(("assistant", msg))
            
            elif action.kind == "tool_call":
                # Validate args first
                tool = str(action.payload.get("tool", ""))
                args = action.payload.get("args", action.payload.get("arguments", {}))
                
                valid, err = validate_tool_args(tool, args)
                if not valid:
                    _append_to_ledger(
                        ledger,
                        world=world,
                        action=ProposedAction(kind="tool_result", payload={"tool": tool}, justification="Args invalid"),
                        decision=f"error:invalid_args:{err}",
                    )
                    local_history.append(("tool", f"{tool}: ERROR - {err}"))
                    continue
                
                # Execute tool
                result = route_action({"tool": tool, "arguments": args}, exec_ctx)
                
                summary = result.output if result.success else f"ERROR: {result.error}"
                local_history.append(("tool", f"{tool}: {str(summary)[:200]}"))
                
                _append_to_ledger(
                    ledger,
                    world=world,
                    action=ProposedAction(kind="tool_result", payload={"tool": tool}, justification="Tool executed"),
                    decision="info:tool_result",
                    extra={"ok": result.success, "summary": str(summary)[:500]},
                )
            
            elif action.kind == "memory_write":
                key = str(action.payload.get("key", ""))
                value = str(action.payload.get("value", ""))
                if memory and hasattr(memory, "store"):
                    try:
                        memory.store(key, value)
                        local_history.append(("tool", f"memory_write: stored '{key}'"))
                    except Exception as e:
                        local_history.append(("tool", f"memory_write: ERROR - {e}"))
                else:
                    local_history.append(("tool", "memory_write: no memory store available"))
            
            elif action.kind == "permission_request":
                req = str(action.payload.get("request", ""))
                why = str(action.payload.get("why", ""))
                final_message = f"I need permission: {req}\n\nReason: {why}"
                local_history.append(("assistant", final_message))
        
        # Check if we have a reply
        if final_message is not None:
            break
    
    if final_message is None:
        final_message = "I couldn't complete that request. Try asking for something specific."
    
    return AgentResult(
        message=final_message,
        steps_taken=step + 1,
        actions_proposed=actions_proposed,
        actions_allowed=actions_allowed,
        actions_denied=actions_denied,
    )
