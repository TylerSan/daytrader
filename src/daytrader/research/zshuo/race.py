"""Symmetric bounce-vs-penetration race around a touched line (spec §3).

The reaction metric is a 1:1 contest measured from the *line price*, not from
the touch bar's close: after the first touch at ``t0``, does price reach
``line + X ticks`` on the bounce side or ``line - X ticks`` on the penetration
side first?

Contract
--------
* ``bounce_dir`` is the direction the line is claimed to push price: +1 for a
  broken swing H (support), -1 for a broken swing L (resistance). The bounce
  target is ``line + dir * half`` and the penetration target
  ``line - dir * half``, so the two are equidistant by construction.
* Bar ``t0`` may resolve only as ``"penetrate"`` or ``"indeterminate"``. Its
  bounce side is unusable: the bar's range up to the moment of the touch was
  traversed *before* the event existed, so crediting it as a bounce would score
  pre-touch movement. A blow-through is different — unambiguous new information
  against the line — so it resolves immediately. But a t0 bar that reaches both
  targets is ``"indeterminate"``, not a penetration: calling it a penetration
  charged every group's widest touch bars to the penetration side, and the
  groups do not carry equally wide touch bars〔spec §3 修订 (二)〕.
* From ``t0 + 1`` onward both sides are live. A bar that reaches both targets
  is ``"indeterminate"`` (intrabar order is unknowable at 5m resolution) and is
  reported, not silently dropped. Otherwise the first side reached wins.
* Unresolved after ``timeout_bars`` bars (or at the end of the frame) is
  ``"timeout"``.
"""
from __future__ import annotations

import pandas as pd

Outcome = str  # "bounce" | "penetrate" | "indeterminate" | "timeout"


def run_race(df: pd.DataFrame, t0: int, line_price: float, bounce_dir: int,
             x_ticks: int, tick_size: float, timeout_bars: int) -> Outcome:
    half = x_ticks * tick_size
    bounce_target = line_price + bounce_dir * half
    pen_target = line_price - bounce_dir * half
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    def _reached(i: int, target: float, upward: bool) -> bool:
        return high[i] >= target if upward else low[i] <= target

    up_is_bounce = bounce_dir > 0
    # touch bar: penetration or indeterminate, never a bounce
    if _reached(t0, pen_target, not up_is_bounce):
        return ("indeterminate" if _reached(t0, bounce_target, up_is_bounce)
                else "penetrate")

    last = min(t0 + timeout_bars, len(df) - 1)
    for i in range(t0 + 1, last + 1):
        bounced = _reached(i, bounce_target, up_is_bounce)
        penetrated = _reached(i, pen_target, not up_is_bounce)
        if bounced and penetrated:
            return "indeterminate"
        if bounced:
            return "bounce"
        if penetrated:
            return "penetrate"
    return "timeout"
