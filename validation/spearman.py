"""Spearman rank correlation, written out so ties and degenerate inputs are explicit.

Ranks are average ranks (ties share the mean of the positions they occupy), and rho is the
Pearson correlation of the two rank vectors, which is the standard tie-corrected definition.
Fewer than two pairs, or a constant rank vector, gives None with the reason, never a number.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SpearmanResult:
    rho: float | None
    n: int
    reason: str | None = None


def average_ranks(values: Sequence[float]) -> list[float]:
    """Rank 1 for the smallest value; tied values share the average of their positions."""
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j) / 2 + 1  # positions are 1-based
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> SpearmanResult:
    if len(x) != len(y):
        raise ValueError(f"length mismatch: {len(x)} vs {len(y)}")
    n = len(x)
    if n < 2:
        return SpearmanResult(rho=None, n=n, reason="fewer than two pairs")
    rx = average_ranks(x)
    ry = average_ranks(y)
    mx = sum(rx) / n
    my = sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return SpearmanResult(rho=None, n=n, reason="constant ranks on one side")
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    return SpearmanResult(rho=sxy / math.sqrt(sxx * syy), n=n)
