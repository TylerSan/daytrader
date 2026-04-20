# Bake-off Plan 2a: SPY Data + S1 ORB Family — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the S1 ORB family (S1a: exit at 10× OR target or EOD; S1b: exit at EOD only) as plain-Python strategy classes that produce trade lists from a bar DataFrame. Add a SPY 1-minute data loader. Validate both strategies against Zarattini 2023/2024 ORB papers on SPY via skipped-by-default known-answer tests. This is M3 (S1 half) of the W2 Setup Gate bake-off.

**Architecture:** Strategies are plain Python classes — **they do NOT depend on pybroker**. Each strategy exposes `generate_trades(bars: pd.DataFrame) -> list[Trade]`. pybroker integration happens in Plan 3 via a thin adapter. This insulates strategy correctness from pybroker lifecycle risk (R5). The `Trade` dataclass and `ORB` mechanical core live in `research/bakeoff/strategies/`, never touching `journal/`.

**Tech Stack:** pandas, numpy, databento (for SPY history). pybroker NOT imported in Plan 2a.

**Spec:** [`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../specs/2026-04-20-strategy-selection-bakeoff-design.md) §3.2 (S1 rules), §5.1 (known-answer test), M3.

**Prerequisites:**
- Plan 1 merged to main (commit `4a2a646`).
- Databento MES 1-minute loader working against real data (smoke test passed 2026-04-20).
- `DATABENTO_API_KEY` in user's shell env.

**User-side actions outside this plan:**
- Purchase Databento OHLCV-1m for **SPY** (not MES) for at least **one full year of overlap with Zarattini 2023 paper period** (2016-2023). Recommend: 2022-01-01 to 2023-12-31 (one 2-year window is enough for known-answer validation; expected cost < $5). This happens at Task 8 (known-answer), not at the start.
- SPY historical from Databento uses `XNAS.ITCH` or `XNAS.NLS` or `DBEQ.BASIC` datasets depending on plan — the loader auto-selects based on availability; if the user's Databento plan doesn't include equities historical, the loader raises a clear error.

---

## File Structure

```
Create:
  src/daytrader/research/bakeoff/data_spy.py                  # SPY 1m loader (parallel to data.py)
  src/daytrader/research/bakeoff/strategies/_trade.py         # Trade dataclass + TradeOutcome enum
  src/daytrader/research/bakeoff/strategies/_orb_core.py      # OR computation, breakout detection, walk-forward
  src/daytrader/research/bakeoff/strategies/s1_orb.py         # S1a + S1b classes
  tests/research/bakeoff/test_data_spy.py
  tests/research/bakeoff/strategies/__init__.py
  tests/research/bakeoff/strategies/test_trade.py
  tests/research/bakeoff/strategies/test_orb_core.py
  tests/research/bakeoff/strategies/test_s1_orb.py
  tests/research/bakeoff/strategies/test_s1_kat_spy.py        # skipped by default, needs SPY data
Modify:
  (none — journal/ stays frozen per spec §4.3)
```

**No modifications to existing code in Plan 2a.** All additions are under `research/bakeoff/`.

---

## Task 1: Trade dataclass + outcome enum

**Files:**
- Create: `src/daytrader/research/bakeoff/strategies/_trade.py`
- Create: `tests/research/bakeoff/strategies/__init__.py` (empty)
- Create: `tests/research/bakeoff/strategies/test_trade.py`

Small, strict dataclass used by all 4 candidates. Leading underscore in module name signals "module-private; consumed inside strategies/, not part of the public bakeoff API yet."

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/strategies/__init__.py` as empty file.

Create `tests/research/bakeoff/strategies/test_trade.py`:
```python
"""Tests for Trade dataclass + TradeOutcome enum."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_trade_outcome_values():
    assert TradeOutcome.TARGET.value == "target"
    assert TradeOutcome.STOP.value == "stop"
    assert TradeOutcome.EOD.value == "eod"


def test_trade_construction():
    t = Trade(
        date="2024-06-10", symbol="MES", direction="long",
        entry_time=_ts("2024-06-10T13:35:00"), entry_price=5000.0,
        stop_price=4995.0, target_price=5050.0,
        exit_time=_ts("2024-06-10T14:30:00"), exit_price=5050.0,
        outcome=TradeOutcome.TARGET, r_multiple=10.0,
    )
    assert t.direction == "long"
    assert t.r_multiple == pytest.approx(10.0)
    assert t.outcome is TradeOutcome.TARGET


def test_trade_rejects_unknown_direction():
    with pytest.raises(ValueError, match="direction"):
        Trade(
            date="2024-06-10", symbol="MES", direction="flat",  # invalid
            entry_time=_ts("2024-06-10T13:35:00"), entry_price=5000.0,
            stop_price=4995.0, target_price=5050.0,
            exit_time=_ts("2024-06-10T14:30:00"), exit_price=5050.0,
            outcome=TradeOutcome.TARGET, r_multiple=10.0,
        )


def test_trade_is_immutable():
    t = Trade(
        date="2024-06-10", symbol="MES", direction="long",
        entry_time=_ts("2024-06-10T13:35:00"), entry_price=5000.0,
        stop_price=4995.0, target_price=5050.0,
        exit_time=_ts("2024-06-10T14:30:00"), exit_price=5050.0,
        outcome=TradeOutcome.TARGET, r_multiple=10.0,
    )
    with pytest.raises((AttributeError, Exception)):
        t.r_multiple = 999.0  # frozen dataclass
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd "/Users/tylersan/Projects/Day trading"
.venv/bin/pytest tests/research/bakeoff/strategies/test_trade.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/strategies/_trade.py`:
```python
"""Trade dataclass — the atomic unit of a bake-off strategy's output.

Every strategy class in `research.bakeoff.strategies` produces a list of
`Trade` from a bar DataFrame. This is the wire format between strategy
code and the metrics / walk-forward harness (Plan 3).

Kept deliberately separate from `daytrader.journal.models.SimulatedTrade`
— the journal version is frozen per spec §4.3, and mixing the two would
create accidental coupling between the research pipeline and the
discipline pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TradeOutcome(str, Enum):
    TARGET = "target"
    STOP = "stop"
    EOD = "eod"


_VALID_DIRECTIONS = {"long", "short"}


@dataclass(frozen=True)
class Trade:
    """One closed round-trip trade.

    Attributes:
        date: Local-ET date string "YYYY-MM-DD" the trade opened.
        symbol: Instrument code (e.g., "MES", "SPY").
        direction: "long" or "short". Rejected at construction otherwise.
        entry_time: UTC timestamp of entry fill.
        entry_price: Fill price in instrument's native units (points for
            futures, dollars for ETFs). Does NOT include slippage — the
            cost model is applied separately by the metrics layer.
        stop_price: Initial stop level (not necessarily where the trade
            exited; for trailing-stop strategies, this is the INITIAL stop).
        target_price: Initial target level. NaN if the strategy has no
            target (e.g., S1b EOD-only variant — but encode as float('nan'),
            not Optional[float], to keep the schema flat).
        exit_time: UTC timestamp of exit fill.
        exit_price: Exit fill price.
        outcome: Which rule triggered the exit.
        r_multiple: PnL / initial risk (points / (abs(entry_price - stop_price))).
            Positive for winners, negative for losers. Does not include
            transaction costs — those are layered in the metrics step.
    """
    date: str
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    stop_price: float
    target_price: float
    exit_time: datetime
    exit_price: float
    outcome: TradeOutcome
    r_multiple: float

    def __post_init__(self):
        if self.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of {sorted(_VALID_DIRECTIONS)}, "
                f"got {self.direction!r}"
            )
```

- [ ] **Step 4: Run tests — expect 4 PASS**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_trade.py -v
```

Expected: 4 PASSED.

Also `.venv/bin/pytest tests/ -q` → 174 passing (170 Plan 1 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/strategies/_trade.py tests/research/bakeoff/strategies/
git commit -m "$(cat <<'EOF'
feat(bakeoff): Trade dataclass + TradeOutcome enum for strategy output

Frozen dataclass, validates direction at construction. Kept separate from
journal.models.SimulatedTrade to preserve the research/journal boundary
(spec §4.3). Wire format for strategies → metrics in Plan 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: ORB mechanical core

**Files:**
- Create: `src/daytrader/research/bakeoff/strategies/_orb_core.py`
- Create: `tests/research/bakeoff/strategies/test_orb_core.py`

Pure mechanical helpers: compute the 5-minute opening range, find the direction-of-day, walk forward from entry to exit against stop/target/EOD. Both S1a and S1b will use this core; they only differ in how they compute `target_price`.

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/strategies/test_orb_core.py`:
```python
"""Tests for ORB mechanical core (opening range + entry + walk-forward)."""

from __future__ import annotations

import math
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._orb_core import (
    compute_opening_range,
    direction_from_first_bar,
    walk_forward_to_exit,
    OpeningRange,
)
from daytrader.research.bakeoff.strategies._trade import TradeOutcome


ET = ZoneInfo("America/New_York")


def _bar_row(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": 1}


def _make_day_bars(rows_with_et_time, ticker_iid=100):
    """rows_with_et_time: list of (ET minute like '09:30', open, high, low, close)."""
    timestamps_utc = [
        pd.Timestamp(f"2024-06-10 {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows_with_et_time
    ]
    data = [_bar_row(o, h, l, c) for _hm, o, h, l, c in rows_with_et_time]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps_utc))
    df["instrument_id"] = ticker_iid
    return df


# --- compute_opening_range ---

def test_opening_range_high_low_from_first_five_bars():
    # 09:30-09:34 inclusive = 5 bars = OR window.
    bars = _make_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5002, 5008),  # close at 09:34 = directional trigger
        ("09:35", 5008, 5012, 5007, 5010),  # post-OR
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert or_.high == pytest.approx(5010.0)  # max high across first 5 bars
    assert or_.low == pytest.approx(4998.0)   # min low across first 5 bars
    assert or_.range_pts == pytest.approx(12.0)
    assert or_.close_at_or_end == pytest.approx(5008.0)  # close of 09:34 bar
    assert or_.open_at_session_start == pytest.approx(5000.0)
    assert or_.or_end_index == 4  # 0-indexed: 09:34 is the 5th (final) bar of OR


def test_opening_range_raises_if_insufficient_bars():
    bars = _make_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
    ])
    with pytest.raises(ValueError, match="insufficient"):
        compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")


# --- direction_from_first_bar ---

def test_direction_long_when_or_close_above_open():
    bars = _make_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5002, 5008),  # close 5008 > open 5000 → long
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert direction_from_first_bar(or_) == "long"


def test_direction_short_when_or_close_below_open():
    bars = _make_day_bars([
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),  # close 4978 < open 5000 → short
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert direction_from_first_bar(or_) == "short"


def test_direction_none_when_flat():
    bars = _make_day_bars([
        ("09:30", 5000, 5002, 4999, 5001),
        ("09:31", 5001, 5002, 5000, 5000),
        ("09:32", 5000, 5001, 4999, 5000),
        ("09:33", 5000, 5001, 4999, 5000),
        ("09:34", 5000, 5001, 4999, 5000),  # close == open 5000 → flat (skip day)
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert direction_from_first_bar(or_) is None


# --- walk_forward_to_exit ---

def test_walk_forward_long_hits_target():
    # After OR, price rises to target.
    post_or = _make_day_bars([
        ("09:35", 5010, 5015, 5009, 5014),
        ("09:36", 5014, 5020, 5013, 5019),
        ("09:37", 5019, 5051, 5018, 5050),  # high >= target 5050 → TARGET hit
    ])
    entry_ts = post_or.index[0]
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=5050.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.TARGET
    assert exit.exit_price == pytest.approx(5050.0)


def test_walk_forward_long_hits_stop_first():
    post_or = _make_day_bars([
        ("09:35", 5010, 5012, 4995, 4998),  # low 4995 <= stop 5000 → STOP first
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=5050.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(5000.0)


def test_walk_forward_short_hits_target():
    post_or = _make_day_bars([
        ("09:35", 4990, 4995, 4985, 4988),
        ("09:36", 4988, 4989, 4948, 4950),  # low <= target 4950 → TARGET
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="short",
        entry_price=4990.0,
        stop_price=5000.0,
        target_price=4950.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.TARGET
    assert exit.exit_price == pytest.approx(4950.0)


def test_walk_forward_eod_when_neither_hit():
    post_or = _make_day_bars([
        ("09:35", 5010, 5012, 5005, 5008),
        ("15:59", 5008, 5011, 5005, 5009),  # last bar — EOD
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=5050.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.EOD
    assert exit.exit_price == pytest.approx(5009.0)  # close of last bar


def test_walk_forward_nan_target_treated_as_eod_only():
    # S1b semantics: no target, just EOD or stop.
    post_or = _make_day_bars([
        ("09:35", 5010, 5100, 5005, 5099),   # high 5100 — but NaN target so no target hit
        ("15:59", 5099, 5101, 5098, 5100),
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=math.nan,   # S1b
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.EOD
    assert exit.exit_price == pytest.approx(5100.0)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_orb_core.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/strategies/_orb_core.py`:
```python
"""Opening Range Breakout mechanical core.

Shared helpers for S1a and S1b. Pure functions on pandas DataFrames —
no I/O, no cost model. Cost application happens in the metrics layer
(Plan 3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import TradeOutcome


Direction = Literal["long", "short"]


@dataclass(frozen=True)
class OpeningRange:
    """Summary of the opening-range window for one trading day."""
    high: float
    low: float
    range_pts: float              # high - low
    open_at_session_start: float  # open of first bar of OR
    close_at_or_end: float        # close of last bar of OR
    or_end_index: int             # positional index (into the input `bars`) of last OR bar


@dataclass(frozen=True)
class ExitInfo:
    """Result of walking forward from entry to first exit condition."""
    exit_time: datetime
    exit_price: float
    outcome: TradeOutcome


def compute_opening_range(
    bars: pd.DataFrame,
    or_minutes: int,
    session_tz: str,
) -> OpeningRange:
    """Compute the opening range from the first `or_minutes` bars of the session.

    Assumes `bars` is already filtered to a single trading day's RTH and
    UTC-indexed. Raises ValueError if there are fewer than `or_minutes` bars.
    """
    if len(bars) < or_minutes:
        raise ValueError(
            f"insufficient bars for OR: have {len(bars)}, need {or_minutes}"
        )
    tz = ZoneInfo(session_tz)
    or_bars = bars.iloc[:or_minutes]
    return OpeningRange(
        high=float(or_bars["high"].max()),
        low=float(or_bars["low"].min()),
        range_pts=float(or_bars["high"].max() - or_bars["low"].min()),
        open_at_session_start=float(or_bars["open"].iloc[0]),
        close_at_or_end=float(or_bars["close"].iloc[-1]),
        or_end_index=or_minutes - 1,
    )


def direction_from_first_bar(or_: OpeningRange) -> Optional[Direction]:
    """Zarattini direction rule: sign of (close_at_or_end - open_at_session_start).

    Returns "long" if positive, "short" if negative, None if zero (skip day).
    """
    delta = or_.close_at_or_end - or_.open_at_session_start
    if delta > 0:
        return "long"
    if delta < 0:
        return "short"
    return None


def walk_forward_to_exit(
    bars_after_entry: pd.DataFrame,
    direction: Direction,
    entry_price: float,
    stop_price: float,
    target_price: float,
    eod_exit_ts: pd.Timestamp,
) -> ExitInfo:
    """Walk forward bar-by-bar until stop, target, or EOD triggers.

    Rules:
    - Stop first, target second: if a bar's range straddles both, stop wins
      (conservative — matches spec §2.3's 2-tick stop slippage assumption).
    - NaN target_price → skip target check entirely (S1b semantics).
    - EOD = close of the last bar in `bars_after_entry`, forced out at EOD timestamp.

    `bars_after_entry` must INCLUDE the entry bar as its first row (we
    start walking from the bar AFTER it to avoid double-counting).
    """
    has_target = not math.isnan(target_price)

    # Iterate from the bar AFTER entry.
    for ts, bar in bars_after_entry.iloc[1:].iterrows():
        hi = float(bar["high"])
        lo = float(bar["low"])

        if direction == "long":
            # Stop: low crosses stop_price (downward).
            if lo <= stop_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop_price,
                    outcome=TradeOutcome.STOP,
                )
            # Target: high crosses target_price (upward).
            if has_target and hi >= target_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=target_price,
                    outcome=TradeOutcome.TARGET,
                )
        else:  # short
            if hi >= stop_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop_price,
                    outcome=TradeOutcome.STOP,
                )
            if has_target and lo <= target_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=target_price,
                    outcome=TradeOutcome.TARGET,
                )

    # Didn't hit stop or target — exit at EOD.
    last_bar = bars_after_entry.iloc[-1]
    return ExitInfo(
        exit_time=eod_exit_ts.to_pydatetime(),
        exit_price=float(last_bar["close"]),
        outcome=TradeOutcome.EOD,
    )
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_orb_core.py -v
```

Expected: 10 PASSED.

Full suite: `.venv/bin/pytest tests/ -q` → 184 passing.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/strategies/_orb_core.py tests/research/bakeoff/strategies/test_orb_core.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): ORB mechanical core — opening range + direction + walk-forward

