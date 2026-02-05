"""
Safe unified diff application.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchResult:
    success: bool
    message: str
    files_modified: list[str]


def apply_patch(
    worktree: Path,
    patch_content: str,
    *,
    dry_run: bool = False,
    strip_level: int = 1,
) -> PatchResult:
    """
    Apply a unified diff to a worktree.

    Uses the system `patch` command for reliability.
    Supports dry-run mode for validation.
    """
    worktree = Path(worktree).resolve()

    if not patch_content.strip():
        return PatchResult(False, "Empty patch content", [])

    # Write patch to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(patch_content)
        patch_file = f.name

    try:
        cmd = [
            "patch",
            f"-p{strip_level}",
            "-d",
            str(worktree),
            "-i",
            patch_file,
        ]

        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Parse modified files from output
        files_modified = []
        for line in result.stdout.splitlines():
            if line.startswith("patching file "):
                fname = line.replace("patching file ", "").strip().strip("'\"")
                files_modified.append(fname)

        if result.returncode == 0:
            action = "validated" if dry_run else "applied"
            return PatchResult(
                True,
                f"Patch {action} successfully",
                files_modified,
            )
        else:
            return PatchResult(
                False,
                f"Patch failed: {result.stderr or result.stdout}",
                [],
            )

    except subprocess.TimeoutExpired:
        return PatchResult(False, "Patch command timed out", [])

    finally:
        Path(patch_file).unlink(missing_ok=True)


def reverse_patch(
    worktree: Path,
    patch_content: str,
    *,
    strip_level: int = 1,
) -> PatchResult:
    """Reverse a previously applied patch."""
    worktree = Path(worktree).resolve()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(patch_content)
        patch_file = f.name

    try:
        result = subprocess.run(
            [
                "patch",
                "-R",
                f"-p{strip_level}",
                "-d",
                str(worktree),
                "-i",
                patch_file,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return PatchResult(True, "Patch reversed successfully", [])
        else:
            return PatchResult(False, f"Reverse failed: {result.stderr}", [])

    finally:
        Path(patch_file).unlink(missing_ok=True)
