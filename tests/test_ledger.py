# tests/test_ledger.py
"""
Ledger hash-chain integrity tests.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rfsn.ledger import AppendOnlyLedger
from rfsn.types import StateSnapshot, ProposedAction


def make_snapshot() -> StateSnapshot:
    """Create a test snapshot."""
    return StateSnapshot(
        repo_id="test/repo@abc",
        fs_tree_hash="abc123",
        toolchain="python3.9",
        tests_passed=True,
        metadata={},
    )


def make_action(kind: str = "patch_plan") -> ProposedAction:
    """Create a test action."""
    return ProposedAction(
        kind=kind,  # type: ignore
        payload={"diff": "test"},
        justification="test action",
    )


class TestLedgerAppend:
    """Ledger append functionality."""

    def test_creates_file_on_first_append(self):
        """Ledger creates file when first entry is appended."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.jsonl")
            ledger = AppendOnlyLedger(path)

            # append(state, action, decision)
            ledger.append(make_snapshot(), make_action(), "allow")

            assert Path(path).exists()

    def test_appends_valid_json(self):
        """Each ledger entry is valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.jsonl")
            ledger = AppendOnlyLedger(path)

            ledger.append(make_snapshot(), make_action(), "allow")
            ledger.append(make_snapshot(), make_action(), "deny")

            with open(path) as f:
                lines = f.readlines()

            assert len(lines) == 2
            for line in lines:
                entry = json.loads(line)
                # Payload contains state and action
                assert "payload" in entry
                assert "state" in entry["payload"]
                assert "action" in entry["payload"]


class TestLedgerHashChain:
    """Ledger hash-chain integrity."""

    def test_entries_have_hash(self):
        """Each entry contains a hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.jsonl")
            ledger = AppendOnlyLedger(path)

            ledger.append(make_snapshot(), make_action(), "allow")

            with open(path) as f:
                entry = json.loads(f.readline())

            assert "entry_hash" in entry
            assert len(entry["entry_hash"]) == 64  # SHA256 hex

    def test_entries_chain_to_previous(self):
        """Each entry references the previous hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.jsonl")
            ledger = AppendOnlyLedger(path)

            ledger.append(make_snapshot(), make_action(), "allow")
            ledger.append(make_snapshot(), make_action(), "deny")

            with open(path) as f:
                lines = f.readlines()

            entry1 = json.loads(lines[0])
            entry2 = json.loads(lines[1])

            assert entry2.get("prev_entry_hash") == entry1.get("entry_hash")

    def test_first_entry_has_zero_prev(self):
        """First entry has zero previous hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.jsonl")
            ledger = AppendOnlyLedger(path)

            ledger.append(make_snapshot(), make_action(), "allow")

            with open(path) as f:
                entry = json.loads(f.readline())

            prev = entry.get("prev_entry_hash")
            assert prev == "0" * 64
