# tests/test_test_delta.py
"""
Tests for test delta computation.
"""
from __future__ import annotations

import pytest

from controller.test_runner import TestResult
from controller.test_delta import TestDelta, quick_test_check


class TestTestDelta:
    """Test TestDelta class."""

    def test_tests_fixed_positive(self):
        baseline = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=5,
            failed_tests=5,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.tests_fixed == 5

    def test_tests_broken_positive(self):
        baseline = TestResult(
            passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=7,
            failed_tests=3,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.tests_broken == 3

    def test_net_change_positive(self):
        baseline = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=3,
            failed_tests=7,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.net_change == 5

    def test_improved_true(self):
        baseline = TestResult(
            passed=False,
            total_tests=5,
            passed_tests=2,
            failed_tests=3,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=False,
            total_tests=5,
            passed_tests=4,
            failed_tests=1,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.improved is True

    def test_improved_false_when_timed_out(self):
        baseline = TestResult(
            passed=False,
            total_tests=5,
            passed_tests=2,
            failed_tests=3,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=False,
            total_tests=5,
            passed_tests=4,
            failed_tests=1,
            error_tests=0,
            output="",
            timed_out=True,  # Timed out
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.improved is False

    def test_regression_true(self):
        baseline = TestResult(
            passed=True,
            total_tests=5,
            passed_tests=5,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=False,
            total_tests=5,
            passed_tests=3,
            failed_tests=2,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.regression is True

    def test_reward_full_success(self):
        baseline = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=5,
            failed_tests=5,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.reward == 1.0

    def test_reward_regression(self):
        baseline = TestResult(
            passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=5,
            failed_tests=5,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        assert delta.reward < 0

    def test_reward_no_change(self):
        baseline = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=5,
            failed_tests=5,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=baseline)
        assert delta.reward == 0.0

    def test_to_dict(self):
        baseline = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=5,
            failed_tests=5,
            error_tests=0,
            output="",
            timed_out=False,
        )
        patched = TestResult(
            passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=patched)
        d = delta.to_dict()

        assert "baseline" in d
        assert "patched" in d
        assert "delta" in d
        assert d["delta"]["fixed"] == 5
        assert d["delta"]["improved"] is True


class TestEmptyResults:
    """Test edge cases with empty results."""

    def test_reward_zero_tests(self):
        baseline = TestResult(
            passed=True,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            error_tests=0,
            output="",
            timed_out=False,
        )
        delta = TestDelta(baseline=baseline, patched=baseline)
        assert delta.reward == 0.0