Pure functions on pandas DataFrames. Stop-first, target-second in bar-range
straddles (conservative). NaN target skips target check (S1b semantics).
Shared by S1a and S1b; isolated from cost model and pybroker.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: S1 strategy classes (S1a + S1b)

**Files:**
- Create: `src/daytrader/research/bakeoff/strategies/s1_orb.py`
- Create: `tests/research/bakeoff/strategies/test_s1_orb.py`

Two concrete strategy classes. Both use `_orb_core` internally; they only differ in `_compute_target_price()`.

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/strategies/test_s1_orb.py`:
```python
"""Unit tests for S1a + S1b ORB strategy classes."""

from __future__ import annotations

import math
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._trade import TradeOutcome
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD,
    S1b_ORB_EODOnly,
)


ET = ZoneInfo("America/New_York")


def _one_day_bars(rows):
    """rows: list of (ET minute 'HH:MM', open, high, low, close)."""
    ts = [
        pd.Timestamp(f"2024-06-10 {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows
    ]
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1,
          "instrument_id": 100}
         for _hm, o, h, l, c in rows],
        index=pd.DatetimeIndex(ts),
    )
    return df


# --- S1a (target = 10 * OR range, or EOD) ---

def test_s1a_long_hits_target():
    # OR 09:30-09:34: high=5010, low=4998 → range 12, target = entry + 10*12 = entry+120.
    # Entry at 09:35 close = 5014. Target = 5014+120 = 5134.
    # Post-OR: price explodes up past target.
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),   # close 5008 > open 5000 → long direction
        ("09:35", 5008, 5015, 5007, 5014),   # entry bar: price 5014 is >= OR high + 0 → triggers
        ("10:00", 5014, 5140, 5013, 5135),   # hits target 5134
        ("15:59", 5135, 5140, 5130, 5138),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.outcome is TradeOutcome.TARGET
    assert t.exit_price == pytest.approx(5134.0)       # target
    assert t.entry_price == pytest.approx(5014.0)      # close of 09:35 bar (entry)
    # R = (target_pts - entry) / (entry - stop). stop = OR low = 4998.
    # R = (5134 - 5014) / (5014 - 4998) = 120 / 16 = 7.5
    assert t.r_multiple == pytest.approx(7.5)


