# Sanity-Floor Backtest — Implementation Plan (Phase B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build offline sanity-floor backtester that accepts a YAML setup definition + 90 days of 1-minute OHLCV, runs bar-by-bar simulation, and writes a verdict. Goal is **rejecting obviously-broken setups** (n<30 or avg_r<0), not proving edge.

**Prerequisite:** Phase A plan complete (`2026-04-16-daytrading-system-foundation.md`).

**Architecture:** New `daytrader.journal.sanity_floor` sub-package. Setup YAML files live in `docs/trading/setups/`. Data loaded from yfinance, cached to `data/cache/ohlcv/`. Runner orchestrates data load + engine + verdict write.

**Spec:** `docs/superpowers/specs/2026-04-16-daytrading-system-design.md` §6.

---

## Task 9: Setup YAML parser + validator

**Files:**
- Create: `src/daytrader/journal/sanity_floor/setup_yaml.py`
- Create: `tests/journal/sanity_floor/test_setup_yaml.py`
- Create: `docs/trading/setups/example_opening_range_breakout.yaml`

- [ ] **Step 1: Write example setup YAML**

`docs/trading/setups/example_opening_range_breakout.yaml`:

```yaml
name: opening_range_breakout
version: v1
symbols: [MES, MNQ]
session_window:
  start: "09:30 America/New_York"
  end: "11:30 America/New_York"
opening_range:
  duration_minutes: 15
entry:
  direction: long_if_above_or_short_if_below
  trigger: price_closes_beyond_or_by_ticks
  ticks: 2
stop:
  rule: opposite_side_of_or
  offset_ticks: 2
target:
  rule: multiple_of_or_range
  multiple: 2.0
filters:
  - no_entry_after: "11:00 America/New_York"
  - min_or_range_ticks: 8
  - max_or_range_ticks: 40
  - skip_if_event: [fomc, cpi, nfp]
```

- [ ] **Step 2: Write failing tests**

`tests/journal/sanity_floor/test_setup_yaml.py`:

```python
"""Tests for setup YAML parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.journal.sanity_floor.setup_yaml import (
    SetupDefinition, SetupYamlError, load_setup_yaml,
)

_VALID = """
name: orb
version: v1
symbols: [MES, MNQ]
session_window:
  start: "09:30 America/New_York"
  end: "11:30 America/New_York"
opening_range:
  duration_minutes: 15
entry:
  direction: long_if_above_or_short_if_below
  trigger: price_closes_beyond_or_by_ticks
  ticks: 2
stop:
  rule: opposite_side_of_or
  offset_ticks: 2
target:
  rule: multiple_of_or_range
  multiple: 2.0
filters: []
"""


def test_load_valid(tmp_path: Path):
    p = tmp_path / "orb.yaml"
    p.write_text(_VALID)
    s = load_setup_yaml(p)
    assert s.name == "orb"
    assert "MES" in s.symbols
    assert s.opening_range["duration_minutes"] == 15
    assert s.entry["ticks"] == 2


def test_reject_missing_required_field(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("name: orb\nversion: v1\n")
    with pytest.raises(SetupYamlError):
        load_setup_yaml(p)


def test_reject_unknown_symbol(tmp_path: Path):
    content = _VALID.replace("[MES, MNQ]", "[AAPL]")
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(SetupYamlError, match="symbol"):
        load_setup_yaml(p)


def test_reject_vague_rule(tmp_path: Path):
    content = _VALID.replace(
        "trigger: price_closes_beyond_or_by_ticks",
        "trigger: strong_breakout_with_confirmation",
    )
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(SetupYamlError, match="trigger"):
        load_setup_yaml(p)


def test_reject_non_integer_ticks(tmp_path: Path):
    content = _VALID.replace("ticks: 2", "ticks: 2.5")
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(SetupYamlError):
        load_setup_yaml(p)
```

- [ ] **Step 3: Implement `src/daytrader/journal/sanity_floor/setup_yaml.py`**

