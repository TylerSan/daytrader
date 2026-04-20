"""Tests for bakeoff data layer."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from daytrader.research.bakeoff.data import detect_rollover_skip_dates, filter_rth
from daytrader.research.bakeoff.data import ET


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


def test_detect_rollover_skip_dates_empty_frame():
    df = pd.DataFrame(
        {"instrument_id": []},
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    assert detect_rollover_skip_dates(df) == []


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
        pd.Timestamp("2024-06-10 09:29", tz=ET),  # 09:29 ET — drop (pre-open)
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
