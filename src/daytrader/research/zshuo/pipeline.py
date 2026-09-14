"""Event assembly, sampling discipline and the §4 verdict (spec §3, §4).

Turns the homogeneous line table from :mod:`gaps` into one event row per first
touch, scores each with the symmetric race of :mod:`race`, applies the V11
sampling discipline (non-overlap), and reduces the result to the bounce-priority
rates the verdict rests on.

Contract
--------
* An **event** is a line whose ``touched_idx`` is set; ``t0`` is that bar.
* ``line_age_bars = touched_idx - created_idx``. Its meaning differs by group —
  time since the *break* for gap, time since *confirmation* for plain — so the
  strata are comparable only bucket-by-bucket, never pooled (spec §3 修订 (二)).
* Auxiliary displacements are measured from the **line price**, signed so that
  the claimed bounce direction is positive, in ticks:
  ``fwd_ret_k`` at ``t0 + k`` (NaN past the end of the frame), and MFE/MAE over
  ``[t0 + 1, race_end]``. ``race_end`` mirrors race.py: the bar the contest was
  decided on, else the last bar of the timeout window. A race that resolved on
  the touch bar itself leaves an empty window and therefore NaN excursions —
  there is no post-event path to measure.
* ``resolved`` = bounce | penetrate. ``indeterminate`` (both targets on one bar)
  and ``timeout`` are excluded from the headline rate and reported separately;
  the bounds table re-admits indeterminate at both extremes, which is what the
  修订 (三) robustness gate is computed on.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import AuditConfig
from .gaps import scan_lines
from .race import run_race
from .stats import diff_ci, wilson

FWD_HORIZONS = (6, 12, 24)
EVENT_COLUMNS = ["line_id", "price", "direction", "kind", "created_idx",
                 "swing_idx", "follow_through", "touched_idx", "outcome",
                 "rth", "line_age_bars", "race_end_idx",
                 *(f"fwd_ret_{k}" for k in FWD_HORIZONS),
                 "mfe_ticks", "mae_ticks"]
OUTCOMES = ("bounce", "penetrate", "indeterminate", "timeout")
KINDS = ("gap", "phantom", "plain")

#: Indeterminate handling rules for the bounds table (spec 修订 (三)).
RULES = ("resolved", "all_bounce", "all_penetrate")


def _race_end(high, low, t0, price, direction, half, timeout, n) -> int:
    """Bar on which the race concluded. Mirrors race.run_race's scan order."""
    bounce_t = price + direction * half
    pen_t = price - direction * half
    up_is_bounce = direction > 0
    hit_pen = low[t0] <= pen_t if up_is_bounce else high[t0] >= pen_t
    if hit_pen:
        return t0  # touch bar resolves as penetrate or indeterminate
    last = min(t0 + timeout, n - 1)
    for i in range(t0 + 1, last + 1):
        hit_b = high[i] >= bounce_t if up_is_bounce else low[i] <= bounce_t
        hit_p = low[i] <= pen_t if up_is_bounce else high[i] >= pen_t
        if hit_b or hit_p:
            return i
    return last


