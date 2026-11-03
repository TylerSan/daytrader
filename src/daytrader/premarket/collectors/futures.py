"""Futures, index, and VIX data collector using yfinance.

Collects current prices AND overnight session data (globex high/low).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


class FuturesCollector(Collector):
    DEFAULT_SYMBOLS = ["ES=F", "NQ=F", "YM=F", "GC=F", "^VIX"]

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
                entry = {
                    "price": info.get("regularMarketPrice"),
                    "change_pct": info.get("regularMarketChangePercent"),
                    "prev_close": info.get("regularMarketPreviousClose"),
                    "day_high": info.get("regularMarketDayHigh"),
                    "day_low": info.get("regularMarketDayLow"),
                    "open": info.get("regularMarketOpen"),
                }

                # Fetch intraday data for overnight session context
                # 1m interval, last 1 day captures globex session
                hist = ticker.history(period="1d", interval="1m")
                if not hist.empty and hasattr(hist.index, 'tz'):
                    hours = hist.index.hour
                    minutes = hist.index.minute

                    # Pre-RTH filter: only bars before 09:30 ET.
                    # This excludes regular-trading-hours bars so the
                    # "overnight" range stays correct even when the
                    # report is generated after the market opens.
                    pre_rth_mask = (hours < 9) | ((hours == 9) & (minutes < 30))
                    pre_rth = hist[pre_rth_mask]

                    if not pre_rth.empty:
                        entry["overnight_high"] = round(float(pre_rth["High"].max()), 2)
                        entry["overnight_low"] = round(float(pre_rth["Low"].min()), 2)
                        entry["overnight_range"] = round(
                            entry["overnight_high"] - entry["overnight_low"], 2
                        )

                    # Asia session approximation: entries with hour 18-23, 0-1
                    asia_mask = (hours >= 18) | (hours <= 1)
                    asia = hist[asia_mask]
                    if not asia.empty:
                        entry["asia_high"] = round(float(asia["High"].max()), 2)
                        entry["asia_low"] = round(float(asia["Low"].min()), 2)

                    # Europe session approximation: entries with hour 2-7
                    europe_mask = (hours >= 2) & (hours <= 7)
                    europe = hist[europe_mask]
                    if not europe.empty:
                        entry["europe_high"] = round(float(europe["High"].max()), 2)
                        entry["europe_low"] = round(float(europe["Low"].min()), 2)

                result[symbol] = entry
            except Exception:
                result[symbol] = {"price": None, "change_pct": None, "prev_close": None}
        return result
