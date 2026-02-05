# upstream_learner/cli.py
"""
CLI for upstream learner operations.

Commands:
- pick: Select best arm/candidate using bandit
- record: Record outcome
- stats: Show arm statistics
- curve: Show learning curve
- export: Export data to JSON
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict

from rfsn.types import ProposedAction
from .outcome_db import OutcomeDB
from .propose import Candidate, select_candidate, record_outcome
from .analytics import LearningAnalytics


def cmd_pick(args, db: OutcomeDB) -> None:
    """Select best candidate."""
    task = json.loads(open(args.task, "rb").read().decode("utf-8"))
    raw = json.loads(open(args.candidates, "rb").read().decode("utf-8"))
    candidates = [
        Candidate(arm_key=o["arm_key"], action=ProposedAction(**o["action"]))
        for o in raw
    ]
    action = select_candidate(db=db, task=task, candidates=candidates, seed=0)
    print(json.dumps(asdict(action), ensure_ascii=False, indent=2))


def cmd_record(args, db: OutcomeDB) -> None:
    """Record outcome."""
    task = json.loads(open(args.task, "rb").read().decode("utf-8"))
    meta = json.loads(args.meta)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record_outcome(db=db, task=task, arm_key=args.arm, reward=args.reward, meta=meta, ts_utc=ts)
    print("OK")


def cmd_stats(args, db: OutcomeDB) -> None:
    """Show arm statistics."""
    analytics = LearningAnalytics(db)
    summary = analytics.experiment_summary()
    
    print("=" * 60)
    print("LEARNING STATISTICS")
    print("=" * 60)
    print(f"Total trials:     {summary.total_trials}")
    print(f"Unique arms:      {summary.unique_arms}")
    print(f"Best arm:         {summary.best_arm} (mean={summary.best_mean:.3f})")
    print(f"Worst arm:        {summary.worst_arm} (mean={summary.worst_mean:.3f})")
    print(f"Est. regret:      {summary.estimated_regret:.3f}")
    print()
    
    if args.verbose and summary.arms:
        print("ARM RANKINGS:")
        print("-" * 60)
        print(f"{'Arm':<30} {'Count':>8} {'Mean':>8} {'Min':>8} {'Max':>8}")
        print("-" * 60)
        for arm in summary.arms[:args.limit]:
            print(f"{arm.arm_key:<30} {arm.count:>8} {arm.mean_reward:>8.3f} {arm.min_reward:>8.3f} {arm.max_reward:>8.3f}")


def cmd_curve(args, db: OutcomeDB) -> None:
    """Show learning curve."""
    analytics = LearningAnalytics(db)
    curve = analytics.learning_curve(arm_key=args.arm, window=args.window)
    
    print(f"Learning curve for: {args.arm or 'all arms'}")
    print(f"Total points: {curve.total_count}")
    print(f"Final mean:   {curve.final_mean:.3f}")
    print(f"Converged:    {curve.is_converged()}")
    print()
    
    if args.verbose and curve.points:
        print("CURVE DATA (last 20 points):")
        print("-" * 40)
        print(f"{'Index':>6} {'Window':>10} {'Cumulative':>12}")
        print("-" * 40)
        for idx, window_mean, cum_mean in curve.points[-20:]:
            print(f"{idx:>6} {window_mean:>10.3f} {cum_mean:>12.3f}")


def cmd_export(args, db: OutcomeDB) -> None:
    """Export data to JSON."""
    analytics = LearningAnalytics(db)
    data = analytics.export_data(limit=args.limit)
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Exported to {args.output}")
    else:
        print(json.dumps(data, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Upstream Learner CLI")
    ap.add_argument("--db", default="outcomes.sqlite3", help="Database path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # pick
    p_pick = sub.add_parser("pick", help="Select best candidate")
    p_pick.add_argument("--task", required=True, help="Task JSON file")
    p_pick.add_argument("--candidates", required=True, help="Candidates JSON file")

    # record
    p_rec = sub.add_parser("record", help="Record outcome")
    p_rec.add_argument("--task", required=True, help="Task JSON file")
    p_rec.add_argument("--arm", required=True, help="Arm key")
    p_rec.add_argument("--reward", type=float, required=True, help="Reward value")
    p_rec.add_argument("--meta", default="{}", help="Metadata JSON")

    # stats
    p_stats = sub.add_parser("stats", help="Show statistics")
    p_stats.add_argument("-v", "--verbose", action="store_true", help="Show arm details")
    p_stats.add_argument("--limit", type=int, default=20, help="Max arms to show")

    # curve
    p_curve = sub.add_parser("curve", help="Show learning curve")
    p_curve.add_argument("--arm", help="Filter by arm key")
    p_curve.add_argument("--window", type=int, default=10, help="Window size")
    p_curve.add_argument("-v", "--verbose", action="store_true", help="Show curve data")

    # export
    p_export = sub.add_parser("export", help="Export data")
    p_export.add_argument("-o", "--output", help="Output file (stdout if not specified)")
    p_export.add_argument("--limit", type=int, default=1000, help="Max outcomes")

    args = ap.parse_args()
    db = OutcomeDB(args.db)

    if args.cmd == "pick":
        cmd_pick(args, db)
    elif args.cmd == "record":
        cmd_record(args, db)
    elif args.cmd == "stats":
        cmd_stats(args, db)
    elif args.cmd == "curve":
        cmd_curve(args, db)
    elif args.cmd == "export":
        cmd_export(args, db)


if __name__ == "__main__":
    main()
