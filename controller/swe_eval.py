# controller/swe_eval.py
"""
SWE-Bench style batch evaluator.

Runs multiple tasks, records outcomes, produces learning curves.

Usage:
    python -m controller.swe_eval \
        --tasks tasks.jsonl \
        --workers 4 \
        --out ./results \
        --db ./outcomes.sqlite
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .run_task import run_task, load_task


@dataclass
class EvalResult:
    """Result of evaluating a single task."""
    task_id: str
    success: bool
    reward: float
    arms: dict[str, str]
    completed_steps: int
    total_steps: int
    wall_time: float
    seed: int
    error: str | None = None


@dataclass
class EvalSummary:
    """Summary of batch evaluation."""
    total_tasks: int
    successful: int
    failed: int
    mean_reward: float
    success_rate: float
    total_time: float
    tasks_per_second: float


def load_tasks(path: str) -> Iterator[dict[str, Any]]:
    """Load tasks from JSONL file."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def run_single_task(
    task: dict[str, Any],
    seed: int,
    out_dir: Path,
    db_path: str,
) -> EvalResult:
    """Run a single task and return result."""
    task_id = task.get("id", "unknown")
    task_out = out_dir / task_id
    task_out.mkdir(parents=True, exist_ok=True)
    
    try:
        result = run_task(
            task=task,
            seed=seed,
            out_dir=task_out,
            db_path=db_path,
        )
        
        return EvalResult(
            task_id=task_id,
            success=result["success"],
            reward=result["reward"],
            arms=result["arms"],
            completed_steps=result["completed_steps"],
            total_steps=result["total_steps"],
            wall_time=result["wall_time"],
            seed=seed,
        )
    except Exception as e:
        return EvalResult(
            task_id=task_id,
            success=False,
            reward=-1.0,
            arms={},
            completed_steps=0,
            total_steps=0,
            wall_time=0.0,
            seed=seed,
            error=str(e),
        )


def run_batch(
    tasks_path: str,
    out_dir: Path,
    db_path: str,
    workers: int = 1,
    base_seed: int = 0,
    limit: int | None = None,
) -> tuple[list[EvalResult], EvalSummary]:
    """
    Run batch evaluation.
    
    Returns (results, summary)
    """
    tasks = list(load_tasks(tasks_path))
    if limit:
        tasks = tasks[:limit]
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    results: list[EvalResult] = []
    start_time = time.time()
    
    if workers == 1:
        # Single-threaded for debugging
        for i, task in enumerate(tasks):
            print(f"[{i+1}/{len(tasks)}] Running {task.get('id', 'unknown')}...")
            result = run_single_task(
                task=task,
                seed=base_seed + i,
                out_dir=out_dir,
                db_path=db_path,
            )
            results.append(result)
            print(f"  -> {'✓' if result.success else '✗'} reward={result.reward:.3f}")
    else:
        # Parallel execution
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for i, task in enumerate(tasks):
                future = executor.submit(
                    run_single_task,
                    task=task,
                    seed=base_seed + i,
                    out_dir=out_dir,
                    db_path=db_path,
                )
                futures[future] = task.get("id", f"task_{i}")
            
            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    status = "✓" if result.success else "✗"
                    print(f"[{len(results)}/{len(tasks)}] {task_id}: {status} reward={result.reward:.3f}")
                except Exception as e:
                    print(f"[{len(results)}/{len(tasks)}] {task_id}: ERROR {e}")
                    results.append(EvalResult(
                        task_id=task_id,
                        success=False,
                        reward=-1.0,
                        arms={},
                        completed_steps=0,
                        total_steps=0,
                        wall_time=0.0,
                        seed=base_seed,
                        error=str(e),
                    ))
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Compute summary
    successful = sum(1 for r in results if r.success)
    mean_reward = sum(r.reward for r in results) / len(results) if results else 0.0
    
    summary = EvalSummary(
        total_tasks=len(results),
        successful=successful,
        failed=len(results) - successful,
        mean_reward=mean_reward,
        success_rate=successful / len(results) if results else 0.0,
        total_time=total_time,
        tasks_per_second=len(results) / total_time if total_time > 0 else 0.0,
    )
    
    return results, summary


def save_results(
    results: list[EvalResult],
    summary: EvalSummary,
    out_dir: Path,
) -> None:
    """Save results to files."""
    # Individual results
    with open(out_dir / "results.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(asdict(r), sort_keys=True) + "\n")
    
    # Summary
    with open(out_dir / "summary.json", "w") as f:
        json.dump(asdict(summary), f, indent=2)
    
    # Arm statistics
    arm_counts: dict[str, dict[str, int]] = {}
    arm_rewards: dict[str, dict[str, list[float]]] = {}
    
    for r in results:
        for cat, arm in r.arms.items():
            if cat not in arm_counts:
                arm_counts[cat] = {}
                arm_rewards[cat] = {}
            if arm not in arm_counts[cat]:
                arm_counts[cat][arm] = 0
                arm_rewards[cat][arm] = []
            arm_counts[cat][arm] += 1
            arm_rewards[cat][arm].append(r.reward)
    
    arm_stats = {}
    for cat in arm_counts:
        arm_stats[cat] = {}
        for arm in arm_counts[cat]:
            rewards = arm_rewards[cat][arm]
            arm_stats[cat][arm] = {
                "count": arm_counts[cat][arm],
                "mean_reward": sum(rewards) / len(rewards) if rewards else 0,
                "min_reward": min(rewards) if rewards else 0,
                "max_reward": max(rewards) if rewards else 0,
            }
    
    with open(out_dir / "arm_stats.json", "w") as f:
        json.dump(arm_stats, f, indent=2)


def print_summary(summary: EvalSummary, out_dir: Path) -> None:
    """Print evaluation summary."""
    print()
    print("=" * 50)
    print("EVALUATION SUMMARY")
    print("=" * 50)
    print(f"Total tasks:     {summary.total_tasks}")
    print(f"Successful:      {summary.successful}")
    print(f"Failed:          {summary.failed}")
    print(f"Success rate:    {summary.success_rate:.1%}")
    print(f"Mean reward:     {summary.mean_reward:.3f}")
    print(f"Total time:      {summary.total_time:.1f}s")
    print(f"Tasks/second:    {summary.tasks_per_second:.2f}")
    print(f"Results saved:   {out_dir}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="SWE-bench style batch evaluator")
    parser.add_argument("--tasks", required=True, help="Path to tasks JSONL")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers")
    parser.add_argument("--out", default="./eval_results", help="Output directory")
    parser.add_argument("--db", default="./outcomes.sqlite", help="Outcome DB path")
    parser.add_argument("--seed", type=int, default=0, help="Base random seed")
    parser.add_argument("--limit", type=int, help="Max tasks to run")
    args = parser.parse_args()
    
    out_dir = Path(args.out)
    
    print(f"Loading tasks from: {args.tasks}")
    print(f"Workers: {args.workers}")
    print(f"Output: {out_dir}")
    print()
    
    results, summary = run_batch(
        tasks_path=args.tasks,
        out_dir=out_dir,
        db_path=args.db,
        workers=args.workers,
        base_seed=args.seed,
        limit=args.limit,
    )
    
    save_results(results, summary, out_dir)
    print_summary(summary, out_dir)


if __name__ == "__main__":
    main()
