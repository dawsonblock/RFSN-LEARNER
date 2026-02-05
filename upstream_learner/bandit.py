# upstream_learner/bandit.py
"""
Multi-armed bandit algorithms for learning.

Supports:
- Thompson Sampling (default)
- UCB1 (Upper Confidence Bound)
- Epsilon-greedy
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class BanditAlgorithm(str, Enum):
    THOMPSON = "thompson"
    UCB1 = "ucb1"
    EPSILON_GREEDY = "epsilon_greedy"


@dataclass(frozen=True)
class ArmStats:
    """Statistics for a single arm."""

    arm_key: str
    n: int
    mean: float
    variance: float = 1.0  # For UCB

    @property
    def ucb_score(self) -> float:
        """UCB1 score: mean + sqrt(2*ln(total)/n)"""
        # total approximated; caller should use ucb_select instead
        if self.n == 0:
            return float("inf")
        return self.mean + math.sqrt(2 * math.log(100) / self.n)


def thompson_select(
    candidates: Iterable[str],
    stats: list[ArmStats],
    *,
    seed: int = 0,
) -> str:
    """
    Thompson sampling with Normal-Normal approximation.

    Sample ~ Normal(mean, 1/sqrt(max(1,n))) and pick best.
    Arms with no history get mean=0, n=0 => high variance => exploration.
    """
    rng = random.Random(seed)
    by_key = {s.arm_key: s for s in stats}

    best_key = None
    best_sample = -float("inf")

    for k in candidates:
        s = by_key.get(k)
        if s is None:
            mu, n = 0.0, 0
        else:
            mu, n = s.mean, s.n

        sigma = 1.0 / math.sqrt(max(1, n))
        sample = rng.gauss(mu, sigma)
        if sample > best_sample:
            best_sample = sample
            best_key = k

    assert best_key is not None
    return best_key


def ucb_select(
    candidates: Iterable[str],
    stats: list[ArmStats],
    *,
    total_pulls: int = 0,
    c: float = 2.0,
) -> str:
    """
    UCB1 (Upper Confidence Bound) selection.

    Score = mean + c * sqrt(ln(total) / n)

    Args:
        candidates: Available arm keys
        stats: Historical statistics per arm
        total_pulls: Total number of pulls across all arms
        c: Exploration constant (higher = more exploration)

    Returns:
        Selected arm key
    """
    by_key = {s.arm_key: s for s in stats}

    if total_pulls == 0:
        total_pulls = sum(s.n for s in stats) or 1

    best_key = None
    best_score = -float("inf")

    for k in candidates:
        s = by_key.get(k)
        if s is None or s.n == 0:
            # Unexplored arm gets infinite score
            return k

        exploration = c * math.sqrt(math.log(total_pulls) / s.n)
        score = s.mean + exploration

        if score > best_score:
            best_score = score
            best_key = k

    assert best_key is not None
    return best_key


def epsilon_greedy_select(
    candidates: Iterable[str],
    stats: list[ArmStats],
    *,
    epsilon: float = 0.1,
    seed: int = 0,
) -> str:
    """
    Epsilon-greedy selection.

    With probability epsilon, choose random arm.
    Otherwise, choose arm with highest mean reward.

    Args:
        candidates: Available arm keys
        stats: Historical statistics per arm
        epsilon: Exploration probability (0.0-1.0)
        seed: Random seed

    Returns:
        Selected arm key
    """
    rng = random.Random(seed)
    cand_list = list(candidates)

    if rng.random() < epsilon:
        # Explore: random choice
        return rng.choice(cand_list)

    # Exploit: best mean
    by_key = {s.arm_key: s for s in stats}

    best_key = cand_list[0]
    best_mean = -float("inf")

    for k in cand_list:
        s = by_key.get(k)
        mean = s.mean if s else 0.0
        if mean > best_mean:
            best_mean = mean
            best_key = k

    return best_key


def select_arm(
    candidates: Iterable[str],
    stats: list[ArmStats],
    *,
    algorithm: BanditAlgorithm = BanditAlgorithm.THOMPSON,
    seed: int = 0,
    **kwargs,
) -> str:
    """
    Unified arm selection with configurable algorithm.

    Args:
        candidates: Available arm keys
        stats: Historical statistics per arm
        algorithm: Which bandit algorithm to use
        seed: Random seed (for Thompson/epsilon-greedy)
        **kwargs: Algorithm-specific parameters
            - epsilon: for epsilon_greedy (default 0.1)
            - c: for UCB1 exploration constant (default 2.0)
            - total_pulls: for UCB1 (auto-computed if not provided)

    Returns:
        Selected arm key
    """
    if algorithm == BanditAlgorithm.THOMPSON:
        return thompson_select(candidates, stats, seed=seed)
    elif algorithm == BanditAlgorithm.UCB1:
        return ucb_select(
            candidates,
            stats,
            total_pulls=kwargs.get("total_pulls", 0),
            c=kwargs.get("c", 2.0),
        )
    elif algorithm == BanditAlgorithm.EPSILON_GREEDY:
        return epsilon_greedy_select(
            candidates,
            stats,
            epsilon=kwargs.get("epsilon", 0.1),
            seed=seed,
        )
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def estimate_regret(
    stats: list[ArmStats],
    total_pulls: int = 0,
) -> float:
    """
    Estimate cumulative regret.

    Regret = sum of (best_mean - arm_mean) * arm_pulls

    Returns:
        Estimated cumulative regret
    """
    if not stats:
        return 0.0

    best_mean = max(s.mean for s in stats)
    regret = 0.0

    for s in stats:
        regret += (best_mean - s.mean) * s.n

    return regret
