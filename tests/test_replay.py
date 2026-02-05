# tests/test_replay.py
"""
Tests for replay engine.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from controller.replay import (
    ReplayRecorder,
    ReplayPlayer,
    ReplayContext,
    ReplayEntry,
)


class TestReplayRecorder:
    """Recorder tests."""

    def test_creates_file(self):
        """Recorder creates file on first record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "replay.jsonl"
            recorder = ReplayRecorder(path)

            recorder.record(
                system="sys",
                user="usr",
                model="test",
                response="hello",
            )

            assert path.exists()
            assert recorder.count == 1

    def test_appends_entries(self):
        """Recorder appends multiple entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "replay.jsonl"
            recorder = ReplayRecorder(path)

            recorder.record(system="s1", user="u1", model="m", response="r1")
            recorder.record(system="s2", user="u2", model="m", response="r2")

            with open(path) as f:
                lines = f.readlines()

            assert len(lines) == 2


class TestReplayPlayer:
    """Player tests."""

    def test_loads_entries(self):
        """Player loads recorded entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "replay.jsonl"

            # Record
            recorder = ReplayRecorder(path)
            recorder.record(system="s", user="u", model="m", response="hello")

            # Play
            player = ReplayPlayer(path)
            assert player.count == 1

    def test_sequential_replay(self):
        """Sequential mode returns entries in order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "replay.jsonl"

            # Record
            recorder = ReplayRecorder(path)
            recorder.record(system="s", user="u", model="m", response="first")
            recorder.record(system="s", user="u", model="m", response="second")

            # Play
            player = ReplayPlayer(path, match_mode="sequential")
            assert player.get() == "first"
            assert player.get() == "second"
            assert player.get() is None


class TestReplayContext:
    """Context manager tests."""

    def test_record_mode(self):
        """Context enables recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "replay.jsonl"

            with ReplayContext(mode="record", path=path) as ctx:
                assert ctx.recorder is not None

    def test_replay_mode(self):
        """Context enables replay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "replay.jsonl"

            # First record something
            with open(path, "w") as f:
                entry = ReplayEntry(
                    request_hash="abc",
                    system="s",
                    user="u",
                    model="m",
                    response="test",
                    latency_ms=0,
                    ts_utc="2024-01-01",
                )
                f.write(entry.to_json() + "\n")

            with ReplayContext(mode="replay", path=path) as ctx:
                assert ctx.player is not None
                assert ctx.player.count == 1
