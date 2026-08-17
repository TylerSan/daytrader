"""SPY 1-minute Databento loader — for Zarattini paper known-answer tests.

Parallel to `data.py` but for an equity ETF. Key differences:
- No continuous contract — SPY is SPY.
- No rollover detection.
- Dataset is equities (ARCX.PILLAR — NYSE Arca, SPY's primary listing venue)
  rather than the GLBX.MDP3 futures feed used for MES.

Originally used DBEQ.BASIC (2023-03-28+) but switched to ARCX.PILLAR
because (a) it's the authoritative SPY venue matching Zarattini paper's
implicit methodology, (b) it has history back to 2018-05-01 enabling
literal paper replication instead of the narrower 2023 window, (c) it's
single-publisher so no multi-venue consolidation is needed, and (d) it's
the same dataset as data_spy_daily.py.

RTH semantics, quality report, and cache layout are identical to the
MES loader, to keep the two loaders ergonomically parallel. ARCX.PILLAR
returns extended-hours bars (04:00-20:00 ET, ~960 bars/day); filter_rth
crops to the 09:30-15:59 RTH window (390 bars/day).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

import pandas as pd

from daytrader.research.bakeoff.data import filter_rth, data_quality_report


_SPY_DATASET = "ARCX.PILLAR"


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


def _consolidate_publishers(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate DBEQ.BASIC per-publisher bars into one bar per minute.

    DBEQ.BASIC emits one row per (timestamp, publisher_id) — i.e. multiple
    rows per minute when SPY trades on multiple venues. For strategy
    backtests we want a single consolidated bar per minute:
      open = first open in minute, high = max, low = min,
      close = last close, volume = sum.
    """
    if not df.index.has_duplicates:
        return df
    agg = df.groupby(df.index).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return agg


def load_spy_1m(
    start: _date,
    end: _date,
    api_key: str,
    cache_dir: Path,
) -> SpyDataset:
    loader = SpyDatabentoLoader(api_key=api_key, cache_dir=cache_dir)
    raw = loader.load(start, end)
    consolidated = _consolidate_publishers(raw)
    rth = filter_rth(consolidated)
    qa = data_quality_report(rth)
    return SpyDataset(bars=rth, quality_report=qa)
