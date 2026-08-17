# Bake-off Plan 1: Data Layer + Cost Model + Baseline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Databento-backed MES 1-minute data loader (with rollover handling + data quality checks), the shared cost model, and a buy-and-hold MES baseline that the bake-off later measures against. This is M1 + M2 of the W2 Setup Gate bake-off.

**Architecture:** New `src/daytrader/research/bakeoff/` package, independent of `journal/sanity_floor/`. All new code goes in `src/daytrader/research/` — no modifications to existing journal code in this plan. Data cached to `data/cache/ohlcv/` (already gitignored). Tests use real-data fixtures (small parquet samples committed under `tests/research/bakeoff/fixtures/`) plus mocked Databento client for the fetch path (no live API calls in unit tests).

**Tech Stack:** Python 3.12, pandas, pyarrow (parquet), pytest, databento SDK (>=0.42), pybroker (>=1.1) — both latter added to `pyproject.toml` in Task 1 but **only imported in later plans**; Plan 1 does not depend on pybroker yet.

**Spec:** [`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../specs/2026-04-20-strategy-selection-bakeoff-design.md) §1.2, §2.3, R1, R3, M1, M2.

**Prerequisites:** Phase 2 journal subsystem merged (done, commit `5b15c05`+).

**User-side actions outside this plan:**
- Purchase Databento OHLCV-1m historical for MES, 2022-01-01 to 2025-12-31 (estimated < $20).
- Configure `DATABENTO_API_KEY` in env or `config/user.yaml`.
- These steps are documented in Task 10 but are not code-executable by the plan.

---

## File Structure

```
Create:
  src/daytrader/research/__init__.py                        # empty namespace
  src/daytrader/research/bakeoff/__init__.py                # version + public API
  src/daytrader/research/bakeoff/data.py                    # MES 1m loader + rollover + QA
  src/daytrader/research/bakeoff/costs.py                   # cost model constants + helpers
  src/daytrader/research/bakeoff/baseline.py                # buy-and-hold equity curve
  src/daytrader/research/bakeoff/strategies/__init__.py     # empty, scaffold for Plan 2
  tests/research/__init__.py
  tests/research/bakeoff/__init__.py
  tests/research/bakeoff/test_data.py
  tests/research/bakeoff/test_costs.py
  tests/research/bakeoff/test_baseline.py
  tests/research/bakeoff/fixtures/mes_1m_sample_2024_06.parquet   # ~20 trading days
  tests/research/bakeoff/fixtures/mes_1m_rollover_2024_q2.parquet # spans rollover

Modify:
  pyproject.toml                                            # add databento, pybroker, quantstats
```

**No modifications to existing `daytrader/journal/` code in Plan 1.**

---

## Task 1: Scaffold package + dependencies

**Files:**
- Create: `src/daytrader/research/__init__.py`
- Create: `src/daytrader/research/bakeoff/__init__.py`
- Create: `src/daytrader/research/bakeoff/strategies/__init__.py`
- Create: `tests/research/__init__.py`
- Create: `tests/research/bakeoff/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create empty namespace files**

Create `src/daytrader/research/__init__.py`:
```python
"""Research subsystem — strategy selection, bake-off, parameter studies.

Kept separate from `daytrader.journal` by design: journal enforces trading
discipline on the critical path; research produces evidence that feeds into
it via explicit `promote` handoffs.
"""
```

Create `src/daytrader/research/bakeoff/__init__.py`:
```python
"""W2 Setup Gate bake-off — compares Zarattini ORB and Intraday Momentum
candidates on MES 1-minute data to produce a locked_setup verdict.

See docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md.
"""
```

Create `src/daytrader/research/bakeoff/strategies/__init__.py`:
```python
"""Strategy implementations. Populated in Plan 2."""
```

Create `tests/research/__init__.py` and `tests/research/bakeoff/__init__.py` as empty files (just `""`).

- [ ] **Step 2: Add dependencies to pyproject.toml**

Modify `pyproject.toml` — add three entries inside the existing `dependencies = [...]` list, keeping alphabetical-ish grouping:

```toml
dependencies = [
    "click>=8.1",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "pandas>=2.2",
    "numpy>=1.26",
    "plotly>=5.18",
    "yfinance>=0.2.36",
    "jinja2>=3.1",
    "anthropic>=0.40",
    "matplotlib>=3.8",
    "pyarrow>=14.0",
    "databento>=0.42",
    "pybroker>=1.1",
    "quantstats>=0.0.62",
]
```

- [ ] **Step 3: Install + verify imports work**

Run:
```bash
cd "/Users/tylersan/Projects/Day trading"
pip install -e ".[dev]"
python -c "import databento; import pybroker; import quantstats; print('ok')"
```

Expected output: `ok` (no ImportError).

If pybroker or databento pin fails with Python 3.12, relax to `>=1.0` / `>=0.40` and retry. Record the actual installed versions; if either is newer than expected (e.g., pybroker 2.0), check its changelog before continuing — the API used in later plans assumes pybroker 1.x Strategy API.

- [ ] **Step 4: Run full existing test suite to confirm no regression**

Run:
```bash
cd "/Users/tylersan/Projects/Day trading"
pytest tests/ -q
```

Expected: all existing tests pass (should be 141 per memory; verify actual count as baseline).

- [ ] **Step 5: Commit**

```bash
cd "/Users/tylersan/Projects/Day trading"
git add pyproject.toml src/daytrader/research/ tests/research/
git commit -m "$(cat <<'EOF'
chore(research): scaffold bakeoff package + add deps

Empty namespace packages under src/daytrader/research/bakeoff/ and matching
tests/ tree; adds databento, pybroker, quantstats to dependencies. No imports
or functionality yet — Plan 1 Task 2+ fill in data layer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Rollover detection from `instrument_id` transitions

**Files:**
- Create: `src/daytrader/research/bakeoff/data.py`
- Create: `tests/research/bakeoff/test_data.py`

Databento's continuous contract (`c-1`, front-month by open interest) returns a DataFrame where `instrument_id` changes on rollover days. We detect those changes and flag the rollover day + the preceding day as skip-days (per R1 mitigation in spec §5.2).

- [ ] **Step 1: Write the failing test**

Create `tests/research/bakeoff/test_data.py`:
```python
"""Tests for bakeoff data layer."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from daytrader.research.bakeoff.data import detect_rollover_skip_dates


def _frame(rows):
    """Helper: build a DataFrame with UTC-indexed timestamps."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(ts, tz="UTC") for ts, _iid in rows]
    )
    return pd.DataFrame(
        {"instrument_id": [iid for _ts, iid in rows]},
        index=idx,
    )


