"""Financial news and economic calendar collector."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


class NewsCollector(Collector):
    """Collects recent financial news headlines for key instruments."""

    DEFAULT_SYMBOLS = ["SPY", "QQQ", "^VIX", "GC=F"]

    def __init__(self, symbols: list[str] | None = None, max_per_symbol: int = 3) -> None:
        self._symbols = symbols or self.DEFAULT_SYMBOLS
        self._max = max_per_symbol

    @property
    def name(self) -> str:
        return "news"

    async def collect(self) -> CollectorResult:
        try:
            data = await asyncio.to_thread(self._fetch)
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data=data,
                success=True,
            )
        except Exception as e:
            return CollectorResult(
                collector_name=self.name,
                timestamp=datetime.now(timezone.utc),
                data={},
                success=False,
                error=str(e),
            )

    def _fetch(self) -> dict:
        all_news: list[dict] = []
        seen_titles: set[str] = set()

        for symbol in self._symbols:
            ticker = yf.Ticker(symbol)
            try:
                news_items = ticker.news or []
                for item in news_items[: self._max]:
                    title = item.get("title", "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append({
                            "title": title,
                            "publisher": item.get("publisher", ""),
                            "link": item.get("link", ""),
                            "symbol": symbol,
                            "published": item.get("providerPublishTime", ""),
                        })
            except Exception:
                continue

        return {"headlines": all_news[:15]}  # Cap at 15 headlines
