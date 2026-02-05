"""
Plan executor - execute plans step by step with gate checks.
"""

from __future__ import annotations

from rfsn.policy import DEFAULT_POLICY, AgentPolicy
from rfsn.types import WorldSnapshot

from ..agent_gate import agent_gate
from ..tool_router import ExecutionContext, route_action
from .types import Plan, PlanResult, PlanStep, StepResult


def execute_step(
    step: PlanStep,
    context: ExecutionContext,
    world: WorldSnapshot,
    policy: AgentPolicy,
) -> StepResult:
    """
    Execute a single plan step.

    1. Gate check
    2. If allowed: execute action
    3. Return result
    """
    action = step.action

    # Gate check
    decision = agent_gate(world, action, policy=policy)

    if not decision.allow:
        return StepResult(
            step_id=step.step_id,
            success=False,
            gated=False,
            gate_reason=decision.reason,
            error=f"Blocked by gate: {decision.reason}",
        )

    # Execute based on action kind
    if action.kind == "tool_call":
        result = route_action(action.payload, context)
        return StepResult(
            step_id=step.step_id,
            success=result.success,
            output=result.output,
            error=result.error,
            gated=True,
            gate_reason=decision.reason,
        )

    elif action.kind == "message_send":
        # Messages are "executed" by returning them
        message = (
            action.payload.get("message", "")
            if isinstance(action.payload, dict)
            else str(action.payload)
        )
        return StepResult(
            step_id=step.step_id,
            success=True,
            output={"message": message},
            gated=True,
            gate_reason=decision.reason,
        )

    elif action.kind == "memory_write":
        # Route through memory tool
        tool_action = {
            "tool": "memory_store",
            "arguments": action.payload if isinstance(action.payload, dict) else {},
        }
        result = route_action(tool_action, context)
        return StepResult(
            step_id=step.step_id,
            success=result.success,
            output=result.output,
            error=result.error,
            gated=True,
            gate_reason=decision.reason,
        )

    else:
        return StepResult(
            step_id=step.step_id,
            success=False,
            error=f"Unsupported action kind: {action.kind}",
            gated=True,
            gate_reason=decision.reason,
        )


def execute_plan(
    plan: Plan,
    context: ExecutionContext,
    world: WorldSnapshot,
    *,
    policy: AgentPolicy | None = None,
    stop_on_failure: bool = True,
) -> PlanResult:
    """
    Execute all steps in a plan.

    Respects step dependencies and can stop on first failure.
    """
    if policy is None:
        policy = DEFAULT_POLICY

    step_results: list[StepResult] = []
    completed = 0
    failed = 0

    # Process steps in order, respecting dependencies
    while True:
        pending = plan.pending_steps
        if not pending:
            break

        # Execute next pending step
        step = pending[0]
        step.status = "in_progress"

        result = execute_step(step, context, world, policy)
        step_results.append(result)

        if result.success:
            step.status = "completed"
            step.result = result.output
            completed += 1
        else:
            step.status = "failed"
            step.error = result.error
            failed += 1

            if stop_on_failure:
                # Skip remaining steps
                for s in plan.steps:
                    if s.status == "pending":
                        s.status = "skipped"
                break

    success = failed == 0 and completed == len(plan.steps)

    return PlanResult(
        plan_id=plan.plan_id,
        success=success,
        step_results=step_results,
        total_steps=len(plan.steps),
        completed_steps=completed,
        failed_steps=failed,
        error=step_results[-1].error if step_results and not step_results[-1].success else None,
    )


def execute_plan_with_rollback(
    plan: Plan,
    context: ExecutionContext,
    world: WorldSnapshot,
    *,
    policy: AgentPolicy | None = None,
    ledger: object | None = None,
) -> PlanResult:
    """
    Execute plan with rollback on failure.

    Uses ledger checkpoint to restore state if execution fails.
    Rollback works by truncating the ledger to the checkpoint and
    replaying from that point (deterministic replay model).
    """
    # Capture checkpoint before execution
    checkpoint_index = None
    if ledger is not None and hasattr(ledger, "load_entries"):
        try:
            entries = ledger.load_entries()
            checkpoint_index = len(entries)
        except Exception:
            pass

    result = execute_plan(plan, context, world, policy=policy, stop_on_failure=True)

    if not result.success and checkpoint_index is not None:
        # Rollback via ledger truncation
        rollback_via_replay(ledger, checkpoint_index)

    return result


def rollback_via_replay(ledger: object, checkpoint_index: int) -> bool:
    """
    Rollback ledger to checkpoint by rebuilding from entries up to checkpoint.

    This implements deterministic rollback by:
    1. Loading all entries up to checkpoint
    2. Rebuilding ledger from those entries only

    Returns True if rollback succeeded, False otherwise.
    """
    if ledger is None:
        return False

    try:
        if hasattr(ledger, "load_entries") and hasattr(ledger, "rebuild_from"):
            entries = ledger.load_entries()
            ledger.rebuild_from(entries[:checkpoint_index])
            return True
        elif hasattr(ledger, "path"):
            # Fallback: truncate file directly (for AppendOnlyLedger)
            from pathlib import Path

            path = Path(ledger.path)
            if not path.exists():
                return False

            lines = path.read_text().strip().split("\n")
            truncated = lines[:checkpoint_index]
            path.write_text("\n".join(truncated) + "\n" if truncated else "")
            return True
    except Exception:
        pass

    return False