```python
"""Setup YAML schema + strict parser.

Philosophy: every rule must be mechanically executable. Reject vague words
and unknown rule names up front to prevent 'judgment calls' leaking into
the backtester.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ALLOWED_SYMBOLS = {"MES", "MNQ", "MGC"}

ALLOWED_TRIGGERS = {
    "price_closes_beyond_or_by_ticks",
    "price_wicks_beyond_or_by_ticks",
    "bar_close_above_prior_high",
    "bar_close_below_prior_low",
}

ALLOWED_STOP_RULES = {
    "opposite_side_of_or",
    "fixed_ticks",
    "atr_multiple",
}

ALLOWED_TARGET_RULES = {
    "multiple_of_or_range",
    "fixed_ticks",
    "atr_multiple",
    "prior_session_extreme",
}

ALLOWED_ENTRY_DIRECTIONS = {
    "long_if_above_or_short_if_below",
    "long_only",
    "short_only",
}

REQUIRED_TOP_KEYS = {
    "name", "version", "symbols",
    "session_window", "entry", "stop", "target",
}


class SetupYamlError(ValueError):
    pass


@dataclass
class SetupDefinition:
    name: str
    version: str
    symbols: list[str]
    session_window: dict[str, Any]
    opening_range: dict[str, Any] | None
    entry: dict[str, Any]
    stop: dict[str, Any]
    target: dict[str, Any]
    filters: list[dict[str, Any]]
    raw: dict[str, Any]


def _req(d: dict, key: str, context: str) -> Any:
    if key not in d:
        raise SetupYamlError(f"{context} missing required key: {key}")
    return d[key]


def load_setup_yaml(path: Path) -> SetupDefinition:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise SetupYamlError(f"{path}: top-level must be a mapping")

    missing = REQUIRED_TOP_KEYS - set(data.keys())
    if missing:
        raise SetupYamlError(f"{path}: missing keys: {sorted(missing)}")

    symbols = data["symbols"]
    if not isinstance(symbols, list) or not symbols:
        raise SetupYamlError(f"{path}: symbols must be non-empty list")
    for s in symbols:
        if s not in ALLOWED_SYMBOLS:
            raise SetupYamlError(
                f"{path}: unknown symbol {s!r} (allowed: {sorted(ALLOWED_SYMBOLS)})"
            )

    session = data["session_window"]
    _req(session, "start", "session_window")
    _req(session, "end", "session_window")

    entry = data["entry"]
    direction = _req(entry, "direction", "entry")
    if direction not in ALLOWED_ENTRY_DIRECTIONS:
        raise SetupYamlError(
            f"entry.direction {direction!r} not in {sorted(ALLOWED_ENTRY_DIRECTIONS)}"
        )
    trigger = _req(entry, "trigger", "entry")
    if trigger not in ALLOWED_TRIGGERS:
        raise SetupYamlError(
            f"entry.trigger {trigger!r} not in {sorted(ALLOWED_TRIGGERS)}"
        )
    ticks = entry.get("ticks", 0)
    if not isinstance(ticks, int):
        raise SetupYamlError(f"entry.ticks must be integer, got {type(ticks).__name__}")

    stop = data["stop"]
    stop_rule = _req(stop, "rule", "stop")
    if stop_rule not in ALLOWED_STOP_RULES:
        raise SetupYamlError(
            f"stop.rule {stop_rule!r} not in {sorted(ALLOWED_STOP_RULES)}"
        )

    target = data["target"]
    target_rule = _req(target, "rule", "target")
    if target_rule not in ALLOWED_TARGET_RULES:
        raise SetupYamlError(
            f"target.rule {target_rule!r} not in {sorted(ALLOWED_TARGET_RULES)}"
        )

    filters = data.get("filters", [])
    if not isinstance(filters, list):
        raise SetupYamlError(f"filters must be a list")

    opening_range = data.get("opening_range")

    return SetupDefinition(
        name=str(data["name"]),
        version=str(data["version"]),
        symbols=list(symbols),
        session_window=dict(session),
        opening_range=dict(opening_range) if opening_range else None,
        entry=dict(entry),
        stop=dict(stop),
        target=dict(target),
        filters=list(filters),
        raw=dict(data),
    )
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/journal/sanity_floor/test_setup_yaml.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/sanity_floor/setup_yaml.py \
        tests/journal/sanity_floor/test_setup_yaml.py \
        docs/trading/setups/example_opening_range_breakout.yaml
git commit -m "feat(sanity_floor): setup YAML schema + strict parser"
```

---

## Task 10: Historical data loader (yfinance + local cache)