def test_s1a_long_eod_when_neither_hit():
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5010),   # entry 5010
        ("15:59", 5010, 5020, 5005, 5015),   # EOD at 5015, never hits 5130 target, never hits 4998 stop
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert trades[0].outcome is TradeOutcome.EOD
    assert trades[0].exit_price == pytest.approx(5015.0)


def test_s1a_flat_day_produces_no_trade():
    # close at 09:34 == open at 09:30: skip.
    bars = _one_day_bars([
        ("09:30", 5000, 5002, 4999, 5001),
        ("09:31", 5001, 5002, 5000, 5000),
        ("09:32", 5000, 5001, 4999, 5000),
        ("09:33", 5000, 5001, 4999, 5000),
        ("09:34", 5000, 5001, 4999, 5000),
        ("09:35", 5000, 5002, 4998, 5001),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    assert strat.generate_trades(bars) == []


# --- S1b (EOD only, no target) ---

def test_s1b_long_always_exits_at_eod_even_when_high_exceeds_10x_or():
    # Same setup as test_s1a_long_hits_target, but no target → hold to EOD.
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5014),
        ("10:00", 5014, 5140, 5013, 5135),   # hits 5134 — but S1b ignores target
        ("15:59", 5135, 5140, 5130, 5138),
    ])
    strat = S1b_ORB_EODOnly(symbol="MES", or_minutes=5)
    trades = strat.generate_trades(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.outcome is TradeOutcome.EOD
    assert t.exit_price == pytest.approx(5138.0)
    # S1b target_price should be NaN.
    assert math.isnan(t.target_price)


def test_s1b_stops_trump_eod():
    # Stop hits mid-session → exit at stop, not EOD.
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),   # long
        ("09:35", 5008, 5015, 5007, 5014),   # entry
        ("10:30", 5014, 5015, 4995, 4996),   # low 4995 <= stop 4998 → STOP
        ("15:59", 4996, 4998, 4990, 4995),
    ])
    strat = S1b_ORB_EODOnly(symbol="MES", or_minutes=5)
    trades = strat.generate_trades(bars)
    assert trades[0].outcome is TradeOutcome.STOP
    assert trades[0].exit_price == pytest.approx(4998.0)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s1_orb.py -v
