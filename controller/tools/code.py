# controller/tools/code.py
"""
Code intelligence tools - search, diff, symbols.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: Any
    error: str | None = None


def grep_files(
    pattern: str,
    directory: str,
    *,
    file_pattern: str = "*",
    max_results: int = 100,
    context_lines: int = 2,
) -> ToolResult:
    """
    Search for pattern in files using regex.

    Args:
        pattern: Regex pattern to search for
        directory: Directory to search in
        file_pattern: Glob pattern for files (e.g., "*.py")
        max_results: Maximum number of matches to return
        context_lines: Lines of context around each match

    Returns:
        ToolResult with list of matches
    """
    try:
        dir_path = Path(directory).resolve()
        if not dir_path.exists():
            return ToolResult(False, None, f"Directory not found: {directory}")
        if not dir_path.is_dir():
            return ToolResult(False, None, f"Not a directory: {directory}")

        regex = re.compile(pattern, re.IGNORECASE)
        matches = []

        for file_path in dir_path.rglob(file_pattern):
            if not file_path.is_file():
                continue
            if file_path.name.startswith("."):
                continue
            if "__pycache__" in str(file_path) or ".git" in str(file_path):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()

                for i, line in enumerate(lines):
                    if regex.search(line):
                        # Get context
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        context = lines[start:end]

                        matches.append(
                            {
                                "file": str(file_path.relative_to(dir_path)),
                                "line": i + 1,
                                "match": line.strip(),
                                "context": context,
                            }
                        )

                        if len(matches) >= max_results:
                            return ToolResult(
                                True,
                                {
                                    "matches": matches,
                                    "truncated": True,
                                    "total_shown": len(matches),
                                },
                            )

            except (PermissionError, UnicodeDecodeError):
                continue

        return ToolResult(
            True,
            {
                "matches": matches,
                "truncated": False,
                "total_shown": len(matches),
            },
        )

    except re.error as e:
        return ToolResult(False, None, f"Invalid regex pattern: {e}")
    except Exception as e:
        return ToolResult(False, None, f"Search failed: {e}")


def apply_diff(
    file_path: str,
    diff: str,
    *,
    dry_run: bool = False,
) -> ToolResult:
    """
    Apply a unified diff to a file.

    Args:
        file_path: Path to file to patch
        diff: Unified diff content
        dry_run: If True, don't actually modify file

    Returns:
        ToolResult with patch result
    """
    try:
        path = Path(file_path).resolve()

        if not path.exists():
            return ToolResult(False, None, f"File not found: {file_path}")

        original = path.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)

        # Parse diff hunks
        hunk_pattern = re.compile(r"^@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)(?:,\d+)?\s*@@")
        hunks = []
        current_hunk = None

        for line in diff.splitlines(keepends=True):
            match = hunk_pattern.match(line)
            if match:
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {
                    "old_start": int(match.group(1)),
                    "new_start": int(match.group(2)),
                    "lines": [],
                }
            elif current_hunk is not None:
                current_hunk["lines"].append(line.rstrip("\n"))

        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            return ToolResult(False, None, "No valid diff hunks found")

        # Apply hunks (simplified - works for basic cases)
        result_lines = list(lines)
        offset = 0

        for hunk in hunks:
            old_start = hunk["old_start"] - 1 + offset
            removals = []
            additions = []

            for line in hunk["lines"]:
                if line.startswith("-") and not line.startswith("---"):
                    removals.append(line[1:])
                elif line.startswith("+") and not line.startswith("+++"):
                    additions.append(line[1:] + "\n")

            # Remove old lines
            for _ in removals:
                if old_start < len(result_lines):
                    result_lines.pop(old_start)
                    offset -= 1

            # Add new lines
            for i, add_line in enumerate(additions):
                result_lines.insert(old_start + i, add_line)
                offset += 1

        result = "".join(result_lines)

        if dry_run:
            return ToolResult(
                True,
                {
                    "mode": "dry_run",
                    "preview": result[:2000] + ("..." if len(result) > 2000 else ""),
                    "hunks_applied": len(hunks),
                },
            )

        path.write_text(result, encoding="utf-8")
        return ToolResult(
            True,
            {
                "mode": "applied",
                "file": str(path),
                "hunks_applied": len(hunks),
            },
        )

    except Exception as e:
        return ToolResult(False, None, f"Diff application failed: {e}")


def get_symbols(
    file_path: str,
    *,
    max_symbols: int = 100,
) -> ToolResult:
    """
    Extract function/class definitions from a Python file.

    Args:
        file_path: Path to Python file
        max_symbols: Maximum symbols to return

    Returns:
        ToolResult with list of symbols
    """
    try:
        path = Path(file_path).resolve()
        if not path.exists():
            return ToolResult(False, None, f"File not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()

        symbols = []
        class_pattern = re.compile(r"^class\s+(\w+)")
        func_pattern = re.compile(r"^(\s*)def\s+(\w+)\s*\(")

        current_class = None

        for i, line in enumerate(lines):
            # Check for class definition
            class_match = class_pattern.match(line)
            if class_match:
                current_class = class_match.group(1)
                symbols.append(
                    {
                        "type": "class",
                        "name": current_class,
                        "line": i + 1,
                    }
                )

            # Check for function definition
            func_match = func_pattern.match(line)
            if func_match:
                indent = len(func_match.group(1))
                name = func_match.group(2)

                if indent > 0 and current_class:
                    full_name = f"{current_class}.{name}"
                else:
                    full_name = name
                    current_class = None  # Reset class if top-level function

                symbols.append(
                    {
                        "type": "method" if indent > 0 else "function",
                        "name": full_name,
                        "line": i + 1,
                    }
                )

            if len(symbols) >= max_symbols:
                break

        return ToolResult(
            True,
            {
                "file": str(path),
                "symbols": symbols,
                "total": len(symbols),
            },
        )

    except Exception as e:
        return ToolResult(False, None, f"Symbol extraction failed: {e}")


# Tool registry
CODE_TOOLS = {
    "grep_files": grep_files,
    "apply_diff": apply_diff,
    "get_symbols": get_symbols,
}