**Files:**
- Create: `src/daytrader/journal/sanity_floor/data_loader.py`
- Create: `tests/journal/sanity_floor/test_data_loader.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for historical data loader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from daytrader.journal.sanity_floor.data_loader import (
    HistoricalDataLoader,
    SYMBOL_TO_YFINANCE,
)


def test_symbol_map_has_all_instruments():
    for s in ("MES", "MNQ", "MGC"):
        assert s in SYMBOL_TO_YFINANCE


def test_cache_path_isolation(tmp_path: Path):
    loader = HistoricalDataLoader(cache_dir=str(tmp_path))
    p1 = loader._cache_path("MES", "1m", date(2026, 1, 1), date(2026, 4, 1))
    p2 = loader._cache_path("MNQ", "1m", date(2026, 1, 1), date(2026, 4, 1))
    assert p1 != p2
    assert "MES" in p1.name


def test_load_uses_cache_when_present(tmp_path: Path):
    loader = HistoricalDataLoader(cache_dir=str(tmp_path))
    # Pre-populate cache with a synthetic DataFrame
    cached_df = pd.DataFrame({
        "Open": [5000.0], "High": [5001.0], "Low": [4999.0],
        "Close": [5000.5], "Volume": [100],
    }, index=pd.DatetimeIndex([pd.Timestamp("2026-04-01 09:30", tz="UTC")]))
    p = loader._cache_path("MES", "1m", date(2026, 4, 1), date(2026, 4, 2))
    cached_df.to_parquet(p)

    df = loader.load(
        symbol="MES", interval="1m",
        start=date(2026, 4, 1), end=date(2026, 4, 2),
    )
    assert len(df) == 1
    assert df["Close"].iloc[0] == 5000.5
```

- [ ] **Step 2: Implement `src/daytrader/journal/sanity_floor/data_loader.py`**

```python
"""Historical OHLCV loader with local parquet cache.

- 1-minute data from yfinance has a ~7-day rolling window limit.
- We cache whatever we fetch to parquet for re-runnability.
- On cache miss, fetch from yfinance and write to cache.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


# yfinance tickers for CME futures continuous contracts
SYMBOL_TO_YFINANCE = {
    "MES": "MES=F",
    "MNQ": "MNQ=F",
    "MGC": "MGC=F",
    # fallbacks at full-size E-mini if micros fail:
    "ES": "ES=F",
    "NQ": "NQ=F",
    "GC": "GC=F",
}


class DataLoadError(RuntimeError):
    pass


class HistoricalDataLoader:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(
        self, symbol: str, interval: str, start: date, end: date
    ) -> Path:
        fname = f"{symbol}_{interval}_{start.isoformat()}_{end.isoformat()}.parquet"
        return self.cache_dir / fname

    def load(
        self,
        symbol: str,
        interval: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame indexed by UTC timestamp.

        Raises DataLoadError if fetch fails and no cache exists.
        """
        p = self._cache_path(symbol, interval, start, end)
        if p.exists():
            return pd.read_parquet(p)

        yf_symbol = SYMBOL_TO_YFINANCE.get(symbol)
        if yf_symbol is None:
            raise DataLoadError(f"unknown symbol: {symbol}")

        try:
            import yfinance as yf
        except ImportError as e:
            raise DataLoadError("yfinance not installed") from e

        df = yf.download(
            yf_symbol,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval=interval,
            auto_adjust=False,
            progress=False,
        )
        if df is None or df.empty:
            raise DataLoadError(
                f"no data returned for {symbol} ({yf_symbol}) "
                f"{interval} {start}→{end}"
            )
        # Flatten MultiIndex columns (yfinance v0.2+ returns them)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        # Ensure UTC index
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        df.to_parquet(p)
        return df
```

- [ ] **Step 3: Add `pyarrow` to dependencies** (parquet backend)

Verify `pyproject.toml` already has `pandas` → pandas ships with `pyarrow` support typically via optional. If parquet write fails in tests, add to `pyproject.toml`:

```toml
dependencies = [
    # ...existing...
    "pyarrow>=14.0",
]
```

Then: `pip install -e .` to install.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/journal/sanity_floor/test_data_loader.py -v
```

Expected: cache test passes (does not hit network). Online fetch test is NOT in the suite (too slow/flaky for CI).

- [ ] **Step 5: Manual fetch smoke test**

```bash
python -c "
from datetime import date, timedelta
from daytrader.journal.sanity_floor.data_loader import HistoricalDataLoader
loader = HistoricalDataLoader('data/cache/ohlcv')
df = loader.load('MES', '1m',
                 date.today() - timedelta(days=5),
                 date.today() - timedelta(days=1))