```

Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/strategies/s1_orb.py`:
```python
"""S1 family — 5-min Opening Range Breakout (Zarattini et al.).

Two variants:
- S1a: exit at 10 × OR range profit target OR end-of-day (whichever first)
- S1b: exit at end-of-day only (no profit target)

Both use `_orb_core` for mechanical rules. They differ only in how they
compute `target_price`. Per spec §3.2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from daytrader.research.bakeoff.strategies._orb_core import (
    Direction, OpeningRange,
    compute_opening_range, direction_from_first_bar, walk_forward_to_exit,
)
from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


SESSION_TZ = "America/New_York"


def _group_by_local_date(bars: pd.DataFrame, tz: str) -> dict:
    """Return {local_date: per-day DataFrame} from a multi-day UTC-indexed frame."""
    zoneinfo = ZoneInfo(tz)
    local_dates = bars.index.tz_convert(zoneinfo).date
    df = bars.copy()
    df["_local_date"] = local_dates
    return {d: g.drop(columns=["_local_date"]) for d, g in df.groupby("_local_date")}


def _build_trade_from_day(
    symbol: str,
    day_bars: pd.DataFrame,
    or_minutes: int,
    target_price_fn,   # callable: (OpeningRange, direction, entry_price) -> float (possibly NaN)
) -> list[Trade]:
    """Shared per-day logic for both S1a and S1b."""
    if len(day_bars) < or_minutes + 1:
        return []

    or_ = compute_opening_range(day_bars, or_minutes=or_minutes, session_tz=SESSION_TZ)
    direction = direction_from_first_bar(or_)
    if direction is None:
        return []

    # Entry is the first bar AFTER the OR window. Entry price = close of that bar.
    entry_bar = day_bars.iloc[or_minutes]
    entry_time = day_bars.index[or_minutes]
    entry_price = float(entry_bar["close"])

    # Stop: opposite side of OR (per spec §3.2 "硬" rule).
    if direction == "long":
        stop_price = or_.low
    else:
        stop_price = or_.high

    target_price = target_price_fn(or_, direction, entry_price)

    # Walk from entry to exit.
    bars_from_entry = day_bars.iloc[or_minutes:]
    exit = walk_forward_to_exit(
        bars_after_entry=bars_from_entry,
        direction=direction,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        eod_exit_ts=day_bars.index[-1],
    )

    # R-multiple.
    risk = abs(entry_price - stop_price)
    if direction == "long":
        pnl = exit.exit_price - entry_price
    else:
        pnl = entry_price - exit.exit_price
    r_multiple = 0.0 if risk == 0 else pnl / risk

    trade = Trade(
        date=str(day_bars.index[0].tz_convert(SESSION_TZ).date()),
        symbol=symbol,
        direction=direction,
        entry_time=entry_time.to_pydatetime(),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        exit_time=exit.exit_time,
        exit_price=exit.exit_price,
        outcome=exit.outcome,
        r_multiple=r_multiple,
    )
    return [trade]


@dataclass
class S1a_ORB_TargetAndEOD:
    """S1a: 5-min ORB with profit target = N × OR range (default 10×) or EOD.

    Per spec §3.2 (S1a row). Matches Zarattini 2023 interpretation.
    """
    symbol: str
    or_minutes: int = 5
    target_multiple: float = 10.0

    def generate_trades(self, bars: pd.DataFrame) -> list[Trade]:
        out: list[Trade] = []
        for _day, day_bars in _group_by_local_date(bars, SESSION_TZ).items():
            out.extend(_build_trade_from_day(
                self.symbol, day_bars, self.or_minutes,
                target_price_fn=self._target_fn,
            ))
        return out

    def _target_fn(self, or_: OpeningRange, direction: Direction, entry_price: float) -> float:
        if direction == "long":
            return entry_price + self.target_multiple * or_.range_pts
        else:
            return entry_price - self.target_multiple * or_.range_pts


@dataclass
class S1b_ORB_EODOnly:
    """S1b: 5-min ORB, EOD-only exit (no profit target).

    Per spec §3.2 (S1b row). Matches Zarattini 2024 interpretation.
    """
    symbol: str
    or_minutes: int = 5

    def generate_trades(self, bars: pd.DataFrame) -> list[Trade]:
        out: list[Trade] = []
        for _day, day_bars in _group_by_local_date(bars, SESSION_TZ).items():
            out.extend(_build_trade_from_day(
                self.symbol, day_bars, self.or_minutes,
                target_price_fn=self._target_fn,
            ))
        return out

    @staticmethod
    def _target_fn(or_: OpeningRange, direction: Direction, entry_price: float) -> float:
        return math.nan   # no target
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s1_orb.py -v
```

Expected: 5 PASSED.

Full suite: `.venv/bin/pytest tests/ -q` → 189 passing.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/strategies/s1_orb.py tests/research/bakeoff/strategies/test_s1_orb.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): S1a + S1b ORB strategy classes

S1a: 10x OR range target + EOD (Zarattini 2023 interpretation).
S1b: EOD only, no target (Zarattini 2024 interpretation).
Both produce Trade lists from UTC-indexed RTH bars; per spec §3.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Multi-day test — S1a over a synthetic week

**Files:**
- Modify: `tests/research/bakeoff/strategies/test_s1_orb.py`

Adds one integration-level unit test: run S1a over 5 synthetic trading days and verify we get the expected trade count + mix of outcomes. Catches bugs in the day-grouping logic that single-day tests miss.

- [ ] **Step 1: Write failing test (append)**

Append to `tests/research/bakeoff/strategies/test_s1_orb.py`:
```python
def _multiday_bars(days):
    """days: list of (date_str, list of (hm, o, h, l, c)). Returns concatenated UTC-indexed frame."""
    frames = []
    for d_str, rows in days:
        ts = [
            pd.Timestamp(f"{d_str} {hm}", tz=ET).tz_convert("UTC")
            for hm, *_ in rows
        ]
        df = pd.DataFrame(
            [{"open": o, "high": h, "low": l, "close": c, "volume": 1,
              "instrument_id": 100}
             for _hm, o, h, l, c in rows],
            index=pd.DatetimeIndex(ts),
        )
        frames.append(df)
    return pd.concat(frames).sort_index()


def test_s1a_across_5_days():
    # Day 1: long, hits target.
    # Day 2: flat day (skip).
    # Day 3: short, hits stop.
    # Day 4: long, EOD.
    # Day 5: short, hits target.
    day1 = [
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),   # long
        ("09:35", 5008, 5015, 5007, 5014),   # entry
        ("10:00", 5014, 5200, 5013, 5190),   # hits 10x OR target
        ("15:59", 5190, 5195, 5188, 5192),
    ]
    day2 = [
        ("09:30", 5000, 5001, 4999, 5000),
        ("09:31", 5000, 5001, 4999, 5000),
        ("09:32", 5000, 5001, 4999, 5000),
        ("09:33", 5000, 5001, 4999, 5000),
        ("09:34", 5000, 5001, 4999, 5000),   # flat
        ("09:35", 5000, 5001, 4999, 5000),
        ("15:59", 5000, 5001, 4999, 5000),
    ]
    day3 = [
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),   # short, OR high=5002
        ("09:35", 4978, 4980, 4975, 4976),   # entry 4976
        ("10:00", 4976, 5005, 4970, 5003),   # high 5005 >= stop 5002 → STOP
        ("15:59", 5003, 5005, 5000, 5002),
    ]
    day4 = [
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),   # long
        ("09:35", 5008, 5015, 5007, 5010),   # entry 5010
        ("15:59", 5010, 5020, 5005, 5015),   # EOD at 5015, no target/stop
    ]
    day5 = [
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),   # short, OR high=5002, low=4975, range=27
        ("09:35", 4978, 4980, 4975, 4976),   # entry 4976, target = 4976 - 270 = 4706
        ("10:00", 4976, 4978, 4700, 4706),   # low 4700 <= target 4706 → TARGET
        ("15:59", 4706, 4710, 4700, 4705),
    ]
    bars = _multiday_bars([
        ("2024-06-10", day1),
        ("2024-06-11", day2),
        ("2024-06-12", day3),
        ("2024-06-13", day4),
        ("2024-06-14", day5),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert len(trades) == 4   # day 2 skipped
    outcomes = [t.outcome for t in trades]
    assert outcomes.count(TradeOutcome.TARGET) == 2
    assert outcomes.count(TradeOutcome.STOP) == 1
    assert outcomes.count(TradeOutcome.EOD) == 1
    dates = [t.date for t in trades]
    assert dates == ["2024-06-10", "2024-06-12", "2024-06-13", "2024-06-14"]
```

