"""
Plan executor - execute plans step by step with gate checks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rfsn.types import WorldSnapshot
from rfsn.policy import AgentPolicy, DEFAULT_POLICY

from ..agent_gate import agent_gate
from ..tool_router import route_action, ExecutionContext
from .types import Plan, PlanStep, PlanResult, StepResult


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
        message = action.payload.get("message", "") if isinstance(action.payload, dict) else str(action.payload)
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
) -> PlanResult:
    """
    Execute plan with rollback on failure.
    
    Note: Actual rollback requires reversible actions, which is not
    always possible. This is a placeholder for future implementation.
    """
    result = execute_plan(plan, context, world, policy=policy, stop_on_failure=True)
    
    if not result.success:
        # TODO: Implement actual rollback for reversible actions
        # For now, just log that we would rollback
        pass
    
    return result
