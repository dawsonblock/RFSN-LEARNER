# tests/test_replay_integrity.py
"""
Tests for replay system integrity features.

Tests cover:
- HMAC signing and verification
- Chain hash integrity
- Tamper detection
- Backward compatibility
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from controller.replay import (
    IntegrityError,
    ReplayContext,
    ReplayEntry,
    ReplayPlayer,
    ReplayRecorder,
    verify_replay_file,
)


class TestReplayRecording:
    """Tests for ReplayRecorder with integrity features."""

    def test_basic_recording(self):
        """Basic recording without integrity features."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path)
        recorder.record(
            system="You are a helper",
            user="Hello",
            model="test-model",
            response="Hi there!",
            latency_ms=100.0,
        )

        assert recorder.count == 1
        assert Path(path).exists()

        # Verify content
        with open(path) as f:
            line = f.read().strip()
            data = json.loads(line)
            assert data["response"] == "Hi there!"
            assert data["latency_ms"] == 100.0

    def test_recording_with_hmac(self):
        """Recording with HMAC signing."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path, secret="test_secret_key")
        recorder.record(
            system="System prompt",
            user="User message",
            model="model-v1",
            response="Response text",
        )

        # Verify HMAC is present
        with open(path) as f:
            data = json.loads(f.read().strip())
            assert "entry_hmac" in data
            assert len(data["entry_hmac"]) == 32

    def test_recording_with_chain_hashing(self):
        """Recording with chain hashing."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path, enable_chain=True)

        # Record multiple entries
        for i in range(3):
            recorder.record(
                system="System",
                user=f"Message {i}",
                model="model",
                response=f"Response {i}",
            )

        # Verify chain hashes
        with open(path) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        assert len(entries) == 3
        assert entries[0]["prev_chain_hash"] == "0" * 16  # Genesis
        assert entries[1]["prev_chain_hash"] == entries[0]["chain_hash"]
        assert entries[2]["prev_chain_hash"] == entries[1]["chain_hash"]


class TestReplayPlayback:
    """Tests for ReplayPlayer with integrity verification."""

    def test_sequential_playback(self):
        """Sequential playback mode."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        # Record
        recorder = ReplayRecorder(path)
        recorder.record(system="S", user="U1", model="M", response="R1")
        recorder.record(system="S", user="U2", model="M", response="R2")

        # Playback
        player = ReplayPlayer(path, match_mode="sequential")
        assert player.get() == "R1"
        assert player.get() == "R2"
        assert player.get() is None  # Exhausted

    def test_hash_playback(self):
        """Hash-based playback mode."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        # Record
        recorder = ReplayRecorder(path)
        recorder.record(system="S", user="Query1", model="M", response="Answer1")
        recorder.record(system="S", user="Query2", model="M", response="Answer2")

        # Playback by hash
        player = ReplayPlayer(path, match_mode="hash")
        assert player.get(system="S", user="Query2", model="M") == "Answer2"
        assert player.get(system="S", user="Query1", model="M") == "Answer1"

    def test_hmac_verification_success(self):
        """Successful HMAC verification."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        secret = "my_secret_key"

        # Record with HMAC
        recorder = ReplayRecorder(path, secret=secret)
        recorder.record(system="S", user="U", model="M", response="R")

        # Verify playback works
        player = ReplayPlayer(path, secret=secret, verify_hmac=True)
        assert player.count == 1
        assert len(player.integrity_errors) == 0

    def test_hmac_verification_failure(self):
        """HMAC verification detects tampering."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        # Record with HMAC
        recorder = ReplayRecorder(path, secret="original_secret")
        recorder.record(system="S", user="U", model="M", response="R")

        # Try to verify with wrong secret - should detect tampering
        try:
            player = ReplayPlayer(path, secret="wrong_secret", verify_hmac=True)
            # IntegrityError should be raised
            assert False, "Expected IntegrityError"
        except IntegrityError as e:
            assert "HMAC mismatch" in str(e)

    def test_chain_verification_success(self):
        """Successful chain hash verification."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path, enable_chain=True)
        for i in range(3):
            recorder.record(system="S", user=f"U{i}", model="M", response=f"R{i}")

        player = ReplayPlayer(path, verify_chain=True)
        assert player.count == 3
        assert len(player.integrity_errors) == 0

    def test_chain_verification_detects_deletion(self):
        """Chain verification detects deleted entries."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path, enable_chain=True)
        for i in range(3):
            recorder.record(system="S", user=f"U{i}", model="M", response=f"R{i}")

        # Remove middle entry (simulates deletion attack)
        with open(path) as f:
            lines = f.readlines()
        with open(path, "w") as f:
            f.write(lines[0])  # Keep first
            f.write(lines[2])  # Skip middle, keep last

        # Chain should be broken
        try:
            player = ReplayPlayer(path, verify_chain=True)
            assert False, "Expected IntegrityError"
        except IntegrityError as e:
            assert "Chain hash" in str(e)


class TestReplayContext:
    """Tests for ReplayContext context manager."""

    def test_record_context(self):
        """Context manager in record mode."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        with ReplayContext(mode="record", path=path) as ctx:
            assert ctx.recorder is not None

            # Simulate intercept
            def mock_llm(system, user, model, **kwargs):
                return f"Response to: {user}"

            response = ctx.intercept(
                system="S",
                user="Hello",
                model="M",
                live_fn=mock_llm,
            )
            assert response == "Response to: Hello"
            assert ctx.recorder.count == 1

    def test_replay_context(self):
        """Context manager in replay mode."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        # First record
        with ReplayContext(mode="record", path=path) as ctx:

            def mock_llm(system, user, model, **kwargs):
                return "Recorded response"

            ctx.intercept(system="S", user="U", model="M", live_fn=mock_llm)

        # Then replay
        with ReplayContext(mode="replay", path=path) as ctx:
            assert ctx.player is not None

            def should_not_be_called(system, user, model, **kwargs):
                raise AssertionError("Should use recorded response")

            response = ctx.intercept(
                system="S",
                user="U",
                model="M",
                live_fn=should_not_be_called,
            )
            assert response == "Recorded response"


class TestVerifyReplayFile:
    """Tests for verify_replay_file utility."""

    def test_verify_valid_file(self):
        """Verify a valid replay file."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path, secret="key", enable_chain=True)
        recorder.record(system="S", user="U", model="M", response="R")

        is_valid, errors = verify_replay_file(path, secret="key")
        assert is_valid
        assert len(errors) == 0

    def test_verify_tampered_file(self):
        """Verify detects tampered file."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        recorder = ReplayRecorder(path, secret="key", enable_chain=True)
        recorder.record(system="S", user="U", model="M", response="R")

        # Tamper with the file
        with open(path, "r") as f:
            data = json.loads(f.read().strip())
        data["response"] = "TAMPERED"
        with open(path, "w") as f:
            f.write(json.dumps(data))

        is_valid, errors = verify_replay_file(path, secret="key")
        assert not is_valid
        assert len(errors) > 0


class TestBackwardCompatibility:
    """Tests for backward compatibility with old replay files."""

    def test_load_file_without_integrity_fields(self):
        """Load replay file without HMAC/chain fields."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            # Write old-format entry
            old_entry = {
                "request_hash": "abc123",
                "system": "S",
                "user": "U",
                "model": "M",
                "response": "R",
                "latency_ms": 50.0,
                "ts_utc": "2024-01-01T00:00:00Z",
                "metadata": {},
            }
            f.write(json.dumps(old_entry).encode() + b"\n")
            path = f.name

        # Should load without errors
        player = ReplayPlayer(path)
        assert player.count == 1
        assert player.get() == "R"
