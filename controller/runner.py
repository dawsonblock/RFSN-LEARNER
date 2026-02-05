"""
Main task execution flow - the controller orchestrator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rfsn.gate import gate
from rfsn.ledger import AppendOnlyLedger

# Add parent to path for local imports
from rfsn.types import GateDecision, StateSnapshot
from upstream_learner.outcome_db import OutcomeDB
from upstream_learner.propose import Candidate, select_candidate

from .hasher import compute_fs_tree_hash
from .patch_applier import apply_patch
from .reward import compute_reward, record_outcome
from .test_runner import TestResult, run_tests


@dataclass
class TaskConfig:
    """Configuration for a single task execution."""

    repo_path: Path
    task_id: str
    test_command: str = "python -m pytest"
    toolchain: str = "python3.12"
    timeout_seconds: int = 300
    memory_limit: str = "2g"
    use_docker: bool = True
    ledger_path: Path | None = None
    outcome_db_path: Path | None = None

    @classmethod
    def from_json(cls, path: Path | str) -> "TaskConfig":
        with open(path) as f:
            data = json.load(f)
        return cls(
            repo_path=Path(data["repo_path"]),
            task_id=data["task_id"],
            test_command=data.get("test_command", "python -m pytest"),
            toolchain=data.get("toolchain", "python3.12"),
            timeout_seconds=data.get("timeout_seconds", 300),
            memory_limit=data.get("memory_limit", "2g"),
            use_docker=data.get("use_docker", True),
            ledger_path=Path(data["ledger_path"]) if data.get("ledger_path") else None,
            outcome_db_path=Path(data["outcome_db_path"]) if data.get("outcome_db_path") else None,
        )


@dataclass
class RunResult:
    """Result of a single task run."""

    task_id: str
    decision: GateDecision
    selected_arm: str | None
    test_result: TestResult | None
    reward: float | None
    error: str | None = None


def build_state_snapshot(config: TaskConfig) -> StateSnapshot:
    """Build a StateSnapshot from the current filesystem state."""
    fs_hash = compute_fs_tree_hash(config.repo_path)

    # Run initial tests to get baseline state
    baseline_tests = run_tests(
        config.repo_path,
        config.test_command,
        timeout_seconds=config.timeout_seconds,
        memory_limit=config.memory_limit,
        use_docker=config.use_docker,
    )

    return StateSnapshot(
        repo_id=str(config.repo_path),
        fs_tree_hash=fs_hash,
        toolchain=config.toolchain,
        tests_passed=baseline_tests.passed,
        metadata={"task_id": config.task_id},
    )


def run_task(
    config: TaskConfig,
    candidates: Sequence[Candidate],
    *,
    allow_commands: bool = False,
) -> RunResult:
    """
    Execute a single task with candidate selection and gating.

    Flow:
    1. Build StateSnapshot from current repo state
    2. Use upstream_learner to select best candidate
    3. Gate the selected action
    4. If allowed: apply patch, run tests
    5. Record outcome and ledger entry
    """
    # Setup paths
    ledger_path = config.ledger_path or Path("rfsn_ledger.jsonl")
    outcome_db_path = config.outcome_db_path or Path("outcomes.db")

    ledger = AppendOnlyLedger(str(ledger_path))
    outcome_db = OutcomeDB(str(outcome_db_path))

    # Step 1: Build state
    try:
        state = build_state_snapshot(config)
    except Exception as e:
        return RunResult(
            task_id=config.task_id,
            decision=GateDecision(False, f"Failed to build state: {e}"),
            selected_arm=None,
            test_result=None,
            reward=None,
            error=str(e),
        )

    # Step 2: Select candidate
    task_dict = {"task_id": config.task_id, "repo": str(config.repo_path)}
    selected_action = select_candidate(db=outcome_db, task=task_dict, candidates=candidates)
    selected_arm = next(c.arm_key for c in candidates if c.action == selected_action)

    # Step 3: Gate the action
    decision = gate(state, selected_action, allow_commands=allow_commands)

    # Step 4: Record to ledger (always, regardless of decision)
    decision_str = "allow" if decision.allow else f"deny:{decision.reason}"
    ledger.append(state, selected_action, decision_str)

    # Step 5: If denied, we're done
    if not decision.allow:
        return RunResult(
            task_id=config.task_id,
            decision=decision,
            selected_arm=selected_arm,
            test_result=None,
            reward=0.0,
        )

    # Step 6: Apply patch if it's a patch action
    test_result = None
    reward = 0.0

    if selected_action.kind == "patch":
        patch_result = apply_patch(
            config.repo_path,
            decision.normalized_action.payload
            if decision.normalized_action
            else selected_action.payload,
        )

        if not patch_result.success:
            return RunResult(
                task_id=config.task_id,
                decision=decision,
                selected_arm=selected_arm,
                test_result=None,
                reward=0.0,
                error=f"Patch failed: {patch_result.message}",
            )

        # Run tests after patch
        test_result = run_tests(
            config.repo_path,
            config.test_command,
            timeout_seconds=config.timeout_seconds,
            memory_limit=config.memory_limit,
            use_docker=config.use_docker,
        )

        reward = compute_reward(test_result)

    elif selected_action.kind == "patch_plan":
        # Plans are non-executable, reward is informational only
        reward = 0.5  # Neutral reward for plans

    # Step 7: Record outcome
    context_key = f"benchmark::{config.task_id}"
    record_outcome(
        outcome_db_path,
        context_key,
        selected_arm,
        reward,
        test_result=test_result,
    )

    return RunResult(
        task_id=config.task_id,
        decision=decision,
        selected_arm=selected_arm,
        test_result=test_result,
        reward=reward,
    )