print(df.head())
print('rows:', len(df))
"
```

Expected: prints a few rows of 1-minute OHLCV for MES.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/journal/sanity_floor/data_loader.py \
        tests/journal/sanity_floor/test_data_loader.py pyproject.toml
git commit -m "feat(sanity_floor): yfinance data loader with parquet cache"
```

---

## Task 11: Backtest engine (bar-by-bar simulation)

**Files:**
- Create: `src/daytrader/journal/sanity_floor/engine.py`
- Create: `tests/journal/sanity_floor/test_engine.py`

Engine takes a `SetupDefinition` + OHLCV DataFrame for one symbol, iterates day-by-day within the session window, identifies entry triggers via YAML rules, simulates forward bars until stop/target/session end. Returns list of per-trade r_multiples.

- [ ] **Step 1: Write tests with synthetic data**

```python
"""Tests for backtest engine with synthetic data (no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from daytrader.journal.sanity_floor.engine import (
    SimulatedTrade, simulate_setup,
)
from daytrader.journal.sanity_floor.setup_yaml import load_setup_yaml


def _synthetic_orb_winner_df() -> pd.DataFrame:
    """One trading day, OR 09:30-09:45 = 5000-5003.
    At 09:50, close crosses 5003+2ticks (5003.5) -> long entry.
    Price walks up to 5009 -> hits target (2*OR_range=2*3=6, entry+6=5009.5).
    Use 1-minute bars in UTC."""
    times = pd.date_range("2026-04-01 13:30", "2026-04-01 15:30",
                          freq="1min", tz="UTC")
    # 13:30 UTC = 09:30 ET during EDT
    rows = []
    for t in times:
        hh, mm = t.hour, t.minute
        if (hh, mm) < (13, 45):
            o, h, l, c = 5000.5, 5003.0, 5000.0, 5002.0
        elif (hh, mm) == (13, 50):
            o, h, l, c = 5002.5, 5003.8, 5002.5, 5003.7  # breakout close
        elif (hh, mm) < (15, 0):
            o, h, l, c = 5003.7 + (mm * 0.1), 5004.5 + mm * 0.1, \
                         5003.5 + mm * 0.1, 5004.0 + mm * 0.1
        else:
            # force target hit
            o, h, l, c = 5009.5, 5010.0, 5009.0, 5009.8
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 100})
    return pd.DataFrame(rows, index=times)


def test_orb_winner_detected(tmp_path: Path):
    yaml_text = """
name: orb
version: v1
symbols: [MES]
session_window:
  start: "09:30 America/New_York"
  end: "11:30 America/New_York"
opening_range:
  duration_minutes: 15
entry:
  direction: long_if_above_or_short_if_below
  trigger: price_closes_beyond_or_by_ticks
  ticks: 2
stop:
  rule: opposite_side_of_or
  offset_ticks: 2
target:
  rule: multiple_of_or_range
  multiple: 2.0
filters: []
"""
    p = tmp_path / "orb.yaml"
    p.write_text(yaml_text)
    setup = load_setup_yaml(p)
    df = _synthetic_orb_winner_df()
    trades = simulate_setup(setup=setup, symbol="MES", df=df, tick_size=0.25)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.r_multiple > 0


def test_no_trades_when_range_too_small():
    # Flat day: OR range = 0 → no breakout possible
    times = pd.date_range("2026-04-01 13:30", "2026-04-01 15:30",
                          freq="1min", tz="UTC")
    df = pd.DataFrame(
        {"Open": 5000.0, "High": 5000.0, "Low": 5000.0,
         "Close": 5000.0, "Volume": 100},
        index=times,
    )
    from daytrader.journal.sanity_floor.setup_yaml import (
        SetupDefinition,
    )
    setup = SetupDefinition(
        name="orb", version="v1", symbols=["MES"],
        session_window={"start": "09:30 America/New_York",
                         "end": "11:30 America/New_York"},
        opening_range={"duration_minutes": 15},
        entry={"direction": "long_if_above_or_short_if_below",
                "trigger": "price_closes_beyond_or_by_ticks", "ticks": 2},
        stop={"rule": "opposite_side_of_or", "offset_ticks": 2},
        target={"rule": "multiple_of_or_range", "multiple": 2.0},
        filters=[{"min_or_range_ticks": 8}],
        raw={},
    )
    trades = simulate_setup(setup=setup, symbol="MES", df=df, tick_size=0.25)
    assert len(trades) == 0
```

