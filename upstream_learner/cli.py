from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from rfsn.types import ProposedAction
from .outcome_db import OutcomeDB
from .propose import Candidate, select_candidate, record_outcome


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="outcomes.sqlite3")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_pick = sub.add_parser("pick")
    p_pick.add_argument("--task", required=True, help="task json")
    p_pick.add_argument("--candidates", required=True, help="candidates json list")

    p_rec = sub.add_parser("record")
    p_rec.add_argument("--task", required=True)
    p_rec.add_argument("--arm", required=True)
    p_rec.add_argument("--reward", type=float, required=True)
    p_rec.add_argument("--meta", default="{}")

    args = ap.parse_args()
    db = OutcomeDB(args.db)

    if args.cmd == "pick":
        task = json.loads(open(args.task, "rb").read().decode("utf-8"))
        raw = json.loads(open(args.candidates, "rb").read().decode("utf-8"))
        candidates = [
            Candidate(arm_key=o["arm_key"], action=ProposedAction(**o["action"]))
            for o in raw
        ]
        action = select_candidate(db=db, task=task, candidates=candidates, seed=0)
        print(json.dumps(asdict(action), ensure_ascii=False, indent=2))
        return

    if args.cmd == "record":
        task = json.loads(open(args.task, "rb").read().decode("utf-8"))
        meta = json.loads(args.meta)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record_outcome(db=db, task=task, arm_key=args.arm, reward=args.reward, meta=meta, ts_utc=ts)
        print("OK")
        return
