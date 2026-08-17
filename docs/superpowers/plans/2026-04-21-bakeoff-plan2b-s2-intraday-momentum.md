# Bake-off Plan 2b: S2 Intraday Momentum — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement S2 Intraday Momentum (Zarattini-Aziz-Barbon 2024 "Beat the Market") as two plain-Python strategy classes (S2a: max 1 trade/day; S2b: max 5 trades/day), plus an ARCX.PILLAR daily SPY loader. Validate mechanical correctness via skipped-by-default KAT on SPY 2023-04-20 → 2023-12-29. Parallel to Plan 2a (S1 ORB family, already merged via PR #1).

**Architecture:** Strategies remain plain Python — no pybroker. S2 adds a two-argument `generate_trades(bars_1m, bars_1d)` signature because it needs daily data for ATR_14. Reuses Plan 2a's `Trade`, `TradeOutcome`, `_known_answer`, and `load_spy_1m`. New daily loader pulls from ARCX.PILLAR (SPY's authoritative listing venue). No modifications to `src/daytrader/journal/`.

**Tech Stack:** pandas, numpy, databento. Python 3.12, existing `.venv`.

**Spec:** [`docs/superpowers/specs/2026-04-21-bakeoff-plan2b-s2-design.md`](../specs/2026-04-21-bakeoff-plan2b-s2-design.md) §3 (rules), §5 (KAT protocol), §6 (task breakdown).

**Prerequisites:**
- Plan 2a merged to main (commit `3d24636`). `Trade`, `TradeOutcome`, `load_spy_1m`, `summary_stats`, `compare_to_paper` all importable.
- `DATABENTO_API_KEY` in shell env.
- User's Databento plan must include ARCX.PILLAR (Task 5 Step 4 verifies this with live smoke).

**User-side actions outside this plan:**
- Confirm ARCX.PILLAR is in Databento subscription (runs at Task 5 Step 4). If not: either upgrade plan or substitute another daily-capable equities dataset in `data_spy_daily.py::_DAILY_DATASET`.
- Purchase SPY daily OHLCV from ARCX.PILLAR covering `2023-03-01 → 2023-12-29`. One-time, expected < $3.

---

## File Structure

```
Create:
  src/daytrader/research/bakeoff/data_spy_daily.py
  src/daytrader/research/bakeoff/strategies/_s2_core.py
  src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py
  tests/research/bakeoff/test_data_spy_daily.py
  tests/research/bakeoff/test_integration_spy_daily.py        # skipped by default
  tests/research/bakeoff/strategies/test_s2_core.py
  tests/research/bakeoff/strategies/test_s2_intraday_momentum.py
  tests/research/bakeoff/strategies/test_s2_kat_spy.py        # skipped by default

Modify: (none — Plan 2a code is reused unchanged)
```

---

## Task 1: S2 mechanical core

**Files:**
- Create: `src/daytrader/research/bakeoff/strategies/_s2_core.py`
- Create: `tests/research/bakeoff/strategies/test_s2_core.py`

Pure helpers on pandas DataFrames. Shared by S2a + S2b; no I/O, no cost model.

Functions to implement (all pure, all testable in isolation):
- `daily_true_range(daily: pd.DataFrame) -> pd.Series` — TR series indexed by day.
- `atr_14(daily: pd.DataFrame) -> pd.Series` — SMA of TR over 14 days, shifted 1 day so value at day `d` uses days `d-14..d-1`.
- `avg_intraday_return_14d(bars_1m: pd.DataFrame, check_times_et: list[str], tz: str) -> pd.DataFrame` — rows=dates, cols=check-time strings, value = 14-day rolling mean of `(close[t,k] - daily_open[k]) / daily_open[k]`, shifted so day `d`'s row uses days `d-14..d-1`.
- `compute_noise_boundary(daily_open: float, overnight_gap: float, avg_intra_return_row: pd.Series) -> tuple[pd.Series, pd.Series]` — returns `(upper, lower)` series keyed by check-time string, applying the gap-asymmetry adjustment from spec §3.3.
- `walk_forward_with_trailing(bars_after_entry, direction, entry_price, initial_stop, atr_14_d, eod_cutoff_ts) -> ExitInfo` — reuses `ExitInfo` / `TradeOutcome` from `_orb_core` / `_trade`; implements Chandelier trailing per spec §3.7 intra-bar order of operations.

### - [ ] Step 1: Write failing tests

Create `tests/research/bakeoff/strategies/test_s2_core.py`:

