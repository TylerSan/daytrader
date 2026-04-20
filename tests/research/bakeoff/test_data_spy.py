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
    assert len(ds.bars) == 1
    assert not hasattr(ds, "rollover_skip_dates")
    assert date(2024, 6, 10) in ds.quality_report.index
