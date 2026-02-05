"""
Reward signal computation and recording.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

# Import upstream learner for recording
from upstream_learner.outcome_db import OutcomeDB

from .test_runner import TestResult


def compute_reward(
    test_result: TestResult,
    *,
    reward_on_pass: float = 1.0,
    reward_on_fail: float = 0.0,
    partial_credit: bool = False,
) -> float:
    """
    Compute reward from test results.

    Default: binary reward (1.0 if all tests pass, 0.0 otherwise).
    With partial_credit=True: reward = passed_tests / total_tests.
    """
    if test_result.timed_out:
        return 0.0

    if partial_credit and test_result.total_tests > 0:
        return test_result.passed_tests / test_result.total_tests

    return reward_on_pass if test_result.passed else reward_on_fail


def record_outcome(
    db_path: Path | str,
    context_key: str,
    arm_key: str,
    reward: float,
    *,
    test_result: TestResult | None = None,
    extra_meta: Mapping[str, Any] | None = None,
) -> None:
    """
    Record an outcome to the upstream learner's OutcomeDB.
    """
    meta: dict[str, Any] = {}

    if test_result is not None:
        meta.update(
            {
                "total_tests": test_result.total_tests,
                "passed_tests": test_result.passed_tests,
                "failed_tests": test_result.failed_tests,
                "timed_out": test_result.timed_out,
            }
        )

    if extra_meta:
        meta.update(extra_meta)

    db = OutcomeDB(str(db_path))
    db.record(
        context_key=context_key,
        arm_key=arm_key,
        reward=reward,
        meta_json=json.dumps(meta) if meta else None,
    )
