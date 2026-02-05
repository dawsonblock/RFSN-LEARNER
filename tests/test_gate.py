# tests/test_gate.py
"""
Gate purity and invariant tests.

The gate must:
- Be a pure function (no I/O, no side effects)
- Always return a Decision
- Never raise exceptions for valid inputs
"""

from __future__ import annotations

from rfsn.gate import gate
from rfsn.types import ProposedAction, StateSnapshot


def make_snapshot(state_hash: str = "abc123") -> StateSnapshot:
    """Create a test snapshot."""
    return StateSnapshot(
        repo_id="test/repo@abc",
        fs_tree_hash=state_hash,
        toolchain="python3.9",
        tests_passed=True,
        metadata={},
    )


def make_action(kind: str = "patch_plan", payload: dict | None = None) -> ProposedAction:
    """Create a test action with a valid kind."""
    return ProposedAction(
        kind=kind,  # type: ignore
        payload=payload or {"diff": "test"},
        justification="test action",
    )


class TestGatePurity:
    """Gate must be pure - same inputs → same outputs."""

    def test_deterministic_output(self):
        """Same inputs always produce same outputs."""
        snapshot = make_snapshot()
        action = make_action()

        result1 = gate(snapshot, action)
        result2 = gate(snapshot, action)

        assert result1.allow == result2.allow
        assert result1.reason == result2.reason

    def test_no_mutation(self):
        """Gate does not mutate its inputs."""
        snapshot = make_snapshot()
        action = make_action()

        original_hash = snapshot.fs_tree_hash
        original_kind = action.kind

        gate(snapshot, action)

        assert snapshot.fs_tree_hash == original_hash
        assert action.kind == original_kind


class TestGateDecisions:
    """Gate decision logic tests."""

    def test_allows_patch_plan(self):
        """Gate allows patch_plan actions."""
        snapshot = make_snapshot()
        action = make_action(kind="patch_plan")

        result = gate(snapshot, action)
        assert result.allow is True

    def test_returns_decision_structure(self):
        """Gate returns a proper decision with allow and reason."""
        snapshot = make_snapshot()
        action = make_action(kind="patch_plan")

        result = gate(snapshot, action)

        assert hasattr(result, "allow")
        assert hasattr(result, "reason")
        assert isinstance(result.allow, bool)
        assert isinstance(result.reason, str)


class TestGateInvariants:
    """Gate invariant preservation tests."""

    def test_returns_decision(self):
        """Gate always returns a Decision object."""
        snapshot = make_snapshot()
        action = make_action()

        result = gate(snapshot, action)

        assert hasattr(result, "allow")
        assert hasattr(result, "reason")
        assert isinstance(result.allow, bool)
        assert isinstance(result.reason, str)

    def test_no_exceptions_on_valid_input(self):
        """Gate never raises exceptions for valid inputs."""
        snapshot = make_snapshot()

        # Only test valid action kinds
        for kind in ["patch_plan"]:
            action = make_action(kind=kind)
            # Should not raise
            result = gate(snapshot, action)
            assert result is not None
