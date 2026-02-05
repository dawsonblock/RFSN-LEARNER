# controller/tool_schema.py
"""
Tool argument schemas for validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Field:
    """Schema field definition."""

    name: str
    required: bool = True
    check: Callable[[Any], bool] = lambda _: True


def is_str(x: Any) -> bool:
    return isinstance(x, str)


def is_int(x: Any) -> bool:
    return isinstance(x, int)


def is_bool(x: Any) -> bool:
    return isinstance(x, bool)


def is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def is_list(x: Any) -> bool:
    return isinstance(x, list)


# Tool schemas matching controller/tools/*.py registries
TOOL_SCHEMAS: dict[str, list[Field]] = {
    # Filesystem tools (controller/tools/filesystem.py)
    "read_file": [
        Field("path", required=True, check=is_str),
        Field("max_bytes", required=False, check=is_int),
    ],
    "write_file": [
        Field("path", required=True, check=is_str),
        Field("content", required=True, check=is_str),
        Field("max_bytes", required=False, check=is_int),
    ],
    "list_dir": [
        Field("path", required=True, check=is_str),
        Field("max_items", required=False, check=is_int),
    ],
    "search_files": [
        Field("directory", required=True, check=is_str),
        Field("pattern", required=True, check=is_str),
        Field("max_results", required=False, check=is_int),
    ],
    # Memory tools (controller/tools/memory.py)
    "memory_store": [
        Field("key", required=True, check=is_str),
        Field("value", required=True, check=is_str),
        Field("tags", required=False, check=is_list),
    ],
    "memory_retrieve": [
        Field("key", required=True, check=is_str),
    ],
    "memory_search": [
        Field("query", required=True, check=is_str),
        Field("max_results", required=False, check=is_int),
    ],
    "memory_delete": [
        Field("key", required=True, check=is_str),
    ],
    # Browser tools (controller/tools/browser.py)
    "fetch_url": [
        Field("url", required=True, check=is_str),
        Field("max_bytes", required=False, check=is_int),
        Field("timeout", required=False, check=is_int),
    ],
    "search_web": [
        Field("query", required=True, check=is_str),
        Field("max_results", required=False, check=is_int),
    ],
}


def allow_unknown_tools() -> bool:
    """
    If True, unknown tools pass schema validation.
    Default: False (tight enforcement).
    """
    return False