```python
"""Tests for S2 Intraday Momentum mechanical core."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._s2_core import (
    atr_14,
    avg_intraday_return_14d,
    compute_noise_boundary,
    daily_true_range,
    walk_forward_with_trailing,
)
from daytrader.research.bakeoff.strategies._trade import TradeOutcome


ET = ZoneInfo("America/New_York")


def _daily(rows):
    """rows: list of (date_str, open, high, low, close). Returns DataFrame
    indexed by tz-naive date."""
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c}
         for _d, o, h, l, c in rows],
        index=pd.DatetimeIndex([r[0] for r in rows]).normalize(),
    )
    df.index.name = "date"
    return df


def _intraday(date_str, rows_hm_ohlc):
    """rows_hm_ohlc: list of ('HH:MM', o, h, l, c). ET timestamps, tz-aware UTC."""
    ts = [
        pd.Timestamp(f"{date_str} {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows_hm_ohlc
    ]
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1}
         for _hm, o, h, l, c in rows_hm_ohlc],
        index=pd.DatetimeIndex(ts),
    )
    return df


# --- daily_true_range ---

def test_daily_true_range_first_row_is_nan():
    d = _daily([
        ("2024-06-10", 100, 102, 99, 101),
        ("2024-06-11", 101, 104, 100, 103),
    ])
    tr = daily_true_range(d)
    assert np.isnan(tr.iloc[0])  # no prev close on first day
    # Day 2: max(104-100, |104-101|, |100-101|) = 4
    assert tr.iloc[1] == pytest.approx(4.0)


def test_daily_true_range_uses_prev_close_for_gap():
    d = _daily([
        ("2024-06-10", 100, 102, 99, 101),
        ("2024-06-11", 105, 106, 104, 105),  # gap up; day-range 2 but gap-to-prev-close=5
    ])
    tr = daily_true_range(d)
    # max(106-104, |106-101|, |104-101|) = max(2, 5, 3) = 5
    assert tr.iloc[1] == pytest.approx(5.0)


# --- atr_14 ---

def test_atr_14_is_nan_until_14_days_accumulated_then_shifted_by_one():
    # Construct 16 days with TR = 1..16 (we'll fake via H-L = TR, no gap).
    rows = []
    for i in range(16):
        tr = i + 1
        rows.append((f"2024-06-{i+1:02d}", 100, 100 + tr, 100, 100))
    d = _daily(rows)
    a = atr_14(d)
    # Shifted by 1: day index 13 (0-based) is the first day whose "prev 14" is days 0..13 → 14 values.
    # atr_14 at index 13 should be SMA(TR[0..13]) = SMA(1..14) = 7.5
    # Actually shifted: we want atr_14 at day d to use days d-14..d-1 (14 values ending day before).
    # So atr_14 at index 14 = SMA(TR[0..13]) = 7.5
    assert np.isnan(a.iloc[13])
    assert a.iloc[14] == pytest.approx(7.5)
    assert a.iloc[15] == pytest.approx(8.5)  # SMA(TR[1..14]) = SMA(2..15) = 8.5


# --- avg_intraday_return_14d ---

def test_avg_intraday_return_14d_single_checktime_rolls_14_days():
    # Build 15 days, each with a 09:30 bar (open=100) and a 10:00 bar (close=100 + (day_idx * 0.1)).
    # Intraday return at 10:00 for day k = (100 + 0.1k - 100) / 100 = 0.001k
    frames = []
    for k in range(15):
        d_str = f"2024-06-{k+1:02d}"
        frames.append(_intraday(d_str, [
            ("09:30", 100, 100, 100, 100),
            ("10:00", 100, 100 + 0.1 * k, 100, 100 + 0.1 * k),
        ]))
    bars = pd.concat(frames).sort_index()
    avg = avg_intraday_return_14d(
        bars, check_times_et=["10:00"], tz="America/New_York"
    )
    # Shifted by 1: day 14 uses days 0..13 → mean(0.001 * 0..13) = 0.001 * 6.5 = 0.0065
    last_date = avg.index[-1]
    assert avg.loc[last_date, "10:00"] == pytest.approx(0.0065, abs=1e-9)


def test_avg_intraday_return_14d_raises_on_missing_0930():
    # No 09:30 bar → no daily_open anchor.
    bars = _intraday("2024-06-10", [
        ("09:31", 100, 101, 99, 100),
        ("10:00", 100, 101, 99, 100),
    ])
    with pytest.raises(ValueError, match="09:30"):
        avg_intraday_return_14d(
            bars, check_times_et=["10:00"], tz="America/New_York"
        )


# --- compute_noise_boundary ---

def test_noise_boundary_no_gap_is_symmetric():
    row = pd.Series({"10:00": 0.003, "10:30": 0.005})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=0.0, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3)
    assert lower["10:00"] == pytest.approx(99.7)


def test_noise_boundary_up_gap_shifts_lower_down():
    row = pd.Series({"10:00": 0.003})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=+0.5, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3)         # unchanged
    assert lower["10:00"] == pytest.approx(99.7 - 0.5)    # pushed down


def test_noise_boundary_down_gap_shifts_upper_up():
    row = pd.Series({"10:00": 0.003})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=-0.4, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3 + 0.4)
    assert lower["10:00"] == pytest.approx(99.7)


def test_noise_boundary_uses_absolute_value_of_return():
    # Negative avg_intra_return must still widen both sides.
    row = pd.Series({"10:00": -0.003})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=0.0, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3)
    assert lower["10:00"] == pytest.approx(99.7)


# --- walk_forward_with_trailing ---

def test_trailing_long_ratchets_stop_up_then_hits():
    # Entry 100, initial stop 96 (= 100 - 2*ATR where ATR=2). Price runs to 110,
    # trailing stop ratchets to 110 - 2*2 = 106. Then price drops to 105, hits stop at 106.
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),   # entry bar (iloc[0], skipped)
        ("10:01", 100, 105, 100, 105),   # trail to 105 - 4 = 101
        ("10:02", 105, 110, 105, 110),   # trail to 110 - 4 = 106
        ("10:03", 110, 110, 104, 105),   # low 104 <= stop 106 → STOP at 106
        ("15:55", 105, 106, 105, 106),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(106.0)


def test_trailing_long_stop_never_moves_down():
    # Price runs up then pulls back before ratcheting — stop shouldn't loosen.
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 108, 100, 108),   # trail to 108 - 4 = 104
        ("10:02", 108, 108, 105, 105),   # candidate 105-4=101 < 104 → keep 104
        ("10:03", 105, 105, 103, 103),   # low 103 < stop 104 → STOP at 104
        ("15:55", 103, 104, 103, 104),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(104.0)


def test_trailing_short_symmetric():
    # Entry 100 short, stop 104. Price drops to 92, trail to 92 + 4 = 96.
    # Price rallies to 97 → STOP at 96.
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 100, 95, 95),     # trail to 95 + 4 = 99
        ("10:02", 95, 95, 92, 92),       # trail to 92 + 4 = 96
        ("10:03", 92, 97, 92, 97),       # high 97 >= stop 96 → STOP at 96
        ("15:55", 97, 97, 96, 96),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="short",
        entry_price=100.0,
        initial_stop=104.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(96.0)


def test_trailing_eod_when_never_stopped():
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 101, 100, 101),
        ("15:55", 101, 102, 100.5, 101.5),   # last bar — forced flat
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.EOD
    assert exit.exit_price == pytest.approx(101.5)


def test_trailing_initial_stop_hits_on_first_bar():
    # Price instantly drops below initial stop on first post-entry bar.
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 100, 95, 95),     # low 95 <= initial stop 96 → STOP at 96
        ("15:55", 95, 96, 95, 96),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(96.0)
```

### - [ ] Step 2: Run tests — expect ImportError

```bash
cd "/Users/tylersan/Projects/Day trading"
.venv/bin/pytest tests/research/bakeoff/strategies/test_s2_core.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.research.bakeoff.strategies._s2_core'`.

### - [ ] Step 3: Implement

Create `src/daytrader/research/bakeoff/strategies/_s2_core.py`:

