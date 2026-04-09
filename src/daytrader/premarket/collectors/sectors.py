"""Sector performance collector using yfinance sector ETFs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLC": "Communication",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLB": "Materials",
}


class SectorCollector(Collector):
    def __init__(self, etfs: dict[str, str] | None = None) -> None:
        self._etfs = etfs or SECTOR_ETFS

    @property
    def name(self) -> str:
        return "sectors"

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
        sectors = {}
        for symbol, sector_name in self._etfs.items():
            ticker = yf.Ticker(symbol)
            try:
                info = ticker.info
                sectors[symbol] = {
                    "name": sector_name,
                    "change_pct": info.get("regularMarketChangePercent"),
                }
            except Exception:
                sectors[symbol] = {"name": sector_name, "change_pct": None}
        return sectors
