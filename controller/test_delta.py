# controller/test_delta.py
"""
Test delta computation: baseline → patch → delta.

Computes reward signals from test execution before/after a patch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .test_runner import TestResult, run_tests


@dataclass(frozen=True)
class TestDelta:
    """Change in test results before/after patch."""

    baseline: TestResult
    patched: TestResult

    @property
    def tests_fixed(self) -> int:
        """Number of tests that changed from failing to passing."""
        return max(0, self.patched.passed_tests - self.baseline.passed_tests)

    @property
    def tests_broken(self) -> int:
        """Number of tests that changed from passing to failing."""
        return max(0, self.baseline.passed_tests - self.patched.passed_tests)

    @property
    def net_change(self) -> int:
        """Net change in passing tests (positive = improvement)."""
        return self.patched.passed_tests - self.baseline.passed_tests

    @property
    def improved(self) -> bool:
        """Did the patch improve test outcomes?"""
        return self.net_change > 0 and not self.patched.timed_out

    @property
    def regression(self) -> bool:
        """Did the patch cause regressions?"""
        return self.net_change < 0 or (self.baseline.passed and not self.patched.passed)

    @property
    def reward(self) -> float:
        """
        Compute reward signal for reinforcement learning.

        Range: [-1.0, 1.0]
        - 1.0: All tests now pass (from some failing)
        - 0.0: No change
        - -1.0: Made things worse
        """
        if self.baseline.total_tests == 0:
            return 0.0

        # Full success: all tests pass after patch
        if self.patched.passed and not self.baseline.passed:
            return 1.0

        # Regression: tests broke
        if self.regression:
            return -0.5 - 0.5 * (self.tests_broken / max(1, self.baseline.total_tests))

        # Partial improvement
        if self.improved:
            return 0.5 * (
                self.tests_fixed / max(1, self.baseline.failed_tests + self.baseline.error_tests)
            )

        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ledger."""
        return {
            "baseline": {
                "passed": self.baseline.passed,
                "total": self.baseline.total_tests,
                "passed_tests": self.baseline.passed_tests,
                "failed_tests": self.baseline.failed_tests,
            },
            "patched": {
                "passed": self.patched.passed,
                "total": self.patched.total_tests,
                "passed_tests": self.patched.passed_tests,
                "failed_tests": self.patched.failed_tests,
            },
            "delta": {
                "fixed": self.tests_fixed,
                "broken": self.tests_broken,
                "net": self.net_change,
                "improved": self.improved,
                "regression": self.regression,
                "reward": self.reward,
            },
        }


def compute_test_delta(
    worktree: Path,
    test_command: str,
    apply_patch_fn: callable,
    *,
    timeout: int = 300,
    use_docker: bool = True,
) -> TestDelta:
    """
    Compute test delta: baseline → apply patch → patched.

    Args:
        worktree: Path to the working directory
        test_command: Command to run tests (e.g., "pytest tests/")
        apply_patch_fn: Function that applies the patch (returns True if successful)
        timeout: Timeout for each test run
        use_docker: Whether to use Docker for isolation

    Returns:
        TestDelta with baseline and patched results
    """
    # 1. Run baseline tests
    baseline = run_tests(
        worktree,
        test_command,
        timeout_seconds=timeout,
        use_docker=use_docker,
    )

    # 2. Apply patch
    try:
        patch_applied = apply_patch_fn()
        if not patch_applied:
            # Patch failed - return baseline with no change
            return TestDelta(baseline=baseline, patched=baseline)
    except Exception:
        return TestDelta(baseline=baseline, patched=baseline)

    # 3. Run tests after patch
    patched = run_tests(
        worktree,
        test_command,
        timeout_seconds=timeout,
        use_docker=use_docker,
    )

    return TestDelta(baseline=baseline, patched=patched)


def quick_test_check(
    worktree: Path,
    test_command: str = "pytest --collect-only -q",
    *,
    timeout: int = 30,
) -> tuple[bool, int]:
    """
    Quick check if tests are discoverable.

    Returns:
        (tests_found: bool, count: int)
    """
    import subprocess

    try:
        result = subprocess.run(
            test_command,
            shell=True,
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Count test items
        import re

        matches = re.findall(r"(\d+)\s+test", result.stdout + result.stderr)
        count = int(matches[0]) if matches else 0

        return result.returncode == 0, count

    except (subprocess.TimeoutExpired, Exception):
        return False, 0
