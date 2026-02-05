from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


SCHEMA_V1 = """
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

# V2: Extended schema for learning curves
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS outcomes_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  
  -- Core fields
  context_key TEXT NOT NULL,
  arm_key TEXT NOT NULL,
  reward REAL NOT NULL,
  ts_utc TEXT NOT NULL,
  
  -- Task identification
  task_id TEXT,
  run_id TEXT,
  seed INTEGER,
  
  -- Execution metrics
  wall_time_ms REAL,
  tool_calls INTEGER,
  gate_denials INTEGER,
  
  -- Test metrics
  tests_passed INTEGER,
  tests_failed INTEGER,
  tests_baseline_passed INTEGER,
  tests_baseline_failed INTEGER,
  
  -- Patch metrics
  patch_size_bytes INTEGER,
  files_changed INTEGER,
  
  -- Flexible metadata
  meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_outcomes_v2_context_arm
ON outcomes_v2(context_key, arm_key);

CREATE INDEX IF NOT EXISTS idx_outcomes_v2_task
ON outcomes_v2(task_id);

CREATE INDEX IF NOT EXISTS idx_outcomes_v2_ts
ON outcomes_v2(ts_utc);
"""


@dataclass(frozen=True)
class Outcome:
    context_key: str
    arm_key: str
    reward: float
    meta: Mapping[str, Any]


@dataclass
class RichOutcome:
    """Extended outcome with full metrics."""
    context_key: str
    arm_key: str
    reward: float
    ts_utc: str = ""
    
    # Task identification
    task_id: str = ""
    run_id: str = ""
    seed: int = 0
    
    # Execution metrics
    wall_time_ms: float = 0.0
    tool_calls: int = 0
    gate_denials: int = 0
    
    # Test metrics
    tests_passed: int = 0
    tests_failed: int = 0
    tests_baseline_passed: int = 0
    tests_baseline_failed: int = 0
    
    # Patch metrics
    patch_size_bytes: int = 0
    files_changed: int = 0
    
    # Extra metadata
    meta: dict[str, Any] = field(default_factory=dict)


class OutcomeDB:
    """
    Outcome storage with rich metrics for learning curves.
    
    Supports both V1 (legacy) and V2 (extended) schemas.
    """
    
    def __init__(self, path: str, use_v2: bool = True):
        self.path = path
        self.use_v2 = use_v2
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.path) as cx:
            cx.executescript(SCHEMA_V1)
            if self.use_v2:
                cx.executescript(SCHEMA_V2)

    def record(
        self,
        *,
        context_key: str,
        arm_key: str,
        reward: float,
        meta_json: str,
        ts_utc: str,
    ) -> None:
        """Record outcome to V1 table (backwards compatible)."""
        with sqlite3.connect(self.path) as cx:
            cx.execute(
                "INSERT INTO outcomes(context_key, arm_key, reward, meta_json, ts_utc) VALUES (?,?,?,?,?)",
                (context_key, arm_key, float(reward), meta_json, ts_utc),
            )

    def record_rich(self, outcome: RichOutcome) -> None:
        """Record rich outcome to V2 table."""
        if not self.use_v2:
            raise RuntimeError("V2 schema not enabled")
        
        ts = outcome.ts_utc or datetime.now(timezone.utc).isoformat()
        
        with sqlite3.connect(self.path) as cx:
            cx.execute(
                """
                INSERT INTO outcomes_v2 (
                    context_key, arm_key, reward, ts_utc,
                    task_id, run_id, seed,
                    wall_time_ms, tool_calls, gate_denials,
                    tests_passed, tests_failed, tests_baseline_passed, tests_baseline_failed,
                    patch_size_bytes, files_changed,
                    meta_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    outcome.context_key,
                    outcome.arm_key,
                    float(outcome.reward),
                    ts,
                    outcome.task_id,
                    outcome.run_id,
                    outcome.seed,
                    outcome.wall_time_ms,
                    outcome.tool_calls,
                    outcome.gate_denials,
                    outcome.tests_passed,
                    outcome.tests_failed,
                    outcome.tests_baseline_passed,
                    outcome.tests_baseline_failed,
                    outcome.patch_size_bytes,
                    outcome.files_changed,
                    json.dumps(outcome.meta, sort_keys=True, separators=(",", ":")),
                ),
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

    def learning_curve(
        self,
        *,
        arm_key: str | None = None,
        task_id: str | None = None,
        window: int = 10,
    ) -> list[tuple[int, float, float]]:
        """
        Get learning curve: (index, mean_reward, cumulative_mean).
        
        Uses V2 table with optional filtering.
        """
        if not self.use_v2:
            return []
        
        query = "SELECT reward FROM outcomes_v2"
        params: list[Any] = []
        conditions = []
        
        if arm_key:
            conditions.append("arm_key = ?")
            params.append(arm_key)
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"
        
        with sqlite3.connect(self.path) as cx:
            rows = cx.execute(query, params).fetchall()
        
        if not rows:
            return []
        
        rewards = [r[0] for r in rows]
        curve = []
        cumsum = 0.0
        
        for i, r in enumerate(rewards):
            cumsum += r
            
            # Windowed mean
            start = max(0, i - window + 1)
            window_rewards = rewards[start:i+1]
            window_mean = sum(window_rewards) / len(window_rewards)
            
            # Cumulative mean
            cum_mean = cumsum / (i + 1)
            
            curve.append((i, window_mean, cum_mean))
        
        return curve

    def arm_performance(self) -> dict[str, dict[str, float]]:
        """
        Get performance summary per arm.
        
        Returns: {arm_key: {count, mean, min, max, stddev}}
        """
        if not self.use_v2:
            return {}
        
        with sqlite3.connect(self.path) as cx:
            rows = cx.execute(
                """
                SELECT 
                    arm_key,
                    COUNT(*) as n,
                    AVG(reward) as mean,
                    MIN(reward) as min,
                    MAX(reward) as max
                FROM outcomes_v2
                GROUP BY arm_key
                ORDER BY mean DESC
                """
            ).fetchall()
        
        result = {}
        for arm_key, n, mean, min_r, max_r in rows:
            result[arm_key] = {
                "count": n,
                "mean": mean,
                "min": min_r,
                "max": max_r,
            }
        return result

    def recent_outcomes(self, limit: int = 100) -> list[RichOutcome]:
        """Get most recent outcomes from V2 table."""
        if not self.use_v2:
            return []
        
        with sqlite3.connect(self.path) as cx:
            rows = cx.execute(
                """
                SELECT 
                    context_key, arm_key, reward, ts_utc,
                    task_id, run_id, seed,
                    wall_time_ms, tool_calls, gate_denials,
                    tests_passed, tests_failed, tests_baseline_passed, tests_baseline_failed,
                    patch_size_bytes, files_changed,
                    meta_json
                FROM outcomes_v2
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        
        results = []
        for row in rows:
            meta = {}
            try:
                meta = json.loads(row[16]) if row[16] else {}
            except:
                pass
            
            results.append(RichOutcome(
                context_key=row[0],
                arm_key=row[1],
                reward=row[2],
                ts_utc=row[3],
                task_id=row[4] or "",
                run_id=row[5] or "",
                seed=row[6] or 0,
                wall_time_ms=row[7] or 0.0,
                tool_calls=row[8] or 0,
                gate_denials=row[9] or 0,
                tests_passed=row[10] or 0,
                tests_failed=row[11] or 0,
                tests_baseline_passed=row[12] or 0,
                tests_baseline_failed=row[13] or 0,
                patch_size_bytes=row[14] or 0,
                files_changed=row[15] or 0,
                meta=meta,
            ))
        
        return results
