from unittest.mock import patch, MagicMock
from decimal import Decimal
import pandas as pd
import pytest

from daytrader.premarket.collectors.levels import LevelsCollector


@pytest.mark.asyncio
async def test_levels_collector_returns_key_levels():
    collector = LevelsCollector(symbols=["SPY"])
    with patch("daytrader.premarket.collectors.levels.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketDayHigh": 542.0,
            "regularMarketDayLow": 538.0,
            "regularMarketPreviousClose": 540.0,
            "regularMarketOpen": 540.5,
        }
        mock_t.history.return_value = pd.DataFrame({
            "High": [542.0, 541.5],
            "Low": [538.0, 538.5],
            "Close": [540.0, 541.0],
            "Volume": [1000000, 1200000],
        })
        mock_cls.return_value = mock_t

        result = await collector.collect()

    assert result.success is True
    assert "SPY" in result.data
    levels = result.data["SPY"]
    assert "prior_day_high" in levels
    assert "prior_day_low" in levels
    assert "prior_day_close" in levels