- [ ] **Step 2: Implement `src/daytrader/journal/sanity_floor/engine.py`**

```python
"""Bar-by-bar simulation engine.

Supports Opening Range Breakout mechanic out of the box. Other
trigger/stop/target combinations should raise NotImplementedError so the
backtester fails loud rather than produce garbage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

import pandas as pd
from zoneinfo import ZoneInfo

from daytrader.journal.sanity_floor.setup_yaml import SetupDefinition


# USD per 1.0 point (same as CLI)
INSTRUMENT_POINT_VALUE = {
    "MES": Decimal("5"), "MNQ": Decimal("2"), "MGC": Decimal("10"),
}

INSTRUMENT_TICK_SIZE = {
    "MES": 0.25, "MNQ": 0.25, "MGC": 0.10,
}


@dataclass
class SimulatedTrade:
    date: str
    symbol: str
    direction: str           # "long" | "short"
    entry_time: datetime
    entry_price: float
    stop_price: float
    target_price: float
    exit_time: datetime
    exit_price: float
    outcome: str             # "target" | "stop" | "session_end"
    r_multiple: float


def _parse_tz_time(s: str) -> tuple[time, ZoneInfo]:
    """'09:30 America/New_York' -> (time(9,30), ZoneInfo('America/New_York'))"""
    parts = s.strip().split(None, 1)
    hm = parts[0]
    tz = parts[1] if len(parts) > 1 else "UTC"
    h, m = hm.split(":")
    return time(int(h), int(m)), ZoneInfo(tz)


def _session_window_utc(
    day_utc: pd.Timestamp, session: dict
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_t, tz = _parse_tz_time(session["start"])
    end_t, _ = _parse_tz_time(session["end"])
    local_day = day_utc.tz_convert(tz).date()
    s_local = datetime.combine(local_day, start_t).replace(tzinfo=tz)
    e_local = datetime.combine(local_day, end_t).replace(tzinfo=tz)
    return pd.Timestamp(s_local).tz_convert("UTC"), pd.Timestamp(e_local).tz_convert("UTC")


def _filter_value(filters: list[dict], key: str, default=None):
    for f in filters:
        if key in f:
            return f[key]
    return default


def simulate_setup(
    setup: SetupDefinition,
    symbol: str,
    df: pd.DataFrame,
    tick_size: float | None = None,
) -> list[SimulatedTrade]:
    """Simulate a setup over the entire DataFrame. Returns per-trade list."""
    if tick_size is None:
        tick_size = INSTRUMENT_TICK_SIZE.get(symbol, 0.25)

    trigger = setup.entry["trigger"]
    if trigger != "price_closes_beyond_or_by_ticks":
        raise NotImplementedError(f"trigger not supported yet: {trigger}")
    if setup.stop["rule"] != "opposite_side_of_or":
        raise NotImplementedError(f"stop rule not supported yet: {setup.stop['rule']}")
    if setup.target["rule"] != "multiple_of_or_range":
        raise NotImplementedError(f"target rule not supported yet: {setup.target['rule']}")
    if not setup.opening_range:
        raise ValueError("opening_range required for this setup")

    or_minutes = int(setup.opening_range["duration_minutes"])
    entry_ticks = int(setup.entry["ticks"])
    stop_offset_ticks = int(setup.stop["offset_ticks"])
    target_multiple = float(setup.target["multiple"])

    min_ticks = _filter_value(setup.filters, "min_or_range_ticks", 0)
    max_ticks = _filter_value(setup.filters, "max_or_range_ticks", 10_000)

    trades: list[SimulatedTrade] = []

    df = df.sort_index()
    unique_days = sorted({ts.date() for ts in df.index})

    for day in unique_days:
        day_df = df[df.index.normalize() == pd.Timestamp(day, tz="UTC")]
        if day_df.empty:
            continue

        s_utc, e_utc = _session_window_utc(
            pd.Timestamp(day, tz="UTC"), setup.session_window
        )
        session_df = df[(df.index >= s_utc) & (df.index <= e_utc)]
        if session_df.empty:
            continue

        or_end = s_utc + pd.Timedelta(minutes=or_minutes)
        or_df = session_df[session_df.index < or_end]
        if or_df.empty:
            continue
        or_high = float(or_df["High"].max())
        or_low = float(or_df["Low"].min())
        or_range = or_high - or_low
        or_range_ticks = or_range / tick_size
        if or_range_ticks < min_ticks or or_range_ticks > max_ticks:
            continue

        after_or = session_df[session_df.index >= or_end]
        entered = False
        for ts, bar in after_or.iterrows():
            if entered:
                break
            close = float(bar["Close"])
            long_trigger = or_high + entry_ticks * tick_size
            short_trigger = or_low - entry_ticks * tick_size

            if close >= long_trigger:
                direction = "long"
                entry = close
                stop = or_low - stop_offset_ticks * tick_size
                target = entry + target_multiple * or_range
                trades.append(
                    _walk_forward(
                        symbol, day, direction, ts, entry, stop, target,
                        after_or.loc[ts:], tick_size,
                    )
                )
                entered = True
            elif close <= short_trigger:
                direction = "short"
                entry = close
                stop = or_high + stop_offset_ticks * tick_size
                target = entry - target_multiple * or_range
                trades.append(
                    _walk_forward(
                        symbol, day, direction, ts, entry, stop, target,
                        after_or.loc[ts:], tick_size,
                    )
                )
                entered = True

    return trades


def _walk_forward(
    symbol: str, day, direction: str,
    entry_ts, entry: float, stop: float, target: float,
    bars: pd.DataFrame, tick_size: float,
) -> SimulatedTrade:
    """Return the SimulatedTrade — exit at stop, target, or session end."""
    for ts, bar in bars.iterrows():
        if ts == entry_ts:
            continue
        hi = float(bar["High"])
        lo = float(bar["Low"])
        if direction == "long":
            if lo <= stop:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, stop, "stop", tick_size)
            if hi >= target:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, target, "target", tick_size)
        else:
            if hi >= stop:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, stop, "stop", tick_size)
            if lo <= target:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, target, "target", tick_size)

    last_ts = bars.index[-1]
    last_close = float(bars["Close"].iloc[-1])
    return _make_trade(
        symbol, day, direction, entry_ts, entry, stop, target,
        last_ts, last_close, "session_end", tick_size,
    )


def _make_trade(
    symbol, day, direction, entry_ts, entry, stop, target,
    exit_ts, exit_price, outcome, tick_size,
) -> SimulatedTrade:
    risk = abs(entry - stop)
    if direction == "long":
        pnl = exit_price - entry
    else:
        pnl = entry - exit_price
    # Apply 1-tick slippage on stops (conservative)
    if outcome == "stop":
        pnl -= tick_size
    # Commission: $4 round-trip / contract, converted to points for simplicity
    # Skip in per-point pnl; factor into USD aggregation later.
    r = 0.0 if risk == 0 else pnl / risk
    return SimulatedTrade(
        date=str(day), symbol=symbol, direction=direction,
        entry_time=entry_ts.to_pydatetime(), entry_price=entry,
        stop_price=stop, target_price=target,
        exit_time=exit_ts.to_pydatetime(), exit_price=exit_price,
        outcome=outcome, r_multiple=r,
    )
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/journal/sanity_floor/test_engine.py -v
```

