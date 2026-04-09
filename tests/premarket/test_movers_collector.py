# tests/premarket/test_movers_collector.py
from unittest.mock import patch, MagicMock
import pytest

from daytrader.premarket.collectors.movers import MoversCollector


@pytest.mark.asyncio
async def test_movers_collector_finds_gappers():
    collector = MoversCollector(universe=["AAPL", "TSLA"], gap_threshold=1.0)
    with patch("daytrader.premarket.collectors.movers.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketPreviousClose": 200.0,
            "preMarketPrice": 205.0,  # +2.5% gap
            "regularMarketPrice": 205.0,
            "regularMarketVolume": 5000000,
            "averageDailyVolume10Day": 3000000,
            "shortName": "Apple Inc.",
        }
        mock_cls.return_value = mock_t
        result = await collector.collect()

    assert result.success is True
    assert len(result.data["movers"]) > 0
    assert result.data["movers"][0]["gap_pct"] == 2.5


@pytest.mark.asyncio
async def test_movers_collector_filters_small_gaps():
    collector = MoversCollector(universe=["AAPL"], gap_threshold=5.0)
    with patch("daytrader.premarket.collectors.movers.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketPreviousClose": 200.0,
            "preMarketPrice": 201.0,  # +0.5% gap, below threshold
            "regularMarketPrice": 201.0,
            "regularMarketVolume": 1000000,
            "averageDailyVolume10Day": 3000000,
            "shortName": "Apple Inc.",
        }
        mock_cls.return_value = mock_t
        result = await collector.collect()

    assert result.success is True
    assert len(result.data["movers"]) == 0  # Filtered out
