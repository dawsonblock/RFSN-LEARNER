# tests/test_shell_hardening.py
"""
Comprehensive tests for shell tool security hardening.
Adapted for strict scoped shell implementation (Deep Extraction Zip 9).
"""
from __future__ import annotations
import os
import pytest
from controller.tools.shell import run_command, run_python

class TestCommandValidation:
    """Tests for command validation via run_command."""

    def test_empty_command_rejected(self):
        result = run_command("")
        assert not result.success
        assert "Empty" in (result.error or "")

    def test_allowed_commands_pass(self):
        allowed = ["ls -la", "echo test", "pwd"]
        for cmd in allowed:
            result = run_command(cmd)
            # Depending on environment, these might fail to run if bins not found, but Validation should pass
            # We assert success OR error is not about validation
            if not result.success:
                assert "not allowed" not in (result.error or "")

    def test_blocked_executables_rejected(self):
        blocked = ["bash -c 'echo test'", "sh -c 'echo test'"]
        for cmd in blocked:
            result = run_command(cmd)
            assert not result.success
            assert "Blocked" in (result.error or "")

    def test_dangerous_patterns_rejected(self):
        dangerous = ["rm -rf /", "rm -rf ~", "sudo ls"]
        for cmd in dangerous:
            result = run_command(cmd)
            assert not result.success
            assert "Blocked" in (result.error or "")

    def test_unknown_command_rejected(self):
        result = run_command("ifconfig_xyz")
        assert not result.success
        assert "not allowed" in (result.error or "")

class TestPathScoping:
    """Tests for path scoping enforcement."""

    def test_absolute_paths_blocked(self):
        # Tools in PATH_TAKING: cat, head, tail, grep, find, cp, mv, mkdir, touch, git
        # 'ls' is NOT in PATH_TAKING in the zip 9 shell.py, so it is allowed to roam.
        # We test only blocked commands.
        blocked = ["cat /etc/passwd", "grep foo /tmp/bar", "find /var -name foo"]
        for cmd in blocked:
            result = run_command(cmd)
            assert not result.success, f"Command '{cmd}' should have been blocked"
            assert "Absolute paths are blocked" in (result.error or "")

    def test_traversal_blocked(self):
        blocked = ["cat ../secret.txt", "grep foo ../bar"]
        for cmd in blocked:
            result = run_command(cmd)
            assert not result.success, f"Command '{cmd}' should have been blocked"
            assert "Path traversal" in (result.error or "")

    def test_relative_paths_inside_cwd_allowed(self, tmp_path):
        # Create a file
        p = tmp_path / "test.txt"
        p.write_text("content")
        
        # We need to run command in tmp_path
        # But run_command uses subprocess which needs 'cat' to be in PATH. 
        # Assuming standard env.
        result = run_command("cat test.txt", cwd=str(tmp_path))
        assert result.success
        assert "content" in result.output["stdout"]

    def test_git_flag_paths_checked(self, tmp_path):
        # git -C /tmp bad
        result = run_command("git -C /tmp status", cwd=str(tmp_path))
        assert not result.success
        assert "Absolute paths are blocked" in (result.error or "")

class TestRunPython:
    """Tests for rules on run_python."""

    def test_run_python_success(self):
        result = run_python("print(1+1)")
        assert result.success
        assert "2" in result.output["stdout"]

    def test_run_python_timeout(self):
        result = run_python("import time; time.sleep(2)", timeout=0.5)
        assert not result.success
        assert "timed out" in (result.error or "")
