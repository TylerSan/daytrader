"""Line detection and lifecycle (spec §2, §3 as revised 2026-09-14 (二)).

Emits the event group and both control groups as one homogeneous table so the
downstream race metric and statistics treat all three alike.

Three line kinds
----------------
``gap``     the audited object: the extremum of a swing that a *body* (close)
            broke through. direction = +1 when a swing **H** was broken upward
            (the line is now support, the bounce points up), -1 for a broken
            swing L.
``phantom`` C1, a **time-displaced placebo**. Drawn in a second pass: for each
            gap we keep its approach geometry (distance D from the breaking
            close to the line, direction, RTH flag) and re-anchor it on a
            random bar ``t_r`` in a *different* trading day with the same RTH
            flag and outside any blackout, at ``close[t_r] - direction * D``.
            Geometry is matched, structure is destroyed. The earlier
            "offset toward the price side" design is void: at a fixed instant
            it degenerates into the gap line itself and produced ~89% drive-by
            same-bar touches.
``plain``   C2: a confirmed swing that was *never* body-broken and is
            wick-tested. An unbroken swing H is resistance (direction -1), an
            unbroken swing L support (+1) — the mirror of the gap convention.

Contract
--------
* No lookahead. A swing enters the active set only at ``confirmed_idx``; the
  only forward-looking field is ``follow_through``, which by definition reads
  the bar after creation and is a covariate, never a creation condition. It is
  ``None`` — unknown, not FT- — when the break lands on the last bar.
* A gap is created on break bar ``t``; touch detection starts at ``t + 1``, so
  the break bar's own wick can never test its own line. Same for a placebo at
  its anchor.
* **Touch requires containment**: ``low <= price <= high``. A bar that leaps
  clean over the line without trading at it is not a test — the line is
  **voided** and yields no event (``touched_idx`` stays NaN). All three kinds
  obey this; for ``plain`` it is unreachable in practice, since a bar wholly
  beyond an unbroken swing also closes beyond it and is caught as a break one
  step earlier.
* Touch is one-shot; each swing yields at most one plain event ever. A body
  break on bar ``t`` pre-empts a plain test on that same bar.
* Expiry uses CME trading-day ordinals (``session_date``, see bars.py), not bar
  counts: a line dies unused once ``ordinal(t) - ordinal(created) >=
  expiry_days``. The same clock applies to plain lines from their
  ``confirmed_idx``, so the C2 control cannot quietly outlive the gaps it is
  compared against (report the count it removes — spec §3 修订 (二)).
* Rollover blackout is **two-sided**: a mask covering ``rollover_blackout_bars``
  bars on each side of every rollover bar is pre-computed from the contract
  calendar (calendar foresight, not price foresight). Inside the mask no line
  is created, no swing is confirmed, no touch is recorded and no event fires;
  swings whose ``idx`` or ``confirmed_idx`` falls in the mask are dropped
  outright. At the rollover bar itself every open line and active swing is
  discarded, and a rollover between a line's creation and its touch voids it.

Output rows
-----------
One row per line, columns fixed by ``LINE_COLUMNS``. ``gap`` and ``phantom``
rows are written at creation and therefore include lines that were never
touched (expired, gapped through, or killed by a rollover), with
``touched_idx`` NaN. ``plain`` rows exist only where a test actually happened,
since an untouched swing is never materialised as a line — so plain rows are
always events, while gap/phantom rows are creations. Events are exactly the
rows where ``touched_idx`` is not null.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .config import AuditConfig
from .swings import find_swings

LINE_COLUMNS = ["line_id", "price", "direction", "kind", "created_idx",
                "swing_idx", "follow_through", "touched_idx"]

#: Disposition channel (spec §3 修订 (二): the voided / expired counts are a
#: reporting obligation, since lines that die unused never appear as rows).
COUNTER_KINDS = ("gap", "phantom", "plain")
COUNTER_FIELDS = ("created", "touched", "voided_gap_through", "voided_rollover",
                  "expired", "open_at_end", "skipped_no_anchor",
                  "expired_at_touch")

_OPEN, _TOUCH, _THROUGH = "open", "touch", "through"


def _state(direction: int, price: float, low: float, high: float) -> str:
    """Containment test: a line is tested only if the bar trades at its price."""
    if low <= price <= high:
        return _TOUCH
    if high < price if direction > 0 else low > price:
        return _THROUGH  # leapt clean over the line without trading at it
    return _OPEN


def blackout_mask(rollover: np.ndarray, bars: int) -> np.ndarray:
    """Two-sided mask: `bars` bars each side of every contract rollover."""
    mask = np.zeros(len(rollover), dtype=bool)
    for t in np.flatnonzero(rollover):
        mask[max(0, t - bars):t + bars + 1] = True
    return mask


def new_counters() -> dict[str, dict[str, int]]:
    return {kind: dict.fromkeys(COUNTER_FIELDS, 0) for kind in COUNTER_KINDS}


def scan_lines(df: pd.DataFrame, cfg: AuditConfig, *, with_counters: bool = False):
    """Detect every line. ``with_counters`` also returns the disposition channel.

    The returned frame is unchanged by the flag; the counters explain what
    happened to the lines that produced no event — expired, gapped through,
    killed by a rollover, still open at the end of the frame — plus the plain
    (C2) candidates that the expiry clock removed at their touch bar, which
    spec §3 修订 (二) requires the report to disclose.
    """
    n = len(df)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    rth = df["rth"].to_numpy(dtype=bool)
    rollover = df["rollover"].to_numpy(dtype=bool)
    session_ord = pd.factorize(df["session_date"])[0]
    masked = blackout_mask(rollover, cfg.rollover_blackout_bars)

    records: list[dict] = []
    counters = new_counters()

    def _emit(price, direction, kind, created_idx, swing_idx, follow_through):
        counters[kind]["created"] += 1
        records.append({"line_id": len(records), "price": float(price),
                        "direction": int(direction), "kind": kind,
                        "created_idx": int(created_idx),
                        "swing_idx": int(swing_idx),
                        "follow_through": follow_through,
                        "touched_idx": None})
        return len(records) - 1

    # ---- pass 1: gap lines and their C2 counterparts ----------------------
    swings = find_swings(df["high"], df["low"], cfg.k)
    by_confirm: dict[int, list] = defaultdict(list)
    for sw in swings.itertuples(index=False):
        if masked[int(sw.idx)] or masked[int(sw.confirmed_idx)]:
            continue  # formed or confirmed under rollover price contamination
        by_confirm[int(sw.confirmed_idx)].append(sw)

    open_lines: list[dict] = []   # {"rec": index into records, price, direction}
    active: list = []             # confirmed, unbroken swings
    tested: set[int] = set()      # swing idx that already produced a plain event
    stale_plain: set[int] = set()  # swing idx dropped by the C2 expiry clock

    for t in range(n):
        if rollover[t]:
            counters["gap"]["voided_rollover"] += len(open_lines)
            open_lines.clear()
            active.clear()
            tested.clear()
        if masked[t]:
            continue  # no creation, no touch, no event, no confirmation

        # 1. expire, then test every line opened on an earlier bar
        survivors = []
        for ln in open_lines:
            created = records[ln["rec"]]["created_idx"]
            if session_ord[t] - session_ord[created] >= cfg.expiry_days:
                counters["gap"]["expired"] += 1
                continue  # stale line, dies without an event
            state = _state(ln["direction"], ln["price"], low[t], high[t])
            if state is _TOUCH:
                records[ln["rec"]]["touched_idx"] = t
                counters["gap"]["touched"] += 1
            elif state is _OPEN:
                survivors.append(ln)
            else:
                counters["gap"]["voided_gap_through"] += 1
        open_lines = survivors

        # 2. swings become usable only once confirmed
        active.extend(by_confirm.get(t, ()))

        # 3. body breaks create the audited gap lines
        unbroken = []
        for sw in active:
            broke = close[t] > sw.price if sw.kind == "H" else close[t] < sw.price
            if not broke:
                unbroken.append(sw)
                continue
            direction = 1 if sw.kind == "H" else -1
            follow = (None if t + 1 >= n
                      else bool(direction * (close[t + 1] - sw.price) > 0))
            rec = _emit(sw.price, direction, "gap", t, sw.idx, follow)
            open_lines.append({"rec": rec, "price": float(sw.price),
                               "direction": direction})
        active = unbroken

        # 4. wick tests of surviving swings are the C2 control
        alive = []
        for sw in active:
            direction = -1 if sw.kind == "H" else 1
            state = _state(direction, sw.price, low[t], high[t])
            if state is _THROUGH:
                if int(sw.idx) not in tested:
                    counters["plain"]["voided_gap_through"] += 1
                continue  # price never traded at it; drop, same as a gap line
            alive.append(sw)
            if sw.idx in tested or t <= sw.confirmed_idx or state is not _TOUCH:
                continue
            if session_ord[t] - session_ord[sw.confirmed_idx] >= cfg.expiry_days:
                if int(sw.idx) not in stale_plain:
                    stale_plain.add(int(sw.idx))
                    counters["plain"]["expired_at_touch"] += 1
                continue
            tested.add(int(sw.idx))
            rec = _emit(sw.price, direction, "plain", sw.confirmed_idx, sw.idx,
                        None)
            records[rec]["touched_idx"] = t
            counters["plain"]["touched"] += 1
        active = alive

    counters["gap"]["open_at_end"] = len(open_lines)

    # ---- pass 2: time-displaced placebo for every gap line ----------------
    rng = np.random.default_rng(cfg.seed)
    pools = {flag: np.flatnonzero((rth == flag) & ~masked) for flag in (False, True)}
    for gap in [r for r in records if r["kind"] == "gap"]:
        t = gap["created_idx"]
        pool = pools[bool(rth[t])]
        pool_ord = session_ord[pool]
        same_day = np.searchsorted(pool_ord, session_ord[t], side="left")
        span = (np.searchsorted(pool_ord, session_ord[t], side="right")
                - same_day)
        if len(pool) - span == 0:
            counters["phantom"]["skipped_no_anchor"] += 1
            continue  # no admissible anchor a trading day away
        draw = int(rng.integers(len(pool) - span))
        anchor = int(pool[draw if draw < same_day else draw + span])
        distance = abs(close[t] - gap["price"])
        rec = _emit(close[anchor] - gap["direction"] * distance,
                    gap["direction"], "phantom", anchor, gap["swing_idx"], None)
        touched, fate = _first_touch(
            anchor, records[rec]["price"], gap["direction"], n, cfg,
            low, high, rollover, masked, session_ord)
        records[rec]["touched_idx"] = touched
        counters["phantom"][fate] += 1

    out = pd.DataFrame(records, columns=LINE_COLUMNS)
    if len(out):
        out = out.astype({"touched_idx": float, "follow_through": object})
    return (out, counters) if with_counters else out


def _first_touch(created, price, direction, n, cfg, low, high, rollover,
                 masked, session_ord):
    """Walk a placebo line forward under the same lifecycle rules as a gap.

    Returns ``(touched_idx | None, fate)`` where fate is the counter field
    naming how the line ended.
    """
    for t in range(created + 1, n):
        if rollover[t]:
            return None, "voided_rollover"  # contract change voids the line
        if session_ord[t] - session_ord[created] >= cfg.expiry_days:
            return None, "expired"
        if masked[t]:
            continue
        state = _state(direction, price, low[t], high[t])
        if state is _TOUCH:
            return t, "touched"
        if state is _THROUGH:
            return None, "voided_gap_through"
    return None, "open_at_end"
