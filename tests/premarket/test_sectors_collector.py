from unittest.mock import patch, MagicMock
import pytest

from daytrader.premarket.collectors.sectors import SectorCollector


@pytest.mark.asyncio
async def test_sector_collector_returns_data():
    collector = SectorCollector()
    with patch("daytrader.premarket.collectors.sectors.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.info = {
            "regularMarketChangePercent": 1.5,
            "shortName": "Technology Select Sector",
        }
        mock_cls.return_value = mock_t
        result = await collector.collect()

    assert result.success is True
    assert result.collector_name == "sectors"
    assert len(result.data) > 0


@pytest.mark.asyncio
async def test_sector_collector_handles_error():
    collector = SectorCollector()
    with patch("daytrader.premarket.collectors.sectors.yf.Ticker") as mock_cls:
        mock_cls.side_effect = Exception("API error")
        result = await collector.collect()

    assert result.success is False
