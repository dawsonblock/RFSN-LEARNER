"""
Plan generator - create plans from goals using strategies.
"""
from __future__ import annotations


from rfsn.types import WorldSnapshot
from .types import Plan, PlanStep, PlanStrategy
from .decomposer import decompose_goal


def generate_plan(
    goal: str,
    context: WorldSnapshot | None = None,
    strategy: PlanStrategy = "direct",
) -> Plan:
    """
    Generate a plan to accomplish a goal.
    
    Strategies:
    - direct: Single step, immediate execution
    - decompose: Break into subtasks
    - search_first: Search for context before acting
    - ask_user: Request clarification first
    """
    if strategy == "direct":
        steps = _direct_strategy(goal)
    elif strategy == "decompose":
        steps = _decompose_strategy(goal, context)
    elif strategy == "search_first":
        steps = _search_first_strategy(goal, context)
    elif strategy == "ask_user":
        steps = _ask_user_strategy(goal)
    else:
        # Fallback
        steps = _direct_strategy(goal)
    
    return Plan.create(
        goal=goal,
        steps=steps,
        strategy=strategy,
        metadata={"context_session": context.session_id if context else None},
    )


def _direct_strategy(goal: str) -> list[PlanStep]:
    """Single direct action."""
    return decompose_goal(goal)[:1]  # Take only first step


def _decompose_strategy(
    goal: str,
    context: WorldSnapshot | None = None,
) -> list[PlanStep]:
    """Fully decompose into subtasks."""
    return decompose_goal(goal, context.metadata if context else None)


def _search_first_strategy(
    goal: str,
    context: WorldSnapshot | None = None,
) -> list[PlanStep]:
    """Search for relevant context before main action."""
    from rfsn.types import ProposedAction
    
    # First: search for relevant files
    search_step = PlanStep.create(
        description="Search for relevant context",
        action=ProposedAction(
            kind="tool_call",
            payload={"tool": "list_dir", "arguments": {"path": "./"}},
            justification=f"Gather context for: {goal}",
        ),
    )
    
    # Then: decompose the actual goal
    main_steps = decompose_goal(goal, context.metadata if context else None)
    
    # Link dependencies
    for step in main_steps:
        if not step.depends_on:
            step.depends_on.append(search_step.step_id)
    
    return [search_step] + main_steps


def _ask_user_strategy(goal: str) -> list[PlanStep]:
    """Request user clarification before proceeding."""
    from rfsn.types import ProposedAction
    
    return [
        PlanStep.create(
            description="Request clarification from user",
            action=ProposedAction(
                kind="message_send",
                payload={
                    "message": f"Before I proceed with '{goal}', could you clarify:\n"
                               f"1. What specific outcome do you expect?\n"
                               f"2. Are there any constraints I should be aware of?"
                },
                justification="Clarification needed before execution",
            ),
        )
    ]


def select_strategy(
    goal: str,
    available_tools: tuple[str, ...] = (),
) -> PlanStrategy:
    """
    Heuristically select the best strategy for a goal.
    
    This can be replaced with learned selection via learner module.
    """
    goal_lower = goal.lower()
    
    # Complex multi-step goals -> decompose
    if any(w in goal_lower for w in [" and ", " then ", " after "]):
        return "decompose"
    
    # Vague goals -> ask_user
    if any(w in goal_lower for w in ["help", "how do i", "what should"]):
        return "ask_user"
    
    # Goals requiring context -> search_first
    if any(w in goal_lower for w in ["analyze", "summarize", "review", "understand"]):
        return "search_first"
    
    # Default -> direct
    return "direct"


def auto_plan(
    goal: str,
    context: WorldSnapshot | None = None,
) -> Plan:
    """
    Automatically generate a plan with the best strategy.
    """
    strategy = select_strategy(
        goal,
        context.enabled_tools if context else (),
    )
    return generate_plan(goal, context, strategy)