Expected: `test_orb_winner_detected` passes (may need timing tweaks to the synthetic bars so that the 09:50 ET bar's close >= or_high + 2 * 0.25). If failing, inspect `print(or_high, or_low)` in the test and adjust synthetic prices.

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/journal/sanity_floor/engine.py \
        tests/journal/sanity_floor/test_engine.py
git commit -m "feat(sanity_floor): bar-by-bar backtest engine for ORB setups"
```

---

## Task 12: Runner + verdict writer

**Files:**
- Create: `src/daytrader/journal/sanity_floor/runner.py`
- Create: `tests/journal/sanity_floor/test_runner.py`

Orchestrates: load setup YAML → load data (per symbol) → run engine → aggregate → write verdict to SQLite + stdout report.

- [ ] **Step 1: Write tests (using in-memory data, not network)**

```python
"""Tests for sanity-floor runner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from daytrader.journal.repository import JournalRepository
from daytrader.journal.sanity_floor.engine import SimulatedTrade
from daytrader.journal.sanity_floor.runner import (
    RunnerConfig, aggregate_and_write_verdict,
)
from daytrader.journal.sanity_floor.setup_yaml import load_setup_yaml


def test_passed_with_good_stats(tmp_path: Path, tmp_journal_db: Path):
    repo = JournalRepository(str(tmp_journal_db))
    repo.initialize()

    # Build 40 trades with mean r = 0.2
    trades = [SimulatedTrade(
        date="2026-04-01", symbol="MES", direction="long",
        entry_time=None, entry_price=5000, stop_price=4995, target_price=5010,
        exit_time=None, exit_price=5005, outcome="target",
        r_multiple=0.2 if i % 2 == 0 else 0.2,
    ) for i in range(40)]

    verdict = aggregate_and_write_verdict(
        repo=repo, setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 16), symbol="MES",
        data_window_days=90, trades=trades,
    )
    assert verdict.passed is True
    assert verdict.n_samples == 40
    assert abs(verdict.avg_r - 0.2) < 0.0001


def test_failed_with_insufficient_samples(tmp_journal_db: Path):
    repo = JournalRepository(str(tmp_journal_db))
    repo.initialize()
    trades = [SimulatedTrade(
        date="2026-04-01", symbol="MES", direction="long",
        entry_time=None, entry_price=5000, stop_price=4995, target_price=5010,
        exit_time=None, exit_price=5005, outcome="target",
        r_multiple=0.5,
    ) for _ in range(20)]
    verdict = aggregate_and_write_verdict(
        repo=repo, setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 16), symbol="MES",
        data_window_days=90, trades=trades,
    )
    assert verdict.passed is False


def test_failed_with_negative_expectancy(tmp_journal_db: Path):
    repo = JournalRepository(str(tmp_journal_db))
    repo.initialize()
    trades = [SimulatedTrade(
        date="2026-04-01", symbol="MES", direction="long",
        entry_time=None, entry_price=5000, stop_price=4995, target_price=5010,
        exit_time=None, exit_price=4995, outcome="stop",
        r_multiple=-1.0,
    ) for _ in range(40)]
    verdict = aggregate_and_write_verdict(
        repo=repo, setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 16), symbol="MES",
        data_window_days=90, trades=trades,
    )
    assert verdict.passed is False
```

- [ ] **Step 2: Implement `src/daytrader/journal/sanity_floor/runner.py`**

```python
"""Runner: orchestrates data load + engine + verdict."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from daytrader.journal.models import SetupVerdict
from daytrader.journal.repository import JournalRepository
from daytrader.journal.sanity_floor.data_loader import (
    DataLoadError, HistoricalDataLoader,
)
from daytrader.journal.sanity_floor.engine import (
    SimulatedTrade, simulate_setup,
)
from daytrader.journal.sanity_floor.setup_yaml import (
    SetupDefinition, load_setup_yaml,
)


MIN_SAMPLES = 30


@dataclass
class RunnerConfig:
    data_window_days: int = 90
    interval: str = "1m"


def aggregate_and_write_verdict(
    repo: JournalRepository,
    setup_name: str,
    setup_version: str,
    run_date: date,
    symbol: str,
    data_window_days: int,
    trades: list[SimulatedTrade],
) -> SetupVerdict:
    n = len(trades)
    win_rate = sum(1 for t in trades if t.r_multiple > 0) / n if n else 0.0
    avg_r = sum(t.r_multiple for t in trades) / n if n else 0.0
    passed = (n >= MIN_SAMPLES) and (avg_r >= 0)
    v = SetupVerdict(
        setup_name=setup_name, setup_version=setup_version,
        run_date=run_date, symbol=symbol,
        data_window_days=data_window_days,
        n_samples=n, win_rate=win_rate, avg_r=avg_r, passed=passed,
    )
    repo.save_setup_verdict(v)
    return v


def run_setup_for_symbol(
    setup: SetupDefinition,
    symbol: str,
    loader: HistoricalDataLoader,
    repo: JournalRepository,
    run_date: date,
    config: RunnerConfig,
) -> SetupVerdict:
    start = run_date - timedelta(days=config.data_window_days)
    try:
        df = loader.load(symbol=symbol, interval=config.interval,
                          start=start, end=run_date)
    except DataLoadError as e:
        # Fail-loud: no verdict for missing data
        raise RuntimeError(
            f"sanity-floor for {setup.name}/{symbol}: {e}. "
            "Verdict not written (fail-loud per spec)."
        ) from e

    trades = simulate_setup(setup=setup, symbol=symbol, df=df)
    return aggregate_and_write_verdict(
        repo=repo, setup_name=setup.name, setup_version=setup.version,
        run_date=run_date, symbol=symbol,
        data_window_days=config.data_window_days,
        trades=trades,
    )
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/journal/sanity_floor/test_runner.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/journal/sanity_floor/runner.py \
        tests/journal/sanity_floor/test_runner.py
git commit -m "feat(sanity_floor): runner with verdict aggregation + write"
```

---

## Task 13: Sanity CLI command

**Files:**
- Modify: `src/daytrader/cli/journal_cmd.py`
- Modify: `src/daytrader/cli/main.py`
- Extend: `tests/journal/test_cli.py`

- [ ] **Step 1: Add test for CLI registration**

Append to `tests/journal/test_cli.py`:

```python
def test_journal_sanity_help():
    from daytrader.cli.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "sanity", "--help"])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Add `sanity` group to `journal_cmd.py`**

