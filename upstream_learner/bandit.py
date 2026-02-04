from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ArmStats:
    arm_key: str
    n: int
    mean: float


def thompson_select(candidates: Iterable[str], stats: list[ArmStats], *, seed: int = 0) -> str:
    """
    Normal-normal Thompson sampling approximation:
    sample ~ Normal(mean, 1/sqrt(max(1,n))) and pick best.
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
