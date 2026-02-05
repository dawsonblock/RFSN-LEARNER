# ui/server.py
"""
RFSN Agent UI Backend - FastAPI Server

Exposes REST + WebSocket endpoints for the interactive UI.
All agent interactions go through the real run_agent_turn().

Run: python ui/server.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from controller.agent_loop import run_agent_turn
from controller.metrics import get_metrics
from controller.tool_router import (
    TOOL_REGISTRY,
    ExecutionContext,
    route_tool_call,
)
from controller.tools.memory import (
    memory_retrieve,
    memory_search,
)
from rfsn.ledger import AppendOnlyLedger
from rfsn.policy import DEV_POLICY
from rfsn.types import WorldSnapshot
from ui.session_store import get_session_store

# =============================================================================
# APP CONFIGURATION
# =============================================================================

app = FastAPI(
    title="RFSN Agent UI",
    description="Interactive UI for the RFSN deterministic agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# RATE LIMITING
# =============================================================================


class RateLimiter:
    """
    Simple in-memory rate limiter for API endpoints.

    Tracks requests per client IP with a sliding window.
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        """Check if client is allowed to make a request."""
        import time

        now = time.time()
        cutoff = now - self.window_seconds

        # Get or create request list
        if client_id not in self._requests:
            self._requests[client_id] = []

        # Filter to only recent requests
        recent = [t for t in self._requests[client_id] if t > cutoff]
        self._requests[client_id] = recent

        if len(recent) >= self.max_requests:
            return False

        self._requests[client_id].append(now)
        return True

    def remaining(self, client_id: str) -> int:
        """Get remaining requests for client."""
        import time

        now = time.time()
        cutoff = now - self.window_seconds
        recent = [t for t in self._requests.get(client_id, []) if t > cutoff]
        return max(0, self.max_requests - len(recent))

    def reset(self, client_id: str) -> None:
        """Reset rate limit for a client."""
        self._requests.pop(client_id, None)


# Rate limiters for different endpoint types
TOOL_LIMITER = RateLimiter(max_requests=30, window_seconds=60)  # 30 tool calls/min
CHAT_LIMITER = RateLimiter(max_requests=20, window_seconds=60)  # 20 messages/min
API_LIMITER = RateLimiter(max_requests=120, window_seconds=60)  # 120 general API calls/min

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================



@dataclass
class Session:
    """Active agent session."""

    session_id: str
    context: ExecutionContext
    ledger: AppendOnlyLedger
    chat_history: list[tuple[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


SESSIONS: dict[str, Session] = {}
WEBSOCKETS: dict[str, list[WebSocket]] = {}


def get_or_create_session(session_id: str | None = None) -> Session:
    """Get existing session or create/restore one."""
    # Check in-memory cache first
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]

    store = get_session_store()
    new_id = session_id or str(uuid.uuid4())[:8]

    # Try to restore from persistent storage
    stored = store.get(new_id)
    if stored:
        ledger_path = f"./tmp/sessions/{new_id}/ledger.jsonl"
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)

        session = Session(
            session_id=new_id,
            context=ExecutionContext(session_id=new_id),
            ledger=AppendOnlyLedger(ledger_path),
            chat_history=list(stored.chat_history),
            created_at=stored.created_at,
        )
        session.context.working_directory = stored.working_directory
        session.context.replay_mode = stored.replay_mode
        SESSIONS[new_id] = session
        return session

    # Create new session
    ledger_path = f"./tmp/sessions/{new_id}/ledger.jsonl"
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)

    session = Session(
        session_id=new_id,
        context=ExecutionContext(session_id=new_id),
        ledger=AppendOnlyLedger(ledger_path),
    )
    SESSIONS[new_id] = session

    # Persist to storage
    store.create(new_id, working_directory=session.context.working_directory)
    return session


def persist_session(session: Session) -> None:
    """Save session state to persistent storage."""
    store = get_session_store()
    store.update(
        session.session_id,
        chat_history=session.chat_history,
        working_directory=session.context.working_directory,
        replay_mode=getattr(session.context, "replay_mode", "none"),
    )


async def broadcast_event(session_id: str, event: dict[str, Any]) -> None:
    """Broadcast event to all WebSocket connections for a session."""
    if session_id in WEBSOCKETS:
        for ws in WEBSOCKETS[session_id]:
            try:
                await ws.send_json(event)
            except Exception:
                pass


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    steps_taken: int
    actions_allowed: int
    actions_denied: int


class PermissionRequest(BaseModel):
    tool: str


class ReplayModeRequest(BaseModel):
    mode: str  # "off" | "record" | "replay"