def test_detect_rollover_skip_dates_no_transitions():
    df = _frame([
        ("2024-06-10 13:30", 100),
        ("2024-06-10 14:00", 100),
        ("2024-06-11 13:30", 100),
    ])
    assert detect_rollover_skip_dates(df) == []


def test_detect_rollover_skip_dates_single_transition():
    df = _frame([
        ("2024-06-10 13:30", 100),   # MESM4
        ("2024-06-11 13:30", 100),
        ("2024-06-12 13:30", 101),   # rollover to MESU4 here
        ("2024-06-13 13:30", 101),
    ])
    # Rollover day + preceding day both skipped.
    assert detect_rollover_skip_dates(df) == [date(2024, 6, 11), date(2024, 6, 12)]


def test_detect_rollover_skip_dates_multiple_transitions():
    df = _frame([
        ("2024-03-14 13:30", 100),
        ("2024-03-15 13:30", 101),   # rollover 1
        ("2024-06-12 13:30", 101),
        ("2024-06-13 13:30", 102),   # rollover 2
    ])
    assert detect_rollover_skip_dates(df) == [
        date(2024, 3, 14), date(2024, 3, 15),
        date(2024, 6, 12), date(2024, 6, 13),
    ]


def test_detect_rollover_skip_dates_missing_column_raises():
    df = pd.DataFrame({"close": [1, 2]}, index=pd.DatetimeIndex(
        [pd.Timestamp("2024-06-10 13:30", tz="UTC"),
         pd.Timestamp("2024-06-11 13:30", tz="UTC")]
    ))
    with pytest.raises(ValueError, match="instrument_id"):
        detect_rollover_skip_dates(df)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd "/Users/tylersan/Projects/Day trading"
pytest tests/research/bakeoff/test_data.py::test_detect_rollover_skip_dates_no_transitions -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.research.bakeoff.data'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/daytrader/research/bakeoff/data.py`:
```python
"""MES 1-minute data loader — Databento-backed with local parquet cache.

Handles:
- Continuous contract front-month via Databento `c-1` symbology
- Rollover day detection via `instrument_id` transitions
- RTH session filter (09:30-16:00 ET)
- Data quality report (missing bar rate per day)

See spec §1.2, §2.3, R1, R3.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd


ET = ZoneInfo("America/New_York")


def detect_rollover_skip_dates(df: pd.DataFrame) -> list[date]:
    """Return sorted list of local-ET dates to skip due to rollover.

    A rollover is a row where `instrument_id` differs from the previous row.
    Both the rollover day and the preceding trading day are skipped to avoid
    false breakouts from mid-day front-month transitions.

    Args:
        df: DataFrame indexed by UTC timestamps, must contain `instrument_id`.

    Returns:
        Sorted unique list of dates (local ET) to exclude from backtests.

    Raises:
        ValueError if `instrument_id` column missing.
    """
    if "instrument_id" not in df.columns:
        raise ValueError("DataFrame must have 'instrument_id' column")
    if df.empty:
        return []

    local_dates = df.index.tz_convert(ET).date
    iids = df["instrument_id"].to_numpy()
    skip: set[date] = set()
    for i in range(1, len(iids)):
        if iids[i] != iids[i - 1]:
            # rollover day (i) + preceding day (i-1)
            skip.add(local_dates[i])
            skip.add(local_dates[i - 1])
    return sorted(skip)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/research/bakeoff/test_data.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/data.py tests/research/bakeoff/test_data.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): detect rollover skip dates from instrument_id transitions

Both the rollover day and the preceding day are skipped (spec R1) to avoid
false breakouts during mid-session front-month transitions. Detection is
purely data-driven (no hardcoded CME calendar) — Databento c-1 symbology
carries the instrument_id directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: RTH session filter

**Files:**
- Modify: `src/daytrader/research/bakeoff/data.py`
- Modify: `tests/research/bakeoff/test_data.py`

Filter to 09:30:00 (inclusive) – 16:00:00 (exclusive) ET. This drops overnight / pre-market / post-market bars. Filtering is timezone-aware: input is UTC-indexed; we compare in ET.

- [ ] **Step 1: Write the failing test**

Append to `tests/research/bakeoff/test_data.py`:
```python
from daytrader.research.bakeoff.data import filter_rth


def _ohlcv_frame(timestamps_ts_tz):
    """timestamps_ts_tz: list of (tz-aware pd.Timestamp) -> DataFrame with OHLCV."""
    idx = pd.DatetimeIndex(timestamps_ts_tz).tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame(
        {"open": range(n), "high": range(n), "low": range(n),
         "close": range(n), "volume": [1] * n,
         "instrument_id": [100] * n},
        index=idx,
    )


def test_filter_rth_keeps_open_and_drops_close_boundary():
    # 13:30 UTC = 09:30 ET (EDT); 20:00 UTC = 16:00 ET (EDT).
    # June 2024 → EDT (UTC-4).
    ts = [
        pd.Timestamp("2024-06-10 13:29", tz=ET),  # 09:29 ET — drop (pre-open)
        pd.Timestamp("2024-06-10 09:30", tz=ET),  # 09:30 ET — KEEP
        pd.Timestamp("2024-06-10 15:59", tz=ET),  # 15:59 ET — KEEP
        pd.Timestamp("2024-06-10 16:00", tz=ET),  # 16:00 ET — drop (close boundary excl.)
        pd.Timestamp("2024-06-10 18:00", tz=ET),  # after-hours — drop
    ]
    df = _ohlcv_frame(ts)
    out = filter_rth(df)
    # Should have 2 rows: 09:30 and 15:59.
    assert len(out) == 2
    assert out.index[0].tz_convert(ET).strftime("%H:%M") == "09:30"
    assert out.index[1].tz_convert(ET).strftime("%H:%M") == "15:59"


