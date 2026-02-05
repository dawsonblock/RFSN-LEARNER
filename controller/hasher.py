"""
Deterministic filesystem hashing for StateSnapshot construction.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    "*.pyc",
    ".DS_Store",
    "node_modules",
    ".venv",
    "venv",
)


def _should_ignore(path: Path, ignore_patterns: Iterable[str]) -> bool:
    """Check if path matches any ignore pattern."""
    name = path.name
    for pattern in ignore_patterns:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False


def hash_file(path: Path) -> str:
    """SHA256 hash of a single file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_fs_tree_hash(
    root: Path | str,
    *,
    ignore_patterns: Iterable[str] = DEFAULT_IGNORE_PATTERNS,
) -> str:
    """
    Compute a deterministic hash of a directory tree.

    Walks in sorted order, hashing (relative_path, file_hash) pairs.
    This ensures reproducibility across runs and platforms.
    """
    root = Path(root).resolve()
    ignore_set = set(ignore_patterns)

    entries: list[tuple[str, str]] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)

        # Filter ignored directories in-place
        dirnames[:] = sorted(d for d in dirnames if not _should_ignore(current / d, ignore_set))

        # Process files in sorted order
        for fname in sorted(filenames):
            fpath = current / fname
            if _should_ignore(fpath, ignore_set):
                continue

            rel_path = fpath.relative_to(root).as_posix()
            file_hash = hash_file(fpath)
            entries.append((rel_path, file_hash))

    # Hash the sorted list of (path, hash) pairs
    tree_hasher = hashlib.sha256()
    for rel_path, file_hash in entries:
        tree_hasher.update(f"{rel_path}:{file_hash}\n".encode("utf-8"))

    return tree_hasher.hexdigest()
