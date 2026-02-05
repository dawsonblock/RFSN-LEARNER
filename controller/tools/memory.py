"""
Memory tools - store, retrieve, search in agent memory.

Uses SQLite for persistence.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: Any
    error: str | None = None


class MemoryStore:
    """Simple key-value memory store with search."""

    def __init__(self, db_path: str = "agent_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    tags TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory(tags)
            """)

    def store(self, key: str, value: str, tags: list[str] | None = None) -> ToolResult:
        """Store a value with optional tags."""
        try:
            now = time.time()
            tags_str = json.dumps(tags or [])

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO memory (key, value, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        tags = excluded.tags,
                        updated_at = excluded.updated_at
                """,
                    (key, value, tags_str, now, now),
                )

            return ToolResult(True, f"Stored '{key}'")
        except Exception as e:
            return ToolResult(False, None, str(e))

    def retrieve(self, key: str) -> ToolResult:
        """Retrieve a value by key."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT value, tags FROM memory WHERE key = ?", (key,)
                ).fetchone()

            if row is None:
                return ToolResult(False, None, f"Key not found: {key}")

            return ToolResult(
                True,
                {
                    "key": key,
                    "value": row[0],
                    "tags": json.loads(row[1]) if row[1] else [],
                },
            )
        except Exception as e:
            return ToolResult(False, None, str(e))

    def search(self, query: str, *, max_results: int = 10) -> ToolResult:
        """Search memory by key or value substring."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT key, value, tags FROM memory
                    WHERE key LIKE ? OR value LIKE ?
                    LIMIT ?
                """,
                    (f"%{query}%", f"%{query}%", max_results),
                ).fetchall()

            results = [
                {
                    "key": row[0],
                    "value": row[1][:200] + "..." if len(row[1]) > 200 else row[1],
                    "tags": json.loads(row[2]) if row[2] else [],
                }
                for row in rows
            ]

            return ToolResult(True, results)
        except Exception as e:
            return ToolResult(False, None, str(e))

    def delete(self, key: str) -> ToolResult:
        """Delete a memory entry."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM memory WHERE key = ?", (key,))
                if cursor.rowcount == 0:
                    return ToolResult(False, None, f"Key not found: {key}")

            return ToolResult(True, f"Deleted '{key}'")
        except Exception as e:
            return ToolResult(False, None, str(e))


# Default instance
_default_store: MemoryStore | None = None


def get_store(db_path: str = "agent_memory.db") -> MemoryStore:
    global _default_store
    if _default_store is None or _default_store.db_path != db_path:
        _default_store = MemoryStore(db_path)
    return _default_store


def memory_store(
    key: str, value: str, tags: list[str] | None = None, db_path: str = "agent_memory.db"
) -> ToolResult:
    """Store a value in memory."""
    return get_store(db_path).store(key, value, tags)


def memory_retrieve(key: str, db_path: str = "agent_memory.db") -> ToolResult:
    """Retrieve a value from memory."""
    return get_store(db_path).retrieve(key)


def memory_search(
    query: str, max_results: int = 10, db_path: str = "agent_memory.db"
) -> ToolResult:
    """Search memory."""
    return get_store(db_path).search(query, max_results=max_results)


def memory_delete(key: str, db_path: str = "agent_memory.db") -> ToolResult:
    """Delete from memory."""
    return get_store(db_path).delete(key)


# Tool registry
MEMORY_TOOLS = {
    "memory_store": memory_store,
    "memory_retrieve": memory_retrieve,
    "memory_search": memory_search,
    "memory_delete": memory_delete,
}