def test_filter_rth_handles_dst_transition():
    # DST boundary 2024-11-03 02:00 ET. Day before = EDT, day after = EST.
    # An 09:30 bar on both days should be kept regardless of UTC offset change.
    ts = [
        pd.Timestamp("2024-11-01 09:30", tz=ET),  # EDT day — keep
        pd.Timestamp("2024-11-04 09:30", tz=ET),  # EST day — keep
    ]
    df = _ohlcv_frame(ts)
    out = filter_rth(df)
    assert len(out) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/research/bakeoff/test_data.py::test_filter_rth_keeps_open_and_drops_close_boundary -v
```

Expected: FAIL with `ImportError: cannot import name 'filter_rth'`.

- [ ] **Step 3: Implement filter_rth**

Append to `src/daytrader/research/bakeoff/data.py`:
```python
from datetime import time


RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only bars whose timestamp falls in [09:30, 16:00) ET.

    Input must be UTC-indexed. DST-aware via zoneinfo. Returns a new DataFrame;
    does not mutate input.
    """
    if df.empty:
        return df.copy()
    local_times = df.index.tz_convert(ET).time
    mask = (local_times >= RTH_OPEN) & (local_times < RTH_CLOSE)
    return df[mask].copy()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
pytest tests/research/bakeoff/test_data.py -v
```

Expected: all tests PASS (6 total).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/data.py tests/research/bakeoff/test_data.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): RTH session filter for MES (09:30-16:00 ET)

DST-aware via zoneinfo. Close boundary exclusive (16:00 bar dropped) —
aligns with 15:55 ET forced-flat rule in spec §3.2/§3.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Data quality check — missing-bar rate per day

**Files:**
- Modify: `src/daytrader/research/bakeoff/data.py`
- Modify: `tests/research/bakeoff/test_data.py`

RTH is 6.5 hours × 60 min = 390 expected 1-min bars per trading day. Check actual bars vs expected; flag days with < 99% coverage per spec R3.

- [ ] **Step 1: Write failing tests**

Append to `tests/research/bakeoff/test_data.py`:
```python
from daytrader.research.bakeoff.data import data_quality_report


def test_data_quality_report_perfect_day():
    # 390 bars at 1-min intervals starting 13:30 UTC (09:30 ET) on 2024-06-10 (EDT).
    start = pd.Timestamp("2024-06-10 09:30", tz=ET).tz_convert("UTC")
    idx = pd.date_range(start, periods=390, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 1,
         "instrument_id": 100},
        index=idx,
    )
    rep = data_quality_report(df)
    assert rep.loc[date(2024, 6, 10), "n_bars"] == 390
    assert rep.loc[date(2024, 6, 10), "coverage_pct"] == pytest.approx(100.0)
    assert rep.loc[date(2024, 6, 10), "flag_low_coverage"] == False


def test_data_quality_report_missing_bars():
    # 385 bars (5 missing) → 98.7% coverage → flag.
    start = pd.Timestamp("2024-06-10 09:30", tz=ET).tz_convert("UTC")
    full = pd.date_range(start, periods=390, freq="1min", tz="UTC")
    # Drop 5 arbitrary bars.
    kept = full.delete([10, 20, 30, 40, 50])
    df = pd.DataFrame(
        {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 1,
         "instrument_id": 100},
        index=kept,
    )
    rep = data_quality_report(df)
    assert rep.loc[date(2024, 6, 10), "n_bars"] == 385
    assert rep.loc[date(2024, 6, 10), "coverage_pct"] < 99.0
    assert rep.loc[date(2024, 6, 10), "flag_low_coverage"] == True


def test_data_quality_report_empty_frame():
    df = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "instrument_id"],
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    rep = data_quality_report(df)
    assert rep.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/research/bakeoff/test_data.py::test_data_quality_report_perfect_day -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Append to `src/daytrader/research/bakeoff/data.py`:
```python
RTH_BARS_PER_DAY = 390       # 6.5h * 60min
LOW_COVERAGE_THRESHOLD = 99.0  # pct; below this → flag


def data_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-day bar counts and coverage flags.

    Expects RTH-filtered input (use filter_rth first). Returns a DataFrame
    indexed by local ET date with columns: n_bars, coverage_pct,
    flag_low_coverage (bool).

    Empty input returns an empty DataFrame with the correct schema.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["n_bars", "coverage_pct", "flag_low_coverage"],
            index=pd.Index([], name="date"),
        )
    local_dates = df.index.tz_convert(ET).date
    by_day = pd.Series(local_dates).value_counts().sort_index()
    coverage = by_day / RTH_BARS_PER_DAY * 100.0
    rep = pd.DataFrame({
        "n_bars": by_day,
        "coverage_pct": coverage,
        "flag_low_coverage": coverage < LOW_COVERAGE_THRESHOLD,
    })
    rep.index.name = "date"
    return rep
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
pytest tests/research/bakeoff/test_data.py -v
```

Expected: all tests PASS (9 total).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/data.py tests/research/bakeoff/test_data.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): per-day data quality report with coverage flag

Flags days with <99% of 390 expected RTH 1-min bars. Spec §5.2 R3 requires
dropping these days from pure OOS counts; flagging is the first half.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Databento loader wrapper with parquet cache

**Files:**
- Modify: `src/daytrader/research/bakeoff/data.py`
- Modify: `tests/research/bakeoff/test_data.py`

Wrap `databento.Historical` client: cache raw fetch to `data/cache/ohlcv/MES_1m_<start>_<end>_raw.parquet`, return the cached frame on subsequent calls. Unit tests mock the Databento client (no live API). Integration test is a separate Task 9.

- [ ] **Step 1: Write failing tests**

Append to `tests/research/bakeoff/test_data.py`:
```python
from unittest.mock import MagicMock
from pathlib import Path

from daytrader.research.bakeoff.data import MesDatabentoLoader


@pytest.fixture
def mock_client(monkeypatch):
    """Patch databento.Historical constructor to return a pre-canned mock."""
    mock = MagicMock()
    mock_df = pd.DataFrame(
        {"open": [100.0, 101.0], "high": [100.5, 101.5],
         "low": [99.5, 100.5], "close": [100.2, 101.2],
         "volume": [500, 600], "instrument_id": [42, 42]},
        index=pd.DatetimeIndex(
            [pd.Timestamp("2024-06-10 13:30", tz="UTC"),
             pd.Timestamp("2024-06-10 13:31", tz="UTC")]
        ),
    )
    mock.timeseries.get_range.return_value.to_df.return_value = mock_df
    monkeypatch.setattr("databento.Historical", lambda *a, **kw: mock)
    return mock


def test_loader_cache_miss_calls_databento(tmp_path, mock_client):
    loader = MesDatabentoLoader(
        api_key="test-key",
        cache_dir=tmp_path,
    )
    df = loader.load(date(2024, 6, 10), date(2024, 6, 10))
    assert len(df) == 2
    assert "instrument_id" in df.columns
    mock_client.timeseries.get_range.assert_called_once()


def test_loader_cache_hit_skips_databento(tmp_path, mock_client):
    loader = MesDatabentoLoader(api_key="test-key", cache_dir=tmp_path)
    # First call populates cache.
    loader.load(date(2024, 6, 10), date(2024, 6, 10))
    mock_client.reset_mock()
    # Second call should NOT hit Databento.
    df2 = loader.load(date(2024, 6, 10), date(2024, 6, 10))
    assert len(df2) == 2
    mock_client.timeseries.get_range.assert_not_called()


def test_loader_missing_api_key_raises():
    with pytest.raises(ValueError, match="api_key"):
        MesDatabentoLoader(api_key="", cache_dir=Path("/tmp"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/research/bakeoff/test_data.py::test_loader_cache_miss_calls_databento -v
```

Expected: FAIL (`MesDatabentoLoader` not importable).

- [ ] **Step 3: Implement loader**

Append to `src/daytrader/research/bakeoff/data.py`:
```python
from dataclasses import dataclass
from pathlib import Path
from datetime import date as _date


@dataclass
class MesDatabentoLoader:
    """Fetch MES 1-minute OHLCV from Databento, cached to parquet.

    Uses Databento's `continuous` symbology with `c-1` (front-month by open
    interest). Raw fetch (including `instrument_id` column for rollover
    detection) is cached to `<cache_dir>/MES_1m_<start>_<end>_raw.parquet`.
    """
    api_key: str
    cache_dir: Path

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("api_key is required")
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, start: _date, end: _date) -> Path:
        return self.cache_dir / (
            f"MES_1m_{start.isoformat()}_{end.isoformat()}_raw.parquet"
        )

    def load(self, start: _date, end: _date) -> pd.DataFrame:
        """Return UTC-indexed DataFrame with OHLCV + instrument_id.

        Inclusive on both ends. Cache-first.
        """
        p = self._cache_path(start, end)
        if p.exists():
            return pd.read_parquet(p)

        import databento
        client = databento.Historical(self.api_key)
        req = client.timeseries.get_range(
            dataset="GLBX.MDP3",
            schema="ohlcv-1m",
            symbols=["MES.c.0"],  # continuous front-month by OI
            stype_in="continuous",
            start=start.isoformat(),
            end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
        )
        df = req.to_df()
        # Normalize timezone to UTC.
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.to_parquet(p)
        return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
pytest tests/research/bakeoff/test_data.py -v
```

Expected: all tests PASS (12 total).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/data.py tests/research/bakeoff/test_data.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): Databento MES 1m loader with parquet cache

Uses continuous symbology (MES.c.0) so instrument_id column is populated for
rollover detection. Cache-first to avoid repeat API charges. Unit tests mock
databento.Historical — integration with live API is covered in Task 9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Orchestrator — end-to-end `load_mes_1m`

**Files:**
- Modify: `src/daytrader/research/bakeoff/data.py`
- Modify: `tests/research/bakeoff/test_data.py`

Single public function that composes: fetch → RTH filter → rollover skip dates → quality report. Returns a `MesDataset` dataclass containing the cleaned DataFrame and the diagnostic artifacts.

- [ ] **Step 1: Write failing test**

Append to `tests/research/bakeoff/test_data.py`:
```python
from daytrader.research.bakeoff.data import load_mes_1m, MesDataset


def test_load_mes_1m_returns_clean_dataset(tmp_path, mock_client):
    # Replace the single-day mock with a 2-day mock that spans a rollover.
    idx = pd.DatetimeIndex([
        pd.Timestamp("2024-06-10 13:30", tz="UTC"),  # 09:30 ET day 1
        pd.Timestamp("2024-06-10 20:30", tz="UTC"),  # 16:30 ET day 1 — after RTH, drop
        pd.Timestamp("2024-06-11 13:30", tz="UTC"),  # 09:30 ET day 2 (new iid)
    ])
    df = pd.DataFrame(
        {"open": [1.0, 1.0, 1.0], "high": [1.0, 1.0, 1.0],
         "low": [1.0, 1.0, 1.0], "close": [1.0, 1.0, 1.0],
         "volume": [1, 1, 1], "instrument_id": [42, 42, 43]},
        index=idx,
    )
    mock_client.timeseries.get_range.return_value.to_df.return_value = df

    ds = load_mes_1m(
        start=date(2024, 6, 10), end=date(2024, 6, 11),
        api_key="test", cache_dir=tmp_path,
    )
    assert isinstance(ds, MesDataset)
    # After RTH filter: 2 bars (post-RTH bar dropped).
    assert len(ds.bars) == 2
    # Rollover between iid 42 and 43 → skip dates 2024-06-10 + 2024-06-11.
    assert ds.rollover_skip_dates == [date(2024, 6, 10), date(2024, 6, 11)]
    # Quality report per remaining day.
    assert set(ds.quality_report.index) == {date(2024, 6, 10), date(2024, 6, 11)}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/research/bakeoff/test_data.py::test_load_mes_1m_returns_clean_dataset -v
```

Expected: FAIL (`load_mes_1m` not importable).

- [ ] **Step 3: Implement**

Append to `src/daytrader/research/bakeoff/data.py`:
```python
@dataclass
class MesDataset:
    """Cleaned MES bars + diagnostic artifacts.

    - bars: UTC-indexed DataFrame, RTH only, has OHLCV + instrument_id
    - rollover_skip_dates: list of ET dates to exclude from trading
    - quality_report: per-day coverage DataFrame
    """
    bars: pd.DataFrame
    rollover_skip_dates: list[_date]
    quality_report: pd.DataFrame


def load_mes_1m(
    start: _date,
    end: _date,
    api_key: str,
    cache_dir: Path,
) -> MesDataset:
    """End-to-end loader: fetch → RTH filter → diagnostics.

    Rollover detection runs on the raw (pre-RTH-filter) data so that mid-day
    instrument_id transitions are not lost.
    """
    loader = MesDatabentoLoader(api_key=api_key, cache_dir=cache_dir)
    raw = loader.load(start, end)
    skip_dates = detect_rollover_skip_dates(raw)
    rth = filter_rth(raw)
    qa = data_quality_report(rth)
    return MesDataset(bars=rth, rollover_skip_dates=skip_dates, quality_report=qa)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/research/bakeoff/test_data.py -v
```

Expected: all tests PASS (13 total).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/data.py tests/research/bakeoff/test_data.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): load_mes_1m orchestrator returns MesDataset

Composes fetch → RTH filter → rollover detection → QA report. Rollover
detection runs on pre-filter data to preserve mid-day instrument_id
transitions that would otherwise be dropped.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Cost model constants + helpers

**Files:**
- Create: `src/daytrader/research/bakeoff/costs.py`
- Create: `tests/research/bakeoff/test_costs.py`

Single shared cost model used by all 4 candidates (spec §2.3). No strategy-specific branching here — just the numbers + one-way-trip and round-trip helpers.

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/test_costs.py`:
```python
"""Tests for bakeoff cost model."""

from __future__ import annotations

import pytest

from daytrader.research.bakeoff.costs import (
    COMMISSION_PER_RT_CONTRACT,
    ENTRY_SLIPPAGE_TICKS,
    STOP_SLIPPAGE_TICKS,
    TARGET_SLIPPAGE_TICKS,
    MES_TICK_SIZE,
    MES_POINT_VALUE,
    entry_slippage_usd,
    stop_slippage_usd,
    target_slippage_usd,
    round_trip_cost_usd,
    tick_to_usd,
)


def test_mes_constants_match_cme_spec():
    assert MES_TICK_SIZE == 0.25
    assert MES_POINT_VALUE == 5.0


def test_tick_to_usd():
    assert tick_to_usd(1) == pytest.approx(1.25)   # 1 tick = 0.25 pts * $5 = $1.25
    assert tick_to_usd(2) == pytest.approx(2.50)
    assert tick_to_usd(0) == 0.0


def test_entry_slippage_is_1_tick():
    assert ENTRY_SLIPPAGE_TICKS == 1
    assert entry_slippage_usd(contracts=1) == pytest.approx(1.25)
    assert entry_slippage_usd(contracts=2) == pytest.approx(2.50)


def test_stop_slippage_is_2_ticks():
    assert STOP_SLIPPAGE_TICKS == 2
    assert stop_slippage_usd(contracts=1) == pytest.approx(2.50)


def test_target_slippage_is_zero_ticks():
    assert TARGET_SLIPPAGE_TICKS == 0
    assert target_slippage_usd(contracts=1) == 0.0
    assert target_slippage_usd(contracts=3) == 0.0


def test_commission_per_round_trip():
    assert COMMISSION_PER_RT_CONTRACT == pytest.approx(4.0)


def test_round_trip_cost_target_exit():
    # Commission + entry slippage + target slippage (0).
    cost = round_trip_cost_usd(contracts=1, exit_kind="target")
    assert cost == pytest.approx(4.0 + 1.25 + 0.0)


def test_round_trip_cost_stop_exit():
    # Commission + entry slippage + stop slippage (2 ticks).
    cost = round_trip_cost_usd(contracts=1, exit_kind="stop")
    assert cost == pytest.approx(4.0 + 1.25 + 2.50)


def test_round_trip_cost_eod_exit_treated_as_target():
    # EOD flat is a market order at close — conservative: model as target (resting).
    cost = round_trip_cost_usd(contracts=1, exit_kind="eod")
    assert cost == pytest.approx(4.0 + 1.25 + 0.0)


def test_round_trip_cost_unknown_exit_kind_raises():
    with pytest.raises(ValueError, match="exit_kind"):
        round_trip_cost_usd(contracts=1, exit_kind="bogus")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/research/bakeoff/test_costs.py -v
```

Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/costs.py`:
```python
"""MES cost model — shared by all 4 bake-off candidates.

