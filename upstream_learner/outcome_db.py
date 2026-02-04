from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  context_key TEXT NOT NULL,
  arm_key TEXT NOT NULL,
  reward REAL NOT NULL,
  meta_json TEXT NOT NULL,
  ts_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outcomes_context_arm
ON outcomes(context_key, arm_key);
"""


@dataclass(frozen=True)
class Outcome:
    context_key: str
    arm_key: str
    reward: float
    meta: Mapping[str, Any]


class OutcomeDB:
    def __init__(self, path: str):
        self.path = path
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.path) as cx:
            cx.executescript(SCHEMA)

    def record(self, *, context_key: str, arm_key: str, reward: float, meta_json: str, ts_utc: str) -> None:
        with sqlite3.connect(self.path) as cx:
            cx.execute(
                "INSERT INTO outcomes(context_key, arm_key, reward, meta_json, ts_utc) VALUES (?,?,?,?,?)",
                (context_key, arm_key, float(reward), meta_json, ts_utc),
            )

    def summary(self, *, context_key: str) -> list[tuple[str, int, float]]:
        """
        Returns: [(arm_key, n, mean_reward), ...]
        """
        with sqlite3.connect(self.path) as cx:
            rows = cx.execute(
                """
                SELECT arm_key, COUNT(*), AVG(reward)
                FROM outcomes
                WHERE context_key = ?
                GROUP BY arm_key
                """,
                (context_key,),
            ).fetchall()
        return [(r[0], int(r[1]), float(r[2])) for r in rows]
