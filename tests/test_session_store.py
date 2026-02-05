# tests/test_session_store.py
"""Tests for session persistence storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from ui.session_store import SessionStore, get_session_store


class TestSessionStore:
    """Test SQLite session storage."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> SessionStore:
        """Create a temp store."""
        return SessionStore(tmp_path / "test_sessions.db")

    def test_create_session(self, store: SessionStore) -> None:
        """Create a new session."""
        session = store.create("test-001", working_directory="/tmp")
        assert session.session_id == "test-001"
        assert session.working_directory == "/tmp"
        assert session.chat_history == []

    def test_get_session(self, store: SessionStore) -> None:
        """Retrieve an existing session."""
        store.create("test-002")
        retrieved = store.get("test-002")
        assert retrieved is not None
        assert retrieved.session_id == "test-002"

    def test_get_nonexistent_session(self, store: SessionStore) -> None:
        """Return None for missing sessions."""
        result = store.get("nonexistent")
        assert result is None

    def test_update_session(self, store: SessionStore) -> None:
        """Update session fields."""
        store.create("test-003")
        success = store.update("test-003", working_directory="/new/path")
        assert success is True

        retrieved = store.get("test-003")
        assert retrieved is not None
        assert retrieved.working_directory == "/new/path"

    def test_append_message(self, store: SessionStore) -> None:
        """Append messages to chat history."""
        store.create("test-004")
        store.append_message("test-004", "user", "Hello")
        store.append_message("test-004", "assistant", "Hi there!")

        retrieved = store.get("test-004")
        assert retrieved is not None
        assert len(retrieved.chat_history) == 2
        assert retrieved.chat_history[0] == ("user", "Hello")
        assert retrieved.chat_history[1] == ("assistant", "Hi there!")

    def test_list_sessions(self, store: SessionStore) -> None:
        """List recent sessions."""
        store.create("session-a")
        store.create("session-b")
        store.create("session-c")

        sessions = store.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_delete_session(self, store: SessionStore) -> None:
        """Delete a session."""
        store.create("test-005")
        deleted = store.delete("test-005")
        assert deleted is True

        retrieved = store.get("test-005")
        assert retrieved is None

    def test_delete_nonexistent(self, store: SessionStore) -> None:
        """Delete returns False for missing sessions."""
        deleted = store.delete("nonexistent")
        assert deleted is False

    def test_metadata_storage(self, store: SessionStore) -> None:
        """Store and retrieve metadata."""
        store.create("test-006", metadata={"key": "value", "count": 42})
        retrieved = store.get("test-006")
        assert retrieved is not None
        assert retrieved.metadata == {"key": "value", "count": 42}

    def test_update_chat_history(self, store: SessionStore) -> None:
        """Directly update chat history."""
        store.create("test-007")
        history = [("user", "msg1"), ("assistant", "msg2")]
        store.update("test-007", chat_history=history)

        retrieved = store.get("test-007")
        assert retrieved is not None
        assert len(retrieved.chat_history) == 2


class TestSessionStoreGlobal:
    """Test global store singleton."""

    def test_get_session_store_returns_same_instance(self, tmp_path: Path) -> None:
        """Global store returns same instance."""
        # Reset global for test
        import ui.session_store

        ui.session_store._store = None

        db_path = tmp_path / "global.db"
        store1 = get_session_store(db_path)
        store2 = get_session_store(db_path)

        assert store1 is store2