Append at bottom of `src/daytrader/cli/journal_cmd.py`:

```python
@click.group("sanity")
def sanity_group():
    """Sanity-floor backtest commands."""


@sanity_group.command("run")
@click.argument("setup_file", type=click.Path(exists=True, path_type=Path))
@click.option("--symbol", multiple=True, default=None,
              help="Override symbols (otherwise use setup's list)")
@click.option("--window-days", default=90, type=int)
def sanity_run(setup_file: Path, symbol: tuple[str, ...], window_days: int):
    """Run sanity-floor backtest on a setup YAML."""
    from datetime import date as _d
    from daytrader.journal.sanity_floor.data_loader import HistoricalDataLoader
    from daytrader.journal.sanity_floor.runner import (
        RunnerConfig, run_setup_for_symbol,
    )
    from daytrader.journal.sanity_floor.setup_yaml import load_setup_yaml

    cfg, repo = _load_cfg_and_repo()
    setup = load_setup_yaml(setup_file)
    loader = HistoricalDataLoader(cache_dir=cfg.journal.data_cache_dir)
    run_date = _d.today()
    symbols = list(symbol) if symbol else setup.symbols
    rconf = RunnerConfig(data_window_days=window_days)
    click.echo(
        "⚠️  Sanity-Floor Backtest — this is NOT a 'good' backtest.\n"
        "    It only rejects obviously broken setups.\n"
        "    Passing does NOT mean the setup has edge.\n"
    )
    for sym in symbols:
        try:
            v = run_setup_for_symbol(
                setup=setup, symbol=sym, loader=loader,
                repo=repo, run_date=run_date, config=rconf,
            )
            status = "PASSED" if v.passed else "FAILED"
            click.echo(
                f"[{status}] {setup.name}/{sym}: "
                f"n={v.n_samples} win_rate={v.win_rate:.2%} "
                f"avg_r={v.avg_r:.3f}"
            )
        except Exception as e:
            click.echo(f"[ERROR] {setup.name}/{sym}: {e}", err=True)
```

