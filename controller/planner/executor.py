# controller/planner/executor.py
"""
Plan executor - execute plans step by step with real rollback support.

ROLLBACK SEMANTICS:
- Workdir filesystem: rolled back via git checkpoint/reset
- SQLite databases: rolled back via file snapshots
- Ledger: append-only (abort events logged, no truncation)
- External side effects: NOT rolled back (network, etc.)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from rfsn.policy import DEFAULT_POLICY, AgentPolicy
from rfsn.types import WorldSnapshot

from ..agent_gate import agent_gate
from ..tool_router import ExecutionContext, route_action
from .sqlite_snapshot import (
    SqliteTarget,
    cleanup_sqlite_snaps,
    restore_sqlite_files,
    snapshot_sqlite_files,
)
from .types import Plan, PlanResult, PlanStep, StepResult
from .workdir_checkpoint import checkpoint, ensure_git_repo, reset_hard

# Tools that can mutate state.
MUTATING_TOOLS = {
    "write_file",
    "apply_diff",
    "memory_delete",
    "memory_store",
    "run_command",
    "run_python",
    "sandbox_exec",
}


def _emit(
    emit: Optional[Callable[[str, Dict[str, Any]], None]],
    typ: str,
    payload: Dict[str, Any],
) -> None:
    """Emit planner event, swallowing exceptions."""
    if emit is None:
        return
    try:
        emit(typ, payload)
    except Exception:
        # Planner emit must never crash execution.
        pass


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
    emit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    enable_workdir_rollback: bool = False,
    sqlite_targets: Optional[List[SqliteTarget]] = None,
    keep_sqlite_snaps: int = 5,
) -> PlanResult:
    """
    Execute all steps in a plan with optional real rollback support.

    REAL ROLLBACK (when enable_workdir_rollback=True):
    - Before each mutating step, creates a git checkpoint
    - On failure, resets workdir to last checkpoint
    - SQLite DBs in sqlite_targets are also snapshotted/restored

    Ledger remains append-only (abort events logged, no truncation).
    """
    if policy is None:
        policy = DEFAULT_POLICY

    step_results: list[StepResult] = []
    completed = 0
    failed = 0
    sqlite_targets = sqlite_targets or []

    # Rollback state
    last_checkpoint: Optional[str] = None
    last_sqlite_checkpoint_id: Optional[str] = None
    rolled_back = False
    rollback_error: Optional[str] = None

    # Initialize workdir checkpoint if enabled
    if enable_workdir_rollback:
        try:
            ensure_git_repo(context.working_directory)
            last_checkpoint = checkpoint(context.working_directory, "plan_start")
            _emit(emit, "planner_checkpoint", {"commit": last_checkpoint, "label": "plan_start"})

            if sqlite_targets:
                last_sqlite_checkpoint_id = f"{int(time.time())}_start"
                snapshot_sqlite_files(context.working_directory, sqlite_targets, last_sqlite_checkpoint_id)
                cleanup_sqlite_snaps(context.working_directory, sqlite_targets, keep_last=keep_sqlite_snaps)
                _emit(emit, "planner_sqlite_snapshot", {
                    "checkpoint_id": last_sqlite_checkpoint_id,
                    "targets": [t.name for t in sqlite_targets],
                })
        except Exception as e:
            _emit(emit, "planner_checkpoint_error", {"error": str(e)})
            # Continue without rollback support
            enable_workdir_rollback = False

    _emit(emit, "planner_start", {
        "steps": len(plan.steps),
        "workdir_rollback": enable_workdir_rollback,
    })

    # Process steps in order, respecting dependencies
    step_index = 0
    while True:
        pending = plan.pending_steps
        if not pending:
            break

        # Execute next pending step
        step = pending[0]
        step.status = "in_progress"

        # Determine if this step can mutate state
        tool_name = ""
        if step.action and step.action.kind == "tool_call":
            payload = step.action.payload
            if isinstance(payload, dict):
                tool_name = str(payload.get("tool", ""))

        is_mutating = tool_name in MUTATING_TOOLS
        is_irreversible = tool_name in ("memory_store", "memory_delete")  # Can't rollback these

        _emit(emit, "planner_step_start", {
            "step": step_index,
            "tool": tool_name,
            "is_mutating": is_mutating,
            "irreversible": is_irreversible,
        })

        if is_mutating and is_irreversible:
            _emit(emit, "planner_note", {
                "step": step_index,
                "note": "mutating_step_irreversible",
                "tool": tool_name,
            })

        # Create checkpoint before mutating workdir step
        if enable_workdir_rollback and is_mutating and not is_irreversible:
            try:
                last_checkpoint = checkpoint(context.working_directory, f"before_step_{step_index}_{tool_name}")
                _emit(emit, "planner_checkpoint", {
                    "commit": last_checkpoint,
                    "label": f"before_step_{step_index}_{tool_name}",
                })

                if sqlite_targets:
                    last_sqlite_checkpoint_id = f"{int(time.time())}_{step_index}"
                    snapshot_sqlite_files(context.working_directory, sqlite_targets, last_sqlite_checkpoint_id)
                    cleanup_sqlite_snaps(context.working_directory, sqlite_targets, keep_last=keep_sqlite_snaps)
            except Exception as e:
                _emit(emit, "planner_checkpoint_error", {"step": step_index, "error": str(e)})

        # Execute the step
        result = execute_step(step, context, world, policy)
        step_results.append(result)

        _emit(emit, "planner_step_end", {
            "step": step_index,
            "tool": tool_name,
            "ok": result.success,
        })

        if result.success:
            step.status = "completed"
            step.result = result.output
            completed += 1
        else:
            step.status = "failed"
            step.error = result.error
            failed += 1

            _emit(emit, "planner_abort", {
                "step": step_index,
                "reason": result.error,
                "tool": tool_name,
            })

            if stop_on_failure:
                # Attempt rollback
                if enable_workdir_rollback and last_checkpoint:
                    rolled_back, rollback_error = _attempt_rollback(
                        context.working_directory,
                        last_checkpoint,
                        emit,
                        sqlite_targets,
                        last_sqlite_checkpoint_id,
                    )

                # Skip remaining steps
                for s in plan.steps:
                    if s.status == "pending":
                        s.status = "skipped"
                break

        step_index += 1

    success = failed == 0 and completed == len(plan.steps)

    _emit(emit, "planner_end", {
        "ok": success,
        "completed_steps": completed,
        "rolled_back": rolled_back,
    })

    return PlanResult(
        plan_id=plan.plan_id,
        success=success,
        step_results=step_results,
        total_steps=len(plan.steps),
        completed_steps=completed,
        failed_steps=failed,
        error=step_results[-1].error if step_results and not step_results[-1].success else None,
    )


def _attempt_rollback(
    workdir: str,
    last_checkpoint: str,
    emit: Optional[Callable[[str, Dict[str, Any]], None]],
    sqlite_targets: List[SqliteTarget],
    last_sqlite_checkpoint_id: Optional[str],
) -> tuple[bool, Optional[str]]:
    """Attempt to rollback workdir and sqlite state to last checkpoint."""
    try:
        reset_hard(workdir, last_checkpoint)
        _emit(emit, "planner_rollback", {"ok": True, "commit": last_checkpoint})

        # Restore sqlite
        if sqlite_targets and last_sqlite_checkpoint_id:
            try:
                restore_sqlite_files(workdir, sqlite_targets, last_sqlite_checkpoint_id)
                _emit(emit, "planner_sqlite_restore", {
                    "ok": True,
                    "checkpoint_id": last_sqlite_checkpoint_id,
                })
            except Exception as e:
                _emit(emit, "planner_sqlite_restore", {
                    "ok": False,
                    "checkpoint_id": last_sqlite_checkpoint_id,
                    "error": str(e),
                })
                return True, f"sqlite_restore_failed: {e}"

        return True, None
    except Exception as e:
        _emit(emit, "planner_rollback", {
            "ok": False,
            "commit": last_checkpoint,
            "error": str(e),
        })
        return False, str(e)


# Legacy compatibility - deprecated, do not use
def execute_plan_with_rollback(
    plan: Plan,
    context: ExecutionContext,
    world: WorldSnapshot,
    *,
    policy: AgentPolicy | None = None,
    ledger: object | None = None,
) -> PlanResult:
    """
    DEPRECATED: Use execute_plan(..., enable_workdir_rollback=True) instead.

    This legacy function is kept for backward compatibility but now uses
    real git-based rollback instead of the broken ledger truncation.
    """
    import warnings
    warnings.warn(
        "execute_plan_with_rollback is deprecated. Use execute_plan with enable_workdir_rollback=True",
        DeprecationWarning,
        stacklevel=2,
    )

    return execute_plan(
        plan,
        context,
        world,
        policy=policy,
        stop_on_failure=True,
        enable_workdir_rollback=True,
    )


# Old rollback function is removed - ledger truncation is NOT rollback
# If you need the old behavior for debugging, it was called rollback_via_replay
# but it has been removed because it violated append-only semantics
