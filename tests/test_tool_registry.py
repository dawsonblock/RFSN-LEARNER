# tests/test_tool_registry.py
"""
Tests for tool registry invariants.

These tests enforce critical safety invariants:
1. Schema validator rejects extra/missing fields
2. Unknown tools are denied
3. High-risk tools require explicit grants
4. Path scope is enforced
5. Budgets are enforced
"""

from controller.budget_enforcer import BudgetEnforcer
from controller.tool_registry import (
    Budget,
    Risk,
    build_tool_registry,
    enforce_path_scope,
    validate_arguments,
)
from controller.tool_router import ExecutionContext, route_tool_call


class TestSchemaValidation:
    """Schema validation must reject invalid arguments."""

    def test_rejects_missing_required_field(self):
        """Schema validation rejects calls with missing required fields."""
        registry = build_tool_registry()
        spec = registry["read_file"]

        # Missing 'path' which is required
        ok, err = validate_arguments(spec, {})
        assert not ok
        assert "missing required arg" in err
        assert "path" in err

    def test_rejects_wrong_type(self):
        """Schema validation rejects wrong argument types."""
        registry = build_tool_registry()
        spec = registry["read_file"]

        # 'path' should be string, not int
        ok, err = validate_arguments(spec, {"path": 123})
        assert not ok
        assert "wrong type" in err

    def test_rejects_extra_fields(self):
        """Schema validation rejects unexpected extra arguments."""
        registry = build_tool_registry()
        spec = registry["read_file"]

        # 'unknown_arg' is not in schema
        ok, err = validate_arguments(spec, {"path": "test.txt", "unknown_arg": "foo"})
        assert not ok
        assert "unexpected args" in err

    def test_accepts_valid_arguments(self):
        """Schema validation accepts valid arguments."""
        registry = build_tool_registry()
        spec = registry["read_file"]

        ok, err = validate_arguments(spec, {"path": "test.txt"})
        assert ok
        assert err == ""

    def test_accepts_optional_fields(self):
        """Schema validation accepts optional fields."""
        registry = build_tool_registry()
        spec = registry["read_file"]

        ok, err = validate_arguments(spec, {"path": "test.txt", "max_bytes": 1000})
        assert ok


class TestUnknownToolDenied:
    """Unknown tools must be denied by the router."""

    def test_unknown_tool_denied(self):
        """Router denies unknown tools with clear error."""
        context = ExecutionContext(session_id="test")

        result = route_tool_call("nonexistent_tool", {}, context)

        assert not result.success
        assert "Unknown tool" in result.error


class TestPermissionGating:
    """High-risk tools require explicit grants."""

    def test_write_file_requires_grant(self):
        """write_file requires explicit permission grant."""
        context = ExecutionContext(
            session_id="test",
            working_directory="/tmp",
        )

        result = route_tool_call(
            "write_file", {"path": "/tmp/test.txt", "content": "hello"}, context
        )

        assert not result.success
        assert "Permission required" in result.error

    def test_write_file_allowed_with_grant(self):
        """write_file works after permission is granted."""
        context = ExecutionContext(
            session_id="test",
            working_directory="/tmp",
        )
        context.permissions.grant_tool("write_file")

        result = route_tool_call(
            "write_file", {"path": "/tmp/test_registry.txt", "content": "hello"}, context
        )

        # Should succeed (or at least not fail on permission)
        assert result.success or "Permission" not in (result.error or "")

    def test_run_command_requires_grant(self):
        """run_command requires explicit permission grant."""
        context = ExecutionContext(session_id="test")

        result = route_tool_call("run_command", {"command": "ls"}, context)

        assert not result.success
        assert "Permission required" in result.error


class TestPathScope:
    """Filesystem tools must be confined to working directory."""

    def test_path_escape_denied(self):
        """Paths outside working_directory are denied."""
        ok, err = enforce_path_scope(workdir="/home/user/project", path="/etc/passwd")

        assert not ok
        assert "escapes" in err

    def test_path_within_workdir_allowed(self):
        """Paths within working_directory are allowed."""
        ok, err = enforce_path_scope(workdir="/tmp", path="/tmp/subdir/file.txt")

        assert ok
        assert err == ""

    def test_relative_path_traversal_denied(self):
        """Relative path traversal (../) is denied."""
        ok, err = enforce_path_scope(
            workdir="/home/user/project", path="/home/user/project/../other"
        )

        assert not ok
        assert "escapes" in err