```python
"""S2 Intraday Momentum mechanical core (spec §3.3 + §3.4 + §3.7).

Pure functions on pandas DataFrames. No I/O, no cost model. Shared by
S2a and S2b.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from daytrader.research.bakeoff.strategies._orb_core import ExitInfo
from daytrader.research.bakeoff.strategies._trade import TradeOutcome


Direction = Literal["long", "short"]


CHECK_TIMES_ET = [
    "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30",
    "14:00", "14:30", "15:00", "15:30",
]


def daily_true_range(daily: pd.DataFrame) -> pd.Series:
    """TR_d = max(high_d - low_d, |high_d - close_{d-1}|, |low_d - close_{d-1}|).

    First row is NaN (no previous close). Assumes `daily` has columns
    open/high/low/close and an ascending date index.
    """
    prev_close = daily["close"].shift(1)
    hl = daily["high"] - daily["low"]
    hc = (daily["high"] - prev_close).abs()
    lc = (daily["low"] - prev_close).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr


def atr_14(daily: pd.DataFrame) -> pd.Series:
    """14-day SMA of daily True Range, shifted by 1 so that atr_14[d] uses
    TR values from days d-14..d-1 (no look-ahead into day d's bar).
    """
    tr = daily_true_range(daily)
    sma = tr.rolling(window=14, min_periods=14).mean()
    return sma.shift(1)


def avg_intraday_return_14d(
    bars_1m: pd.DataFrame,
    check_times_et: list[str],
    tz: str,
) -> pd.DataFrame:
    """For each (date, check_time) pair, rolling 14-day mean of
    (close[t,k] - daily_open[k]) / daily_open[k], using days d-14..d-1
    (shifted by 1 to avoid look-ahead).

    Returns a DataFrame indexed by date, columns = check_times_et.
    Raises ValueError if any date lacks a 09:30 ET bar (no daily_open anchor).
    """
    zoneinfo = ZoneInfo(tz)
    local = bars_1m.index.tz_convert(zoneinfo)
    local_date = pd.Series(local.date, index=bars_1m.index, name="_d")
    local_hm = pd.Series(
        [t.strftime("%H:%M") for t in local], index=bars_1m.index, name="_hm"
    )
    tagged = bars_1m.assign(_d=local_date, _hm=local_hm)

    # daily_open[k] = open of 09:30 bar. Raise if any date missing.
    opens = tagged[tagged["_hm"] == "09:30"].groupby("_d")["open"].first()
    missing = set(tagged["_d"].unique()) - set(opens.index)
    if missing:
        raise ValueError(f"missing 09:30 bar for dates: {sorted(missing)}")

    per_day_return = {}
    for ct in check_times_et:
        ct_closes = tagged[tagged["_hm"] == ct].groupby("_d")["close"].first()
        ret = (ct_closes - opens) / opens
        per_day_return[ct] = ret

    per_day_df = pd.DataFrame(per_day_return).sort_index()
    rolled = per_day_df.rolling(window=14, min_periods=14).mean()
    return rolled.shift(1)


def compute_noise_boundary(
    daily_open: float,
    overnight_gap: float,
    avg_intra_return_row: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Spec §3.3 noise boundary with gap asymmetry.

    `avg_intra_return_row` is one row of `avg_intraday_return_14d`'s output:
    index = check-time strings, values = 14-day means.
    """
    abs_ret = avg_intra_return_row.abs()
    raw_upper = daily_open * (1 + abs_ret)
    raw_lower = daily_open * (1 - abs_ret)
    if overnight_gap > 0:
        lower = raw_lower - overnight_gap
        upper = raw_upper
    elif overnight_gap < 0:
        upper = raw_upper + abs(overnight_gap)
        lower = raw_lower
    else:
        upper, lower = raw_upper, raw_lower
    return upper, lower


def walk_forward_with_trailing(
    bars_after_entry: pd.DataFrame,
    direction: Direction,
    entry_price: float,
    initial_stop: float,
    atr_14_d: float,
    eod_cutoff_ts: pd.Timestamp,
) -> ExitInfo:
    """Chandelier trailing stop from entry to exit.

    Rules (spec §3.7):
    - `bars_after_entry` INCLUDES the entry bar as row 0 (skipped in the loop).
    - On each post-entry bar: (a) check stop against *current* trailing stop
      (set from the previous bar's update, or initial_stop on the first
      post-entry bar), using this bar's high/low. If hit, exit at the stop
      price. (b) If not hit, update trailing using this bar's high (long) or
      low (short). Trailing never loosens.
    - If the last bar is reached without a stop hit, force-flat at its close
      (EOD cutoff).
    """
    stop = initial_stop

    for i in range(1, len(bars_after_entry)):
        ts = bars_after_entry.index[i]
        bar = bars_after_entry.iloc[i]
        hi = float(bar["high"])
        lo = float(bar["low"])

        if direction == "long":
            if lo <= stop:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop,
                    outcome=TradeOutcome.STOP,
                )
            # Update trailing using this bar's high; never loosens.
            candidate = hi - 2.0 * atr_14_d
            if candidate > stop:
                stop = candidate
        else:  # short
            if hi >= stop:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop,
                    outcome=TradeOutcome.STOP,
                )
            candidate = lo + 2.0 * atr_14_d
            if candidate < stop:
                stop = candidate

    last_bar = bars_after_entry.iloc[-1]
    return ExitInfo(
        exit_time=eod_cutoff_ts.to_pydatetime(),
        exit_price=float(last_bar["close"]),
        outcome=TradeOutcome.EOD,
    )
```

### - [ ] Step 4: Run tests — expect all PASS

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s2_core.py -v
```

Expected: 13 PASSED.

Full suite: `.venv/bin/pytest tests/ -q` → 213 passed, 5 skipped.

### - [ ] Step 5: Commit

```bash
git add src/daytrader/research/bakeoff/strategies/_s2_core.py tests/research/bakeoff/strategies/test_s2_core.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): S2 mechanical core — noise boundary + ATR + Chandelier trailing

Pure pandas functions: daily_true_range, atr_14 (shifted to avoid
look-ahead), avg_intraday_return_14d (per-minute-of-day 14d rolling),
compute_noise_boundary (gap-asymmetric upper/lower), and
walk_forward_with_trailing (stop-first then ratchet per spec §3.7).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: S2a + S2b strategy classes

**Files:**
- Create: `src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py`
- Create: `tests/research/bakeoff/strategies/test_s2_intraday_momentum.py`

Two classes. Both call a shared per-day driver that iterates check times, applies the noise boundary, and hands open trades to `walk_forward_with_trailing`. They differ only in `max_trades_per_day`.

### - [ ] Step 1: Write failing tests

Create `tests/research/bakeoff/strategies/test_s2_intraday_momentum.py`:

