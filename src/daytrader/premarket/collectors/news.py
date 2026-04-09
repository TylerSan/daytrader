"""Financial news and economic calendar collector."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


def _extract_news_item(item: dict, symbol: str) -> dict | None:
    """Extract title/publisher from yfinance news item (handles both API formats)."""
    # New format: nested under "content"
    content = item.get("content", {})
    title = content.get("title") or item.get("title", "")
    if not title:
        return None

    publisher = ""
    provider = content.get("provider", {})
    if isinstance(provider, dict):
        publisher = provider.get("displayName", "")
    if not publisher:
        publisher = item.get("publisher", "")

    link = ""
    canonical = content.get("canonicalUrl", {})
    if isinstance(canonical, dict):
        link = canonical.get("url", "")
    if not link:
        link = item.get("link", "")

    published = content.get("pubDate") or item.get("providerPublishTime", "")
    summary = content.get("summary", "")

    return {
        "title": title,
        "publisher": publisher,
        "link": link,
        "symbol": symbol,
        "published": published,
        "summary": summary[:200] if summary else "",
    }


class NewsCollector(Collector):
    """Collects recent financial news headlines for key instruments."""

    DEFAULT_SYMBOLS = ["SPY", "QQQ", "^VIX", "GC=F", "ES=F"]

    def __init__(self, symbols: list[str] | None = None, max_per_symbol: int = 5) -> None:
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
            try:
                ticker = yf.Ticker(symbol)
                news_items = ticker.news or []
                for item in news_items[: self._max]:
                    parsed = _extract_news_item(item, symbol)
                    if parsed and parsed["title"] not in seen_titles:
                        seen_titles.add(parsed["title"])
                        all_news.append(parsed)
            except Exception:
                continue

        return {"headlines": all_news[:20]}
