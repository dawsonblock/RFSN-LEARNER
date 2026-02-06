# controller/planner/sqlite_snapshot.py
"""
SQLite snapshot system for database state rollback.

Copies SQLite files at checkpoints and restores them on rollback.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class SqliteTarget:
    """A SQLite database to snapshot."""
    name: str
    path: str  # absolute or relative to workdir


def _resolve(workdir: str, p: str) -> Path:
    """Resolve path relative to workdir if not absolute."""
    wd = Path(workdir).resolve()
    pp = Path(p)
    if not pp.is_absolute():
        pp = wd / pp
    return pp.resolve()


def snapshot_sqlite_files(
    workdir: str,
    targets: Iterable[SqliteTarget],
    checkpoint_id: str,
) -> List[str]:
    """
    Copy each sqlite file to <path>.rfsn_snap.<checkpoint_id>

    Returns list of created snapshot paths.
    """
    created: List[str] = []
    for t in targets:
        db = _resolve(workdir, t.path)
        if not db.exists():
            # If DB doesn't exist yet, skip; rollback will also skip.
            continue
        snap = db.with_name(db.name + f".rfsn_snap.{checkpoint_id}")
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, snap)
        created.append(str(snap))
    return created


def restore_sqlite_files(
    workdir: str,
    targets: Iterable[SqliteTarget],
    checkpoint_id: str,
) -> None:
    """Restore each sqlite file from its snapshot. If snapshot missing, skip."""
    for t in targets:
        db = _resolve(workdir, t.path)
        snap = db.with_name(db.name + f".rfsn_snap.{checkpoint_id}")
        if not snap.exists():
            continue
        db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snap, db)


def cleanup_sqlite_snaps(
    workdir: str,
    targets: Iterable[SqliteTarget],
    keep_last: Optional[int] = 5,
) -> None:
    """Optional cleanup: keep only N most recent snapshots per DB."""
    for t in targets:
        db = _resolve(workdir, t.path)
        if not db.parent.exists():
            continue
        snaps = sorted(
            db.parent.glob(db.name + ".rfsn_snap.*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if keep_last is None:
            continue
        for p in snaps[keep_last:]:
            try:
                p.unlink()
            except Exception:
                pass
