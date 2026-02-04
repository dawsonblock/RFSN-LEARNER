from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    # Deterministic serialization for hashing and replay
    # Custom encoder to handle frozenset and tuple
    class SafeEncoder(json.JSONEncoder):
        def default(self, o: Any) -> Any:
            if isinstance(o, frozenset):
                return sorted(list(o))
            if isinstance(o, tuple):
                return list(o)
            if isinstance(o, set):
                return sorted(list(o))
            return super().default(o)
    
    return json.dumps(
        obj, cls=SafeEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_json(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj))


def hash_mapping(m: Mapping[str, Any]) -> str:
    return sha256_json(m)
