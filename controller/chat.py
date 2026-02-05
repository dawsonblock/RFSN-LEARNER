"""
Interactive CLI chat loop demonstrating the agent flow.

User → proposal → gate → tool → response
With ledger + learner integration.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from rfsn.types import WorldSnapshot
from rfsn.ledger import AppendOnlyLedger
from rfsn.policy import AgentPolicy, DEFAULT_POLICY, DEV_POLICY

from .action_parser import parse_llm_response
from .agent_gate import agent_gate
from .tool_router import route_action, list_available_tools, ExecutionContext
from .tools.filesystem import ToolResult
from .planner import execute_plan
from .planner.generator import generate_plan
from .learner_bridge import LearnerBridge, LearnerConfig
from .replay_store import ReplayStore
from .agent_loop import run_agent_turn, AgentConfig
from .context_builder import ContextConfig


def create_world_snapshot(
    session_id: str,
    context: ExecutionContext,
    policy: AgentPolicy,
) -> WorldSnapshot:
    """Create a WorldSnapshot for the current session state."""
    return WorldSnapshot(
        session_id=session_id,
        world_state_hash=context.compute_world_hash(),
        enabled_tools=tuple(sorted(policy.allowed_tools)),
        permissions=frozenset(),
        system_clean=True,
        metadata={"user_id": context.user_id},
    )


def format_result(result: ToolResult) -> str:
    """Format a tool result for display."""
    if result.success:
        if isinstance(result.output, list):
            return "\n".join(f"  - {item}" for item in result.output[:20])
        elif isinstance(result.output, dict):
            return json.dumps(result.output, indent=2)
        else:
            return str(result.output)
    else:
        return f"Error: {result.error}"


def run_demo_mode():
    """Run a non-interactive demo showing the flow."""
    print("=== RFSN Agent Demo ===\n")
    
    session_id = str(uuid.uuid4())[:8]
    policy = DEV_POLICY
    context = ExecutionContext(session_id=session_id)
    ledger = AppendOnlyLedger("agent_ledger.jsonl")
    
    demo_actions = [
        # Allowed action
        '{"action": "tool_call", "tool": "list_dir", "arguments": {"path": "./"}, "justification": "List current directory"}',
        # Blocked tool
        '{"action": "tool_call", "tool": "dangerous_tool", "arguments": {}, "justification": "Try dangerous tool"}',
        # Memory write
        '{"action": "tool_call", "tool": "memory_store", "arguments": {"key": "demo_key", "value": "demo_value"}, "justification": "Store test value"}',
        # Message send
        '{"action": "message_send", "message": "Hello, this is a test message", "justification": "Greet user"}',
    ]
    
    for i, raw in enumerate(demo_actions, 1):
        print(f"--- Demo action {i} ---")
        print(f"Raw: {raw[:60]}...")
        
        # Parse
        action = parse_llm_response(raw)
        print(f"Parsed: kind={action.kind}, payload={action.payload}")
        
        # Create snapshot
        snapshot = create_world_snapshot(session_id, context, policy)
        
        # Gate
        decision = agent_gate(snapshot, action, policy=policy)
        print(f"Decision: {'ALLOW' if decision.allow else 'DENY'} - {decision.reason}")
        
        # Log to ledger
        decision_str = "allow" if decision.allow else f"deny:{decision.reason}"
        ledger.append(snapshot, action, decision_str)
        
        # Execute if allowed
        if decision.allow and action.kind == "tool_call":
            result = route_action(action.payload, context)
            print(f"Result: {format_result(result)[:100]}")
        
        print()
    
    print(f"Ledger entries written to: agent_ledger.jsonl")
    print("Demo complete!")


def run_interactive_mode(policy: AgentPolicy, replay: ReplayStore | None = None):
    """Run an interactive chat loop."""
    session_id = str(uuid.uuid4())[:8]
    context = ExecutionContext(session_id=session_id)
    ledger = AppendOnlyLedger("agent_ledger.jsonl")
    
    print("=== RFSN Agent Chat ===")
    print(f"Session: {session_id}")
    print(f"Policy: {'DEV (permissive)' if policy == DEV_POLICY else 'DEFAULT (restrictive)'}")
    print()
    print("Commands:")
    print("  /tools          - List available tools")
    print("  /policy         - Show current policy")
    print("  /plan <goal>    - Generate and execute a plan")
    print("  /quit           - Exit")
    print("  /{tool} args    - Call a tool directly")
    print("  {json}          - Send JSON action")
    print()
    
    # Initialize the learner bridge (closes the learning loop)
    learner = LearnerBridge(LearnerConfig(
        db_path=str(Path("./tmp/outcomes.sqlite")),
        enabled=True,
    ))
    print(f"Learner: enabled, db=./tmp/outcomes.sqlite")
    print()
    
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        # Meta commands
        if user_input == "/quit":
            print("Goodbye!")
            break
        
        if user_input == "/tools":
            print("\nAvailable tools:")
            for tool in list_available_tools():
                allowed = "✓" if tool["name"] in policy.allowed_tools else "✗"
                print(f"  [{allowed}] {tool['name']}: {tool['description']}")
            print()
            continue
        
        if user_input == "/policy":
            print(f"\nAllowed tools: {sorted(policy.allowed_tools)}")
            print(f"Path prefixes: {policy.allowed_path_prefixes}")
            print(f"Max payload: {policy.max_payload_bytes} bytes")
            print()
            continue
        
        if user_input.startswith("/plan "):
            goal = user_input[6:].strip()
            if not goal:
                print("Usage: /plan <goal>")
                continue
            
            print(f"\n[PLANNING] Goal: {goal}")
            
            # Learner picks strategy via Thompson sampling
            seed = int(uuid.uuid4().int & 0xFFFFFFFF)
            strategy = learner.choose_plan_strategy(goal=goal, seed=seed)
            
            # Generate plan with learned strategy
            snapshot = create_world_snapshot(session_id, context, policy)
            plan = generate_plan(goal, snapshot, strategy=strategy)
            
            print(f"[PLAN] Strategy: {plan.strategy} (learned), Steps: {len(plan.steps)}")
            for i, step in enumerate(plan.steps, 1):
                print(f"  {i}. {step.description} [{step.action.kind}]")
            
            print("\n[EXECUTING]")
            result = execute_plan(plan, context, snapshot, policy=policy)
            
            for sr in result.step_results:
                step = plan.get_step(sr.step_id)
                status = "✓" if sr.success else "✗"
                desc = step.description if step else sr.step_id
                print(f"  [{status}] {desc}")
                if sr.output and isinstance(sr.output, dict) and "message" in sr.output:
                    print(f"      → {sr.output['message']}")
                elif sr.error:
                    print(f"      → Error: {sr.error}")
            
            print(f"\n[RESULT] {'SUCCESS' if result.success else 'FAILED'} ({result.completed_steps}/{result.total_steps} steps)")
            
            # Record outcome to learner DB - THIS IS THE CLOSED LOOP
            learner.record_plan_outcome(
                goal=goal,
                strategy=strategy,
                plan=plan,
                result=result,
                meta={
                    "session_id": session_id,
                    "policy": "DEV" if policy == DEV_POLICY else "DEFAULT",
                    "seed": seed,
                },
            )
            print(f"[LEARNER] Recorded outcome: reward computed from {result.completed_steps}/{result.total_steps} steps")
            
            # Log to ledger
            for step in plan.steps:
                decision_str = "allow" if step.status == "completed" else f"deny:{step.error}"
                ledger.append(snapshot, step.action, decision_str)
            
            print()
            continue
        
        # Parse user input as action
        action = parse_llm_response(user_input)
        
        # Create snapshot
        snapshot = create_world_snapshot(session_id, context, policy)
        
        # Gate check
        decision = agent_gate(snapshot, action, policy=policy)
        
        # Log to ledger
        decision_str = "allow" if decision.allow else f"deny:{decision.reason}"
        ledger.append(snapshot, action, decision_str)
        
        if not decision.allow:
            print(f"\n[DENIED] {decision.reason}")
            if decision.suggested_alternative:
                print(f"[HINT] {decision.suggested_alternative}")
            print()
            continue
        
        # Execute
        print(f"\n[ALLOWED] {decision.reason}")
        
        if action.kind == "tool_call":
            result = route_action(action.payload, context)
            print(f"\nResult:\n{format_result(result)}")
        
        elif action.kind == "message_send":
            msg = action.payload.get("message", "") if isinstance(action.payload, dict) else str(action.payload)
            print(f"\nAgent: {msg}")
        
        elif action.kind == "memory_write":
            # Route through tool_call
            tool_action = {
                "tool": "memory_store",
                "arguments": action.payload if isinstance(action.payload, dict) else {},
            }
            result = route_action(tool_action, context)
            print(f"\nResult: {format_result(result)}")
        
        print()


def main():
    parser = argparse.ArgumentParser(description="RFSN Agent Chat")
    parser.add_argument("--demo", action="store_true", help="Run demo mode")
    parser.add_argument("--dev", action="store_true", help="Use permissive dev policy")
    parser.add_argument("--ledger", default="agent_ledger.jsonl", help="Ledger file path")
    parser.add_argument("--replay", default="off", choices=["off", "record", "replay"],
                        help="Replay mode: off|record|replay")
    parser.add_argument("--replay-file", default="./tmp/replay.jsonl",
                        help="Replay file path")
    
    args = parser.parse_args()
    
    # Initialize replay store
    replay_store = ReplayStore(path=args.replay_file, mode=args.replay)
    
    if args.demo:
        run_demo_mode()
    else:
        policy = DEV_POLICY if args.dev else DEFAULT_POLICY
        run_interactive_mode(policy, replay=replay_store)


if __name__ == "__main__":
    main()
