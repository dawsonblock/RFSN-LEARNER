# ui/server.py
"""
RFSN Agent UI Backend - FastAPI Server

Exposes REST + WebSocket endpoints for the interactive UI.
All agent interactions go through the real run_agent_turn().

Run: python ui/server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from controller.agent_loop import run_agent_turn
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
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


SESSIONS: dict[str, Session] = {}
WEBSOCKETS: dict[str, list[WebSocket]] = {}


def get_or_create_session(session_id: str | None = None) -> Session:
    """Get existing session or create new one."""
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]

    new_id = session_id or str(uuid.uuid4())[:8]
    ledger_path = f"./tmp/sessions/{new_id}/ledger.jsonl"
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)

    session = Session(
        session_id=new_id,
        context=ExecutionContext(session_id=new_id),
        ledger=AppendOnlyLedger(ledger_path),
    )
    SESSIONS[new_id] = session
    return session


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
            "ts": datetime.utcnow().isoformat(),
        },
    )

    # Create world snapshot
    world = WorldSnapshot(
        cwd=session.context.working_directory,
        session_id=session.session_id,
        enabled_tools=list(TOOL_REGISTRY.keys()),
    )

    # Run agent turn
    try:
        result = run_agent_turn(
            user_text=request.message,
            chat_history=session.chat_history,
            world=world,
            policy=DEV_POLICY,
            ledger=session.ledger,
            exec_ctx=session.context,
        )

        # Update chat history
        session.chat_history.append(("user", request.message))
        session.chat_history.append(("assistant", result.message))

        # Broadcast response
        await broadcast_event(
            session.session_id,
            {
                "type": "agent_message",
                "content": result.message,
                "steps_taken": result.steps_taken,
                "actions_allowed": result.actions_allowed,
                "actions_denied": result.actions_denied,
                "ts": datetime.utcnow().isoformat(),
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
                "ts": datetime.utcnow().isoformat(),
            },
        )
        raise HTTPException(status_code=500, detail=str(e))


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
                "ts": datetime.utcnow().isoformat(),
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
    """Verify ledger hash chain integrity."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not os.path.exists(session.ledger.path):
        return {"valid": True, "entries": 0, "message": "Empty ledger"}

    entries = []
    with open(session.ledger.path, "r") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    if not entries:
        return {"valid": True, "entries": 0}

    # Verify chain
    prev_hash = "0" * 64
    for i, entry in enumerate(entries):
        if entry.get("prev_entry_hash") != prev_hash:
            return {
                "valid": False,
                "entries": len(entries),
                "broken_at": i,
                "message": f"Chain broken at entry {i}",
            }
        prev_hash = entry.get("entry_hash", "")

    return {"valid": True, "entries": len(entries)}


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
            "ts": datetime.utcnow().isoformat(),
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
async def get_permissions(session_id: str = Query(None)):
    """Get current permission state."""
    if session_id and session_id in SESSIONS:
        session = SESSIONS[session_id]
        return {
            "granted_tools": list(session.context.permissions.granted_tools),
            "session_id": session_id,
        }
    return {"granted_tools": [], "session_id": None}


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
            "ts": datetime.utcnow().isoformat(),
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
            "ts": datetime.utcnow().isoformat(),
        },
    )

    return {"revoked": True, "tool": request.tool}


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
            "ts": datetime.utcnow().isoformat(),
        },
    )

    return {"mode": request.mode, "session_id": session.session_id}


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


@app.get("/api/sessions")
async def list_sessions():
    """List all active sessions."""
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "created_at": s.created_at,
                "messages": len(s.chat_history),
            }
            for s in SESSIONS.values()
        ]
    }


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
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("🚀 Starting RFSN Agent UI Server...")
    print("   http://localhost:8080")
    print("   API docs: http://localhost:8080/docs")
    uvicorn.run(app, host="0.0.0.0", port=8080)
