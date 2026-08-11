from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pandas as pd
import pytest

from daytrader.premarket.collectors.futures import (
    FuturesCollector,
    compute_indicators,
)


def _daily_frame(closes: list[float]) -> pd.DataFrame:
    """Build a daily OHLC frame from a close series (H/L = close ±0.5%)."""
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="B", tz="UTC")
    close = pd.Series(closes, index=idx)
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close),
            "High": close * 1.005,
            "Low": close * 0.995,
            "Close": close,
        },
        index=idx,
    )


@pytest.fixture
def mock_yf_ticker():
    ticker = MagicMock()
    ticker.info = {"regularMarketPrice": 5425.50, "regularMarketChangePercent": 0.35}
    ticker.fast_info = {"last_price": 5425.50}
    return ticker


@pytest.mark.asyncio
async def test_futures_collector_returns_data():
    collector = FuturesCollector(symbols=["ES=F", "NQ=F", "^VIX"])
    with patch("daytrader.premarket.collectors.futures.yf.Ticker") as mock_ticker_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketPrice": 5425.50,
            "regularMarketChangePercent": 0.35,
            "regularMarketPreviousClose": 5400.0,
        }
        mock_ticker_cls.return_value = mock_t

        result = await collector.collect()

    assert result.success is True
    assert result.collector_name == "futures"
    assert "ES=F" in result.data
    assert result.data["ES=F"]["price"] == 5425.50


@pytest.mark.asyncio
async def test_futures_collector_handles_error():
    collector = FuturesCollector(symbols=["ES=F"])
    with patch("daytrader.premarket.collectors.futures.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.side_effect = Exception("Network error")
        result = await collector.collect()

    assert result.success is False
    assert "Network error" in result.error


def test_compute_indicators_empty_returns_empty():
    assert compute_indicators(pd.DataFrame()) == {}
    assert compute_indicators(None) == {}


def test_compute_indicators_missing_columns_returns_empty():
    df = pd.DataFrame({"Close": [1, 2, 3]})
    assert compute_indicators(df) == {}


def test_compute_indicators_uptrend_full_fields():
    # 120 rising closes (~24 weeks) → price above both SMAs → uptrend, and
    # enough weekly bars for the 14-week ATR.
    closes = [7000 + i * 10 for i in range(120)]
    out = compute_indicators(_daily_frame(closes))

    assert out["trend"] == "up"
    for key in (
        "atr_14",
        "atr_14_pct",
        "atr_14_weekly",
        "sma_20",
        "sma_50",
        "dist_sma20_pct",
        "range_20d_high",
        "range_20d_low",
        "range_position_pct",
        "change_5d_pct",
        "change_20d_pct",
    ):
        assert key in out and out[key] is not None

    last = closes[-1]
    assert out["sma_20"] < last          # rising series → SMA below price
    assert out["dist_sma20_pct"] > 0
    assert out["range_20d_high"] >= last
    assert 0 <= out["range_position_pct"] <= 100


def test_compute_indicators_downtrend():
    closes = [7000 - i * 10 for i in range(60)]
    out = compute_indicators(_daily_frame(closes))
    assert out["trend"] == "down"
    assert out["dist_sma20_pct"] < 0


def test_compute_indicators_short_history_partial_fields():
    # Only 10 bars: no SMA20/SMA50/ATR, but momentum where possible.
    out = compute_indicators(_daily_frame([7000 + i for i in range(10)]))
    assert "sma_20" not in out
    assert "atr_14" not in out
    assert "trend" not in out
    assert out.get("change_5d_pct") is not None


@pytest.mark.asyncio
async def test_futures_collector_attaches_indicators():
    collector = FuturesCollector(symbols=["ES=F"])
    daily = _daily_frame([7000 + i * 10 for i in range(60)])
    empty_1m = pd.DataFrame(columns=["High", "Low", "Close"])

    with patch("daytrader.premarket.collectors.futures.yf.Ticker") as mock_ticker_cls:
        mock_t = MagicMock()
        mock_t.info = {"regularMarketPrice": 7590.0, "regularMarketPreviousClose": 7580.0}
        # First history() call is the 1m overnight fetch, second is the daily fetch.
        mock_t.history.side_effect = [empty_1m, daily]
        mock_ticker_cls.return_value = mock_t

        result = await collector.collect()

    assert result.success is True
    ind = result.data["ES=F"]["indicators"]
    assert ind["trend"] == "up"
    assert ind["atr_14"] is not None