```python
"""Unit tests for S2a + S2b Intraday Momentum strategy classes."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._trade import TradeOutcome
from daytrader.research.bakeoff.strategies.s2_intraday_momentum import (
    S2a_IntradayMomentum_Max1,
    S2b_IntradayMomentum_Max5,
)


ET = ZoneInfo("America/New_York")


def _minutes(date_str, rows):
    """rows: list of ('HH:MM', o, h, l, c)."""
    ts = [
        pd.Timestamp(f"{date_str} {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows
    ]
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1}
         for _hm, o, h, l, c in rows],
        index=pd.DatetimeIndex(ts),
    )


def _build_14day_warmup_1m():
    """Build 14 uneventful prior days of 1m bars (09:30 + each check time +
    15:55) so that avg_intraday_return_14d warmup is satisfied. All bars at
    100.0 → avg_intra_return is 0 everywhere, meaning noise boundary is
    exactly daily_open (trivially breached by any move)."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    frames = []
    for k in range(14):
        d = f"2024-05-{k+1:02d}"
        rows = [(hm, 100.0, 100.0, 100.0, 100.0) for hm in hm_list]
        frames.append(_minutes(d, rows))
    return pd.concat(frames).sort_index()


def _build_14day_warmup_daily():
    """14 prior daily bars with TR = 1.0 each → ATR_14 = 1.0."""
    rows = [(f"2024-05-{k+1:02d}", 100.0, 100.5, 99.5, 100.0) for k in range(14)]
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c}
         for _d, o, h, l, c in rows],
        index=pd.DatetimeIndex([r[0] for r in rows]).normalize(),
    )
    df.index.name = "date"
    return df


def test_s2a_no_trigger_day_produces_no_trade():
    warmup_1m = _build_14day_warmup_1m()
    warmup_d = _build_14day_warmup_daily()

    # Trading day — price hugs daily_open, never breaks boundary (boundary
    # sits exactly at open because avg_intra_return=0 in warmup).
    # BUT: with avg_intra_return=0, ANY movement triggers. So we need
    # boundary > 0 width. Use a day with low volatility: add one real
    # intraday-return data point to warmup so avg is non-zero.
    # Simpler: make day open bar at 100, and have all bars equal 100 → no
    # strict > or < crossing.
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    flat_rows = [(hm, 100.0, 100.0, 100.0, 100.0) for hm in hm_list]
    trading = _minutes("2024-05-15", flat_rows)
    # Daily for trading day.
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}],
        index=pd.DatetimeIndex(["2024-05-15"]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert trades == []


def test_s2a_long_entry_on_upward_break():
    warmup_1m = _build_14day_warmup_1m()
    warmup_d = _build_14day_warmup_daily()

    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    # Build a trading day where avg_intra_return is forced non-zero by
    # replacing the last warmup day's 10:00 close with 100.14 (gives
    # avg = 0.14/14/100 = 0.0001 → boundary width 0.01% = $0.01 at 100).
    # Actually simpler: set the test-day boundary to a known value by
    # manipulating only the trading day's bars directly.
    # Use trading day: open at 100, at 10:00 price = 100.5 (> upper ~ 100.01) → long.
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = []
    for hm in hm_list:
        if hm == "10:00":
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))   # entry trigger
        elif hm == "10:30":
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))
        elif hm == "15:55":
            rows.append((hm, 100.5, 100.6, 100.4, 100.5))   # EOD
        else:
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))
    trading = _minutes("2024-05-15", rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 100.6, "low": 99.9, "close": 100.5}],
        index=pd.DatetimeIndex(["2024-05-15"]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.entry_price == pytest.approx(100.5)
    # S2a: only 1 trade per day, even if more breakouts happen after.


def test_s2a_ignores_second_trigger_same_day():
    """S2a max 1/day: after first trade closes, later triggers ignored."""
    warmup_1m = _build_14day_warmup_1m()
    warmup_d = _build_14day_warmup_daily()

    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    # Trading day: long breakout at 10:00 → stop out at 10:30 (quick loss) →
    # another breakout at 11:00. S2a must skip the 11:00 trigger.
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = []
    for hm in hm_list:
        if hm == "09:30":
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
        elif hm == "10:00":
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))   # entry long @ 100.5
        elif hm == "10:01":  # intra-bar — not in list, so use 10:30 below
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))
        elif hm == "10:30":
            rows.append((hm, 98.0, 98.0, 98.0, 98.0))       # stop hit somewhere in 10:00-10:30
        elif hm == "11:00":
            rows.append((hm, 101.0, 101.0, 101.0, 101.0))   # would trigger long — S2a ignores
        elif hm == "15:55":
            rows.append((hm, 101.0, 101.0, 100.0, 100.0))
        else:
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
    # Ensure time ordering: CHECK_TIMES_ET already sorted.
    trading = _minutes("2024-05-15", rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0}],
        index=pd.DatetimeIndex(["2024-05-15"]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert len(trades) == 1


def test_s2b_allows_up_to_5_trades_same_day():
    """S2b with 2 sequential breakouts on same day → both recorded."""
    warmup_1m = _build_14day_warmup_1m()
    warmup_d = _build_14day_warmup_daily()

    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = []
    for hm in hm_list:
        if hm == "09:30":
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
        elif hm == "10:00":
            rows.append((hm, 100.5, 100.5, 100.5, 100.5))   # entry 1 long
        elif hm == "10:30":
            rows.append((hm, 98.0, 98.0, 98.0, 98.0))       # stop out trade 1
        elif hm == "11:00":
            rows.append((hm, 101.0, 101.0, 101.0, 101.0))   # entry 2 long
        elif hm == "11:30":
            rows.append((hm, 97.0, 97.0, 97.0, 97.0))       # stop out trade 2
        elif hm == "15:55":
            rows.append((hm, 97.0, 97.0, 97.0, 97.0))
        else:
            rows.append((hm, 100.0, 100.0, 100.0, 100.0))
    trading = _minutes("2024-05-15", rows)
    trading_d = pd.DataFrame(
        [{"open": 100.0, "high": 101.0, "low": 97.0, "close": 97.0}],
        index=pd.DatetimeIndex(["2024-05-15"]).normalize(),
    )
    trading_d.index.name = "date"

    bars_1m = pd.concat([warmup_1m, trading]).sort_index()
    bars_1d = pd.concat([warmup_d, trading_d])

    strat = S2b_IntradayMomentum_Max5(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    assert len(trades) == 2


def test_s2_skips_days_before_warmup_ready():
    """First day in the input (no 14d history) → no signal, silent skip."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET
    hm_list = ["09:30"] + CHECK_TIMES_ET + ["15:55"]
    rows = [(hm, 100.0, 101.0, 99.0, 101.0) for hm in hm_list]
    day1 = _minutes("2024-05-01", rows)
    day1_d = pd.DataFrame(
        [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 101.0}],
        index=pd.DatetimeIndex(["2024-05-01"]).normalize(),
    )
    day1_d.index.name = "date"
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(day1, day1_d)
    assert trades == []
```