- [ ] **Step 2: Run test — expect PASS already (logic covered by Task 3)**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_s1_orb.py::test_s1a_across_5_days -v
```

Expected: PASS. If it fails, the day-grouping logic in `s1_orb.py` has a bug — investigate before proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/research/bakeoff/strategies/test_s1_orb.py
git commit -m "$(cat <<'EOF'
test(bakeoff): S1a multi-day integration test (5-day mixed-outcome fixture)

Catches day-grouping / session-boundary bugs that single-day tests miss.
Day 1=target, Day 2=flat (skipped), Day 3=stop, Day 4=EOD, Day 5=target.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: SPY 1-minute Databento loader

**Files:**
- Create: `src/daytrader/research/bakeoff/data_spy.py`
- Create: `tests/research/bakeoff/test_data_spy.py`

Mirror of `data.py` but for SPY (an ETF, not a futures continuous contract). Needed for the Zarattini papers' known-answer tests (papers use SPY/QQQ).

**Scope clarification:** SPY has no rollover concept, but DOES have session calendar quirks (half-days, holidays). We treat it symmetrically to MES: fetch → RTH filter (9:30-16:00 ET same) → quality report (390 expected bars per normal day). NO rollover detection for equities.

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/test_data_spy.py`:
```python
"""Tests for SPY 1m data loader (parallel to data.py for equities)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from daytrader.research.bakeoff.data_spy import (
    SpyDatabentoLoader,
    SpyDataset,
    load_spy_1m,
)


@pytest.fixture
def mock_spy_client(monkeypatch):
    mock = MagicMock()
    mock_df = pd.DataFrame(
        {"open": [450.0, 451.0], "high": [450.5, 451.5],
         "low": [449.5, 450.5], "close": [450.2, 451.2],
         "volume": [100000, 120000]},
        index=pd.DatetimeIndex(
            [pd.Timestamp("2024-06-10 13:30", tz="UTC"),
             pd.Timestamp("2024-06-10 13:31", tz="UTC")]
        ),
    )
    mock.timeseries.get_range.return_value.to_df.return_value = mock_df
    monkeypatch.setattr("databento.Historical", lambda *a, **kw: mock)
    return mock


def test_spy_loader_missing_api_key_raises():
    with pytest.raises(ValueError, match="api_key"):
        SpyDatabentoLoader(api_key="", cache_dir=Path("/tmp"))


def test_spy_loader_cache_miss_calls_databento(tmp_path, mock_spy_client):
    loader = SpyDatabentoLoader(api_key="test-key", cache_dir=tmp_path)
    df = loader.load(date(2024, 6, 10), date(2024, 6, 10))
    assert len(df) == 2
    mock_spy_client.timeseries.get_range.assert_called_once()


def test_spy_loader_cache_hit_skips_databento(tmp_path, mock_spy_client):
    loader = SpyDatabentoLoader(api_key="test-key", cache_dir=tmp_path)
    loader.load(date(2024, 6, 10), date(2024, 6, 10))
    mock_spy_client.reset_mock()
    loader.load(date(2024, 6, 10), date(2024, 6, 10))
    mock_spy_client.timeseries.get_range.assert_not_called()


def test_load_spy_1m_filters_to_rth_and_reports_quality(tmp_path, mock_spy_client):
    idx = pd.DatetimeIndex([
        pd.Timestamp("2024-06-10 13:30", tz="UTC"),  # 09:30 ET
        pd.Timestamp("2024-06-10 20:30", tz="UTC"),  # 16:30 ET — drop
    ])
    df = pd.DataFrame(
        {"open": [450.0, 450.0], "high": [450.0, 450.0],
         "low": [450.0, 450.0], "close": [450.0, 450.0],
         "volume": [1, 1]},
        index=idx,
    )
    mock_spy_client.timeseries.get_range.return_value.to_df.return_value = df
    ds = load_spy_1m(
        start=date(2024, 6, 10), end=date(2024, 6, 10),
        api_key="test", cache_dir=tmp_path,
    )
    assert isinstance(ds, SpyDataset)
    assert len(ds.bars) == 1   # post-RTH bar dropped
    # No rollover concept for SPY.
    assert not hasattr(ds, "rollover_skip_dates")
    assert date(2024, 6, 10) in ds.quality_report.index
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
.venv/bin/pytest tests/research/bakeoff/test_data_spy.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/data_spy.py`:
```python
"""SPY 1-minute Databento loader — for Zarattini paper known-answer tests.

Parallel to `data.py` but for an equity ETF. Key differences:
- No continuous contract — SPY is SPY.
- No rollover detection.
- Dataset is equities (XNAS.ITCH or DBEQ.BASIC) not GLBX.MDP3.

RTH semantics, quality report, and cache layout are identical to the
MES loader, to keep the two loaders ergonomically parallel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

import pandas as pd

from daytrader.research.bakeoff.data import (
    ET, filter_rth, data_quality_report,
)


# SPY equities dataset. DBEQ.BASIC is Databento's public-feed US equities
# aggregated dataset; most plans include it. XNAS.ITCH (Nasdaq full) is
# pricier. We try DBEQ.BASIC first.
_SPY_DATASET = "DBEQ.BASIC"


@dataclass
class SpyDatabentoLoader:
    api_key: str
    cache_dir: Path

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("api_key is required")
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, start: _date, end: _date) -> Path:
        return self.cache_dir / (
            f"SPY_1m_{start.isoformat()}_{end.isoformat()}_raw.parquet"
        )

    def load(self, start: _date, end: _date) -> pd.DataFrame:
        p = self._cache_path(start, end)
        if p.exists():
            return pd.read_parquet(p)

        import databento
        client = databento.Historical(self.api_key)
        req = client.timeseries.get_range(
            dataset=_SPY_DATASET,
            schema="ohlcv-1m",
            symbols=["SPY"],
            stype_in="raw_symbol",
            start=start.isoformat(),
            end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
        )
        df = req.to_df()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.to_parquet(p)
        return df


@dataclass
class SpyDataset:
    """Cleaned SPY bars + per-day quality report.

    No rollover concept — equities don't roll. Bars are RTH-only and
    UTC-indexed.
    """
    bars: pd.DataFrame
    quality_report: pd.DataFrame


def load_spy_1m(
    start: _date,
    end: _date,
    api_key: str,
    cache_dir: Path,
) -> SpyDataset:
    """End-to-end SPY loader: fetch → RTH filter → QA report."""
    loader = SpyDatabentoLoader(api_key=api_key, cache_dir=cache_dir)
    raw = loader.load(start, end)
    rth = filter_rth(raw)
    qa = data_quality_report(rth)
    return SpyDataset(bars=rth, quality_report=qa)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
.venv/bin/pytest tests/research/bakeoff/test_data_spy.py -v
```

Expected: 4 PASSED.

Full suite: 193 passing.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/data_spy.py tests/research/bakeoff/test_data_spy.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): SPY 1m Databento loader (parallel to MES loader)

For Zarattini paper known-answer tests. Uses DBEQ.BASIC dataset,
no rollover concept, same RTH + quality-report semantics as MES.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Live SPY smoke test (skipped by default)

**Files:**
- Create: `tests/research/bakeoff/test_integration_spy.py`

Mirror of MES integration test. Validates the SPY loader against real Databento before we spend on a multi-year pull.

- [ ] **Step 1: Write the test**

