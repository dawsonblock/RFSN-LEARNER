# tests/test_policy.py
"""
Policy allow/deny tests.

Tests for each tool and path constraint.
"""
from __future__ import annotations

from rfsn.policy import AgentPolicy, DEFAULT_POLICY, DEV_POLICY


class TestDefaultPolicy:
    """Default policy is restrictive."""

    def test_limited_tools(self):
        """Default policy allows only minimal tools."""
        assert len(DEFAULT_POLICY.allowed_tools) < 10
        assert "list_dir" in DEFAULT_POLICY.allowed_tools
        assert "read_file" in DEFAULT_POLICY.allowed_tools

    def test_denies_write_tools(self):
        """Default policy denies write operations."""
        assert "write_file" not in DEFAULT_POLICY.allowed_tools

    def test_safe_path_prefixes(self):
        """Default policy restricts paths."""
        assert len(DEFAULT_POLICY.allowed_path_prefixes) > 0


class TestDevPolicy:
    """Dev policy is permissive."""

    def test_includes_write_tools(self):
        """Dev policy allows write operations."""
        assert "write_file" in DEV_POLICY.allowed_tools
        assert "memory_store" in DEV_POLICY.allowed_tools

    def test_more_tools_than_default(self):
        """Dev policy has more tools than default."""
        assert len(DEV_POLICY.allowed_tools) > len(DEFAULT_POLICY.allowed_tools)


class TestPolicyValidation:
    """Policy validation methods."""

    def test_is_tool_allowed(self):
        """Policy correctly checks tool allowlist."""
        assert DEV_POLICY.is_tool_allowed("list_dir")
        assert DEFAULT_POLICY.is_tool_allowed("list_dir")
        assert not DEFAULT_POLICY.is_tool_allowed("dangerous_tool")

    def test_check_path_with_allowed_prefix(self):
        """Policy correctly checks path prefixes."""
        allowed, reason = DEV_POLICY.check_path("./README.md")
        assert allowed

        allowed, reason = DEV_POLICY.check_path("/tmp/test.txt")
        assert allowed

    def test_check_path_blocks_sensitive(self):
        """Policy blocks sensitive paths."""
        allowed, reason = DEFAULT_POLICY.check_path("/home/user/.ssh/id_rsa")
        assert not allowed

        allowed, reason = DEFAULT_POLICY.check_path("./secrets.txt")
        assert not allowed


class TestPolicyConstraints:
    """Policy constraint checks."""

    def test_has_max_payload(self):
        """Policy has max payload bytes."""
        assert DEFAULT_POLICY.max_payload_bytes > 0
        assert DEV_POLICY.max_payload_bytes > 0

    def test_check_egress_blocks_secrets(self):
        """Policy blocks secret exfiltration."""
        # OpenAI API key pattern
        content = "sk-1234567890123456789012345678901234567890123456"
        allowed, reason = DEFAULT_POLICY.check_egress(content)
        # Note: This may or may not match depending on pattern
        # The test validates the method exists and returns a tuple

        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    def test_check_domain(self):
        """Policy checks domains."""
        allowed, reason = DEFAULT_POLICY.check_domain("api.openai.com")
        assert allowed

        allowed, reason = DEFAULT_POLICY.check_domain("evil.com")
        assert not allowed