### - [ ] Step 2: Run tests — expect ImportError

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s2_intraday_momentum.py -v
```

Expected: FAIL.

### - [ ] Step 3: Implement

Create `src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py`:

```python
"""S2 Intraday Momentum strategies (Zarattini-Aziz-Barbon 2024).

Two variants sharing identical entry/exit logic; differ only in
max trades per day. Per spec §3.3, §3.5-§3.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from daytrader.research.bakeoff.strategies._s2_core import (
    CHECK_TIMES_ET,
    atr_14,
    avg_intraday_return_14d,
    compute_noise_boundary,
    walk_forward_with_trailing,
)
from daytrader.research.bakeoff.strategies._trade import Trade


SESSION_TZ = "America/New_York"
EOD_CUTOFF_ET = "15:55"


def _group_by_local_date(bars: pd.DataFrame, tz: str) -> dict:
    zoneinfo = ZoneInfo(tz)
    local_dates = bars.index.tz_convert(zoneinfo).date
    df = bars.copy()
    df["_local_date"] = local_dates
    return {d: g.drop(columns=["_local_date"]) for d, g in df.groupby("_local_date")}


def _local_hm(ts: pd.Timestamp, tz: str) -> str:
    return ts.tz_convert(ZoneInfo(tz)).strftime("%H:%M")


def _run_day(
    symbol: str,
    day_bars_1m: pd.DataFrame,
    daily_open: float,
    prev_close: float,
    atr_14_d: float,
    avg_intra_row: pd.Series,
    max_trades: int,
) -> list[Trade]:
    """Core per-day logic. Returns 0..max_trades Trades for the day."""
    # Warmup check: if any required input is NaN, skip the day silently.
    if (
        np.isnan(atr_14_d)
        or avg_intra_row.isna().any()
        or np.isnan(daily_open)
        or np.isnan(prev_close)
    ):
        return []

    overnight_gap = daily_open - prev_close
    upper, lower = compute_noise_boundary(
        daily_open=daily_open,
        overnight_gap=overnight_gap,
        avg_intra_return_row=avg_intra_row,
    )

    # Build a local-time minute index for fast lookup.
    local_hm = np.array([_local_hm(ts, SESSION_TZ) for ts in day_bars_1m.index])

    # EOD cutoff: the 15:55 bar (or latest bar if 15:55 is missing).
    eod_mask = local_hm == EOD_CUTOFF_ET
    if eod_mask.any():
        eod_idx = int(np.argmax(eod_mask))  # first match
    else:
        eod_idx = len(day_bars_1m) - 1
    eod_ts = day_bars_1m.index[eod_idx]

    trades: list[Trade] = []
    open_until_idx = -1  # exclusive — bars with idx < open_until_idx are "in-trade" window

    for ct in CHECK_TIMES_ET:
        if len(trades) >= max_trades:
            break

        matches = np.where(local_hm == ct)[0]
        if len(matches) == 0:
            continue
        ct_idx = int(matches[0])

        # Skip triggers while a prior trade was still open.
        if ct_idx < open_until_idx:
            continue

        ct_bar = day_bars_1m.iloc[ct_idx]
        price = float(ct_bar["close"])
        ct_upper = float(upper[ct])
        ct_lower = float(lower[ct])

        direction: str | None = None
        if price > ct_upper:
            direction = "long"
        elif price < ct_lower:
            direction = "short"
        if direction is None:
            continue

        entry_price = price
        if direction == "long":
            initial_stop = entry_price - 2.0 * atr_14_d
        else:
            initial_stop = entry_price + 2.0 * atr_14_d

        # Walk from the check-time bar through EOD cutoff.
        bars_after = day_bars_1m.iloc[ct_idx : eod_idx + 1]
        if len(bars_after) < 2:
            # No room for a post-entry bar — skip this trigger.
            continue

        exit_info = walk_forward_with_trailing(
            bars_after_entry=bars_after,
            direction=direction,
            entry_price=entry_price,
            initial_stop=initial_stop,
            atr_14_d=atr_14_d,
            eod_cutoff_ts=eod_ts,
        )

        # Map exit_time back to a bar index to know when to allow re-entry.
        if exit_info.exit_time == eod_ts.to_pydatetime():
            exit_idx_in_day = eod_idx
        else:
            # Find the bar whose timestamp matches exit_time.
            match = np.where(day_bars_1m.index == pd.Timestamp(exit_info.exit_time))[0]
            exit_idx_in_day = int(match[0]) if len(match) > 0 else eod_idx

        open_until_idx = exit_idx_in_day + 1

        risk = abs(entry_price - initial_stop)
        pnl = (exit_info.exit_price - entry_price) if direction == "long" \
            else (entry_price - exit_info.exit_price)
        r_multiple = 0.0 if risk == 0 else pnl / risk

        trades.append(Trade(
            date=str(day_bars_1m.index[0].tz_convert(SESSION_TZ).date()),
            symbol=symbol,
            direction=direction,
            entry_time=day_bars_1m.index[ct_idx].to_pydatetime(),
            entry_price=entry_price,
            stop_price=initial_stop,
            target_price=float("nan"),  # S2 has no fixed target — trailing only
            exit_time=exit_info.exit_time,
            exit_price=exit_info.exit_price,
            outcome=exit_info.outcome,
            r_multiple=r_multiple,
        ))

    return trades


def _generate(
    symbol: str,
    bars_1m: pd.DataFrame,
    bars_1d: pd.DataFrame,
    max_trades: int,
) -> list[Trade]:
    atr_series = atr_14(bars_1d)
    avg_intra = avg_intraday_return_14d(
        bars_1m, check_times_et=CHECK_TIMES_ET, tz=SESSION_TZ
    )

    per_day = _group_by_local_date(bars_1m, SESSION_TZ)
    out: list[Trade] = []

    # Build a daily_open / prev_close table from the daily bars.
    prev_close_series = bars_1d["close"].shift(1)

    for d, day_bars in per_day.items():
        d_idx = pd.Timestamp(d).normalize()
        if d_idx not in bars_1d.index:
            continue
        daily_open = float(bars_1d.loc[d_idx, "open"])
        prev_close = float(prev_close_series.loc[d_idx]) if not pd.isna(prev_close_series.loc[d_idx]) else float("nan")
        atr_d = float(atr_series.loc[d_idx]) if d_idx in atr_series.index else float("nan")

        if d_idx not in avg_intra.index:
            continue
        avg_row = avg_intra.loc[d_idx]

        out.extend(_run_day(
            symbol=symbol,
            day_bars_1m=day_bars,
            daily_open=daily_open,
            prev_close=prev_close,
            atr_14_d=atr_d,
            avg_intra_row=avg_row,
            max_trades=max_trades,
        ))

    return out


@dataclass
class S2a_IntradayMomentum_Max1:
    """S2a: max 1 trade per day (conservative). Per spec §3.3 + §3.6."""
    symbol: str

    def generate_trades(
        self, bars_1m: pd.DataFrame, bars_1d: pd.DataFrame
    ) -> list[Trade]:
        return _generate(self.symbol, bars_1m, bars_1d, max_trades=1)


@dataclass
class S2b_IntradayMomentum_Max5:
    """S2b: max 5 trades per day (Contract ceiling, close to paper intent)."""
    symbol: str

    def generate_trades(
        self, bars_1m: pd.DataFrame, bars_1d: pd.DataFrame
    ) -> list[Trade]:
        return _generate(self.symbol, bars_1m, bars_1d, max_trades=5)
```

### - [ ] Step 4: Run tests — expect all PASS

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s2_intraday_momentum.py -v
```

Expected: 5 PASSED.

**If `test_s2a_ignores_second_trigger_same_day` fails:** double-check `open_until_idx` logic — after exit, the NEXT check time whose bar is at or after `exit_idx+1` should be eligible, but S2a's `max_trades=1` cap should block it anyway. The cap is the primary guard; the `open_until_idx` guard matters for S2b.

### - [ ] Step 5: Commit

```bash
git add src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py tests/research/bakeoff/strategies/test_s2_intraday_momentum.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): S2a + S2b Intraday Momentum strategy classes

S2a: max 1 trade/day (conservative). S2b: max 5/day (Contract ceiling).
Entry at the 12 check times (10:00..15:30 ET) when price breaches
gap-adjusted noise boundary; exit via Chandelier trailing stop (2×ATR_14
from daily TR) or forced flat at 15:55 ET. Reuses Plan 2a's Trade type.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: S2 multi-day integration test

**Files:**
- Modify: `tests/research/bakeoff/strategies/test_s2_intraday_momentum.py` (append)

A mixed-fixture test across several trading days to catch day-grouping, warmup-boundary, and cap-reset bugs that single-day tests miss.

### - [ ] Step 1: Append failing test

Append to `tests/research/bakeoff/strategies/test_s2_intraday_momentum.py`:

```python
def _multiday_1m(days):
    """days: list of (date_str, list of ('HH:MM', o, h, l, c))."""
    frames = [_minutes(d, rows) for d, rows in days]
    return pd.concat(frames).sort_index()


def _multiday_daily(rows):
    """rows: list of (date_str, open, high, low, close)."""
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c}
         for _d, o, h, l, c in rows],
        index=pd.DatetimeIndex([r[0] for r in rows]).normalize(),
    )
    df.index.name = "date"
    return df


def test_s2b_counts_at_least_as_many_trades_as_s2a_across_days():
    """Sanity check: same 5-day multi-day fixture — S2b trade count
    must be >= S2a's."""
    from daytrader.research.bakeoff.strategies._s2_core import CHECK_TIMES_ET

    # 14 warmup days (uneventful) + 5 "real" days.
    warmup_days_1m = []
    for k in range(14):
        d = f"2024-05-{k+1:02d}"
        rows = [(hm, 100.0, 100.0, 100.0, 100.0)
                for hm in ["09:30"] + CHECK_TIMES_ET + ["15:55"]]
        warmup_days_1m.append((d, rows))

    # Real days — each with at least one breakout.
    real_days_1m = []
    for k in range(5):
        d = f"2024-05-{k+15:02d}"
        rows = []
        for hm in ["09:30"] + CHECK_TIMES_ET + ["15:55"]:
            if hm == "10:00":
                rows.append((hm, 100.5, 100.5, 100.5, 100.5))   # long trigger
            elif hm == "10:30":
                rows.append((hm, 98.0, 98.0, 98.0, 98.0))       # stop out trade 1
            elif hm == "11:00":
                rows.append((hm, 101.0, 101.0, 101.0, 101.0))   # S2b second trigger
            elif hm == "11:30":
                rows.append((hm, 99.0, 99.0, 99.0, 99.0))
            elif hm == "15:55":
                rows.append((hm, 99.0, 99.0, 99.0, 99.0))
            else:
                rows.append((hm, 100.0, 100.0, 100.0, 100.0))
        real_days_1m.append((d, rows))

    bars_1m = _multiday_1m(warmup_days_1m + real_days_1m)

    # Daily: warmup with TR=1, real days with some TR for ATR stability.
    warmup_d = [(f"2024-05-{k+1:02d}", 100.0, 100.5, 99.5, 100.0) for k in range(14)]
    real_d = [(f"2024-05-{k+15:02d}", 100.0, 101.0, 98.0, 99.0) for k in range(5)]
    bars_1d = _multiday_daily(warmup_d + real_d)

    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    assert len(s2b) >= len(s2a), f"S2b {len(s2b)} < S2a {len(s2a)} — logic bug"
    # All S2a trades must be on unique dates (max 1/day).
    assert len(set(t.date for t in s2a)) == len(s2a)
