# controller/replay.py
"""
Deterministic replay engine for LLM calls.

Enables:
- Recording mode: capture all LLM calls to a file
- Replay mode: inject recorded responses instead of calling LLM
- Debugging: reproduce exact failures
- Offline analysis: study LLM behavior without API costs

Usage:
    # Recording
    recorder = ReplayRecorder("run_001.jsonl")
    llm = LLMClient(config, recorder=recorder)
    
    # Replay
    replayer = ReplayPlayer("run_001.jsonl")
    llm = LLMClient(config, replayer=replayer)
"""
from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass, field, asdict
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


@dataclass
class ReplayEntry:
    """Single recorded LLM call."""
    request_hash: str
    system: str
    user: str
    model: str
    response: str
    latency_ms: float
    ts_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
    
    @classmethod
    def from_json(cls, line: str) -> "ReplayEntry":
        data = json.loads(line)
        return cls(**data)


class ReplayRecorder:
    """
    Records LLM calls to a JSONL file.
    
    Thread-safe append-only recording.
    """
    
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._count = 0
    
    def record(
        self,
        system: str,
        user: str,
        model: str,
        response: str,
        latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single LLM call."""
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
        
        with open(self.path, "a") as f:
            f.write(entry.to_json() + "\n")
        
        self._count += 1
    
    @property
    def count(self) -> int:
        return self._count


class ReplayPlayer:
    """
    Replays recorded LLM calls from a JSONL file.
    
    Supports two matching modes:
    - Sequential: return entries in order
    - Hash-based: match by request content hash
    """
    
    def __init__(self, path: str | Path, match_mode: str = "sequential"):
        self.path = Path(path)
        self.match_mode = match_mode
        self._entries: list[ReplayEntry] = []
        self._by_hash: dict[str, list[ReplayEntry]] = {}
        self._seq_idx = 0
        
        self._load()
    
    def _load(self) -> None:
        """Load all entries from file."""
        if not self.path.exists():
            return
        
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = ReplayEntry.from_json(line)
                self._entries.append(entry)
                
                # Index by hash
                if entry.request_hash not in self._by_hash:
                    self._by_hash[entry.request_hash] = []
                self._by_hash[entry.request_hash].append(entry)
    
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


@dataclass
class ReplayContext:
    """
    Context manager for replay/record mode.
    
    Usage:
        with ReplayContext(mode="record", path="run.jsonl") as ctx:
            # All LLM calls in this block are recorded
            ...
    """
    mode: str  # "record", "replay", "live"
    path: str | Path | None = None
    match_mode: str = "sequential"
    
    recorder: ReplayRecorder | None = field(default=None, init=False)
    player: ReplayPlayer | None = field(default=None, init=False)
    
    def __enter__(self) -> "ReplayContext":
        if self.mode == "record" and self.path:
            self.recorder = ReplayRecorder(self.path)
        elif self.mode == "replay" and self.path:
            self.player = ReplayPlayer(self.path, match_mode=self.match_mode)
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
