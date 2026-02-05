# controller/replay_store.py
"""
JSONL replay store for deterministic tool execution.

Modes:
- "off": Normal execution (default)
- "record": Execute tools and save outputs
- "replay": Return saved outputs instead of executing
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ReplayRecord:
    """A recorded tool execution."""
    action_id: str
    tool: str
    args: dict[str, Any]
    ok: bool
    summary: str
    data: dict[str, Any] | None = None


class ReplayStore:
    """
    JSONL replay store for tool outputs.
    
    - record mode: appends tool results
    - replay mode: finds matching action_id and returns stored output
    """

    def __init__(self, path: str, mode: str = "off"):
        """
        Initialize replay store.
        
        Args:
            path: Path to JSONL file
            mode: "off" | "record" | "replay"
        """
        if mode not in ("off", "record", "replay"):
            raise ValueError("mode must be off|record|replay")
        self.path = path
        self.mode = mode
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, ReplayRecord] | None = None

    def _load_index(self) -> None:
        """Load replay index from file."""
        idx: dict[str, ReplayRecord] = {}
        p = Path(self.path)
        if not p.exists():
            self._index = {}
            return
        
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    rec = ReplayRecord(
                        action_id=str(obj["action_id"]),
                        tool=str(obj["tool"]),
                        args=dict(obj.get("args", {})),
                        ok=bool(obj.get("ok", False)),
                        summary=str(obj.get("summary", "")),
                        data=obj.get("data", None),
                    )
                    idx[rec.action_id] = rec
                except Exception:
                    # Skip corrupted lines
                    continue
        self._index = idx

    def get(self, action_id: str) -> ReplayRecord | None:
        """Get a recorded result by action ID."""
        if self.mode != "replay":
            return None
        if self._index is None:
            self._load_index()
        return (self._index or {}).get(action_id)

    def put(self, rec: ReplayRecord) -> None:
        """Record a tool execution result."""
        if self.mode != "record":
            return
        
        obj = {
            "action_id": rec.action_id,
            "tool": rec.tool,
            "args": rec.args,
            "ok": rec.ok,
            "summary": rec.summary,
            "data": rec.data,
        }
        
        with Path(self.path).open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")

    def count(self) -> int:
        """Count recorded entries."""
        if self._index is None:
            self._load_index()
        return len(self._index or {})