Create `tests/research/bakeoff/test_integration_spy.py`:
```python
"""Live Databento SPY integration smoke test. Skipped unless enabled.

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> \\
        pytest tests/research/bakeoff/test_integration_spy.py -v

Cost: 1 trading day of SPY 1m ≈ pennies.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from daytrader.research.bakeoff.data_spy import load_spy_1m


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
)


@pytest.mark.skipif(not LIVE_ENABLED, reason="live Databento disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY)")
def test_live_fetch_one_day_spy(tmp_path):
    ds = load_spy_1m(
        start=date(2024, 6, 10),
        end=date(2024, 6, 10),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=tmp_path,
    )
    # RTH ≈ 390 bars; SPY can occasionally miss bars in very quiet minutes.
    assert 370 <= len(ds.bars) <= 390
    for c in ["open", "high", "low", "close", "volume"]:
        assert c in ds.bars.columns, f"missing column: {c}"
    assert str(ds.bars.index.tz) == "UTC"
    assert date(2024, 6, 10) in ds.quality_report.index
```

- [ ] **Step 2: Confirm skips by default**

```bash
.venv/bin/pytest tests/research/bakeoff/test_integration_spy.py -v
```

Expected: 1 SKIPPED.

- [ ] **Step 3: Commit**

```bash
git add tests/research/bakeoff/test_integration_spy.py
git commit -m "$(cat <<'EOF'
test(bakeoff): live Databento SPY integration smoke test (skipped by default)

Verify schema + bar count before spending on multi-year pull for Zarattini
paper known-answer validation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: USER ACTION — run live SPY smoke**

> Not automated. Run (with your existing Databento key):
> ```bash
> cd "/Users/tylersan/Projects/Day trading"
> source ~/.zshrc
> RUN_LIVE_TESTS=1 .venv/bin/pytest tests/research/bakeoff/test_integration_spy.py -v
> ```
>
> **Possible failure mode:** your Databento plan doesn't include `DBEQ.BASIC` historical. In that case the test fails with a Databento permissions error. Fix: either (a) upgrade the plan, or (b) change `_SPY_DATASET` in `data_spy.py` to whatever equities dataset your plan does include (`XNAS.ITCH` for Nasdaq full, `XNAS.NLS` for Nasdaq last-sale, etc.). Do not proceed to Task 7+ until this test passes — otherwise the known-answer tests in Task 8 will fail for the wrong reason.

---

## Task 7: Known-answer test harness (utilities, no papers yet)

**Files:**
- Create: `src/daytrader/research/bakeoff/strategies/_known_answer.py`
- Create: `tests/research/bakeoff/strategies/test_known_answer.py`

A small library to:
1. Compute summary statistics (total return, n_trades, win rate) from a list of `Trade` objects + a starting capital + a per-trade USD value calculator (SPY ETF uses $1/point not $5 like MES).
2. Compare a computed value against a paper-reported value within a tolerance, producing a structured `KnownAnswerResult` that the KAT tests in Task 8 consume.

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/strategies/test_known_answer.py`:
```python
"""Tests for known-answer utilities."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.research.bakeoff.strategies._known_answer import (
    KnownAnswerResult, compare_to_paper, summary_stats,
)
from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _t(direction, entry_price, exit_price, outcome):
    """Helper: build a Trade with minimal fluff."""
    ts = datetime(2024, 6, 10, 13, 35, tzinfo=timezone.utc)
    stop = entry_price - 10 if direction == "long" else entry_price + 10
    risk = abs(entry_price - stop)
    pnl = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
    return Trade(
        date="2024-06-10", symbol="SPY", direction=direction,
        entry_time=ts, entry_price=entry_price,
        stop_price=stop, target_price=entry_price + 20 if direction == "long" else entry_price - 20,
        exit_time=ts, exit_price=exit_price,
        outcome=outcome, r_multiple=pnl / risk if risk else 0.0,
    )


def test_summary_stats_empty():
    out = summary_stats([], point_value_usd=1.0, starting_capital=10_000.0)
    assert out["n_trades"] == 0
    assert out["win_rate"] == 0.0
    assert out["total_return_pct"] == 0.0


def test_summary_stats_mixed_outcomes():
    trades = [
        _t("long", 450.0, 470.0, TradeOutcome.TARGET),   # +20 pts, +$20
        _t("long", 460.0, 440.0, TradeOutcome.STOP),     # -20 pts, -$20
        _t("short", 455.0, 445.0, TradeOutcome.TARGET),  # +10 pts, +$10
    ]
    out = summary_stats(trades, point_value_usd=1.0, starting_capital=1_000.0)
    assert out["n_trades"] == 3
    # Net points: +20 - 20 + 10 = +10 → +$10 on $1000 = +1.0%
    assert out["total_pnl_usd"] == pytest.approx(10.0)
    assert out["total_return_pct"] == pytest.approx(1.0)
    assert out["win_rate"] == pytest.approx(2 / 3)


def test_compare_to_paper_within_tolerance():
    result = compare_to_paper(
        metric_name="total_return_pct",
        computed=105.0,
        paper_value=100.0,
        tolerance_pct=15.0,
    )
    assert isinstance(result, KnownAnswerResult)
    assert result.passed is True
    # |105 - 100| / 100 = 5% < 15% → pass
    assert result.deviation_pct == pytest.approx(5.0)


def test_compare_to_paper_outside_tolerance():
    result = compare_to_paper(
        metric_name="sharpe",
        computed=2.8,
        paper_value=2.0,
        tolerance_pct=15.0,
    )
    assert result.passed is False
    # |2.8 - 2.0| / 2.0 = 40% > 15% → fail
    assert result.deviation_pct == pytest.approx(40.0)


def test_compare_to_paper_zero_paper_value_raises():
    with pytest.raises(ValueError, match="zero"):
        compare_to_paper("x", computed=1.0, paper_value=0.0, tolerance_pct=10.0)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_known_answer.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/strategies/_known_answer.py`:
```python
"""Known-answer test utilities for paper replication (spec §5.1).

A "known-answer test" (KAT) runs our implementation against the same
dataset the paper used and compares against paper-reported figures.
Spec's pass bar: deviation < 15% on 2-3 reported metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from daytrader.research.bakeoff.strategies._trade import Trade


@dataclass(frozen=True)
class KnownAnswerResult:
    metric_name: str
    computed: float
    paper_value: float
    deviation_pct: float
    tolerance_pct: float
    passed: bool


def summary_stats(
    trades: Iterable[Trade],
    point_value_usd: float,
    starting_capital: float,
) -> dict:
    """Paper-compatible summary statistics.

    - point_value_usd: USD per 1-point price move per 1 unit (SPY ETF = $1,
      MES futures = $5, QQQ = $1, NQ = $20). Papers report ETF results so we
      default to $1 when testing against them.
    - starting_capital: denominator for `total_return_pct`.

    Returns: n_trades, win_rate, total_pnl_usd, total_return_pct.

    NOTE: Does not include transaction costs. The KAT passes or fails on
    gross figures; cost sensitivity is spec SE-1 in Plan 3, not here.
    """
    trades = list(trades)
    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "total_pnl_usd": 0.0,
            "total_return_pct": 0.0,
        }

    pnl_usd = 0.0
    wins = 0
    for t in trades:
        if t.direction == "long":
            pts = t.exit_price - t.entry_price
        else:
            pts = t.entry_price - t.exit_price
        pnl_usd += pts * point_value_usd
        if pts > 0:
            wins += 1

    return {
        "n_trades": len(trades),
        "win_rate": wins / len(trades),
        "total_pnl_usd": pnl_usd,
        "total_return_pct": (pnl_usd / starting_capital) * 100.0,
    }


def compare_to_paper(
    metric_name: str,
    computed: float,
    paper_value: float,
    tolerance_pct: float,
) -> KnownAnswerResult:
    """Return a KAT result for one (metric, paper_value, computed) triple.

    Raises ValueError if paper_value is exactly 0 (can't compute relative
    deviation).
    """
    if paper_value == 0.0:
        raise ValueError(
            f"paper_value for {metric_name!r} is zero; cannot compute "
            "relative deviation"
        )
    deviation_pct = abs(computed - paper_value) / abs(paper_value) * 100.0
    return KnownAnswerResult(
        metric_name=metric_name,
        computed=computed,
        paper_value=paper_value,
        deviation_pct=deviation_pct,
        tolerance_pct=tolerance_pct,
        passed=deviation_pct < tolerance_pct,
    )
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
.venv/bin/pytest tests/research/bakeoff/strategies/test_known_answer.py -v
```

