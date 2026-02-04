"""
Test execution with resource limits and result parsing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .docker_runner import ContainerConfig, run_in_container


@dataclass(frozen=True)
class TestResult:
    passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    output: str
    timed_out: bool


def _parse_pytest_output(output: str) -> tuple[int, int, int, int]:
    """
    Parse pytest output for test counts.
    Returns (total, passed, failed, errors).
    """
    # Match patterns like "5 passed", "2 failed", "1 error"
    passed = 0
    failed = 0
    errors = 0
    
    # Look for summary line like "===== 5 passed, 2 failed in 1.23s ====="
    summary_match = re.search(
        r"=+\s*([\d\w\s,]+)\s+in\s+[\d.]+s?\s*=+",
        output,
        re.IGNORECASE,
    )
    
    if summary_match:
        summary = summary_match.group(1)
        
        passed_match = re.search(r"(\d+)\s+passed", summary)
        if passed_match:
            passed = int(passed_match.group(1))
        
        failed_match = re.search(r"(\d+)\s+failed", summary)
        if failed_match:
            failed = int(failed_match.group(1))
        
        error_match = re.search(r"(\d+)\s+error", summary)
        if error_match:
            errors = int(error_match.group(1))
    
    total = passed + failed + errors
    return total, passed, failed, errors


def _parse_unittest_output(output: str) -> tuple[int, int, int, int]:
    """
    Parse unittest output for test counts.
    Returns (total, passed, failed, errors).
    """
    # Match "Ran X tests"
    ran_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    total = int(ran_match.group(1)) if ran_match else 0
    
    # Check for OK (all passed)
    if re.search(r"^OK\s*$", output, re.MULTILINE):
        return total, total, 0, 0
    
    # Parse failures and errors
    failed = 0
    errors = 0
    
    result_match = re.search(
        r"FAILED\s*\((?:failures=(\d+))?(?:,?\s*errors=(\d+))?\)",
        output,
    )
    if result_match:
        failed = int(result_match.group(1) or 0)
        errors = int(result_match.group(2) or 0)
    
    passed = max(0, total - failed - errors)
    return total, passed, failed, errors


def run_tests(
    worktree: Path,
    test_command: str,
    *,
    timeout_seconds: int = 300,
    memory_limit: str = "2g",
    use_docker: bool = True,
) -> TestResult:
    """
    Run tests in the worktree with resource limits.
    
    Supports pytest and unittest output parsing.
    If use_docker=False, runs directly (less isolation).
    """
    worktree = Path(worktree).resolve()
    
    if use_docker:
        config = ContainerConfig(
            memory_limit=memory_limit,
            network_disabled=True,
        )
        
        result = run_in_container(
            test_command,
            worktree,
            config=config,
            timeout_seconds=timeout_seconds,
        )
        
        output = result.stdout + "\n" + result.stderr
        exit_code = result.exit_code
        timed_out = result.timed_out
    else:
        import subprocess
        try:
            proc = subprocess.run(
                test_command,
                shell=True,
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = proc.stdout + "\n" + proc.stderr
            exit_code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            output = "Test execution timed out"
            exit_code = -1
            timed_out = True
    
    # Try pytest parsing first, then unittest
    total, passed, failed, errors = _parse_pytest_output(output)
    if total == 0:
        total, passed, failed, errors = _parse_unittest_output(output)
    
    # Determine overall pass/fail
    tests_passed = (exit_code == 0) and (failed == 0) and (errors == 0)
    
    return TestResult(
        passed=tests_passed,
        total_tests=total,
        passed_tests=passed,
        failed_tests=failed,
        error_tests=errors,
        output=output,
        timed_out=timed_out,
    )
