"""Line detection and lifecycle (spec §2). Emits the event group and both
control groups as one homogeneous table so downstream stats treat them alike.

Three line kinds
----------------
``gap``     the audited object: the extremum of a swing that a *body* (close)
            broke through. direction = +1 when a swing **H** was broken upward
            (the line is now support, the bounce points up), -1 for a broken
            swing L.
``phantom`` C1 control, created on the same bar as its gap, at
            ``gap_price + direction * delta`` where delta is a seeded uniform
            draw from ``cfg.phantom_offset_ticks`` — i.e. a structureless line
            offset onto the side price currently sits on, so it faces the same
            approach as the gap it shadows.
``plain``   C2 control: a confirmed swing that was *never* body-broken and is
            wick-tested. An unbroken swing H is resistance (direction -1), an
            unbroken swing L support (+1) — the mirror of the gap convention.

Contract
--------
* No lookahead. A swing enters the active set only at ``confirmed_idx``; the
  only forward-looking field is ``follow_through``, which by definition reads
  the bar after creation and is a covariate, never a creation condition.
* A gap/phantom pair is created on break bar ``t``; touch detection starts at
  ``t + 1``, so the break bar's own wick can never test its own line.
* Touch is one-shot: ``low <= price`` for a +1 line, ``high >= price`` for a -1
  line, after which the line is closed. Each swing yields at most one plain
  event ever.
* A body break on bar ``t`` pre-empts a plain test on that same bar: the swing
  becomes a gap and produces no C2 event.
* Expiry uses CME trading-day ordinals (``session_date``, see bars.py), not bar
  counts: a line dies unused once ``ordinal(t) - ordinal(created) >=
  expiry_days``. The same clock is applied to plain lines from their
  ``confirmed_idx``, so the C2 control cannot quietly outlive the gaps it is
  compared against.
* At a rollover bar every open line and every active swing is discarded (price
  gap between contracts), and for ``rollover_blackout_bars`` afterwards no line
  is created, no touch is recorded and no plain event fires. Swings whose
  confirmation falls inside that window are dropped outright, which also
  removes swings formed before the roll but confirmed after it.

Lines that are voided (expired, or killed by a rollover) stay in the output
with ``touched_idx`` NaN; events are exactly the rows where ``touched_idx``
is not null.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .config import AuditConfig
from .swings import find_swings

LINE_COLUMNS = ["line_id", "price", "direction", "kind", "created_idx",
                "swing_idx", "follow_through", "touched_idx"]


def scan_lines(df: pd.DataFrame, cfg: AuditConfig) -> pd.DataFrame:
    n = len(df)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    rollover = df["rollover"].to_numpy(dtype=bool)
    session_ord = pd.factorize(df["session_date"])[0]

    swings = find_swings(df["high"], df["low"], cfg.k)
    by_confirm: dict[int, list] = defaultdict(list)
    for sw in swings.itertuples(index=False):
        by_confirm[int(sw.confirmed_idx)].append(sw)

    rng = np.random.default_rng(cfg.seed)
    lo_ticks, hi_ticks = cfg.phantom_offset_ticks

    records: list[dict] = []
    open_lines: list[dict] = []   # {"rec": index into records, price, direction}
    active: list = []             # confirmed, unbroken swings
    tested: set[int] = set()      # swing idx that already produced a plain event
    blackout_until = -1

    def _emit(price, direction, kind, created_idx, swing_idx, follow_through):
        records.append({"line_id": len(records), "price": float(price),
                        "direction": int(direction), "kind": kind,
                        "created_idx": int(created_idx),
                        "swing_idx": int(swing_idx),
                        "follow_through": follow_through,
                        "touched_idx": None})
        return len(records) - 1

    for t in range(n):
        if rollover[t]:
            open_lines.clear()
            active.clear()
            tested.clear()
            blackout_until = t + cfg.rollover_blackout_bars
        if t <= blackout_until:
            continue  # no creation, no touch, and confirmations here are dropped

        # 1. expire, then test every line opened on an earlier bar
        survivors = []
        for ln in open_lines:
            created = records[ln["rec"]]["created_idx"]
            if session_ord[t] - session_ord[created] >= cfg.expiry_days:
                continue  # stale line, dies without an event
            touched = (low[t] <= ln["price"] if ln["direction"] > 0
                       else high[t] >= ln["price"])
            if touched:
                records[ln["rec"]]["touched_idx"] = t
            else:
                survivors.append(ln)
        open_lines = survivors

        # 2. swings become usable only once confirmed
        active.extend(by_confirm.get(t, ()))

        # 3. body breaks create a gap + its phantom shadow
        unbroken = []
        for sw in active:
            broke = close[t] > sw.price if sw.kind == "H" else close[t] < sw.price
            if not broke:
                unbroken.append(sw)
                continue
            direction = 1 if sw.kind == "H" else -1
            follow = bool(t + 1 < n and direction * (close[t + 1] - sw.price) > 0)
            gap_rec = _emit(sw.price, direction, "gap", t, sw.idx, follow)
            open_lines.append({"rec": gap_rec, "price": float(sw.price),
                               "direction": direction})
            delta = float(rng.integers(lo_ticks, hi_ticks + 1)) * cfg.tick_size
            ghost_price = sw.price + direction * delta
            ghost_rec = _emit(ghost_price, direction, "phantom", t, sw.idx, None)
            open_lines.append({"rec": ghost_rec, "price": float(ghost_price),
                               "direction": direction})
        active = unbroken

        # 4. wick tests of surviving swings are the C2 control
        for sw in active:
            if sw.idx in tested or t <= sw.confirmed_idx:
                continue
            if session_ord[t] - session_ord[sw.confirmed_idx] >= cfg.expiry_days:
                continue
            touched = (high[t] >= sw.price if sw.kind == "H"
                       else low[t] <= sw.price)
            if not touched:
                continue
            tested.add(int(sw.idx))
            rec = _emit(sw.price, -1 if sw.kind == "H" else 1, "plain",
                        sw.confirmed_idx, sw.idx, None)
            records[rec]["touched_idx"] = t

    out = pd.DataFrame(records, columns=LINE_COLUMNS)
    return out.astype({"touched_idx": float}) if len(out) else out
