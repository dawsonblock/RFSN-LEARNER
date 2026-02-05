# controller/action_io.py
"""
Strict JSON parsing and normalization into ProposedAction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from rfsn.types import ProposedAction


@dataclass(frozen=True)
class ParsedProposal:
    """Parsed proposal from LLM output."""
    actions: list[ProposedAction]


class ProposalError(Exception):
    """Raised when LLM output cannot be parsed into actions."""
    pass


def parse_llm_json(text: str) -> ParsedProposal:
    """
    Parse LLM JSON output into a structured proposal.
    
    Args:
        text: Raw LLM output (should be valid JSON)
    
    Returns:
        ParsedProposal with list of ProposedAction
    
    Raises:
        ProposalError: If JSON is invalid or doesn't match schema
    """
    # Handle markdown code blocks if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    
    try:
        obj = json.loads(text)
    except Exception as e:
        raise ProposalError(f"LLM output was not valid JSON: {e}") from e

    if not isinstance(obj, dict):
        raise ProposalError("LLM JSON must be an object")

    actions = obj.get("actions")
    if not isinstance(actions, list):
        raise ProposalError("LLM JSON must have an 'actions' list")

    parsed: list[ProposedAction] = []
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            raise ProposalError(f"actions[{i}] must be an object")

        kind = a.get("kind")
        payload = a.get("payload", {})

        if not isinstance(kind, str) or not kind:
            raise ProposalError(f"actions[{i}].kind must be a non-empty string")

        if not isinstance(payload, dict):
            raise ProposalError(f"actions[{i}].payload must be an object")

        parsed.append(ProposedAction(
            kind=kind,  # type: ignore
            payload=payload,
            justification=a.get("justification", f"LLM proposed {kind}"),
        ))

    if not parsed:
        raise ProposalError("actions list must not be empty")

    return ParsedProposal(actions=parsed)


def validate_tool_args(tool: str, args: dict) -> tuple[bool, str]:
    """
    Validate tool arguments against known schemas.
    
    Returns:
        (is_valid, error_message)
    """
    # Tool schemas (extensible)
    SCHEMAS = {
        "read_file": {"required": ["path"]},
        "write_file": {"required": ["path", "content"]},
        "run_command": {"required": ["command"]},
        "search_code": {"required": ["query"]},
        "list_files": {"required": ["directory"]},
    }
    
    if tool not in SCHEMAS:
        # Unknown tools pass through (gate will handle)
        return True, ""
    
    schema = SCHEMAS[tool]
    for field in schema.get("required", []):
        if field not in args:
            return False, f"Missing required field: {field}"
    
    return True, ""
