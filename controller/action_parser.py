"""
Parse LLM output into ProposedAction.

Handles JSON format and simple text parsing.
"""

from __future__ import annotations

import json
import re
from typing import Any

from rfsn.types import ProposedAction


def parse_json_action(response: str) -> ProposedAction | None:
    """
    Parse JSON-formatted action from LLM response.

    Expected format:
    {
        "action": "tool_call",
        "tool": "read_file",
        "arguments": {"path": "/some/file"},
        "justification": "Need to read config"
    }
    """
    # Try to extract JSON from response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return None

    # Determine action kind
    action = data.get("action", "tool_call")

    # Map to our ActionKind
    kind_map = {
        "tool_call": "tool_call",
        "tool": "tool_call",
        "message": "message_send",
        "message_send": "message_send",
        "memory": "memory_write",
        "memory_write": "memory_write",
        "permission": "permission_request",
        "permission_request": "permission_request",
    }

    kind = kind_map.get(action, "tool_call")

    # Build payload
    if kind == "tool_call":
        payload = {
            "tool": data.get("tool", data.get("name", "")),
            "arguments": data.get("arguments", data.get("args", {})),
        }
    elif kind == "message_send":
        payload = {
            "message": data.get("message", data.get("content", "")),
        }
    elif kind == "memory_write":
        payload = {
            "key": data.get("key", ""),
            "value": data.get("value", ""),
            "tags": data.get("tags", []),
        }
    else:
        payload = data

    justification = data.get("justification", data.get("reason", "No justification provided"))
    risk_tags = tuple(data.get("risk_tags", []))

    return ProposedAction(
        kind=kind,
        payload=payload,
        justification=justification,
        risk_tags=risk_tags,
    )


def parse_simple_command(response: str) -> ProposedAction | None:
    """
    Parse simple text commands like:
    - /read_file /path/to/file
    - /memory_store key:value
    - /search query text
    """
    response = response.strip()
    if not response.startswith("/"):
        return None

    parts = response[1:].split(maxsplit=1)
    if not parts:
        return None

    tool_name = parts[0]
    args_str = parts[1] if len(parts) > 1 else ""

    # Simple argument parsing
    arguments: dict[str, Any] = {}

    if tool_name == "read_file":
        arguments["path"] = args_str.strip()
    elif tool_name == "list_dir":
        arguments["path"] = args_str.strip() or "./"
    elif tool_name == "memory_store":
        if ":" in args_str:
            key, value = args_str.split(":", 1)
            arguments["key"] = key.strip()
            arguments["value"] = value.strip()
    elif tool_name == "memory_retrieve":
        arguments["key"] = args_str.strip()
    elif tool_name == "memory_search":
        arguments["query"] = args_str.strip()
    elif tool_name == "search_files":
        parts = args_str.split(maxsplit=1)
        arguments["directory"] = parts[0] if parts else "./"
        arguments["pattern"] = parts[1] if len(parts) > 1 else "*"
    elif tool_name == "fetch_url":
        arguments["url"] = args_str.strip()
    else:
        # Generic: assume single positional arg
        if args_str:
            arguments["input"] = args_str

    return ProposedAction(
        kind="tool_call",
        payload={"tool": tool_name, "arguments": arguments},
        justification=f"User command: /{tool_name}",
        risk_tags=(),
    )


def parse_message_response(response: str) -> ProposedAction:
    """
    Parse a plain text response as a message_send action.
    Fallback when no structured action is detected.
    """
    return ProposedAction(
        kind="message_send",
        payload={"message": response},
        justification="LLM response to user",
        risk_tags=(),
    )


def parse_llm_response(response: str) -> ProposedAction:
    """
    Parse LLM response into a ProposedAction.

    Tries JSON first, then simple commands, then falls back to message.
    """
    # Try JSON format
    action = parse_json_action(response)
    if action:
        return action

    # Try simple command format
    action = parse_simple_command(response)
    if action:
        return action

    # Fallback to message
    return parse_message_response(response)
