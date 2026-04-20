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
