"""Futures, index, and VIX data collector using yfinance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


class FuturesCollector(Collector):
    DEFAULT_SYMBOLS = ["ES=F", "NQ=F", "YM=F", "^VIX"]

    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = symbols or self.DEFAULT_SYMBOLS

    @property
    def name(self) -> str:
        return "futures"

    async def collect(self) -> CollectorResult:
        try:
            data = await asyncio.to_thread(self._fetch_all)
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

    def _fetch_all(self) -> dict:
        result = {}
        for symbol in self._symbols:
            ticker = yf.Ticker(symbol)
            try:
                info = ticker.info
                result[symbol] = {
                    "price": info.get("regularMarketPrice"),
                    "change_pct": info.get("regularMarketChangePercent"),
                    "prev_close": info.get("regularMarketPreviousClose"),
                }
            except Exception:
                result[symbol] = {"price": None, "change_pct": None, "prev_close": None}
        return result