class TestBudgetEnforcement:
    """Per-turn budgets must be enforced."""

    def test_budget_exceeded(self):
        """Tool calls exceeding budget are denied."""
        enforcer = BudgetEnforcer()
        budget = Budget(calls_per_turn=2)

        # First two calls succeed
        ok1, _ = enforcer.check_and_charge(tool="test", budget=budget)
        ok2, _ = enforcer.check_and_charge(tool="test", budget=budget)

        # Third call exceeds budget
        ok3, err = enforcer.check_and_charge(tool="test", budget=budget)

        assert ok1 and ok2
        assert not ok3
        assert "exceeded" in err

    def test_budget_resets_on_new_turn(self):
        """Budget resets when new turn starts."""
        enforcer = BudgetEnforcer()
        budget = Budget(calls_per_turn=1)

        # Use up budget
        enforcer.check_and_charge(tool="test", budget=budget)
        ok_before, _ = enforcer.check_and_charge(tool="test", budget=budget)

        # Reset turn
        enforcer.reset_turn()

        # Should work again
        ok_after, _ = enforcer.check_and_charge(tool="test", budget=budget)

        assert not ok_before
        assert ok_after


class TestRegistryCompleteness:
    """Registry must have all expected tools."""

    def test_registry_has_18_tools(self):
        """Registry should have exactly 18 tools."""
        registry = build_tool_registry()
        assert len(registry) == 18

    def test_all_high_risk_require_grant(self):
        """All HIGH risk tools should require explicit grant."""
        registry = build_tool_registry()

        high_risk = [name for name, spec in registry.items() if spec.risk == Risk.HIGH]
        require_grant = [
            name for name, spec in registry.items() if spec.permission.require_explicit_grant
        ]

        # Every high-risk tool should require grant
        for tool in high_risk:
            assert tool in require_grant, f"High-risk tool {tool} should require grant"

    def test_all_tools_have_budgets(self):
        """Every tool must have a budget defined."""
        registry = build_tool_registry()

        for name, spec in registry.items():
            assert spec.budget is not None, f"Tool {name} missing budget"
            assert spec.budget.calls_per_turn > 0, f"Tool {name} has zero call budget"


class TestReplayModeBlocking:
    """Destructive tools must be blocked during replay."""

    def test_write_file_blocked_in_replay(self):
        """write_file should be denied when replay_mode is 'replay'."""
        context = ExecutionContext(
            session_id="test",
            working_directory="/tmp",
        )
        context.permissions.grant_tool("write_file")
        context.replay_mode = "replay"

        result = route_tool_call(
            "write_file", {"path": "/tmp/test.txt", "content": "hello"}, context
        )

        assert not result.success
        assert "denied in replay mode" in result.error

    def test_write_file_allowed_in_record(self):
        """write_file should be allowed when replay_mode is 'record'."""
        context = ExecutionContext(
            session_id="test",
            working_directory="/tmp",
        )
        context.permissions.grant_tool("write_file")
        context.replay_mode = "record"

        result = route_tool_call(
            "write_file", {"path": "/tmp/test_replay.txt", "content": "hello"}, context
        )

        # Should succeed (file may not exist but permission OK)
        assert result.success or "replay" not in (result.error or "").lower()

    def test_read_file_allowed_in_replay(self):
        """read_file should be allowed even in replay mode (read-only)."""
        context = ExecutionContext(
            session_id="test",
            working_directory="/tmp",
        )
        context.replay_mode = "replay"

        # read_file doesn't have deny_in_replay set
        result = route_tool_call("read_file", {"path": "/tmp"}, context)

        # Should not fail due to replay mode
        assert "replay" not in (result.error or "").lower()

    def test_memory_delete_blocked_in_replay(self):
        """memory_delete should be denied when replay_mode is 'replay'."""
        context = ExecutionContext(session_id="test")
        context.permissions.grant_tool("memory_delete")
        context.replay_mode = "replay"

        result = route_tool_call("memory_delete", {"key": "test_key"}, context)

        assert not result.success
        assert "denied in replay mode" in result.error

    def test_apply_diff_blocked_in_replay(self):
        """apply_diff should be denied when replay_mode is 'replay'."""
        context = ExecutionContext(
            session_id="test",
            working_directory="/tmp",
        )
        context.permissions.grant_tool("apply_diff")
        context.replay_mode = "replay"

        result = route_tool_call(
            "apply_diff",
            {"file_path": "/tmp/test.py", "diff": "@@ -1,1 +1,1 @@\n-old\n+new"},
            context,
        )

        assert not result.success
        assert "denied in replay mode" in result.error