Conservative:
- Commission at Topstep's high end ($4 RT, vs IBKR's ~$2.04)
- 1 tick slippage on entry (market-on-open-bar)
- 2 ticks slippage on stop (market-on-stop, MES liquidity < ES)
- 0 ticks slippage on target / EOD (resting limit fill)

See spec §2.3.
"""

from __future__ import annotations

from typing import Literal

# CME MES spec.
MES_TICK_SIZE: float = 0.25           # points per tick
MES_POINT_VALUE: float = 5.0          # USD per 1-point move, 1 contract

# Cost constants.
COMMISSION_PER_RT_CONTRACT: float = 4.0   # USD, round-trip
ENTRY_SLIPPAGE_TICKS: int = 1
STOP_SLIPPAGE_TICKS: int = 2
TARGET_SLIPPAGE_TICKS: int = 0

ExitKind = Literal["target", "stop", "eod"]


def tick_to_usd(ticks: int | float, contracts: int = 1) -> float:
    """Convert tick count to USD for N contracts."""
    return ticks * MES_TICK_SIZE * MES_POINT_VALUE * contracts


def entry_slippage_usd(contracts: int = 1) -> float:
    return tick_to_usd(ENTRY_SLIPPAGE_TICKS, contracts)


def stop_slippage_usd(contracts: int = 1) -> float:
    return tick_to_usd(STOP_SLIPPAGE_TICKS, contracts)


def target_slippage_usd(contracts: int = 1) -> float:
    return tick_to_usd(TARGET_SLIPPAGE_TICKS, contracts)


def round_trip_cost_usd(contracts: int, exit_kind: ExitKind) -> float:
    """Total cost for one round-trip = commission + entry slip + exit slip.

    EOD flat is modeled as a resting target fill (0 exit slip), conservative
    vs modeling it as a market-on-close (which would add ~1 tick).
    """
    if exit_kind == "target":
        exit_slip = target_slippage_usd(contracts)
    elif exit_kind == "stop":
        exit_slip = stop_slippage_usd(contracts)
    elif exit_kind == "eod":
        exit_slip = target_slippage_usd(contracts)
    else:
        raise ValueError(f"exit_kind must be target/stop/eod, got {exit_kind!r}")
    return COMMISSION_PER_RT_CONTRACT * contracts + entry_slippage_usd(contracts) + exit_slip
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/research/bakeoff/test_costs.py -v
```

Expected: all tests PASS (10 total).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/costs.py tests/research/bakeoff/test_costs.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): shared MES cost model (spec §2.3)

Commission $4 RT + entry 1-tick + stop 2-tick + target/EOD 0-tick slippage.
Constants exposed for SE-1 cost-multiplier sensitivity sweep (×0 / ×1 / ×2)
in later plans.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Buy-and-hold MES baseline equity curve

**Files:**
- Create: `src/daytrader/research/bakeoff/baseline.py`
- Create: `tests/research/bakeoff/test_baseline.py`

Computes a 1-contract buy-and-hold MES equity curve across the data period. Rolls on instrument_id transitions, paying roll slippage per roll (2 ticks ≈ sell-at-bid + buy-at-ask). Spec §2.4 defines this as the baseline Sharpe comparison.

- [ ] **Step 1: Write failing tests**

Create `tests/research/bakeoff/test_baseline.py`:
```python
"""Tests for buy-and-hold MES baseline."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.baseline import buy_and_hold_mes_equity
from daytrader.research.bakeoff.costs import MES_POINT_VALUE, tick_to_usd


