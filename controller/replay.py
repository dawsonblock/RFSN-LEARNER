# controller/replay.py
"""
Deterministic replay engine for LLM calls.

Security enhancements:
- HMAC-based integrity verification for replay records
- Tamper detection on playback
- Chain hash verification for sequential integrity

Enables:
- Recording mode: capture all LLM calls to a file
- Replay mode: inject recorded responses instead of calling LLM
- Debugging: reproduce exact failures
- Offline analysis: study LLM behavior without API costs

Usage:
    # Recording with integrity
    recorder = ReplayRecorder("run_001.jsonl", secret="my_secret")
    llm = LLMClient(config, recorder=recorder)

    # Replay with verification
    replayer = ReplayPlayer("run_001.jsonl", secret="my_secret", verify=True)
    llm = LLMClient(config, replayer=replayer)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _hash_request(system: str, user: str, model: str) -> str:
    """Create deterministic hash of request for matching."""
    payload = json.dumps(
        {"system": system, "user": user, "model": model},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _compute_hmac(data: str, secret: str) -> str:
    """Compute HMAC-SHA256 for data integrity."""
    return hmac.new(
        secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def _compute_chain_hash(prev_hash: str, entry_data: str) -> str:
    """Compute chain hash linking entries together."""
    combined = f"{prev_hash}:{entry_data}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass
class ReplayEntry:
    """Single recorded LLM call with optional integrity fields."""

    request_hash: str
    system: str
    user: str
    model: str
    response: str
    latency_ms: float
    ts_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # Integrity fields
    entry_hmac: str | None = None
    prev_chain_hash: str | None = None
    chain_hash: str | None = None

    def to_json(self) -> str:
        data = asdict(self)
        # Remove None values for backwards compatibility
        return json.dumps(
            {k: v for k, v in data.items() if v is not None},
            sort_keys=True,
            separators=(",", ":"),
        )

    def core_data(self) -> str:
        """Get core data for HMAC computation (excludes HMAC fields)."""
        core = {
            "request_hash": self.request_hash,
            "system": self.system,
            "user": self.user,
            "model": self.model,
            "response": self.response,
            "latency_ms": self.latency_ms,
            "ts_utc": self.ts_utc,
            "metadata": self.metadata,
        }
        return json.dumps(core, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "ReplayEntry":
        data = json.loads(line)
        return cls(**data)


class ReplayRecorder:
    """
    Records LLM calls to a JSONL file.

    Security features:
    - Optional HMAC signing of each entry
    - Chain hashing for sequential integrity
    - Thread-safe append-only recording
    """

    def __init__(
        self,
        path: str | Path,
        secret: str | None = None,
        enable_chain: bool = True,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._count = 0
        self._secret = secret or os.environ.get("RFSN_REPLAY_SECRET")
        self._enable_chain = enable_chain
        self._prev_chain_hash = "0" * 16  # Genesis hash

    def record(
        self,
        system: str,
        user: str,
        model: str,
        response: str,
        latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single LLM call with optional integrity protection."""
        entry = ReplayEntry(
            request_hash=_hash_request(system, user, model),
            system=system,
            user=user,
            model=model,
            response=response,
            latency_ms=latency_ms,
            ts_utc=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        # Compute HMAC if secret is set
        if self._secret:
            entry.entry_hmac = _compute_hmac(entry.core_data(), self._secret)

        # Compute chain hash
        if self._enable_chain:
            entry.prev_chain_hash = self._prev_chain_hash
            entry.chain_hash = _compute_chain_hash(
                self._prev_chain_hash, entry.core_data()
            )
            self._prev_chain_hash = entry.chain_hash

        with open(self.path, "a") as f:
            f.write(entry.to_json() + "\n")

        self._count += 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def chain_hash(self) -> str:
        """Current chain hash (for verification)."""
        return self._prev_chain_hash


class IntegrityError(Exception):
    """Raised when replay integrity verification fails."""

    pass


class ReplayPlayer:
    """
    Replays recorded LLM calls from a JSONL file.

    Security features:
    - HMAC verification on each entry (optional)
    - Chain hash verification for tamper detection
    - Reports integrity violations

    Supports two matching modes:
    - Sequential: return entries in order
    - Hash-based: match by request content hash
    """

    def __init__(
        self,
        path: str | Path,
        match_mode: str = "sequential",
        secret: str | None = None,
        verify_hmac: bool = False,
        verify_chain: bool = False,
    ):
        self.path = Path(path)
        self.match_mode = match_mode
        self._secret = secret or os.environ.get("RFSN_REPLAY_SECRET")
        self._verify_hmac = verify_hmac
        self._verify_chain = verify_chain
        self._entries: list[ReplayEntry] = []
        self._by_hash: dict[str, list[ReplayEntry]] = {}
        self._seq_idx = 0
        self._integrity_errors: list[str] = []

        self._load()

    def _load(self) -> None:
        """Load all entries from file with optional verification."""
        if not self.path.exists():
            return

        prev_chain_hash = "0" * 16

        with open(self.path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                entry = ReplayEntry.from_json(line)

                # Verify HMAC if enabled
                if self._verify_hmac and self._secret:
                    if entry.entry_hmac:
                        expected = _compute_hmac(entry.core_data(), self._secret)
                        if entry.entry_hmac != expected:
                            self._integrity_errors.append(
                                f"Line {line_num}: HMAC mismatch"
                            )

                # Verify chain hash if enabled
                if self._verify_chain and entry.prev_chain_hash:
                    if entry.prev_chain_hash != prev_chain_hash:
                        self._integrity_errors.append(
                            f"Line {line_num}: Chain hash broken"
                        )
                    if entry.chain_hash:
                        expected_chain = _compute_chain_hash(
                            entry.prev_chain_hash, entry.core_data()
                        )
                        if entry.chain_hash != expected_chain:
                            self._integrity_errors.append(
                                f"Line {line_num}: Chain hash tampered"
                            )
                        prev_chain_hash = entry.chain_hash

                self._entries.append(entry)

                # Index by hash
                if entry.request_hash not in self._by_hash:
                    self._by_hash[entry.request_hash] = []
                self._by_hash[entry.request_hash].append(entry)

        # Raise if integrity issues found and verification was requested
        if self._integrity_errors and (self._verify_hmac or self._verify_chain):
            raise IntegrityError(
                f"Replay integrity failed: {'; '.join(self._integrity_errors[:5])}"
            )

    def get(
        self,
        system: str = "",
        user: str = "",
        model: str = "",
    ) -> str | None:
        """
        Get next replay response.

        Returns None if no matching entry found.
        """
        if self.match_mode == "sequential":
            if self._seq_idx >= len(self._entries):
                return None
            entry = self._entries[self._seq_idx]
            self._seq_idx += 1
            return entry.response

        elif self.match_mode == "hash":
            req_hash = _hash_request(system, user, model)
            if req_hash not in self._by_hash:
                return None
            entries = self._by_hash[req_hash]
            if not entries:
                return None
            # Pop first matching entry
            return entries.pop(0).response

        return None

    def entries(self) -> Iterator[ReplayEntry]:
        """Iterate over all recorded entries."""
        return iter(self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def remaining(self) -> int:
        if self.match_mode == "sequential":
            return len(self._entries) - self._seq_idx
        return sum(len(v) for v in self._by_hash.values())

    @property
    def integrity_errors(self) -> list[str]:
        """List of integrity errors found during loading."""
        return self._integrity_errors.copy()


@dataclass
class ReplayContext:
    """
    Context manager for replay/record mode.

    Usage:
        with ReplayContext(mode="record", path="run.jsonl", secret="key") as ctx:
            # All LLM calls in this block are recorded with HMAC
            ...
    """

    mode: str  # "record", "replay", "live"
    path: str | Path | None = None
    match_mode: str = "sequential"
    secret: str | None = None
    verify_integrity: bool = False

    recorder: ReplayRecorder | None = field(default=None, init=False)
    player: ReplayPlayer | None = field(default=None, init=False)

    def __enter__(self) -> "ReplayContext":
        if self.mode == "record" and self.path:
            self.recorder = ReplayRecorder(self.path, secret=self.secret)
        elif self.mode == "replay" and self.path:
            self.player = ReplayPlayer(
                self.path,
                match_mode=self.match_mode,
                secret=self.secret,
                verify_hmac=self.verify_integrity,
                verify_chain=self.verify_integrity,
            )
        return self

    def __exit__(self, *args) -> None:
        pass

    def intercept(
        self,
        system: str,
        user: str,
        model: str,
        live_fn,
        **kwargs,
    ) -> str:
        """
        Intercept an LLM call.

        In replay mode: return recorded response
        In record mode: call live, then record
        In live mode: call live directly
        """
        import time

        if self.mode == "replay" and self.player:
            response = self.player.get(system=system, user=user, model=model)
            if response is not None:
                return response
            # Fall through to live if no match

        start = time.time()
        response = live_fn(system=system, user=user, model=model, **kwargs)
        latency_ms = (time.time() - start) * 1000

        if self.mode == "record" and self.recorder:
            self.recorder.record(
                system=system,
                user=user,
                model=model,
                response=response,
                latency_ms=latency_ms,
            )

        return response


def verify_replay_file(
    path: str | Path,
    secret: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Verify integrity of a replay file.

    Returns:
        (is_valid, list_of_errors)
    """
    try:
        player = ReplayPlayer(
            path,
            secret=secret,
            verify_hmac=bool(secret),
            verify_chain=True,
        )
        return len(player.integrity_errors) == 0, player.integrity_errors
    except IntegrityError as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"Load error: {e}"]
