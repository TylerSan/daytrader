"""Unit tests for daytrader.reports.core.yf_client.YFClient (no network)."""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from daytrader.core.ib_client import OHLCV, Snapshot
from daytrader.reports.core.yf_client import YF_TICKERS, YFClient, YFDataUnavailable

NOW = datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc)


def _frame(n, start="2026-10-28 00:00", freq="h", tz="UTC", multi=None, base=100.0):
    idx = pd.date_range(start=start, periods=n, freq=freq, tz=tz)
    data = {
        "Open": [base + i for i in range(n)],
        "High": [base + i + 2 for i in range(n)],
        "Low": [base + i - 1 for i in range(n)],
        "Close": [base + i + 0.5 for i in range(n)],
        "Adj Close": [base + i + 0.5 for i in range(n)],
        "Volume": [10.0 * (i + 1) for i in range(n)],
    }
    df = pd.DataFrame(data, index=idx)
    if multi:
        df.columns = pd.MultiIndex.from_tuples(
            [(c, multi) for c in df.columns], names=["Price", "Ticker"]
        )
    return df


class FakeDownload:
    def __init__(self, df):
        self.df = df
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.df


def _client(df):
    dl = FakeDownload(df)
    return YFClient(download=dl, now=lambda: NOW), dl


# -- symbol mapping ---------------------------------------------------------


@pytest.mark.parametrize(
    "sym,ticker",
    [
        ("MES", "ES=F"), ("ES", "ES=F"), ("MNQ", "NQ=F"), ("NQ", "NQ=F"),
        ("MGC", "GC=F"), ("GC", "GC=F"), ("SPX", "^GSPC"), ("NDX", "^NDX"),
        ("GLD", "GLD"),
    ],
)
def test_symbol_mapping(sym, ticker):
    assert YF_TICKERS[sym] == ticker
    c, dl = _client(_frame(5, freq="D"))
    c.get_bars(sym, "1D", 5)
    assert dl.calls[0][0][0] == ticker


def test_unknown_symbol_raises_valueerror_without_download():
    c, dl = _client(_frame(5))
    with pytest.raises(ValueError):
        c.get_bars("ZZZ", "1H", 5)
    assert dl.calls == []


# -- timeframe -> interval --------------------------------------------------


@pytest.mark.parametrize(
    "tf,interval,max_days",
    [
        ("1m", "1m", 7), ("5m", "5m", 60), ("15m", "15m", 60),
        ("1H", "1h", 730), ("4H", "1h", 730), ("1D", "1d", None),
        ("1W", "1wk", None), ("1M", "1mo", None),
    ],
)
def test_timeframe_interval_and_window(tf, interval, max_days):
    c, dl = _client(_frame(3))
    # huge intraday request -> window clamped to yfinance limits
    c.get_bars("MES", tf, 50000 if max_days else 100)
    args, kw = dl.calls[0]
    assert kw["interval"] == interval
    assert isinstance(kw["start"], datetime) and isinstance(kw["end"], datetime)
    assert kw["start"] < NOW <= kw["end"]
    assert kw["prepost"] is True
    assert kw["auto_adjust"] is False
    assert kw["progress"] is False
    assert kw["threads"] is False
    assert "period" not in kw
    if max_days is not None:
        assert NOW - kw["start"] <= timedelta(days=max_days)


def test_window_generous_for_requested_bars():
    c, dl = _client(_frame(3))
    c.get_bars("MES", "1D", 20)
    kw = dl.calls[0][1]
    assert NOW - kw["start"] >= timedelta(days=20)


def test_unsupported_timeframe_raises_before_download():
    c, dl = _client(_frame(5))
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        c.get_bars("MES", "2H", 5)
    assert dl.calls == []


# -- normalisation ----------------------------------------------------------


def test_flat_columns_tz_aware_index():
    c, _ = _client(_frame(3, tz="America/New_York"))
    out = c.get_bars("MES", "1H", 3)
    assert len(out) == 3
    assert all(isinstance(b, OHLCV) for b in out)
    assert out[0].timestamp.tzinfo is not None
    assert out[0].timestamp.utcoffset() == timedelta(0)
    # 00:00 New York (EDT, -4) == 04:00 UTC
    assert out[0].timestamp == datetime(2026, 10, 28, 4, 0, tzinfo=timezone.utc)
    assert isinstance(out[0].close, float)


def test_multiindex_columns_tz_naive_index():
    c, _ = _client(_frame(3, tz=None, multi="ES=F"))
    out = c.get_bars("MES", "1H", 3)
    assert len(out) == 3
    assert out[0].timestamp == datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
    assert out[-1].close == 102.5
    assert out[-1].volume == 30.0


def test_truncation_oldest_first_last_n():
    c, _ = _client(_frame(10))
    out = c.get_bars("MES", "1H", 4)
    assert [b.open for b in out] == [106.0, 107.0, 108.0, 109.0]
    assert out == sorted(out, key=lambda b: b.timestamp)


def test_end_time_filter():
    c, dl = _client(_frame(10))
    end = datetime(2026, 10, 28, 5, 0, tzinfo=timezone.utc)
    out = c.get_bars("MES", "1H", 50, end_time=end)
    assert out[-1].timestamp == end
    assert len(out) == 6
    kw = dl.calls[0][1]
    assert kw["start"] < end <= kw["end"]


def test_nan_rows_dropped():
    df = _frame(5)
    df.iloc[2, df.columns.get_loc("Close")] = float("nan")
    c, _ = _client(df)
    out = c.get_bars("MES", "1H", 5, end_time=None)
    assert len(out) == 4
    assert all(not math.isnan(b.close) for b in out)


