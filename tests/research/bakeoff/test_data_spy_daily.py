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
    assert isinstance(df.index, pd.DatetimeIndex)
    assert (df.index == df.index.normalize()).all()
    for c in ["open", "high", "low", "close"]:
        assert c in df.columns
