# ui/session_store.py
"""
Persistent session storage using SQLite.

Stores session state including chat history, context, and metadata.
Survives server restarts.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class StoredSession:
    """Session data retrieved from storage."""

    session_id: str
    chat_history: list[tuple[str, str]]
    working_directory: str
    replay_mode: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class SessionStore:
    """SQLite-backed session persistence."""

    def __init__(self, db_path: str | Path = "sessions.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    chat_history TEXT NOT NULL DEFAULT '[]',
                    working_directory TEXT NOT NULL DEFAULT '.',
                    replay_mode TEXT NOT NULL DEFAULT 'none',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                ON sessions(updated_at DESC)
            """)

    @contextmanager
    def _conn(self):
        """Context manager for database connection."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get(self, session_id: str) -> StoredSession | None:
        """Retrieve a session by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if not row:
                return None

            # Convert JSON lists back to tuples for chat_history
            raw_history = json.loads(row["chat_history"])
            chat_history = [tuple(msg) for msg in raw_history]

            return StoredSession(
                session_id=row["session_id"],
                chat_history=chat_history,
                working_directory=row["working_directory"],
                replay_mode=row["replay_mode"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=json.loads(row["metadata"]),
            )

    def create(
        self,
        session_id: str,
        *,
        working_directory: str = ".",
        replay_mode: str = "none",
        metadata: dict[str, Any] | None = None,
    ) -> StoredSession:
        """Create a new session."""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                (session_id, working_directory, replay_mode, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    working_directory,
                    replay_mode,
                    now,
                    now,
                    json.dumps(metadata or {}),
                ),
            )

        return StoredSession(
            session_id=session_id,
            chat_history=[],
            working_directory=working_directory,
            replay_mode=replay_mode,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def update(
        self,
        session_id: str,
        *,
        chat_history: list[tuple[str, str]] | None = None,
        working_directory: str | None = None,
        replay_mode: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update session fields. Returns True if session existed."""
        updates = []
        params = []

        if chat_history is not None:
            updates.append("chat_history = ?")
            params.append(json.dumps(chat_history))

        if working_directory is not None:
            updates.append("working_directory = ?")
            params.append(working_directory)

        if replay_mode is not None:
            updates.append("replay_mode = ?")
            params.append(replay_mode)

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(session_id)

        with self._conn() as conn:
            result = conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                params,
            )
            return result.rowcount > 0

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> bool:
        """Append a message to chat history. Returns True if successful."""
        session = self.get(session_id)
        if not session:
            return False

        history = session.chat_history + [(role, content)]
        return self.update(session_id, chat_history=history)

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recent sessions."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT session_id, created_at, updated_at,
                       json_array_length(chat_history) as message_count
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        with self._conn() as conn:
            result = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            return result.rowcount > 0


# Global instance
_store: SessionStore | None = None


def get_session_store(db_path: str | Path = "sessions.db") -> SessionStore:
    """Get or create global session store."""
    global _store
    if _store is None:
        _store = SessionStore(db_path)
    return _store