ET = ZoneInfo("America/New_York")


def _bars(rows):
    """rows: list of (ts_utc_str, close, iid)."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(ts, tz="UTC") for ts, _c, _i in rows]
    )
    return pd.DataFrame(
        {"open": [c for _t, c, _i in rows],
         "high": [c for _t, c, _i in rows],
         "low":  [c for _t, c, _i in rows],
         "close": [c for _t, c, _i in rows],
         "volume": [1] * len(rows),
         "instrument_id": [i for _t, _c, i in rows]},
        index=idx,
    )


def test_buy_and_hold_flat_price_zero_pnl():
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-10 15:59", 5000.0, 100),
        ("2024-06-11 13:30", 5000.0, 100),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    assert eq.iloc[0] == pytest.approx(10_000.0)
    assert eq.iloc[-1] == pytest.approx(10_000.0)


def test_buy_and_hold_price_up_gains_pnl():
    # Price rises 10 points → 10 * $5 = $50 gain on 1 contract.
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-10 15:59", 5010.0, 100),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    assert eq.iloc[-1] == pytest.approx(10_050.0)


def test_buy_and_hold_rollover_pays_2_ticks_cost():
    # On instrument_id change, pay 2 ticks (1 sell + 1 buy entry slippage) = $2.50.
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-11 13:30", 5000.0, 100),
        ("2024-06-12 13:30", 5000.0, 101),   # rollover — cost $2.50
        ("2024-06-13 13:30", 5000.0, 101),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    expected_end = 10_000.0 - tick_to_usd(2)   # 2 ticks = $2.50 roll cost
    assert eq.iloc[-1] == pytest.approx(expected_end)


def test_buy_and_hold_index_matches_bars():
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-10 15:59", 5005.0, 100),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    assert len(eq) == len(bars)
    assert (eq.index == bars.index).all()


def test_buy_and_hold_empty_bars_raises():
    bars = _bars([])
    with pytest.raises(ValueError, match="empty"):
        buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/research/bakeoff/test_baseline.py -v
```

Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

Create `src/daytrader/research/bakeoff/baseline.py`:
```python
"""Buy-and-hold MES baseline for bake-off comparison (spec §2.4).

