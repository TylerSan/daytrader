"""ARCX.PILLAR daily SPY loader — for S2 ATR_14 warmup.

Parallel to `data_spy.py` but:
- dataset = ARCX.PILLAR (SPY's authoritative listing venue, NYSE Arca)
- schema = ohlcv-1d (daily bars, already consolidated at source)
- no RTH filter (daily bars are EOD — no intraday semantics)
- no publisher consolidation (daily tape is single-valued per day)
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
