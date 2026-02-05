# controller/turn_utils.py
"""
Turn management utilities for consistent budget reset across all entrypoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tool_router import ExecutionContext


def start_turn(context: "ExecutionContext") -> None:
    """
    Hard reset per-turn budgets.

    Call once per user input / request across all entrypoints
    (chat, cli, API, etc.) to ensure consistent budget enforcement.
    """
    context.start_new_turn()