Holds 1 contract of the front-month MES continuously across the data window.
On instrument_id transitions (rollover), pays 2 ticks of slippage (sell
front + buy next). No commission modeled on rolls — Databento continuous
contract splicing is back-office, not retail-initiated.
"""

from __future__ import annotations

import pandas as pd

from daytrader.research.bakeoff.costs import MES_POINT_VALUE, tick_to_usd


def buy_and_hold_mes_equity(
    bars: pd.DataFrame,
    starting_capital: float,
    contracts: int = 1,
) -> pd.Series:
    """Return an equity curve Series, UTC-indexed, same length as `bars`.

    Args:
        bars: UTC-indexed DataFrame with `close` and `instrument_id`.
        starting_capital: USD at bars.index[0].
        contracts: position size (default 1).

    PnL accrues mark-to-market bar by bar on `close`. At instrument_id
    transitions, deducts `2 * tick_to_usd(1, contracts)` as roll cost.
    """
    if bars.empty:
        raise ValueError("bars must not be empty")

    closes = bars["close"].to_numpy()
    iids = bars["instrument_id"].to_numpy()

    # Mark-to-market PnL per bar (contracts * point_value * close_diff).
    equity = [starting_capital]
    for i in range(1, len(bars)):
        pnl = (closes[i] - closes[i - 1]) * MES_POINT_VALUE * contracts
        roll_cost = 0.0
        if iids[i] != iids[i - 1]:
            roll_cost = tick_to_usd(2, contracts)  # 2 ticks total = sell + buy
        equity.append(equity[-1] + pnl - roll_cost)

    return pd.Series(equity, index=bars.index, name="buy_and_hold_equity")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/research/bakeoff/test_baseline.py -v
```

Expected: all tests PASS (5 total).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/research/bakeoff/baseline.py tests/research/bakeoff/test_baseline.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): buy-and-hold MES baseline equity curve

Marks-to-market each bar on close, deducts 2 ticks on rollover days.
Provides the reference curve for the 'excess Sharpe > 0.3' gate in
spec §2.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Integration smoke test (live Databento, skipped by default)

**Files:**
- Create: `tests/research/bakeoff/test_integration_data.py`

Real-API smoke test that purchases a single trading day of data. Skipped unless `DATABENTO_API_KEY` env var is set and `RUN_LIVE_TESTS=1`. This is the first time we verify the loader against real Databento, so any schema mismatch (column names, dtypes, index semantics) surfaces here and not later during the full bake-off run.

- [ ] **Step 1: Write skipped-by-default integration test**

Create `tests/research/bakeoff/test_integration_data.py`:
```python
"""Live Databento integration smoke test. Skipped unless explicitly enabled.

