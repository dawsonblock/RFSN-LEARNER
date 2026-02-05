# controller/agent_loop.py
"""
Core agent loop: LLM → parse → validate → gate → execute → ledger.

Supports:
- Per-tool schema validation (pre-gate)
- Replay/record mode for deterministic runs
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from controller.action_io import ProposalError, parse_llm_json
from controller.agent_gate import agent_gate
from controller.context_builder import ContextConfig, build_context
from controller.llm_client import LLMClient, LLMConfig
from controller.prompts import SYSTEM_PROMPT, user_prompt
from controller.replay_store import ReplayRecord, ReplayStore
from controller.tool_router import ExecutionContext, route_action
from controller.validate_tool_call import validate_tool_call
from rfsn.ledger import AppendOnlyLedger
from rfsn.policy import DEFAULT_POLICY, AgentPolicy
from rfsn.types import ProposedAction, WorldSnapshot

# Type for event emission callback
EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass
class AgentConfig:
    """Configuration for the agent loop."""

    max_steps: int = 6
    context_cfg: ContextConfig | None = None
    llm_cfg: LLMConfig | None = None
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
    actions_replayed: int = 0


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
        pass


def _action_id(action: ProposedAction) -> str:
    """Stable ID for replay: hash kind + canonical payload."""
    payload = action.payload if isinstance(action.payload, dict) else {}
    blob = json.dumps(
        {"kind": action.kind, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


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
    replay: ReplayStore | None = None,
    emit: EmitFn | None = None,
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
        replay: Optional replay store for record/replay mode

    Returns:
        AgentResult with message and stats
    """
    # Helper to safely emit events
    def E(event_type: str, payload: dict[str, Any]) -> None:
        if emit is None:
            return
        try:
            emit(event_type, payload)
        except Exception:
            pass

    if cfg is None:
        cfg = AgentConfig()
    if policy is None:
        policy = DEFAULT_POLICY
    if exec_ctx is None:
        exec_ctx = ExecutionContext(session_id="default")

    llm = LLMClient(cfg.llm_cfg)
    E("turn_start", {"user_text": user_text})

    local_history = list(chat_history)
    final_message: str | None = None

    actions_proposed = 0
    actions_allowed = 0
    actions_denied = 0
    actions_replayed = 0

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
                action=ProposedAction(
                    kind="tool_call", payload={"error": "llm_call"}, justification="LLM call failed"
                ),
                decision=f"error:llm_call:{e}",
            )
            return AgentResult(
                message=f"LLM call failed: {e}",
                steps_taken=step,
                actions_proposed=actions_proposed,
                actions_allowed=actions_allowed,
                actions_denied=actions_denied,
                actions_replayed=actions_replayed,
            )

        E("llm_raw", {"step": step, "raw_head": raw[:1000]})

        # Parse JSON
        try:
            proposal = parse_llm_json(raw)
        except ProposalError as e:
            _append_to_ledger(
                ledger,
                world=world,
                action=ProposedAction(
                    kind="message_send",
                    payload={"message": "LLM_JSON_PARSE_ERROR"},
                    justification="Parse failed",
                ),
                decision="deny:llm_json_parse_error",
                extra={"error": str(e), "raw_head": raw[:500]},
            )
            return AgentResult(
                message="I couldn't parse the model output. Try a simpler request.",
                steps_taken=step + 1,
                actions_proposed=actions_proposed,
                actions_allowed=actions_allowed,
                actions_denied=actions_denied,
                actions_replayed=actions_replayed,
            )

        E("proposal_parsed", {"step": step, "num_actions": len(proposal.actions)})

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

            # 1) Schema validation for tool calls (pre-gate)
            v = validate_tool_call(action)
            if not v.ok:
                E("deny", {"step": step, "reason": "tool_args_invalid", "error": v.error, "action": {"kind": action.kind}})
                _append_to_ledger(
                    ledger,
                    world=world,
                    action=action,
                    decision="deny:tool_args_invalid",
                    extra={"error": v.error, "step": step},
                )
                E("ledger_append", {"step": step, "decision": "deny:tool_args_invalid"})
                # Feedback to model
                local_history.append(("tool", f"tool_args_invalid: {v.error}"))
                actions_denied += 1
                continue

            # 2) Gate decision
            decision = agent_gate(world, action, policy=policy)
            E("gate_decision", {
                "step": step,
                "allowed": decision.allow,
                "reason": decision.reason,
                "action": {"kind": action.kind, "payload": action.payload},
            })

            _append_to_ledger(
                ledger,
                world=world,
                action=action,
                decision="allow" if decision.allow else "deny",
                extra={"reason": decision.reason, "step": step},
            )
            E("ledger_append", {"step": step, "decision": "allow" if decision.allow else "deny"})

            if not decision.allow:
                actions_denied += 1
                continue

            actions_allowed += 1

            # 3) Replay handling for tool calls
            if action.kind == "tool_call" and replay is not None and replay.mode == "replay":
                aid = _action_id(action)
                rec = replay.get(aid)
                if rec is not None:
                    E("replay_hit", {"step": step, "tool": rec.tool, "action_id": aid, "ok": rec.ok, "summary": rec.summary})
                    _append_to_ledger(
                        ledger,
                        world=world,
                        action=ProposedAction(
                            kind="tool_call",
                            payload={"kind": action.kind, "replayed": True},
                            justification="Replay",
                        ),
                        decision="info:tool_result_replay",
                        extra={
                            "ok": rec.ok,
                            "summary": rec.summary,
                            "action_id": aid,
                            "step": step,
                        },
                    )
                    local_history.append(("tool", f"{rec.tool} (replay): {rec.summary}"))
                    actions_replayed += 1
                    continue
                else:
                    E("replay_miss", {"step": step, "action_id": aid})

            # 4) Execute based on action kind
            if action.kind == "message_send":
                msg = str(action.payload.get("message", ""))
                final_message = msg
                local_history.append(("assistant", msg))

            elif action.kind == "tool_call":
                tool = str(action.payload.get("tool", ""))
                args = action.payload.get("args", action.payload.get("arguments", {}))
                E("tool_call", {"step": step, "tool": tool, "arguments": args})

                # Execute tool
                result = route_action({"tool": tool, "arguments": args}, exec_ctx)

                ok = result.success
                summary = str(result.output) if result.success else f"ERROR: {result.error}"
                E("tool_result", {"step": step, "tool": tool, "ok": ok, "summary": summary[:500]})

                # 5) Record tool outputs for replay
                if replay is not None and replay.mode == "record":
                    aid = _action_id(action)
                    if isinstance(args, dict):
                        # Store structured output for replay (especially useful for shell tools)
                        data = result.output if isinstance(result.output, dict) else None
                        replay.put(
                            ReplayRecord(
                                action_id=aid,
                                tool=tool,
                                args=dict(args),
                                ok=ok,
                                summary=summary[:500],
                                data=data,
                            )
                        )

                _append_to_ledger(
                    ledger,
                    world=world,
                    action=ProposedAction(
                        kind="tool_call", payload={"tool": tool}, justification="Tool executed"
                    ),
                    decision="info:tool_result",
                    extra={"ok": ok, "summary": summary[:500], "step": step},
                )

                local_history.append(("tool", f"{tool}: {summary[:200]}"))

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

    E("turn_end", {"final_message": final_message})

    return AgentResult(
        message=final_message,
        steps_taken=step + 1,
        actions_proposed=actions_proposed,
        actions_allowed=actions_allowed,
        actions_denied=actions_denied,
        actions_replayed=actions_replayed,
    )
