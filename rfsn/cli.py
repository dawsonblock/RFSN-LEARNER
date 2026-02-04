from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .gate import gate
from .ledger import AppendOnlyLedger
from .types import ProposedAction, StateSnapshot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="rfsn_ledger.jsonl")
    ap.add_argument("--state", required=True, help="Path to JSON StateSnapshot")
    ap.add_argument("--action", required=True, help="Path to JSON ProposedAction")
    ap.add_argument("--allow-commands", action="store_true")
    args = ap.parse_args()

    with open(args.state, "rb") as f:
        state = StateSnapshot(**json.loads(f.read().decode("utf-8")))
    with open(args.action, "rb") as f:
        action = ProposedAction(**json.loads(f.read().decode("utf-8")))

    decision = gate(state, action, allow_commands=args.allow_commands)
    led = AppendOnlyLedger(args.ledger)
    led.append(state, decision.normalized_action or action, decision.reason)

    print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))