Run with:
    DATABENTO_API_KEY=<key> RUN_LIVE_TESTS=1 \
        pytest tests/research/bakeoff/test_integration_data.py -v

Cost: downloads 1 trading day of MES 1m OHLCV (~390 rows). Expected Databento
bill: << $1 (OHLCV-1m is Databento's cheapest schema).
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from daytrader.research.bakeoff.data import load_mes_1m


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
)


@pytest.mark.skipif(not LIVE_ENABLED, reason="live Databento disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY)")
def test_live_fetch_one_day_mes(tmp_path):
    ds = load_mes_1m(
        start=date(2024, 6, 10),
        end=date(2024, 6, 10),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=tmp_path,
    )
    # RTH = 390 bars for a normal session; allow small missing-bar tolerance.
    assert 380 <= len(ds.bars) <= 390
    # Required columns.
    for c in ["open", "high", "low", "close", "volume", "instrument_id"]:
        assert c in ds.bars.columns, f"missing column: {c}"
    # UTC index.
    assert str(ds.bars.index.tz) == "UTC"
    # No rollover expected on an isolated mid-June day.
    assert ds.rollover_skip_dates == []
    # Quality report has that one date.
    assert date(2024, 6, 10) in ds.quality_report.index
```

- [ ] **Step 2: Verify it skips by default**

Run:
```bash
pytest tests/research/bakeoff/test_integration_data.py -v
```

Expected: 1 SKIPPED (reason: live Databento disabled).

- [ ] **Step 3: Commit**

```bash
git add tests/research/bakeoff/test_integration_data.py
git commit -m "$(cat <<'EOF'
test(bakeoff): live Databento integration smoke test (skipped by default)

Verifies column schema + UTC tz + row count before spending real money on
the full 4-year pull. Enable with RUN_LIVE_TESTS=1 + DATABENTO_API_KEY.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: USER ACTION — fetch 1 day manually**

> This step is not an automated test. The human (or a trusted agent) runs:
> ```bash
> export DATABENTO_API_KEY=<key from Databento portal>
> RUN_LIVE_TESTS=1 pytest tests/research/bakeoff/test_integration_data.py -v
> ```
> Expected: PASSED, followed by a Databento invoice email for pennies.
>
> **If this test fails** (e.g., schema name changed, symbology rejected, credentials wrong), fix the loader in Task 5 and re-run this task before proceeding to Task 10. **Do not skip and bulk-fetch 4 years — that's the $20 move.**

---

## Task 10: Documentation — Databento setup + runbook

**Files:**
- Create: `docs/research/bakeoff/databento-setup.md`
- Create: `docs/research/bakeoff/README.md`

Human-readable runbook so that this plan can be re-executed by a fresh engineer (or future-you) months later.

- [ ] **Step 1: Write Databento setup doc**

Create `docs/research/bakeoff/databento-setup.md`:
```markdown
# Databento Setup for W2 Setup Gate Bake-off

## What you're buying

MES front-month continuous 1-minute OHLCV from 2022-01-01 to 2025-12-31.

Schema: `ohlcv-1m`
Dataset: `GLBX.MDP3`
Symbol: `MES.c.0` (continuous, front-month by open interest)
Size: ~500 MB compressed parquet
Expected cost: $5–$20 one-time (Databento historical billing is per-byte; OHLCV-1m is the cheapest schema)

## Steps

1. Create an account at https://databento.com/signup if you don't have one.
2. Confirm your default billing method has funds / a PO covers the ~$20 expected charge.
3. Generate an API key at https://databento.com/portal/keys.
4. Store it locally — **do not commit**:
   ```bash
   # option A: env var
   export DATABENTO_API_KEY="db-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

   # option B: config/user.yaml (already gitignored)
   echo "databento_api_key: db-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" >> config/user.yaml
   ```
5. Run the single-day smoke test FIRST (Task 9 step 4). **Only proceed past this if it passes.**

## Pulling the full 4-year dataset

After the smoke test passes:
```bash
python -c "
from datetime import date
from pathlib import Path
import os

from daytrader.research.bakeoff.data import load_mes_1m

ds = load_mes_1m(
    start=date(2022, 1, 3),
    end=date(2025, 12, 31),
    api_key=os.environ['DATABENTO_API_KEY'],
    cache_dir=Path('data/cache/ohlcv'),
)
print(f'Bars: {len(ds.bars):,}')
print(f'Rollover skip dates: {len(ds.rollover_skip_dates)}')
print(f'Low-coverage days: {int(ds.quality_report[\"flag_low_coverage\"].sum())}')
"
```

Expected output roughly:
- Bars: ~370,000–390,000 (≈ 1000 trading days × 390 bars, minus low-coverage days)
- Rollover skip dates: ~32 (4 quarterly rollovers/year × 4 years × 2 days each)
- Low-coverage days: typically < 15 (holidays, partial sessions, outages)

## Troubleshooting

- **`databento.common.error.BentoHttpError: 401`**: API key wrong or expired.
- **`401: insufficient permissions`**: your Databento plan doesn't include GLBX.MDP3 historical; contact Databento support to add futures.
- **DataFrame returned but `instrument_id` missing**: symbology wrong. Double-check `stype_in="continuous"` and `symbols=["MES.c.0"]`.
- **Bill shock (>$100)**: you almost certainly downloaded a non-OHLCV schema by accident. Cancel, get a refund, verify `schema="ohlcv-1m"`.
```

- [ ] **Step 2: Write bakeoff README**

Create `docs/research/bakeoff/README.md`:
```markdown
# Bake-off research module

Implementation of the W2 Setup Gate bake-off described in
[`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../../superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md).

## Current status (Plan 1 complete)

