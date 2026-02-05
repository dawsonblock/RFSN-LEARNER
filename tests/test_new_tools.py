# tests/test_new_tools.py
"""
Tests for new tool modules: shell, code, reasoning.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from controller.tools.code import get_symbols, grep_files
from controller.tools.reasoning import ask_user, plan, think
from controller.tools.shell import ALLOWED_PREFIXES, run_command, run_python


class TestShellTools:
    """Tests for shell execution tools."""

    def test_run_command_echo(self):
        result = run_command("echo hello world")
        assert result.success is True
        assert "hello world" in result.output["stdout"]

    def test_run_command_pwd(self):
        result = run_command("pwd")
        assert result.success is True
        assert len(result.output["stdout"]) > 0

    def test_run_command_blocked(self):
        result = run_command("rm -rf /")
        assert result.success is False
        assert "blocked" in result.error.lower()

    def test_run_command_not_in_allowlist(self):
        # Use a command that is definitely not in the allowlist
        result = run_command("nmap localhost")
        assert result.success is False

    def test_run_python_simple(self):
        result = run_python("print(1 + 1)")
        assert result.success is True
        assert "2" in result.output["stdout"]

    def test_run_python_multiline(self):
        code = "x = 5\ny = 10\nprint(x + y)"
        result = run_python(code)
        assert result.success is True
        assert "15" in result.output["stdout"]

    def test_run_python_syntax_error(self):
        result = run_python("def broken(")
        assert result.success is False

    def test_allowed_prefixes_includes_safe_commands(self):
        assert "echo" in ALLOWED_PREFIXES
        assert "ls" in ALLOWED_PREFIXES
        assert "cat" in ALLOWED_PREFIXES
        assert "grep" in ALLOWED_PREFIXES


class TestCodeTools:
    """Tests for code intelligence tools."""

    def test_grep_files_finds_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def hello():\n    return 'world'\n")

            result = grep_files("hello", tmpdir)
            assert result.success is True
            assert len(result.output["matches"]) > 0
            assert "test.py" in result.output["matches"][0]["file"]

    def test_grep_files_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo():\n    pass\n")

            result = grep_files("nonexistent_pattern_xyz", tmpdir)
            assert result.success is True
            assert len(result.output["matches"]) == 0

    def test_grep_files_invalid_directory(self):
        result = grep_files("test", "/nonexistent/path/xyz")
        assert result.success is False

    def test_get_symbols_python_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "example.py"
            test_file.write_text("""
class MyClass:
    def method(self):
        pass

def standalone_function():
    pass

CONSTANT = 42
""")
            result = get_symbols(str(test_file))
            assert result.success is True
            # Should find class and functions
            symbols = result.output["symbols"]
            symbol_names = [s["name"] for s in symbols]
            assert "MyClass" in symbol_names
            assert "standalone_function" in symbol_names

    def test_get_symbols_nonexistent_file(self):
        result = get_symbols("/nonexistent/file.py")
        assert result.success is False


class TestReasoningTools:
    """Tests for reasoning tools (no side effects)."""

    def test_think_returns_thought(self):
        result = think("I need to analyze this problem step by step.")
        assert result.success is True
        assert "analyze" in result.output["thought"].lower()
        assert result.output["recorded"] is True

    def test_think_empty_input(self):
        result = think("")
        assert result.success is True

    def test_plan_returns_steps(self):
        result = plan(
            goal="Fix the bug in auth module",
            steps=["Read the code", "Identify the issue", "Write a fix"],
        )
        assert result.success is True
        assert result.output["goal"] == "Fix the bug in auth module"
        assert result.output["total_steps"] == 3
        assert result.output["steps"][0]["step"] == "Read the code"

    def test_plan_empty_steps(self):
        result = plan(goal="Do something", steps=[])
        assert result.success is True
        assert result.output["total_steps"] == 0

    def test_ask_user_returns_question(self):
        result = ask_user("Should I proceed with the refactoring?")
        assert result.success is True
        assert "proceed" in result.output["question"].lower()
        assert result.output["awaiting_response"] is True

    def test_ask_user_with_options(self):
        result = ask_user(
            "Which approach should I use?",
            options=["Option A: Fast", "Option B: Safe"],
        )
        assert result.success is True
        assert result.output["options"] is not None
        assert "Option A: Fast" in result.output["options"]
