from __future__ import annotations

import json
from typing import Iterator

from .crypto import sha256_json


def iter_ledger(path: str) -> Iterator[dict]:
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                yield json.loads(line.decode("utf-8"))


def verify_hash_chain(path: str) -> tuple[bool, str]:
    prev = "0" * 64
    for i, obj in enumerate(iter_ledger(path)):
        if obj["prev_entry_hash"] != prev:
            return False, f"Broken chain at line {i}: prev mismatch"
        entry_core = dict(obj)
        entry_hash = entry_core.pop("entry_hash")
        expected = sha256_json(entry_core)
        if expected != entry_hash:
            return False, f"Broken hash at line {i}: entry hash mismatch"
        prev = entry_hash
    return True, "OK"