- ✅ Data layer: `daytrader.research.bakeoff.data.load_mes_1m`
- ✅ Cost model: `daytrader.research.bakeoff.costs`
- ✅ Buy-and-hold baseline: `daytrader.research.bakeoff.baseline.buy_and_hold_mes_equity`
- ⬜ Strategies (S1a/S1b/S2a/S2b) — Plan 2
- ⬜ Walk-forward + metrics + DSR — Plan 3
- ⬜ `promote` CLI + YAML v2 + Contract integration — Plan 4

## Quick test

```bash
pytest tests/research/bakeoff/ -v
```

## Fetching data

See `databento-setup.md`.

## Running baseline (sanity check)

```python
from datetime import date
from pathlib import Path
import os

from daytrader.research.bakeoff.data import load_mes_1m
from daytrader.research.bakeoff.baseline import buy_and_hold_mes_equity

ds = load_mes_1m(
    start=date(2024, 1, 2), end=date(2024, 12, 31),
    api_key=os.environ["DATABENTO_API_KEY"],
    cache_dir=Path("data/cache/ohlcv"),
)
eq = buy_and_hold_mes_equity(ds.bars, starting_capital=10_000.0)
print(f"Start: ${eq.iloc[0]:,.2f}")
print(f"End:   ${eq.iloc[-1]:,.2f}")
print(f"Return: {(eq.iloc[-1] / eq.iloc[0] - 1) * 100:+.2f}%")
```

MES 2024 should show roughly +20–25% before cost (S&P 500 total return), minus ~$80 in rollover costs (4 rolls × $2.50 × $5/contract adjustment, exact value depends on roll levels). A significant deviation means the baseline code has a bug — do not proceed to Plan 2 until that's resolved.
```

- [ ] **Step 3: Commit**

```bash
git add docs/research/
git commit -m "$(cat <<'EOF'
docs(bakeoff): Databento setup + Plan 1 runbook

Cost expectations, smoke-test-first workflow, troubleshooting for common
Databento errors, sanity-check snippet that verifies MES 2024 baseline
returns match realistic market return (~20%).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Final verification + Plan 1 close-out

**Files:** (no code changes — verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd "/Users/tylersan/Projects/Day trading"
pytest tests/ -q
```

Expected: all existing 141 journal tests still pass + **new bake-off tests added in Tasks 2-8 all pass**. Concrete new-test count: ~28 (13 data + 10 costs + 5 baseline, all excluding the skipped live integration test).

If anything regressed in the journal subsystem, this plan has broken its "no modifications to existing code" invariant — bisect the commits in this plan and fix.

- [ ] **Step 2: Verify directory structure**

Run:
```bash
cd "/Users/tylersan/Projects/Day trading"
find src/daytrader/research tests/research docs/research -type f | sort
```

Expected output:
```
docs/research/bakeoff/README.md
docs/research/bakeoff/databento-setup.md
src/daytrader/research/__init__.py
src/daytrader/research/bakeoff/__init__.py
src/daytrader/research/bakeoff/baseline.py
src/daytrader/research/bakeoff/costs.py
src/daytrader/research/bakeoff/data.py
src/daytrader/research/bakeoff/strategies/__init__.py
tests/research/__init__.py
tests/research/bakeoff/__init__.py
tests/research/bakeoff/test_baseline.py
tests/research/bakeoff/test_costs.py
tests/research/bakeoff/test_data.py
tests/research/bakeoff/test_integration_data.py
```

- [ ] **Step 3: Sanity-scan that journal code is untouched**

Run:
```bash
git log --oneline main~<n>..HEAD -- src/daytrader/journal/ tests/journal/
```

where `<n>` = number of commits made in this plan. Expected: **empty output** — Plan 1 touched zero files under `journal/`.

If any commit in this plan modified journal code, that's a spec violation (spec §4.3 requires journal changes only in later plans). Revert and redo.

- [ ] **Step 4: (OPTIONAL) Run live smoke test if user wants**

This is the user's call, not the plan's — but if they want to validate the whole Plan 1 against real Databento before moving on, this is the moment:

```bash
RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> pytest tests/research/bakeoff/test_integration_data.py -v
```

Expected: 1 PASSED. Cost: pennies.

- [ ] **Step 5: Announce Plan 1 done + propose Plan 2 scope**

Plan 1 produces working, tested software: data layer + cost model + baseline. Plan 2 starts the strategy implementations (S1a, S1b, S2a, S2b) with SPY known-answer tests (spec M3/M4). **Do not start Plan 2 without writing its plan first** — the known-answer testing approach benefits from iterative refinement based on Plan 1 learnings (e.g., Databento returned column names, fixture shapes).

---

## Self-Review

**Spec coverage (§ numbers refer to `2026-04-20-strategy-selection-bakeoff-design.md`):**

| Spec item | Covered by |
|---|---|
| §1.2 新增 `research/bakeoff/` 包结构 | Task 1, 2, 7, 8 |
| §1.2 `data.py` | Task 2, 3, 4, 5, 6 |
| §1.2 `costs.py` | Task 7 |
| §2.3 成本模型全部 5 个常量 | Task 7 |
| §2.4 baseline (buy-and-hold MES) 定义 | Task 8 |
| R1 MES rollover 处理 | Task 2 + Task 8 (roll slippage) |
| R3 缺 bar 检测 | Task 4 |
| R6 MES 规格硬编码 + unit test | Task 7 |
| M1 数据层 + Databento + 质检 + 单元测试 | Tasks 2-6 + Task 9 |
| M2 成本模型 + baseline | Task 7, 8 |
| §4.3 "Phase 2 既有代码改动面 = 0 行(本 plan)" | Task 11 Step 3 |

**Placeholder scan:** No `TBD`/`TODO`/"implement later"/"add appropriate error handling" in the plan. Every code step shows complete code.

**Type consistency check:**
- `MesDataset` defined in Task 6, referenced only there.
- `MesDatabentoLoader` defined in Task 5, used internally by `load_mes_1m` (Task 6) — signature consistent.
- `ExitKind` literal `"target" | "stop" | "eod"` defined in Task 7; no downstream usage in Plan 1.
- `buy_and_hold_mes_equity` signature matches all test usages in Task 8.

**Scope check:** Plan 1 = M1 + M2 only. No strategy code, no pybroker usage, no journal modifications. Self-contained and testable on its own. ✓

