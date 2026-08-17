"""Key price levels collector using yfinance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


class LevelsCollector(Collector):
    DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM"]

    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = symbols or self.DEFAULT_SYMBOLS

    @property
    def name(self) -> str:
        return "levels"

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
        result = {}
        for symbol in self._symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                hist = ticker.history(period="5d")

                levels = {
                    "prior_day_high": info.get("regularMarketDayHigh"),
                    "prior_day_low": info.get("regularMarketDayLow"),
                    "prior_day_close": info.get("regularMarketPreviousClose"),
                    "premarket_price": info.get("preMarketPrice"),
                }

                if not hist.empty and "Volume" in hist.columns:
                    vol = hist["Volume"]
                    close = hist["Close"]
                    if vol.sum() > 0:
                        vwap = (close * vol).sum() / vol.sum()
                        levels["approx_vwap_5d"] = round(float(vwap), 2)

                    levels["weekly_high"] = round(float(hist["High"].max()), 2)
                    levels["weekly_low"] = round(float(hist["Low"].min()), 2)

                result[symbol] = levels
            except Exception:
                result[symbol] = {}
        return result
