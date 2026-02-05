# controller/budget_enforcer.py
"""
Per-turn budget enforcement for tool calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .tool_registry import Budget


@dataclass
class TurnBudgetState:
    """Tracks budget usage for current turn."""
    calls: dict[str, int] = field(default_factory=dict)
    bytes: dict[str, int] = field(default_factory=dict)


class BudgetEnforcer:
    """
    Per-turn budget enforcement. Reset at the start of each user turn.
    """

    def __init__(self) -> None:
        self.state = TurnBudgetState()

    def reset_turn(self) -> None:
        """Reset all budgets for new turn."""
        self.state = TurnBudgetState()

    def check_and_charge(
        self,
        *,
        tool: str,
        budget: Budget,
        estimated_bytes: int = 0,
    ) -> tuple[bool, str]:
        """
        Check if tool call is within budget, and charge if so.
        
        Returns (ok, error_message).
        """
        # Check call count
        c = self.state.calls.get(tool, 0) + 1
        if c > budget.calls_per_turn:
            return False, f"budget exceeded: calls_per_turn {c}/{budget.calls_per_turn}"
        self.state.calls[tool] = c

        # Check bytes if applicable
        if budget.max_bytes is not None:
            b = self.state.bytes.get(tool, 0) + max(0, int(estimated_bytes))
            if b > budget.max_bytes:
                return False, f"budget exceeded: max_bytes {b}/{budget.max_bytes}"
            self.state.bytes[tool] = b

        return True, ""

    def get_usage(self, tool: str) -> dict[str, int]:
        """Get current usage for a tool."""
        return {
            "calls": self.state.calls.get(tool, 0),
            "bytes": self.state.bytes.get(tool, 0),
        }
