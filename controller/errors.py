# controller/errors.py
"""
Error taxonomy with structured codes for machine-readable analysis.

Error codes follow the pattern: {category}:{specific_code}

Categories:
- deny: Gate/policy denials
- schema: Argument validation failures
- budget: Resource limit exceeded
- perm: Permission failures
- tool: Tool execution errors
- llm: LLM-related errors
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    DENY = "deny"
    SCHEMA = "schema"
    BUDGET = "budget"
    PERM = "perm"
    TOOL = "tool"
    LLM = "llm"


# Structured error codes
class ErrorCode:
    # Deny codes (gate/policy)
    DENY_UNKNOWN_TOOL = "deny:unknown_tool"
    DENY_POLICY_FORBIDDEN = "deny:policy_forbidden"
    DENY_PATH_ESCAPE = "deny:path_escape"
    DENY_DOMAIN_BLOCKED = "deny:domain_blocked"
    DENY_PAYLOAD_SIZE = "deny:payload_size"

    # Schema codes (validation)
    SCHEMA_MISSING_REQUIRED = "schema:missing_required"
    SCHEMA_WRONG_TYPE = "schema:wrong_type"
    SCHEMA_UNEXPECTED_ARG = "schema:unexpected_arg"
    SCHEMA_INVALID_FORMAT = "schema:invalid_format"

    # Budget codes
    BUDGET_CALLS_EXCEEDED = "budget:calls_exceeded"
    BUDGET_BYTES_EXCEEDED = "budget:bytes_exceeded"
    BUDGET_RESULTS_EXCEEDED = "budget:results_exceeded"
    BUDGET_TIMEOUT = "budget:timeout"

    # Permission codes
    PERM_GRANT_REQUIRED = "perm:grant_required"
    PERM_SCOPE_DENIED = "perm:scope_denied"

    # Tool execution codes
    TOOL_TIMEOUT = "tool:timeout"
    TOOL_NOT_FOUND = "tool:not_found"
    TOOL_BAD_ARGS = "tool:bad_args"
    TOOL_EXTERNAL_FAILURE = "tool:external_failure"
    TOOL_INTERNAL_ERROR = "tool:internal_error"
    TOOL_COMMAND_BLOCKED = "tool:command_blocked"

    # LLM codes
    LLM_PARSE_ERROR = "llm:parse_error"
    LLM_PROVIDER_ERROR = "llm:provider_error"
    LLM_RATE_LIMIT = "llm:rate_limit"
    LLM_CONTEXT_TOO_LONG = "llm:context_too_long"
    LLM_EMPTY_RESPONSE = "llm:empty_response"


@dataclass(frozen=True)
class StructuredError:
    """Structured error for machine-readable logging."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"code": self.code, "message": self.message}
        if self.details:
            d["details"] = self.details
        return d

    @property
    def category(self) -> str:
        return self.code.split(":")[0] if ":" in self.code else "unknown"


def make_error(code: str, message: str, **details: Any) -> StructuredError:
    """Create a structured error."""
    return StructuredError(
        code=code,
        message=message,
        details=details if details else None,
    )


# Convenience constructors
def deny_unknown_tool(tool: str) -> StructuredError:
    return make_error(ErrorCode.DENY_UNKNOWN_TOOL, f"Unknown tool: {tool}", tool=tool)


def deny_path_escape(path: str, workdir: str) -> StructuredError:
    return make_error(
        ErrorCode.DENY_PATH_ESCAPE, "Path escapes workdir", path=path, workdir=workdir
    )


def schema_missing_required(tool: str, arg: str) -> StructuredError:
    return make_error(
        ErrorCode.SCHEMA_MISSING_REQUIRED, f"Missing required arg: {arg}", tool=tool, arg=arg
    )


def schema_wrong_type(tool: str, arg: str, expected: str) -> StructuredError:
    return make_error(
        ErrorCode.SCHEMA_WRONG_TYPE, f"Wrong type for {arg}", tool=tool, arg=arg, expected=expected
    )


def budget_calls_exceeded(tool: str, used: int, limit: int) -> StructuredError:
    return make_error(
        ErrorCode.BUDGET_CALLS_EXCEEDED, "Call limit exceeded", tool=tool, used=used, limit=limit
    )


def perm_grant_required(tool: str) -> StructuredError:
    return make_error(ErrorCode.PERM_GRANT_REQUIRED, f"Permission required for: {tool}", tool=tool)


def tool_timeout(tool: str, timeout: int) -> StructuredError:
    return make_error(
        ErrorCode.TOOL_TIMEOUT, f"Tool timed out after {timeout}s", tool=tool, timeout=timeout
    )


def tool_command_blocked(command: str, reason: str) -> StructuredError:
    return make_error(
        ErrorCode.TOOL_COMMAND_BLOCKED, f"Command blocked: {reason}", command=command, reason=reason
    )


def llm_parse_error(raw: str | None = None) -> StructuredError:
    return make_error(
        ErrorCode.LLM_PARSE_ERROR, "Failed to parse LLM response", raw=raw[:200] if raw else None
    )
