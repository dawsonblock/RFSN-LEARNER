"""
CLI for the controller.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rfsn.types import ProposedAction
from upstream_learner.propose import Candidate

from .runner import TaskConfig, run_task


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RFSN Controller - Execute tasks with gating and learning"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a task with candidates")
    run_parser.add_argument(
        "--task",
        "-t",
        required=True,
        help="Path to task config JSON",
    )
    run_parser.add_argument(
        "--candidates",
        "-c",
        required=True,
        help="Path to candidates JSON (list of {arm_key, action})",
    )
    run_parser.add_argument(
        "--allow-commands",
        action="store_true",
        help="Allow command-type actions (dangerous)",
    )
    run_parser.add_argument(
        "--output",
        "-o",
        help="Path to write result JSON",
    )

    # Hash command
    hash_parser = subparsers.add_parser("hash", help="Compute fs_tree_hash for a directory")
    hash_parser.add_argument("path", help="Directory to hash")

    args = parser.parse_args()

    if args.command == "hash":
        from .hasher import compute_fs_tree_hash

        result = compute_fs_tree_hash(Path(args.path))
        print(result)
        return 0

    elif args.command == "run":
        # Load task config
        config = TaskConfig.from_json(args.task)

        # Load candidates
        with open(args.candidates) as f:
            candidates_data = json.load(f)

        candidates = []
        for c in candidates_data:
            action = ProposedAction(
                kind=c["action"]["kind"],
                payload=c["action"]["payload"],
                justification=c["action"]["justification"],
                risk_tags=tuple(c["action"].get("risk_tags", [])),
            )
            candidates.append(Candidate(c["arm_key"], action))

        # Run task
        result = run_task(config, candidates, allow_commands=args.allow_commands)

        # Format output
        output = {
            "task_id": result.task_id,
            "decision": {
                "allow": result.decision.allow,
                "reason": result.decision.reason,
            },
            "selected_arm": result.selected_arm,
            "reward": result.reward,
        }

        if result.test_result:
            output["test_result"] = {
                "passed": result.test_result.passed,
                "total_tests": result.test_result.total_tests,
                "passed_tests": result.test_result.passed_tests,
                "failed_tests": result.test_result.failed_tests,
            }

        if result.error:
            output["error"] = result.error

        output_json = json.dumps(output, indent=2)

        if args.output:
            Path(args.output).write_text(output_json)
        else:
            print(output_json)

        return 0 if result.decision.allow else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
