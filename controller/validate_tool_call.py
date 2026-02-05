# controller/validate_tool_call.py
"""
Pre-gate validation of tool_call arguments against schemas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rfsn.types import ProposedAction
from controller.tool_schema import TOOL_SCHEMAS, allow_unknown_tools


@dataclass(frozen=True)
class ValidationResult:
    """Result of tool call validation."""
    ok: bool
    error: str = ""


def validate_tool_call(action: ProposedAction) -> ValidationResult:
    """
    Validate a tool_call action against its schema.
    
    Returns ValidationResult with ok=True if valid,
    or ok=False with error message if invalid.
    """
    if action.kind != "tool_call":
        return ValidationResult(ok=True)

    payload = action.payload
    if not isinstance(payload, dict):
        return ValidationResult(ok=False, error="tool_call.payload must be a dict")

    tool = payload.get("tool")
    args = payload.get("args", payload.get("arguments", {}))

    if not isinstance(tool, str) or not tool:
        return ValidationResult(ok=False, error="tool_call.payload.tool must be a non-empty string")

    if not isinstance(args, dict):
        return ValidationResult(ok=False, error="tool_call.payload.args must be an object")

    schema = TOOL_SCHEMAS.get(tool)
    if schema is None:
        if allow_unknown_tools():
            return ValidationResult(ok=True)
        return ValidationResult(ok=False, error=f"Unknown tool '{tool}' (no schema)")

    # Check required fields
    for f in schema:
        if f.required and f.name not in args:
            return ValidationResult(ok=False, error=f"Tool '{tool}' missing required arg '{f.name}'")

    # Type/shape checks (only for provided fields)
    for f in schema:
        if f.name in args and not f.check(args.get(f.name)):
            return ValidationResult(ok=False, error=f"Tool '{tool}' arg '{f.name}' failed validation")

    # Block unexpected keys (tight by default)
    allowed = {f.name for f in schema}
    extra = [k for k in args.keys() if k not in allowed]
    if extra:
        return ValidationResult(ok=False, error=f"Tool '{tool}' has unexpected args: {extra}")

    return ValidationResult(ok=True)
