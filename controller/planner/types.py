"""
Core types for the hierarchical planner.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


from rfsn.types import ProposedAction


StepStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PlanStrategy = Literal["direct", "decompose", "search_first", "ask_user"]


@dataclass
class PlanStep:
    """A single step in a plan."""
    step_id: str
    description: str
    action: ProposedAction
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = "pending"
    error: str | None = None
    result: Any = None
    
    @classmethod
    def create(
        cls,
        description: str,
        action: ProposedAction,
        depends_on: list[str] | None = None,
    ) -> PlanStep:
        return cls(
            step_id=str(uuid.uuid4())[:8],
            description=description,
            action=action,
            depends_on=depends_on or [],
        )


@dataclass
class Plan:
    """A hierarchical plan with multiple steps."""
    plan_id: str
    goal: str
    steps: list[PlanStep]
    strategy: PlanStrategy
    metadata: Mapping[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        goal: str,
        steps: list[PlanStep],
        strategy: PlanStrategy = "direct",
        metadata: Mapping[str, Any] | None = None,
    ) -> Plan:
        return cls(
            plan_id=str(uuid.uuid4())[:8],
            goal=goal,
            steps=steps,
            strategy=strategy,
            metadata=metadata or {},
        )
    
    @property
    def pending_steps(self) -> list[PlanStep]:
        """Get steps that are ready to execute (pending + deps satisfied)."""
        completed_ids = {s.step_id for s in self.steps if s.status == "completed"}
        return [
            s for s in self.steps
            if s.status == "pending"
            and all(dep in completed_ids for dep in s.depends_on)
        ]
    
    @property
    def is_complete(self) -> bool:
        """Check if all steps are completed or skipped."""
        return all(s.status in ("completed", "skipped") for s in self.steps)
    
    @property
    def has_failed(self) -> bool:
        """Check if any step has failed."""
        return any(s.status == "failed" for s in self.steps)
    
    def get_step(self, step_id: str) -> PlanStep | None:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: str
    success: bool
    output: Any = None
    error: str | None = None
    gated: bool = True  # was allowed by gate
    gate_reason: str = ""


@dataclass
class PlanResult:
    """Result of executing an entire plan."""
    plan_id: str
    success: bool
    step_results: list[StepResult]
    total_steps: int
    completed_steps: int
    failed_steps: int
    error: str | None = None
    
    @property
    def completion_rate(self) -> float:
        if self.total_steps == 0:
            return 1.0
        return self.completed_steps / self.total_steps