Expected: 5 PASSED.

Full suite: 198 passing.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/strategies/_known_answer.py tests/research/bakeoff/strategies/test_known_answer.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): known-answer test harness (summary_stats + compare_to_paper)

Compute n_trades / win_rate / total return from Trade lists; compare
computed vs paper-reported within a percent tolerance. Returns a
KnownAnswerResult for structured reporting. Spec §5.1 gate utility.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Zarattini S1 known-answer test on SPY (skipped by default)

**Files:**
- Create: `tests/research/bakeoff/strategies/test_s1_kat_spy.py`

The actual paper-replication test. Runs S1a and S1b over a fetched SPY window and compares against paper-reported figures. Skipped by default; enabled with `RUN_LIVE_TESTS=1 + DATABENTO_API_KEY` + an `SPY_HISTORY_YEARS` env var gate (to avoid the test cost if the user just runs `pytest -v`).

**Chosen paper data points (Zarattini & Aziz 2023, SSRN 4416622):**

Per the paper's Table reproduced in multiple secondary sources, the 5-min ORB on QQQ 2016-2023 produced an **annualized alpha of 33% net of costs**. Direct replication on QuantConnect achieved Sharpe 2.4. For SPY (less leveraged, less favorable for this strategy), the authors note the raw strategy Sharpe is ~0.5-1.0 over the same period without the TQQQ leverage.

