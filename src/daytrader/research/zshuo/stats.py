"""Binomial proportion intervals (spec §4). Pure stdlib — no scipy.

Wilson score intervals rather than the normal approximation: the audit's
strata (FT+/-, line-age buckets, overnight) run thin, and Wald intervals
misbehave badly at small n and at proportions near 0 or 1.

Differences between two independent proportions use Newcombe's method 10,
which propagates each group's Wilson bounds instead of pooling a standard
error, and so inherits that small-sample behaviour: the interval stays inside
[-1, 1] and does not collapse when one arm is degenerate.
"""
from __future__ import annotations

import math

NAN = float("nan")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Return (point estimate, lower bound, upper bound). n == 0 -> all NaN."""
    if n <= 0:
        return NAN, NAN, NAN
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return p, center - margin, center + margin


def diff_ci(k1: int, n1: int, k2: int, n2: int,
            z: float = 1.96) -> tuple[float, float, float]:
    """Newcombe method 10 interval for p1 - p2. Returns (diff, lower, upper)."""
    p1, l1, u1 = wilson(k1, n1, z)
    p2, l2, u2 = wilson(k2, n2, z)
    if math.isnan(p1) or math.isnan(p2):
        return NAN, NAN, NAN
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, lo, hi
