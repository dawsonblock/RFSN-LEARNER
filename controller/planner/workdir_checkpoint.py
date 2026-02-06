# controller/planner/workdir_checkpoint.py
"""
Git-based workdir checkpoint system for real rollback semantics.

Creates checkpoint commits before mutating steps and can reset --hard
on failure to restore previous state.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)


def ensure_git_repo(workdir: str) -> None:
    """Ensure workdir is a git repo. Initialize if not."""
    wd = Path(workdir).resolve()
    wd.mkdir(parents=True, exist_ok=True)

    # If already a repo, do nothing.
    if (wd / ".git").exists():
        return

    r = _run(["git", "init"], wd)
    if r.returncode != 0:
        raise RuntimeError(f"git init failed: {r.stderr.strip()}")

    # Basic identity for local commits
    _run(["git", "config", "user.email", "rfsn@local"], wd)
    _run(["git", "config", "user.name", "RFSN Planner"], wd)

    # Commit initial state (even if empty)
    _run(["git", "add", "-A"], wd)
    _run(["git", "commit", "-m", "checkpoint:init", "--allow-empty"], wd)


def checkpoint(workdir: str, label: str) -> str:
    """
    Create a checkpoint commit in the workdir.

    Returns the commit hash.
    """
    wd = Path(workdir).resolve()
    ensure_git_repo(str(wd))

    _run(["git", "add", "-A"], wd)
    _run(["git", "commit", "-m", f"checkpoint:{label}", "--allow-empty"], wd)

    # Get current HEAD
    head = _run(["git", "rev-parse", "HEAD"], wd)
    if head.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {head.stderr.strip()}")
    return head.stdout.strip()


def reset_hard(workdir: str, commit: str) -> None:
    """Reset workdir to a previous checkpoint commit."""
    wd = Path(workdir).resolve()
    ensure_git_repo(str(wd))

    r = _run(["git", "reset", "--hard", commit], wd)
    if r.returncode != 0:
        raise RuntimeError(f"git reset --hard failed: {r.stderr.strip()}")

    # Clean untracked files created during the step
    r2 = _run(["git", "clean", "-fd"], wd)
    if r2.returncode != 0:
        raise RuntimeError(f"git clean -fd failed: {r2.stderr.strip()}")


def get_current_commit(workdir: str) -> Optional[str]:
    """Get current HEAD commit hash, or None if not a git repo."""
    wd = Path(workdir).resolve()
    if not (wd / ".git").exists():
        return None
    head = _run(["git", "rev-parse", "HEAD"], wd)
    if head.returncode != 0:
        return None
    return head.stdout.strip()