class ManualToolRequest(BaseModel):
    tool: str
    arguments: dict[str, Any]
    session_id: str | None = None


# =============================================================================
# CHAT ENDPOINT
# =============================================================================


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the agent and get a response.
    Uses the real run_agent_turn() function.
    """
    session = get_or_create_session(request.session_id)
    session.context.start_new_turn()

    # Broadcast event
    await broadcast_event(
        session.session_id,
        {
            "type": "user_message",
            "content": request.message,
            "ts": datetime.now(UTC).isoformat(),
        },
    )

    # Create world snapshot
    world = WorldSnapshot(
        cwd=session.context.working_directory,
        session_id=session.session_id,
        enabled_tools=list(TOOL_REGISTRY.keys()),
    )

    # Emit callback for real-time streaming
    def emit(event_type: str, payload: dict) -> None:
        """Emit events to WebSocket clients (fire-and-forget)."""
        try:
            asyncio.create_task(
                broadcast_event(
                    session.session_id,
                    {"type": event_type, **payload, "ts": datetime.now(UTC).isoformat()},
                )
            )
        except Exception:
            pass

    # Run agent turn
    try:
        result = run_agent_turn(
            user_text=request.message,
            chat_history=session.chat_history,
            world=world,
            policy=DEV_POLICY,
            ledger=session.ledger,
            exec_ctx=session.context,
            emit=emit,
        )

        # Update chat history
        session.chat_history.append(("user", request.message))
        session.chat_history.append(("assistant", result.message))
        persist_session(session)

        # Broadcast response
        await broadcast_event(
            session.session_id,
            {
                "type": "agent_message",
                "content": result.message,
                "steps_taken": result.steps_taken,
                "actions_allowed": result.actions_allowed,
                "actions_denied": result.actions_denied,
                "ts": datetime.now(UTC).isoformat(),
            },
        )

        return ChatResponse(
            reply=result.message,
            session_id=session.session_id,
            steps_taken=result.steps_taken,
            actions_allowed=result.actions_allowed,
            actions_denied=result.actions_denied,
        )
    except Exception as e:
        await broadcast_event(
            session.session_id,
            {
                "type": "error",
                "error": str(e),
                "ts": datetime.now(UTC).isoformat(),
            },
        )
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SESSIONS MANAGEMENT ENDPOINT
# =============================================================================


@app.get("/api/sessions")
async def list_sessions(limit: int = 50):
    """List all persisted sessions."""
    store = get_session_store()
    sessions = store.list_sessions(limit=limit)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Get session details including chat history."""
    store = get_session_store()
    stored = store.get(session_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": stored.session_id,
        "created_at": stored.created_at,
        "updated_at": stored.updated_at,
        "message_count": len(stored.chat_history),
        "chat_history": stored.chat_history,
        "working_directory": stored.working_directory,
        "replay_mode": stored.replay_mode,
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a persisted session."""
    store = get_session_store()
    if store.delete(session_id):
        # Also remove from in-memory cache
        SESSIONS.pop(session_id, None)
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Session not found")


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================


@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for live event streaming."""
    await websocket.accept()

    if session_id not in WEBSOCKETS:
        WEBSOCKETS[session_id] = []
    WEBSOCKETS[session_id].append(websocket)

    try:
        # Send initial state
        session = get_or_create_session(session_id)
        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "replay_mode": session.context.replay_mode,
                "ts": datetime.now(UTC).isoformat(),
            }
        )

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)

                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    finally:
        if session_id in WEBSOCKETS:
            WEBSOCKETS[session_id] = [ws for ws in WEBSOCKETS[session_id] if ws != websocket]


# =============================================================================
# LEDGER ENDPOINTS
# =============================================================================