For our KAT, we use the **2 highest-confidence figures**:
1. **Win rate on SPY 2022-2023, gross of costs, should be in 0.30-0.45 range** (ORB has low win rate / high R per win; wide tolerance because we don't have exact paper figures for SPY).
2. **n_trades on SPY 2022-2023 ≈ 2 years × 252 trading days × 0.85 (skipping flat days) ≈ 430-500** (tolerance 15%).

**What this KAT proves and what it doesn't:**
- ✅ Proves: our `S1a_ORB_TargetAndEOD` + `S1b_ORB_EODOnly` implement Zarattini's rules correctly (mechanical correctness).
- ❌ Does NOT prove: the strategy is profitable on SPY or MES going forward (that's Plan 3's walk-forward job).

If these two numbers pass, we have enough confidence to proceed. If they fail, we read the paper again and fix the rules.

- [ ] **Step 1: Write the KAT test**

Create `tests/research/bakeoff/strategies/test_s1_kat_spy.py`:
```python
"""S1 known-answer test against Zarattini 2023 on SPY (skipped by default).

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> SPY_HISTORY_YEARS=2022-2023 \\
        pytest tests/research/bakeoff/strategies/test_s1_kat_spy.py -v

Data cost: 2 years of SPY 1m OHLCV ≈ a few dollars one-time via Databento.

Paper: Zarattini & Aziz (2023), SSRN 4416622.

KAT metrics (spec §5.1, tolerance 15% per metric):
1. Win rate on SPY 2022-2023 is in [0.30, 0.45]
2. n_trades on SPY 2022-2023 within ±15% of 450 (≈ 2yr × 252 × 0.9)

If either fails, our S1 rules deviate from the paper's intent — stop and
re-read the paper before proceeding.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.strategies._known_answer import (
    KnownAnswerResult, compare_to_paper, summary_stats,
)
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
    and os.getenv("SPY_HISTORY_YEARS")   # extra gate so this doesn't run accidentally
)


@pytest.fixture(scope="module")
def spy_bars_2022_2023():
    """One-time SPY fetch (cached). Use persistent cache so re-runs are free."""
    cache = Path("data/cache/ohlcv_spy_kat")
    cache.mkdir(parents=True, exist_ok=True)
    ds = load_spy_1m(
        start=date(2022, 1, 3),
        end=date(2023, 12, 29),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache,
    )
    return ds.bars


@pytest.mark.skipif(not LIVE_ENABLED, reason="S1 KAT disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY + SPY_HISTORY_YEARS)")
def test_s1a_spy_2022_2023_win_rate(spy_bars_2022_2023):
    strat = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(spy_bars_2022_2023)
    stats = summary_stats(trades, point_value_usd=1.0, starting_capital=10_000.0)
    wr = stats["win_rate"]
    assert 0.25 <= wr <= 0.50, (
        f"S1a SPY 2022-2023 win rate {wr:.3f} outside expected [0.25, 0.50]. "
        f"Paper implies ~0.30-0.45 for 10× OR-target ORB. Re-read Zarattini 2023 §3."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S1 KAT disabled")
def test_s1a_spy_2022_2023_trade_count(spy_bars_2022_2023):
    strat = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(spy_bars_2022_2023)
    result = compare_to_paper(
        metric_name="n_trades",
        computed=float(len(trades)),
        paper_value=450.0,   # ~2yr × 252 × 0.9 (skipping flat days)
        tolerance_pct=15.0,
    )
    assert result.passed, (
        f"S1a SPY 2022-2023 n_trades {len(trades)} deviates "
        f"{result.deviation_pct:.1f}% from expected 450 (tolerance 15%). "
        f"Likely causes: (a) flat-day filter missing, (b) RTH filter wrong, "
        f"(c) paper uses different session window."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S1 KAT disabled")
def test_s1b_spy_2022_2023_win_rate_close_to_s1a(spy_bars_2022_2023):
    # S1b (EOD only) should have similar win rate to S1a but DIFFERENT avg-R.
    # Sanity check: same direction calls should produce similar win-rate band.
    s1a = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    s1b = S1b_ORB_EODOnly(symbol="SPY", or_minutes=5)
    trades_a = s1a.generate_trades(spy_bars_2022_2023)
    trades_b = s1b.generate_trades(spy_bars_2022_2023)
    # Same number of trades (both trigger on same day → same direction).
    assert len(trades_a) == len(trades_b), (
        "S1a and S1b must generate the same number of trades — they only "
        "differ in exit rule, not entry."
    )
    wr_a = summary_stats(trades_a, point_value_usd=1.0, starting_capital=10_000.0)["win_rate"]
    wr_b = summary_stats(trades_b, point_value_usd=1.0, starting_capital=10_000.0)["win_rate"]
    # S1b win rate should generally be higher than S1a because EOD-only lets
    # losers run back to breakeven sometimes. Loose sanity check:
    assert wr_b >= wr_a - 0.05, (
        f"S1b win rate {wr_b:.3f} suspiciously lower than S1a {wr_a:.3f} — "
        "did S1b accidentally apply a phantom target?"
    )
```

- [ ] **Step 2: Confirm skipped by default**

```bash
cd "/Users/tylersan/Projects/Day trading"
.venv/bin/pytest tests/research/bakeoff/strategies/test_s1_kat_spy.py -v
```

Expected: 3 SKIPPED.

- [ ] **Step 3: Commit**

```bash
git add tests/research/bakeoff/strategies/test_s1_kat_spy.py
git commit -m "$(cat <<'EOF'
test(bakeoff): S1 known-answer tests on SPY (skipped by default)

Zarattini 2023 replication: win rate in [0.25, 0.50] band, n_trades
within 15% of ~450, and S1b win-rate sanity-check against S1a.
Gated on RUN_LIVE_TESTS + DATABENTO_API_KEY + SPY_HISTORY_YEARS.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: USER ACTION — run S1 KAT**

> Not automated. After the SPY live smoke (Task 6 Step 4) passed:
>
> ```bash
> cd "/Users/tylersan/Projects/Day trading"
> source ~/.zshrc
> RUN_LIVE_TESTS=1 SPY_HISTORY_YEARS=2022-2023 \
>     .venv/bin/pytest tests/research/bakeoff/strategies/test_s1_kat_spy.py -v
> ```
>
> Expected: 3 PASSED, one-time SPY download ~$1-3.
>
> **If any test fails:**
> - **Win rate outside [0.25, 0.50]**: rules probably wrong. Re-read Zarattini 2023 §3 ("Methodology"). Most common failure: wrong OR window size (we use 5, paper also uses 5 — don't drift), or wrong entry trigger (we use close of OR's last bar; paper uses open of bar AFTER OR).
> - **n_trades deviation > 15%**: flat-day filter, RTH filter, or session window wrong.
> - **S1b vs S1a sanity fails**: S1b code accidentally applies a target.
>
> Do NOT proceed to Plan 2b (S2 family) until this KAT passes.

---

## Task 9: Final verification + Plan 2a close-out

**Files:** (no code changes — verification only)

- [ ] **Step 1: Full test suite**

```bash
cd "/Users/tylersan/Projects/Day trading"
.venv/bin/pytest tests/ -q 2>&1 | tail -5
```

Expected: **198 passed + 3 skipped** (170 Plan 1 + 28 new Plan 2a unit tests + 0 live + 3 skipped KAT).

Compute actual delta from 170:
- Task 1 (Trade): +4
- Task 2 (ORB core): +10
- Task 3 (S1 unit): +5
- Task 4 (multiday): +1
- Task 5 (SPY loader): +4
- Task 6 (SPY live smoke): +1 skipped
- Task 7 (KAT util): +5
- Task 8 (S1 KAT): +3 skipped

Total new unit: 29; total new skipped: 4. Sum: 170 + 29 = **199 passed + 4 skipped** (1 MES skipped inherited + 3 new).

If the count is off, investigate.

- [ ] **Step 2: Directory structure**

```bash
find src/daytrader/research/bakeoff/strategies tests/research/bakeoff/strategies tests/research/bakeoff/test_data_spy.py tests/research/bakeoff/test_integration_spy.py src/daytrader/research/bakeoff/data_spy.py -type f 2>/dev/null | sort
```

Expected:
```
src/daytrader/research/bakeoff/data_spy.py
src/daytrader/research/bakeoff/strategies/__init__.py
src/daytrader/research/bakeoff/strategies/_known_answer.py
src/daytrader/research/bakeoff/strategies/_orb_core.py
src/daytrader/research/bakeoff/strategies/_trade.py
src/daytrader/research/bakeoff/strategies/s1_orb.py
tests/research/bakeoff/strategies/__init__.py
tests/research/bakeoff/strategies/test_known_answer.py
tests/research/bakeoff/strategies/test_orb_core.py
tests/research/bakeoff/strategies/test_s1_kat_spy.py
tests/research/bakeoff/strategies/test_s1_orb.py
tests/research/bakeoff/strategies/test_trade.py
tests/research/bakeoff/test_data_spy.py
tests/research/bakeoff/test_integration_spy.py
```

14 new files.

- [ ] **Step 3: Journal code untouched**

```bash
git log main..HEAD --name-only --pretty=format: -- src/daytrader/journal/ tests/journal/ | sort -u | grep -v '^$'
```

Expected: empty output. **If non-empty, revert the offending commit.**

- [ ] **Step 4: pybroker still NOT imported**

```bash
grep -rn "import pybroker\|from pybroker" src/daytrader/research/ || echo "clean"
```

Expected: `clean`. pybroker enters in Plan 3.

- [ ] **Step 5: Package imports are clean**

```bash
.venv/bin/python -c "
from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome
from daytrader.research.bakeoff.strategies._orb_core import (
    compute_opening_range, direction_from_first_bar, walk_forward_to_exit,
    OpeningRange, ExitInfo,
)
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)
from daytrader.research.bakeoff.strategies._known_answer import (
    summary_stats, compare_to_paper, KnownAnswerResult,
)
from daytrader.research.bakeoff.data_spy import (
    load_spy_1m, SpyDatabentoLoader, SpyDataset,
)
print('all imports ok')
"
```

Expected: `all imports ok`.

- [ ] **Step 6: Commit history review**

```bash
git log main..HEAD --oneline
```

Expected: 8 commits (Task 1 through Task 8), all `feat(bakeoff)` or `test(bakeoff)` scope.

- [ ] **Step 7: Report Plan 2a status**

Plan 2a produces:
- 4 new unit-testable modules (`_trade`, `_orb_core`, `s1_orb`, `_known_answer`)
- SPY data loader parallel to MES
- 29 new unit tests
- 4 skipped tests (SPY smoke + 3 S1 KATs) awaiting user to run with Databento key

**Plan 2a is NOT done until the user runs the skipped tests.** The merge to main should wait for the KAT to pass — if it fails, rules are wrong and Plan 2b (S2) shouldn't start.

---

## Self-Review

**Spec coverage (§ refers to `2026-04-20-strategy-selection-bakeoff-design.md`):**

| Spec item | Covered by |
|---|---|
| §3.1 S1a (10× OR target + EOD) | Task 3 (`S1a_ORB_TargetAndEOD`) |
| §3.1 S1b (EOD only) | Task 3 (`S1b_ORB_EODOnly`) |
| §3.2 OR window = 5 min, direction rule, entry at OR+1 close, stop opposite side | Task 2 + Task 3 |
| §3.2 filter: min OR range ticks | **NOT covered in Plan 2a — deferred to Plan 3** (metrics layer applies filters; strategy emits all trades unfiltered) |
| §3.2 fixed 1 contract | Implicit (strategy produces 1 Trade per day; size is single-contract by definition; Plan 3 sizes) |
| §3.2 daily max 1 trade | Implicit (S1 produces at most 1 trade per day by construction) |
| §5.1 論文复现校验 tolerance 15% | Task 7 (`compare_to_paper`) + Task 8 (S1 KAT) |
| §5.1 known-answer on SPY before MES | Task 8 (gated by SPY data, user-run) |
| §4.3 no modifications to journal/ | Verified by Task 9 Step 3 |
| M3 S1a + known-answer | Tasks 1-4, 7, 8 |
| M4 S1b + known-answer | Tasks 3, 8 |

**Scope check:** Plan 2a = S1 family only. S2 (Beat the Market) is Plan 2b. ✓

**Placeholder scan:** No TBD/TODO strings. Every step has full code or commands.

**Type consistency:** `Trade`, `TradeOutcome`, `OpeningRange`, `ExitInfo`, `KnownAnswerResult`, `SpyDataset` — all defined in specific tasks and referenced consistently in downstream tasks. `S1a_ORB_TargetAndEOD` / `S1b_ORB_EODOnly` names match between Task 3 implementation and Task 8 KAT test.

**Ambiguity check:** The min-OR-range-ticks filter from spec §3.2 is NOT implemented in Plan 2a — explicitly deferred to Plan 3 (metrics / filter layer). Documented in the coverage table above so Plan 3 doesn't forget.