def build_events(df: pd.DataFrame, cfg: AuditConfig,
                 lines: pd.DataFrame | None = None) -> pd.DataFrame:
    """One scored row per first touch, with the spec §3 auxiliary metrics."""
    if lines is None:
        lines = scan_lines(df, cfg)
    ev = lines[lines["touched_idx"].notna()].copy() if len(lines) else lines.copy()
    if not len(ev):
        return pd.DataFrame(columns=EVENT_COLUMNS)

    ev["touched_idx"] = ev["touched_idx"].astype(int)
    n = len(df)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    rth = df["rth"].to_numpy(dtype=bool)
    race_df = df[["high", "low"]]
    half = cfg.x_ticks * cfg.tick_size
    tick = cfg.tick_size

    t0s = ev["touched_idx"].to_numpy()
    prices = ev["price"].to_numpy(dtype=float)
    dirs = ev["direction"].to_numpy(dtype=int)

    outcomes, ends, mfe, mae = [], [], [], []
    for t0, price, direction in zip(t0s, prices, dirs):
        window = race_df.iloc[t0:min(t0 + cfg.race_timeout_bars, n - 1) + 1]
        outcomes.append(run_race(window, 0, price, direction, cfg.x_ticks,
                                 tick, cfg.race_timeout_bars))
        end = _race_end(high, low, t0, price, direction, half,
                        cfg.race_timeout_bars, n)
        ends.append(end)
        if end < t0 + 1:
            mfe.append(np.nan)
            mae.append(np.nan)
            continue
        hi = high[t0 + 1:end + 1].max()
        lo = low[t0 + 1:end + 1].min()
        best, worst = (hi, lo) if direction > 0 else (lo, hi)
        mfe.append(direction * (best - price) / tick)
        mae.append(direction * (worst - price) / tick)

    ev["outcome"] = outcomes
    ev["race_end_idx"] = ends
    ev["rth"] = rth[t0s]
    ev["line_age_bars"] = t0s - ev["created_idx"].to_numpy(dtype=int)
    for k in FWD_HORIZONS:
        j = t0s + k
        inside = j < n
        vals = np.where(inside,
                        dirs * (close[np.minimum(j, n - 1)] - prices) / tick,
                        np.nan)
        ev[f"fwd_ret_{k}"] = vals
    ev["mfe_ticks"] = mfe
    ev["mae_ticks"] = mae
    return ev[EVENT_COLUMNS].reset_index(drop=True)


def apply_nonoverlap(ev: pd.DataFrame, min_gap: int) -> pd.DataFrame:
    """Spec §3 sampling discipline: within (kind, direction), events closer
    than ``min_gap`` bars collapse to the earlier one."""
    if not len(ev):
        return ev
    keep: list[int] = []
    for _, grp in ev.groupby(["kind", "direction"], sort=False):
        grp = grp.sort_values("touched_idx", kind="mergesort")
        last = None
        for pos, t in zip(grp.index, grp["touched_idx"].to_numpy()):
            if last is None or t - last >= min_gap:
                keep.append(pos)
                last = t
    return ev.loc[sorted(keep)].reset_index(drop=True)


def placebo_same_bar_share(ev: pd.DataFrame) -> float:
    """Share of placebo events landing on a bar that also carries a gap event.

    Reporting obligation of spec §3 修订 (二): the control is only as
    independent as this number is small.
    """
    phantom = ev[ev["kind"] == "phantom"]
    if not len(phantom):
        return float("nan")
    gap_bars = set(ev.loc[ev["kind"] == "gap", "touched_idx"])
    return float(phantom["touched_idx"].isin(gap_bars).mean())


def anchor_reuse_share(lines: pd.DataFrame) -> float:
    """Share of placebo draws that landed on an already-used anchor bar.

    ``1 - unique_anchors / draws``: the excess, not the size of the collided
    groups, so a bar drawn twice contributes one reuse. Placebo lines sharing
    an anchor share a price path, so the control is not fully independent.
    """
    phantom = lines[lines["kind"] == "phantom"]
    if not len(phantom):
        return float("nan")
    return float(1.0 - phantom["created_idx"].nunique() / len(phantom))


def opposite_direction_same_bar_share(ev: pd.DataFrame, kind: str) -> float:
    """Share of events of ``kind`` whose touch bar also carries an event of the
    same kind in the opposite direction: two races reading one bar's H and L in
    opposite senses, so those two rows are not independent draws."""
    sub = ev[ev["kind"] == kind]
    if not len(sub):
        return float("nan")
    up = set(sub.loc[sub["direction"] > 0, "touched_idx"])
    down = set(sub.loc[sub["direction"] < 0, "touched_idx"])
    clash = up & down
    return float(sub["touched_idx"].isin(clash).mean())


def summarize(ev: pd.DataFrame) -> pd.DataFrame:
    """Per kind: outcome counts, resolved n, bounce count, rate and Wilson CI."""
    rows = []
    for kind in KINDS:
        sub = ev[ev["kind"] == kind]
        counts = {o: int((sub["outcome"] == o).sum()) for o in OUTCOMES}
        k, n = counts["bounce"], counts["bounce"] + counts["penetrate"]
        rate, lo, hi = wilson(k, n)
        rows.append({"kind": kind, "n_events": len(sub), **counts,
                     "n_resolved": n, "bounce": k, "rate": rate,
                     "ci_lo": lo, "ci_hi": hi})
    return pd.DataFrame(rows).set_index("kind")