@app.get("/api/ledger/{session_id}")
async def get_ledger(session_id: str, limit: int = Query(100, ge=1, le=1000)):
    """Get ledger entries for a session."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    entries = []
    if os.path.exists(session.ledger.path):
        with open(session.ledger.path, "r") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

    return {"entries": entries[-limit:], "total": len(entries)}


@app.get("/api/ledger/{session_id}/verify")
async def verify_ledger(session_id: str):
    """
    Verify ledger integrity:
      1) Chain linkage: prev_entry_hash matches previous entry_hash
      2) Entry integrity: entry_hash matches recomputed hash of entry core (minus entry_hash)
    """
    sess = get_or_create_session(session_id)
    p = Path(sess.ledger.path)
    if not p.exists():
        return {"ok": True, "entries": 0, "note": "ledger missing (empty)"}

    def canonical_json(obj) -> bytes:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def sha256_hex(b: bytes) -> str:
        import hashlib
        return hashlib.sha256(b).hexdigest()

    entries: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                return {"ok": False, "error": "invalid_json_line"}

    prev_hash: str | None = None

    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            return {"ok": False, "index": i, "error": "entry_not_object"}

        stored_entry_hash = e.get("entry_hash")
        if not isinstance(stored_entry_hash, str) or not stored_entry_hash:
            return {"ok": False, "index": i, "error": "missing_entry_hash"}

        # 1) Chain linkage
        if i == 0:
            prev_declared = e.get("prev_entry_hash", None)
            if prev_declared not in (None, "", "null"):
                return {
                    "ok": False,
                    "index": i,
                    "error": "genesis_prev_entry_hash_not_empty",
                    "prev_entry_hash": prev_declared,
                }
        else:
            prev_declared = e.get("prev_entry_hash")
            if prev_declared != prev_hash:
                return {
                    "ok": False,
                    "index": i,
                    "error": "chain_mismatch",
                    "expected_prev_entry_hash": prev_hash,
                    "got_prev_entry_hash": prev_declared,
                }

        # 2) Entry integrity: recompute over the entry without entry_hash
        core = dict(e)
        core.pop("entry_hash", None)
        recomputed = sha256_hex(canonical_json(core))
        if recomputed != stored_entry_hash:
            return {
                "ok": False,
                "index": i,
                "error": "entry_hash_mismatch",
                "expected_entry_hash": recomputed,
                "got_entry_hash": stored_entry_hash,
            }

        prev_hash = stored_entry_hash

    return {"ok": True, "entries": len(entries)}


# =============================================================================
# TOOLS ENDPOINTS
# =============================================================================


@app.get("/api/tools")
async def get_tools():
    """Get list of all registered tools (JSON-safe)."""
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        # Serialize schema fields to plain dicts
        schema_list = []
        try:
            for f in spec.schema:
                schema_list.append(
                    {
                        "name": getattr(f, "name", ""),
                        "required": bool(getattr(f, "required", True)),
                        "kind": getattr(f, "kind", "any"),
                    }
                )
        except Exception:
            pass

        tools.append(
            {
                "name": name,
                "risk": str(spec.risk.value),
                "description": (spec.handler.__doc__ or "").strip().split("\n")[0],
                "require_grant": bool(spec.permission.require_explicit_grant),
                "deny_in_replay": bool(spec.permission.deny_in_replay),
                "budget": {
                    "calls_per_turn": int(getattr(spec.budget, "calls_per_turn", 0)),
                    "max_bytes": getattr(spec.budget, "max_bytes", None),
                    "max_results": getattr(spec.budget, "max_results", None),
                },
                "schema": schema_list,
            }
        )
    return {"tools": tools}


@app.post("/api/tools/run")
async def run_tool_manually(request: ManualToolRequest):
    """Run a tool manually (for testing)."""
    # Rate limit check
    client_id = request.session_id or "anonymous"
    if not TOOL_LIMITER.is_allowed(client_id):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "remaining": 0,
                "retry_after_seconds": 60,
            },
        )

    session = get_or_create_session(request.session_id)

    result = route_tool_call(
        tool_name=request.tool,
        arguments=request.arguments,
        context=session.context,
    )

    await broadcast_event(
        session.session_id,
        {
            "type": "manual_tool_call",
            "tool": request.tool,
            "success": result.success,
            "ts": datetime.now(UTC).isoformat(),
        },
    )

    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "rate_limit_remaining": TOOL_LIMITER.remaining(client_id),
    }


# =============================================================================
# PERMISSIONS ENDPOINTS
# =============================================================================


@app.get("/api/perms")
async def get_perms(session_id: str = Query(None)):
    if not session_id or session_id not in SESSIONS:
        return {"granted_tools": [], "python_execution_enabled": False}
    sess = SESSIONS[session_id]
    return {
        "granted_tools": sorted(list(sess.context.permissions.granted_tools)),
        "python_execution_enabled": bool(getattr(sess.context.permissions, "python_execution_enabled", False)),
    }


@app.post("/api/perms/grant")
async def grant_permission(request: PermissionRequest, session_id: str = Query(None)):
    """Grant permission for a tool."""
    session = get_or_create_session(session_id)
    session.context.permissions.grant_tool(request.tool)

    await broadcast_event(
        session.session_id,
        {
            "type": "permission_granted",
            "tool": request.tool,
            "ts": datetime.now(UTC).isoformat(),
        },
    )

    return {"granted": True, "tool": request.tool}


@app.post("/api/perms/revoke")
async def revoke_permission(request: PermissionRequest, session_id: str = Query(None)):
    """Revoke permission for a tool."""
    session = get_or_create_session(session_id)
    session.context.permissions.revoke_tool(request.tool)

    await broadcast_event(
        session.session_id,
        {
            "type": "permission_revoked",
            "tool": request.tool,
            "ts": datetime.now(UTC).isoformat(),
        },
    )

    return {"revoked": True, "tool": request.tool}


class PythonToggleRequest(BaseModel):
    session_id: str
    enabled: bool


@app.post("/api/perms/python")
async def set_python(req: PythonToggleRequest):
    sess = get_or_create_session(req.session_id)
    if req.enabled:
        sess.context.permissions.enable_python()
    else:
        sess.context.permissions.disable_python()
    await broadcast_event(sess.session_id, {"type": "python_toggle", "enabled": bool(req.enabled)})
    return {"ok": True, "python_execution_enabled": bool(getattr(sess.context.permissions, "python_execution_enabled", False))}


# =============================================================================
# MEMORY ENDPOINTS
# =============================================================================


@app.get("/api/memory/search")
async def search_memory(q: str = Query(""), session_id: str = Query(None)):
    """Search memory database."""
    session = get_or_create_session(session_id)
    db_path = session.context.memory_db_path

    try:
        result = memory_search(query=q, max_results=50, db_path=db_path)
        return {"results": result.output if result.success else [], "query": q}
    except Exception as e:
        return {"results": [], "query": q, "error": str(e)}


@app.get("/api/memory/key/{key}")
async def get_memory_key(key: str, session_id: str = Query(None)):
    """Get specific memory key."""
    session = get_or_create_session(session_id)
    db_path = session.context.memory_db_path

    try:
        result = memory_retrieve(key=key, db_path=db_path)
        return {"key": key, "value": result.output if result.success else None}
    except Exception as e:
        return {"key": key, "value": None, "error": str(e)}


@app.get("/api/memory/keys")
async def list_memory_keys(session_id: str = Query(None)):
    """List all memory keys."""
    # Note: memory_list_keys not available in current API
    return {"keys": [], "message": "Memory key listing not implemented"}


# =============================================================================
# FILESYSTEM ENDPOINTS
# =============================================================================


@app.get("/api/fs/list")
async def list_directory(path: str = Query("."), session_id: str = Query(None)):
    """List directory contents (safe, scoped to working directory)."""
    session = get_or_create_session(session_id)
    workdir = session.context.working_directory

    # Resolve and validate path
    target = Path(workdir) / path
    try:
        target = target.resolve()
        workdir_resolved = Path(workdir).resolve()

        if not str(target).startswith(str(workdir_resolved)):
            raise HTTPException(status_code=403, detail="Path outside working directory")

        if not target.exists():
            raise HTTPException(status_code=404, detail="Path not found")

        if not target.is_dir():
            raise HTTPException(status_code=400, detail="Not a directory")

        items = []
        for item in target.iterdir():
            items.append(
                {
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )

        return {
            "path": str(target.relative_to(workdir_resolved)),
            "items": sorted(items, key=lambda x: (not x["is_dir"], x["name"])),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fs/read")
async def read_file(path: str, session_id: str = Query(None)):
    """Read file contents (safe, scoped)."""
    session = get_or_create_session(session_id)
    workdir = session.context.working_directory

    target = Path(workdir) / path
    try:
        target = target.resolve()
        workdir_resolved = Path(workdir).resolve()

        if not str(target).startswith(str(workdir_resolved)):
            raise HTTPException(status_code=403, detail="Path outside working directory")

        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not target.is_file():
            raise HTTPException(status_code=400, detail="Not a file")

        # Limit file size
        if target.stat().st_size > 1_000_000:
            raise HTTPException(status_code=400, detail="File too large (>1MB)")

        content = target.read_text(errors="replace")
        return {"path": str(target.relative_to(workdir_resolved)), "content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# REPLAY ENDPOINTS
# =============================================================================


@app.get("/api/replay/mode")
async def get_replay_mode(session_id: str = Query(None)):
    """Get current replay mode."""
    if session_id and session_id in SESSIONS:
        return {"mode": SESSIONS[session_id].context.replay_mode}
    return {"mode": "off"}


@app.post("/api/replay/mode")
async def set_replay_mode(request: ReplayModeRequest, session_id: str = Query(None)):
    """Set replay mode."""
    if request.mode not in ("off", "record", "replay"):
        raise HTTPException(status_code=400, detail="Invalid mode")

    session = get_or_create_session(session_id)
    session.context.replay_mode = request.mode

    await broadcast_event(
        session.session_id,
        {
            "type": "replay_mode_changed",
            "mode": request.mode,
            "ts": datetime.now(UTC).isoformat(),
        },
    )

    return {"mode": request.mode, "session_id": session.session_id}


class ReplayImportRequest(BaseModel):
    """Request to import replay data."""

    data: list[dict]  # List of replay records
    session_id: str | None = None


@app.get("/api/replay/export")
async def export_replay(session_id: str = Query(None)):
    """
    Export replay data as downloadable JSONL file.

    Returns a streaming response with the replay log for the session.
    """
    session = get_or_create_session(session_id)

    # Find the replay file path
    replay_path = Path(f"replay_{session.session_id}.jsonl")

    if not replay_path.exists():
        # Return empty JSONL if no replay data
        return StreamingResponse(
            io.BytesIO(b""),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="replay_{session.session_id}.jsonl"'
            },
        )

    # Stream the file content
    def iter_file():
        with open(replay_path, "rb") as f:
            yield from f

    return StreamingResponse(
        iter_file(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="replay_{session.session_id}.jsonl"'
        },
    )


@app.get("/api/replay/data")
async def get_replay_data(session_id: str = Query(None)):
    """
    Get replay data as JSON array.

    Returns parsed replay records for UI display.
    """
    session = get_or_create_session(session_id)
    replay_path = Path(f"replay_{session.session_id}.jsonl")

    records = []
    if replay_path.exists():
        with open(replay_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    return {
        "session_id": session.session_id,
        "record_count": len(records),
        "records": records,
    }


@app.post("/api/replay/import")
async def import_replay(request: ReplayImportRequest):
    """
    Import replay data from JSON array.

    Appends records to the session's replay file.
    """
    session = get_or_create_session(request.session_id)
    replay_path = Path(f"replay_{session.session_id}.jsonl")

    imported_count = 0
    with open(replay_path, "a", encoding="utf-8") as f:
        for record in request.data:
            # Validate required fields
            if "action_id" not in record or "tool" not in record:
                continue
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            imported_count += 1

    return {
        "session_id": session.session_id,
        "imported_count": imported_count,
        "message": f"Imported {imported_count} replay records",
    }


@app.delete("/api/replay/clear")
async def clear_replay(session_id: str = Query(None)):
    """
    Clear replay data for a session.

    Deletes the replay file.
    """
    session = get_or_create_session(session_id)
    replay_path = Path(f"replay_{session.session_id}.jsonl")

    deleted = False
    if replay_path.exists():
        replay_path.unlink()
        deleted = True

    return {
        "session_id": session.session_id,
        "deleted": deleted,
        "message": "Replay data cleared" if deleted else "No replay data to clear",
    }


# =============================================================================
# BUDGET ENDPOINTS
# =============================================================================


@app.get("/api/budgets")
async def get_budgets(session_id: str = Query(None)):
    """Get current budget state."""
    if session_id and session_id in SESSIONS:
        session = SESSIONS[session_id]
        budgets = session.context.budgets
        return {
            "tool_calls": dict(budgets.tool_calls),
            "bytes_used": dict(budgets.bytes_used),
            "turn_number": budgets.turn_number,
        }
    return {"tool_calls": {}, "bytes_used": {}, "turn_number": 0}


# =============================================================================
# WORLD STATE ENDPOINTS
# =============================================================================


@app.get("/api/world")
async def get_world_state(session_id: str = Query(None)):
    """Get current world state."""
    if session_id and session_id in SESSIONS:
        session = SESSIONS[session_id]
        return {
            "session_id": session_id,
            "cwd": session.context.working_directory,
            "memory_db_path": session.context.memory_db_path,
            "replay_mode": session.context.replay_mode,
            "enabled_tools": list(TOOL_REGISTRY.keys()),
            "granted_permissions": list(session.context.permissions.granted_tools),
            "created_at": session.created_at,
        }
    return {"session_id": None, "message": "No active session"}


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "sessions": len(SESSIONS),
    }



# =============================================================================
# METRICS ENDPOINT
# =============================================================================


@app.get("/api/metrics", response_class=PlainTextResponse)
async def metrics_prometheus():
    """Prometheus-compatible metrics endpoint."""
    registry = get_metrics()
    # Update active sessions gauge
    registry.active_sessions.set(len(SESSIONS))
    return registry.to_prometheus()


@app.get("/api/metrics/json")
async def metrics_json():
    """JSON metrics endpoint."""
    registry = get_metrics()
    registry.active_sessions.set(len(SESSIONS))
    return registry.to_dict()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("🚀 Starting RFSN Agent UI Server...")
    print("   http://localhost:8080")
    print("   API docs: http://localhost:8080/docs")
    uvicorn.run(app, host="0.0.0.0", port=8080)
