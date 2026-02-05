# controller/ledger_events.py
"""
Helper functions for logging first-class events to the ledger.
"""

from __future__ import annotations

from typing import Any, Mapping

from rfsn.ledger import AppendOnlyLedger
from rfsn.types import ProposedAction


def ledger_info(
    ledger: AppendOnlyLedger,
    *,
    world,
    kind: str,
    payload: Mapping[str, Any],
    decision: str = "info:event",
    extra: Mapping[str, Any] | None = None,
) -> None:
    """
    Log an informational event to the ledger.

    Use for permission grants/revokes and other first-class events
    that should be recorded for replay.
    """
    # Convert world to state snapshot if needed
    if hasattr(world, "to_state_snapshot"):
        state = world.to_state_snapshot()
    else:
        state = world

    # Create action with required justification - cast kind for type checker
    action = ProposedAction(
        kind=kind,  # type: ignore[arg-type]
        payload=dict(payload),
        justification=f"System event: {kind}",
    )

    ledger.append(
        state=state,
        action=action,
        decision=decision,
        extra_payload=dict(extra or {}),
    )