def rule_counts(ev: pd.DataFrame, kind: str, rule: str) -> tuple[int, int]:
    """(bounce, n) for one kind under an indeterminate-handling ``rule``."""
    sub = ev[ev["kind"] == kind]["outcome"]
    b = int((sub == "bounce").sum())
    p = int((sub == "penetrate").sum())
    i = int((sub == "indeterminate").sum())
    if rule == "resolved":
        return b, b + p
    if rule == "all_bounce":
        return b + i, b + p + i
    if rule == "all_penetrate":
        return b, b + p + i
    raise ValueError(f"unknown rule {rule!r}")


@dataclass(frozen=True)
class Bounds:
    """Bounce rate under both extreme readings of the indeterminate events."""
    n: int
    k_all_penetrate: int
    rate_all_penetrate: float
    k_all_bounce: int
    rate_all_bounce: float


def bounds_rates(ev: pd.DataFrame, kind: str) -> Bounds:
    k_lo, n = rule_counts(ev, kind, "all_penetrate")
    k_hi, _ = rule_counts(ev, kind, "all_bounce")
    rate = (lambda k: k / n if n else float("nan"))
    return Bounds(n, k_lo, rate(k_lo), k_hi, rate(k_hi))


# --------------------------------------------------------------- §4 verdict

MIN_EFFECT = 0.05  # spec §4: CONFIRMED needs +5 percentage points


def classify(gap: tuple[int, int], phantom: tuple[int, int],
             plain: tuple[int, int]) -> str:
    """Spec §4 four-state rule on (bounce, n) triples.

    "Higher than" means the Newcombe interval for the difference excludes 0 on
    the positive side; CONFIRMED additionally needs both effects >= +5pp.
    """
    d1, lo1, _ = diff_ci(gap[0], gap[1], phantom[0], phantom[1])
    d2, lo2, _ = diff_ci(gap[0], gap[1], plain[0], plain[1])
    if np.isnan(d1) or np.isnan(d2):
        return "UNDECIDED"
    above_c1 = lo1 > 0
    above_c2 = lo2 > 0
    if not above_c1:
        return "REFUTED"
    if not above_c2:
        return "PARTIAL"
    if d1 >= MIN_EFFECT and d2 >= MIN_EFFECT:
        return "CONFIRMED"
    return "UNDECIDED"


def verdict(ev: pd.DataFrame) -> dict:
    """Headline verdict with the 修订 (三) bounds-robustness gate.

    The §4 rule is evaluated three times: on resolved events only (the headline
    reading) and with every indeterminate event forced to bounce, then to
    penetrate. A decided verdict stands only if all three agree; otherwise it
    degrades to UNDECIDED and the resolved-only reading is reported as the
    tendency.

    修订 (三) names PARTIAL/REFUTED explicitly. The gate is applied to
    CONFIRMED as well: it can only ever be stricter, and a CONFIRMED that
    survives only one reading of the indeterminate events is exactly the kind
    of headline the revision exists to prevent.
    """
    by_rule = {rule: classify(*(rule_counts(ev, kind, rule) for kind in KINDS))
               for rule in RULES}
    main = by_rule["resolved"]
    robust = len(set(by_rule.values())) == 1
    final = main if (robust and main != "UNDECIDED") else "UNDECIDED"
    return {"verdict": final, "main": main, "robust": robust,
            "by_rule": by_rule,
            "tendency": None if final != "UNDECIDED" or main == "UNDECIDED"
            else main}


def effects(ev: pd.DataFrame, rule: str = "resolved") -> dict:
    """gap - phantom and gap - plain differences with Newcombe intervals."""
    c = {kind: rule_counts(ev, kind, rule) for kind in KINDS}
    return {
        "gap_minus_phantom": diff_ci(*c["gap"], *c["phantom"]),
        "gap_minus_plain": diff_ci(*c["gap"], *c["plain"]),
        "counts": c,
    }
