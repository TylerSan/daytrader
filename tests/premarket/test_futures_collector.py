from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.futures import FuturesCollector


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
