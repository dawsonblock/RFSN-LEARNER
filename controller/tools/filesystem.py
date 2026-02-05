"""
Filesystem tools - read, write, list, search.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: Any
    error: str | None = None


def read_file(path: str, *, max_bytes: int = 100_000) -> ToolResult:
    """Read contents of a file."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return ToolResult(False, None, f"File not found: {path}")
        if not p.is_file():
            return ToolResult(False, None, f"Not a file: {path}")

        size = p.stat().st_size
        if size > max_bytes:
            return ToolResult(False, None, f"File too large: {size} > {max_bytes}")

        content = p.read_text(encoding="utf-8", errors="replace")
        return ToolResult(True, content)
    except Exception as e:
        return ToolResult(False, None, str(e))


def write_file(path: str, content: str, *, max_bytes: int = 100_000) -> ToolResult:
    """Write content to a file."""
    try:
        if len(content.encode("utf-8")) > max_bytes:
            return ToolResult(False, None, f"Content too large: > {max_bytes} bytes")

        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolResult(True, f"Wrote {len(content)} chars to {path}")
    except Exception as e:
        return ToolResult(False, None, str(e))


def list_dir(path: str, *, max_items: int = 1000) -> ToolResult:
    """List contents of a directory."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return ToolResult(False, None, f"Directory not found: {path}")
        if not p.is_dir():
            return ToolResult(False, None, f"Not a directory: {path}")

        items = []
        for i, entry in enumerate(sorted(p.iterdir())):
            if i >= max_items:
                items.append(f"... truncated at {max_items} items")
                break
            suffix = "/" if entry.is_dir() else ""
            items.append(entry.name + suffix)

        return ToolResult(True, items)
    except Exception as e:
        return ToolResult(False, None, str(e))


def search_files(
    directory: str,
    pattern: str,
    *,
    max_results: int = 100,
) -> ToolResult:
    """Search for files matching a pattern."""
    try:
        p = Path(directory).resolve()
        if not p.exists():
            return ToolResult(False, None, f"Directory not found: {directory}")

        matches = []
        for match in p.rglob(pattern):
            if len(matches) >= max_results:
                break
            matches.append(str(match.relative_to(p)))

        return ToolResult(True, matches)
    except Exception as e:
        return ToolResult(False, None, str(e))


# Tool registry
FILESYSTEM_TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "search_files": search_files,
}
