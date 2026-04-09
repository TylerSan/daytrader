# tests/premarket/test_news_collector.py
from unittest.mock import patch, MagicMock
import pytest

from daytrader.premarket.collectors.news import NewsCollector


@pytest.mark.asyncio
async def test_news_collector_returns_headlines():
    collector = NewsCollector(symbols=["SPY"])
    with patch("daytrader.premarket.collectors.news.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.news = [
            {"title": "Market rallies on earnings", "publisher": "Reuters", "link": "http://example.com", "providerPublishTime": 1712000000},
            {"title": "Fed holds rates steady", "publisher": "Bloomberg", "link": "http://example.com", "providerPublishTime": 1712000100},
        ]
        mock_cls.return_value = mock_t
        result = await collector.collect()

    assert result.success is True
    assert len(result.data["headlines"]) == 2
    assert result.data["headlines"][0]["title"] == "Market rallies on earnings"


@pytest.mark.asyncio
async def test_news_collector_deduplicates():
    collector = NewsCollector(symbols=["SPY", "QQQ"])
    with patch("daytrader.premarket.collectors.news.yf.Ticker") as mock_cls:
        mock_t = MagicMock()
        mock_t.news = [
            {"title": "Same headline", "publisher": "Reuters", "link": "http://example.com", "providerPublishTime": 1712000000},
        ]
        mock_cls.return_value = mock_t
        result = await collector.collect()

    assert result.success is True
    assert len(result.data["headlines"]) == 1  # Deduplicated


@pytest.mark.asyncio
async def test_news_collector_handles_error():
    collector = NewsCollector(symbols=["SPY"])
    with patch("daytrader.premarket.collectors.news.yf.Ticker") as mock_cls:
        mock_cls.side_effect = Exception("API error")
        result = await collector.collect()

    assert result.success is False