```

### - [ ] Step 2: Run test — expect PASS

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s2_intraday_momentum.py::test_s2b_counts_at_least_as_many_trades_as_s2a_across_days -v
```

Expected: PASS.

### - [ ] Step 3: Commit

```bash
git add tests/research/bakeoff/strategies/test_s2_intraday_momentum.py
git commit -m "$(cat <<'EOF'
test(bakeoff): S2 multi-day integration (S2b >= S2a count invariant)

Catches day-grouping + cap-reset bugs across 5-day fixture with warmup.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: ARCX.PILLAR daily SPY loader

**Files:**
- Create: `src/daytrader/research/bakeoff/data_spy_daily.py`
- Create: `tests/research/bakeoff/test_data_spy_daily.py`

Parallel to `data_spy.py` but simpler: no RTH filter (daily is already EOD), no publisher consolidation (daily is consolidated at source). Dataset = ARCX.PILLAR, schema = `ohlcv-1d`.

### - [ ] Step 1: Write failing tests

Create `tests/research/bakeoff/test_data_spy_daily.py`:

```python
"""Tests for ARCX.PILLAR daily SPY loader."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from daytrader.research.bakeoff.data_spy_daily import (
    SpyDailyDatabentoLoader,
    load_spy_daily,
)


@pytest.fixture
def mock_daily_client(monkeypatch):
    mock = MagicMock()
    mock_df = pd.DataFrame(
        {"open": [450.0, 451.0], "high": [451.5, 452.0],
         "low": [449.0, 450.0], "close": [451.0, 451.5],
         "volume": [50_000_000, 60_000_000]},
        index=pd.DatetimeIndex(
            [pd.Timestamp("2023-03-01", tz="UTC"),
             pd.Timestamp("2023-03-02", tz="UTC")]
        ),
    )
    mock.timeseries.get_range.return_value.to_df.return_value = mock_df
    monkeypatch.setattr("databento.Historical", lambda *a, **kw: mock)
    return mock


def test_daily_loader_missing_api_key_raises():
    with pytest.raises(ValueError, match="api_key"):
        SpyDailyDatabentoLoader(api_key="", cache_dir=Path("/tmp"))


def test_daily_loader_cache_miss_calls_databento(tmp_path, mock_daily_client):
    loader = SpyDailyDatabentoLoader(api_key="test", cache_dir=tmp_path)
    df = loader.load(date(2023, 3, 1), date(2023, 3, 2))
    assert len(df) == 2
    mock_daily_client.timeseries.get_range.assert_called_once()
    kwargs = mock_daily_client.timeseries.get_range.call_args.kwargs
    assert kwargs["dataset"] == "ARCX.PILLAR"
    assert kwargs["schema"] == "ohlcv-1d"


def test_daily_loader_cache_hit_skips_databento(tmp_path, mock_daily_client):
    loader = SpyDailyDatabentoLoader(api_key="test", cache_dir=tmp_path)
    loader.load(date(2023, 3, 1), date(2023, 3, 2))
    mock_daily_client.reset_mock()
    loader.load(date(2023, 3, 1), date(2023, 3, 2))
    mock_daily_client.timeseries.get_range.assert_not_called()


def test_load_spy_daily_returns_date_normalized_index(tmp_path, mock_daily_client):
    df = load_spy_daily(
        start=date(2023, 3, 1), end=date(2023, 3, 2),
        api_key="test", cache_dir=tmp_path,
    )
    # Index should be a DatetimeIndex normalized to midnight, no tz (daily bars
    # have no intraday timestamp semantics).
    assert isinstance(df.index, pd.DatetimeIndex)
    assert (df.index == df.index.normalize()).all()
    for c in ["open", "high", "low", "close"]:
        assert c in df.columns
```

### - [ ] Step 2: Run tests — expect ImportError

```bash
.venv/bin/pytest tests/research/bakeoff/test_data_spy_daily.py -v
```

Expected: FAIL.

### - [ ] Step 3: Implement

Create `src/daytrader/research/bakeoff/data_spy_daily.py`:

```python
"""ARCX.PILLAR daily SPY loader — for S2 ATR_14 warmup.

Parallel to `data_spy.py` but:
- dataset = ARCX.PILLAR (SPY's authoritative listing venue)
- schema = ohlcv-1d (daily bars, already consolidated at source)
- no RTH filter (daily bars are EOD — no intraday semantics)
- no publisher consolidation (daily tape is single-value per day)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

import pandas as pd


_DAILY_DATASET = "ARCX.PILLAR"


@dataclass
class SpyDailyDatabentoLoader:
    api_key: str
    cache_dir: Path

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("api_key is required")
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, start: _date, end: _date) -> Path:
        return self.cache_dir / (
            f"SPY_1d_{start.isoformat()}_{end.isoformat()}_raw.parquet"
        )

    def load(self, start: _date, end: _date) -> pd.DataFrame:
        p = self._cache_path(start, end)
        if p.exists():
            return pd.read_parquet(p)

        import databento
        client = databento.Historical(self.api_key)
        req = client.timeseries.get_range(
            dataset=_DAILY_DATASET,
            schema="ohlcv-1d",
            symbols=["SPY"],
            stype_in="raw_symbol",
            start=start.isoformat(),
            end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
        )
        df = req.to_df()
        # Normalize index to tz-naive midnight dates — daily bars have no
        # intraday timestamp semantics and downstream S2 core keys by date.
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df.index = df.index.normalize()
        df.index.name = "date"
        df.to_parquet(p)
        return df


def load_spy_daily(
    start: _date,
    end: _date,
    api_key: str,
    cache_dir: Path,
) -> pd.DataFrame:
    """End-to-end loader. Returns daily OHLCV DataFrame keyed by date."""
    loader = SpyDailyDatabentoLoader(api_key=api_key, cache_dir=cache_dir)
    return loader.load(start, end)
```

### - [ ] Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/research/bakeoff/test_data_spy_daily.py -v
```

Expected: 4 PASSED.

### - [ ] Step 5: Commit

