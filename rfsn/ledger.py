from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from typing import Any, Mapping

from .crypto import sha256_json, sha256_bytes, canonical_json
from .types import LedgerEntry, ProposedAction, StateSnapshot


class AppendOnlyLedger:
    """
    Simple JSONL ledger with a hash chain.
    No edits. No deletes. Rotation is allowed by external tooling.
    """

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _now_utc_iso(self) -> str:
        # Ledger is an outer component; keep it simple.
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _last_entry_hash(self) -> str:
        if not os.path.exists(self.path):
            return "0" * 64
        last = None
        with open(self.path, "rb") as f:
            for line in f:
                if line.strip():
                    last = line
        if not last:
            return "0" * 64
        obj = json.loads(last.decode("utf-8"))
        return obj["entry_hash"]

    def append(
        self,
        state: StateSnapshot,
        action: ProposedAction,
        decision: str,
        extra_payload: Mapping[str, Any] | None = None,
    ) -> LedgerEntry:
        prev = self._last_entry_hash()

        state_hash = sha256_json(asdict(state))
        action_hash = sha256_json(asdict(action))

        idx = 0
        if os.path.exists(self.path):
            with open(self.path, "rb") as f:
                for line in f:
                    if line.strip():
                        idx += 1

        payload: dict[str, Any] = {
            "state": asdict(state),
            "action": asdict(action),
            "decision": decision,
        }
        if extra_payload:
            payload["extra"] = dict(extra_payload)

        entry_core = {
            "idx": idx,
            "ts_utc": self._now_utc_iso(),
            "state_hash": state_hash,
            "action_hash": action_hash,
            "decision": decision,
            "prev_entry_hash": prev,
            "payload": payload,
        }

        entry_hash = sha256_bytes(canonical_json(entry_core))
        entry_obj = dict(entry_core)
        entry_obj["entry_hash"] = entry_hash

        with open(self.path, "ab") as f:
            f.write(canonical_json(entry_obj) + b"\n")

        return LedgerEntry(
            idx=idx,
            ts_utc=entry_obj["ts_utc"],
            state_hash=state_hash,
            action_hash=action_hash,
            decision=decision,
            prev_entry_hash=prev,
            entry_hash=entry_hash,
            payload=payload,
        )