def test_empty_frame_returns_empty_list():
    c, _ = _client(pd.DataFrame())
    assert c.get_bars("MES", "1H", 5) == []


def test_none_download_returns_empty_list():
    c, _ = _client(None)
    assert c.get_bars("MES", "1D", 5) == []


def test_warning_when_under_70pct(capsys):
    c, _ = _client(_frame(3))
    c.get_bars("MES", "1H", 10)
    err = capsys.readouterr().err
    assert "[yf_client] WARNING: requested 10 1H bars for MES, received 3" in err


def test_no_warning_when_enough(capsys):
    c, _ = _client(_frame(10))
    c.get_bars("MES", "1H", 10)
    assert "WARNING" not in capsys.readouterr().err


# -- 4H aggregation ---------------------------------------------------------


def test_4h_aggregation_eight_hourly_bars():
    c, _ = _client(_frame(8, start="2026-10-28 00:00"))
    out = c.get_bars("MES", "4H", 2)
    assert len(out) == 2
    a, b = out
    assert a.timestamp == datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
    assert b.timestamp == datetime(2026, 10, 28, 4, 0, tzinfo=timezone.utc)
    # bars 0..3: open 100..103, high +2, low -1, close +0.5, vol 10..40
    assert (a.open, a.high, a.low, a.close, a.volume) == (100.0, 105.0, 99.0, 103.5, 100.0)
    # bars 4..7
    assert (b.open, b.high, b.low, b.close, b.volume) == (104.0, 109.0, 103.0, 107.5, 260.0)


def test_4h_partial_buckets_kept_and_utc_aligned():
    # starts 02:00 UTC -> bucket 0 has 2 bars (02,03), bucket 1 has 4, bucket 2 has 1
    c, _ = _client(_frame(7, start="2026-10-28 02:00"))
    out = c.get_bars("MES", "4H", 10)
    assert [b.timestamp.hour for b in out] == [2, 4, 8]
    assert out[0].volume == 10.0 + 20.0
    assert out[2].open == out[2].close - 0.5  # single-bar bucket


# -- daily close ------------------------------------------------------------


def test_get_daily_close_index_maps_and_returns_last_close():
    df = _frame(5, freq="D", tz=None)
    df.iloc[-1, df.columns.get_loc("Close")] = float("nan")  # trailing NaN skipped
    c, dl = _client(df)
    px = c.get_daily_close(SimpleNamespace(symbol="SPX", lastTradeDateOrContractMonth=""))
    assert isinstance(px, float)
    assert px == 103.5
    args, kw = dl.calls[0]
    assert args[0] == "^GSPC"
    assert kw["interval"] == "1d"
    assert NOW - kw["start"] <= timedelta(days=11)


def test_get_daily_close_without_month_attr():
    c, dl = _client(_frame(3, freq="D"))
    assert c.get_daily_close(SimpleNamespace(symbol="GLD")) == 102.5
    assert dl.calls[0][0][0] == "GLD"


def test_get_daily_close_specific_future_month_unavailable():
    c, dl = _client(_frame(3, freq="D"))
    with pytest.raises(YFDataUnavailable):
        c.get_daily_close(
            SimpleNamespace(symbol="MES", lastTradeDateOrContractMonth="20261219")
        )
    assert dl.calls == []


def test_get_daily_close_empty_raises():
    c, _ = _client(pd.DataFrame())
    with pytest.raises(RuntimeError):
        c.get_daily_close(SimpleNamespace(symbol="NDX", lastTradeDateOrContractMonth=""))


# -- snapshot ---------------------------------------------------------------


def test_get_snapshot_from_last_1m_bar():
    c, dl = _client(_frame(5, freq="min"))
    snap = c.get_snapshot("MNQ")
    assert isinstance(snap, Snapshot)
    assert snap.bid == snap.ask == snap.last == 104.5
    assert dl.calls[0][1]["interval"] == "1m"
    assert dl.calls[0][0][0] == "NQ=F"


def test_get_snapshot_empty_raises():
    c, _ = _client(pd.DataFrame())
    with pytest.raises(YFDataUnavailable):
        c.get_snapshot("MES")


# -- unavailable data / lifecycle ------------------------------------------


@pytest.mark.parametrize(
    "method", ["get_open_interest", "get_contract_chain", "get_active_front_expiry"]
)
def test_unavailable_methods(method):
    c, dl = _client(_frame(3))
    with pytest.raises(YFDataUnavailable) as ei:
        getattr(c, method)("MES")
    assert isinstance(ei.value, RuntimeError)
    assert dl.calls == []


def test_lifecycle_noops():
    c, dl = _client(_frame(3))
    assert c.connect() is None
    assert c.connect(timeout=3) is None
    assert c.disconnect() is None
    assert c.reconnect() is None
    assert c.is_healthy() is True
    assert c.source_name == "yfinance"
    assert dl.calls == []


def test_default_construction_does_not_import_network():
    c = YFClient()
    assert c.is_healthy() is True


# -- real network smoke (opt-in) -------------------------------------------


@pytest.mark.skipif(
    os.environ.get("DAYTRADER_NET_TESTS") != "1",
    reason="set DAYTRADER_NET_TESTS=1 to hit Yahoo Finance",
)
def test_network_smoke():
    c = YFClient()
    bars = c.get_bars("MES", "1D", 3)
    assert bars and 1000 < bars[-1].close < 20000
    spx = c.get_daily_close(SimpleNamespace(symbol="SPX", lastTradeDateOrContractMonth=""))
    assert 1000 < spx < 20000