```bash
git add src/daytrader/research/bakeoff/data_spy_daily.py tests/research/bakeoff/test_data_spy_daily.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): ARCX.PILLAR daily SPY loader for S2 ATR warmup

Parallel to DBEQ.BASIC 1m loader but simpler: schema=ohlcv-1d on SPY's
authoritative listing venue (NYSE Arca). No RTH filter (daily is EOD),
no publisher consolidation (daily tape is single-valued). Index
normalized to tz-naive dates for downstream S2 core keying.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Live daily smoke test (skipped by default)

**Files:**
- Create: `tests/research/bakeoff/test_integration_spy_daily.py`

Mirror of Plan 2a's SPY 1m live smoke, for daily data. Validates ARCX.PILLAR plan access before multi-month pull.

### - [ ] Step 1: Write the test

Create `tests/research/bakeoff/test_integration_spy_daily.py`:

```python
"""Live Databento SPY daily integration smoke test. Skipped unless enabled.

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> \\
        pytest tests/research/bakeoff/test_integration_spy_daily.py -v

Cost: 1 week of SPY daily ≈ pennies.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from daytrader.research.bakeoff.data_spy_daily import load_spy_daily


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
)


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="live Databento disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY)",
)
def test_live_fetch_one_week_spy_daily(tmp_path):
    df = load_spy_daily(
        start=date(2023, 6, 5),   # Mon
        end=date(2023, 6, 9),     # Fri
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=tmp_path,
    )
    # 5 trading days.
    assert 4 <= len(df) <= 5
    for c in ["open", "high", "low", "close"]:
        assert c in df.columns, f"missing column: {c}"
    # Sanity: SPY daily close in June 2023 should be ~$430 (loose band).
    assert 380 <= df["close"].mean() <= 500
```

### - [ ] Step 2: Confirm skips by default

```bash
.venv/bin/pytest tests/research/bakeoff/test_integration_spy_daily.py -v
```

Expected: 1 SKIPPED.

### - [ ] Step 3: Commit

```bash
git add tests/research/bakeoff/test_integration_spy_daily.py
git commit -m "$(cat <<'EOF'
test(bakeoff): live Databento ARCX.PILLAR daily smoke (skipped by default)

Verify schema + SPY daily bar count before multi-month S2 KAT pull.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### - [ ] Step 4: USER ACTION — run live daily smoke

> Not automated. Run with your Databento key:
> ```bash
> cd "/Users/tylersan/Projects/Day trading"
> source ~/.zshrc
> RUN_LIVE_TESTS=1 .venv/bin/pytest tests/research/bakeoff/test_integration_spy_daily.py -v
> ```
>
> **Possible failure mode:** ARCX.PILLAR not in your Databento plan → permissions error. Fix: either (a) upgrade plan, or (b) change `_DAILY_DATASET` in `data_spy_daily.py` to an available equities dataset (`XNAS.BASIC` with `ohlcv-1d` is a common fallback; note SPY on Nasdaq is a secondary quote). Do not proceed to Task 6 until this smoke passes.

---

## Task 6: S2 Known-answer test on SPY (skipped by default)

**Files:**
- Create: `tests/research/bakeoff/strategies/test_s2_kat_spy.py`

Four KAT anchors per spec §5 (anchors table). Gated on `RUN_LIVE_TESTS + DATABENTO_API_KEY + SPY_HISTORY_YEARS`.

### - [ ] Step 1: Write the KAT test

Create `tests/research/bakeoff/strategies/test_s2_kat_spy.py`:

```python
"""S2 known-answer test (Zarattini-Aziz-Barbon 2024) on SPY 2023.

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> SPY_HISTORY_YEARS=2023 \\
        pytest tests/research/bakeoff/strategies/test_s2_kat_spy.py -v

Data cost: reuses Plan 2a's cached SPY 1m (2023-04-03 → 2023-12-29) +
one new ARCX.PILLAR daily pull (2023-03-01 → 2023-12-29, ~$1-3).

Anchors (tolerance 15% per spec §5.1, band for #2 widened if needed):
1. S2a n_trades within ±15% of 75 (≈ 170 trading days × 0.44 hit-rate guess)
2. S2a win rate in [0.30, 0.65] (momentum + ATR trailing plausibility band)
3. len(S2b trades) >= len(S2a trades) — strict (S2b only loosens cap)
4. |avg_R(S2b) - avg_R(S2a)| / |avg_R(S2a)| < 0.30 — same entries, same
   exits, different intraday throttling → avg-R per trade should be close

If #1 or #2 fail outside forgiveness, STOP and debug rules per spec §5
calibration policy before merging.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.data_spy_daily import load_spy_daily
from daytrader.research.bakeoff.strategies._known_answer import (
    compare_to_paper, summary_stats,
)
from daytrader.research.bakeoff.strategies.s2_intraday_momentum import (
    S2a_IntradayMomentum_Max1, S2b_IntradayMomentum_Max5,
)


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
    and os.getenv("SPY_HISTORY_YEARS")
)