- [ ] **Step 3: Wire into main**

Modify the import line at the bottom of `src/daytrader/cli/main.py`:

```python
from daytrader.cli.journal_cmd import (
    pre_trade, post_trade, circuit_group, sanity_group,
)

journal.add_command(pre_trade)
journal.add_command(post_trade)
journal.add_command(circuit_group)
journal.add_command(sanity_group)
```

- [ ] **Step 4: Run CLI tests + manual smoke**

```bash
python -m pytest tests/journal/ -v
daytrader journal sanity --help
daytrader journal sanity run docs/trading/setups/example_opening_range_breakout.yaml --window-days 7
```

Expected: sanity run prints PASS/FAIL per symbol (may error if network unavailable — acceptable).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/cli/journal_cmd.py src/daytrader/cli/main.py tests/journal/test_cli.py
git commit -m "feat(journal): add 'daytrader journal sanity run' CLI"
```

---

## Phase B Self-Review

- [ ] All sanity_floor tests pass (`python -m pytest tests/journal/sanity_floor/ -q`)
- [ ] Example YAML can be parsed (`python -c "from pathlib import Path; from daytrader.journal.sanity_floor.setup_yaml import load_setup_yaml; print(load_setup_yaml(Path('docs/trading/setups/example_opening_range_breakout.yaml')))"`)
- [ ] `daytrader journal sanity --help` works
- [ ] Manual smoke run against yfinance produces a verdict for at least one symbol

Proceed to Phase C plan: `2026-04-16-dryrun-resume-obsidian.md`.