@pytest.fixture(scope="module")
def s2_bars():
    cache_1m = Path("data/cache/ohlcv_spy_kat")
    cache_1d = Path("data/cache/ohlcv_spy_daily_kat")
    cache_1m.mkdir(parents=True, exist_ok=True)
    cache_1d.mkdir(parents=True, exist_ok=True)
    ds = load_spy_1m(
        start=date(2023, 4, 3),
        end=date(2023, 12, 29),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache_1m,
    )
    daily = load_spy_daily(
        start=date(2023, 3, 1),     # 20+ trading days warmup before 2023-04-03
        end=date(2023, 12, 29),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache_1d,
    )
    return ds.bars, daily


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="S2 KAT disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY + SPY_HISTORY_YEARS)",
)
def test_s2a_spy_2023_n_trades(s2_bars):
    bars_1m, bars_1d = s2_bars
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    result = compare_to_paper(
        metric_name="n_trades",
        computed=float(len(trades)),
        paper_value=75.0,   # 170 days × 0.44 hit-rate (guess)
        tolerance_pct=15.0,
    )
    assert result.passed, (
        f"S2a n_trades {len(trades)} deviates {result.deviation_pct:.1f}% "
        f"from expected 75 (tolerance 15%). Likely causes: "
        f"(a) warmup skip off-by-one, (b) check-time local-tz mismatch, "
        f"(c) boundary calc wrong."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2a_spy_2023_win_rate(s2_bars):
    bars_1m, bars_1d = s2_bars
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    stats = summary_stats(trades, point_value_usd=1.0, starting_capital=10_000.0)
    wr = stats["win_rate"]
    assert 0.30 <= wr <= 0.65, (
        f"S2a SPY 2023 win rate {wr:.3f} outside plausible [0.30, 0.65] band. "
        f"Momentum + ATR trailing is typically 40-55% for liquid equities. "
        f"If too low: trailing too tight, or boundary too narrow → false breakouts. "
        f"If too high: trailing too loose, or boundary too wide → hindsight bias."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2b_count_at_least_s2a_count(s2_bars):
    bars_1m, bars_1d = s2_bars
    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    assert len(s2b) >= len(s2a), (
        f"S2b ({len(s2b)}) must have >= trades than S2a ({len(s2a)}); "
        "S2b only loosens the per-day cap, nothing else."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2a_and_s2b_avg_r_close(s2_bars):
    bars_1m, bars_1d = s2_bars
    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    if not s2a or not s2b:
        pytest.skip("need both S2a and S2b trades to compare")
    avg_r_a = sum(t.r_multiple for t in s2a) / len(s2a)
    avg_r_b = sum(t.r_multiple for t in s2b) / len(s2b)
    if avg_r_a == 0:
        pytest.skip("S2a avg R is exactly 0 — cannot compute relative gap")
    rel_gap = abs(avg_r_b - avg_r_a) / abs(avg_r_a)
    assert rel_gap < 0.30, (
        f"S2a avg_R {avg_r_a:.3f} vs S2b avg_R {avg_r_b:.3f} — gap "
        f"{rel_gap*100:.1f}% exceeds 30%. Same entries + same exits "
        "should give similar per-trade R. Check cap-reset / re-entry logic."
    )
```

### - [ ] Step 2: Confirm skipped by default

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s2_kat_spy.py -v
```

Expected: 4 SKIPPED.

### - [ ] Step 3: Commit

```bash
git add tests/research/bakeoff/strategies/test_s2_kat_spy.py
git commit -m "$(cat <<'EOF'
test(bakeoff): S2 known-answer tests on SPY (skipped by default)

Four anchors per spec §5:
  1. S2a n_trades ≈ 75 ±15%
  2. S2a win rate in [0.30, 0.65]
  3. len(S2b) >= len(S2a) strict
  4. |avg_R(S2a) - avg_R(S2b)| / |avg_R(S2a)| < 30%
Gated on RUN_LIVE_TESTS + DATABENTO_API_KEY + SPY_HISTORY_YEARS.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### - [ ] Step 4: USER ACTION — run S2 KAT

> Not automated. After Task 5's daily smoke passed:
>
> ```bash
> cd "/Users/tylersan/Projects/Day trading"
> source ~/.zshrc
> RUN_LIVE_TESTS=1 SPY_HISTORY_YEARS=2023 \
>     .venv/bin/pytest tests/research/bakeoff/strategies/test_s2_kat_spy.py -v
> ```
>
> Expected: 4 PASSED. One-time daily download ~$1-3 (1m already cached from Plan 2a).
>
> **If a test fails:** apply spec §5 calibration policy:
> - **#1 n_trades wildly off:** check warmup cutoff date, 09:30 ET bar detection, check-time local timezone handling.
> - **#2 win rate outside band:** if just slightly off, widen band once with a rationale commit (same as Plan 2a's S1a band widening).
> - **#3 S2b < S2a:** real bug — S2b must never under-count. Inspect the cap-and-reset logic.
> - **#4 avg-R gap > 30%:** phantom cap leakage in S2a or phantom bonus in S2b. Inspect `open_until_idx` + `max_trades` interaction.
>
> Do NOT merge to main until all 4 pass (or #2 is widened once with a documented rationale).

---

## Task 7: Final verification + close-out

**Files:** (no code changes — verification only)

### - [ ] Step 1: Full test suite

```bash
cd "/Users/tylersan/Projects/Day trading"
.venv/bin/pytest tests/ -q 2>&1 | tail -5
```

Expected tally:
- Baseline (Plan 2a on main): 200 passed, 5 skipped.
- Task 1 (_s2_core): +13 passed.
- Task 2 (S2 strategy classes): +5 passed.
- Task 3 (S2 multi-day): +1 passed.
- Task 4 (daily loader): +4 passed.
- Task 5 (daily live smoke): +1 skipped.
- Task 6 (S2 KAT): +4 skipped.

**Expected: 223 passed, 10 skipped.**

If the count is off, investigate.

### - [ ] Step 2: Directory structure

```bash
find src/daytrader/research/bakeoff/data_spy_daily.py \
     src/daytrader/research/bakeoff/strategies/_s2_core.py \
     src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py \
     tests/research/bakeoff/test_data_spy_daily.py \
     tests/research/bakeoff/test_integration_spy_daily.py \
     tests/research/bakeoff/strategies/test_s2_core.py \
     tests/research/bakeoff/strategies/test_s2_intraday_momentum.py \
     tests/research/bakeoff/strategies/test_s2_kat_spy.py \
     -type f 2>/dev/null | sort
```

Expected: 8 files listed.

### - [ ] Step 3: Journal code untouched

```bash
git log main..HEAD --name-only --pretty=format: -- src/daytrader/journal/ tests/journal/ | sort -u | grep -v '^$'
```

Expected: empty output.

### - [ ] Step 4: pybroker still NOT imported

```bash
grep -rn "import pybroker\|from pybroker" src/daytrader/research/ || echo "clean"
```

Expected: `clean`.

### - [ ] Step 5: Package imports

```bash
.venv/bin/python -c "
from daytrader.research.bakeoff.strategies._s2_core import (
    atr_14, avg_intraday_return_14d, compute_noise_boundary,
    daily_true_range, walk_forward_with_trailing, CHECK_TIMES_ET,
)
from daytrader.research.bakeoff.strategies.s2_intraday_momentum import (
    S2a_IntradayMomentum_Max1, S2b_IntradayMomentum_Max5,
)
from daytrader.research.bakeoff.data_spy_daily import (
    load_spy_daily, SpyDailyDatabentoLoader,
)
print('all imports ok')
"
```

Expected: `all imports ok`.

### - [ ] Step 6: Commit history review

```bash
git log main..HEAD --oneline
```

Expected: 6 commits (Tasks 1-6, `feat(bakeoff)` / `test(bakeoff)` only).

### - [ ] Step 7: Report Plan 2b status

Summarize:
- 3 new modules (`_s2_core`, `s2_intraday_momentum`, `data_spy_daily`)
- ~23 new unit tests
- 5 new skipped tests (1 daily smoke + 4 KAT)
- Ready for user to run skipped live tests.

**Plan 2b is NOT done until the user runs Tasks 5 & 6 live tests.** Do not merge to main until S2 KAT 4/4 passes. If KAT fails, re-read spec §3.3 before widening bands — n_trades and S2b-vs-S2a anchors should be strict; only #2 (win rate band) may be widened once with documented rationale per spec §5.

---

## Self-Review

**Spec coverage (§ refers to `2026-04-21-bakeoff-plan2b-s2-design.md`):**

| Spec item | Covered by |
|---|---|
| §2.1 file structure | Tasks 1, 2, 4, 5, 6 |
| §2.4 two-arg signature | Task 2 (`generate_trades(bars_1m, bars_1d)`) |
| §3.1 daily_open / prev_close / overnight_gap | Task 2 `_run_day` |
| §3.2 avg_intraday_return_14d (per-minute-of-day) | Task 1 `avg_intraday_return_14d` |
| §3.3 noise boundary with gap asymmetry | Task 1 `compute_noise_boundary` |
| §3.4 ATR_14 from daily TR, shifted | Task 1 `atr_14` + `daily_true_range` |
| §3.5 entry at 12 check times, skip when open | Task 2 `_run_day` |
| §3.6 S2a=1/day, S2b=5/day | Task 2 `_generate(max_trades=...)` |
| §3.7 initial stop + Chandelier trailing + 15:55 EOD | Task 1 `walk_forward_with_trailing` + Task 2 EOD cutoff detection |
| §3.8 fixed 1 unit | Implicit (1 Trade per entry) |
| §4 warmup chain (both ATR_14 and avg_intraday_return) | Task 2 NaN-skip in `_run_day` |
| §5 KAT 4 anchors + calibration policy | Task 6 |
| §6 task breakdown | Tasks 1-7 (one-to-one) |
| §7 R-2b-1 (ARCX.PILLAR access) | Task 5 Step 4 user action |
| §7 R-2b-4 (session quirks) | Inherited from Plan 2a's RTH filter |

**Placeholder scan:** No TBD/TODO. Every step has concrete code or exact commands.

**Type consistency:** `ExitInfo` reused from `_orb_core`. `Trade` / `TradeOutcome` reused from `_trade`. `CHECK_TIMES_ET` defined once in `_s2_core` and imported by `s2_intraday_momentum`. Class names `S2a_IntradayMomentum_Max1` / `S2b_IntradayMomentum_Max5` used consistently in implementation (Task 2), unit tests (Tasks 2-3), and KAT (Task 6).

**Ambiguity resolved:**
- "price[t]" = close of the 1-min bar at time t (spec §3.5 clarification, carried into Task 2).
- Trailing-stop update order: stop-check first using previous bar's stop, then update using current bar's extreme (spec §3.7, implemented in Task 1 `walk_forward_with_trailing`).
- 15:55 EOD exit: `eod_cutoff_ts` = the 15:55 bar's timestamp, or last available bar if 15:55 is missing (handles half-days).
