"""Pre-market movers scanner — identifies stocks with unusual activity."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult

# Universe to scan — high-liquidity stocks commonly traded intraday
SCAN_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "NFLX", "JPM", "BAC", "GS", "XOM", "CVX",
    "COIN", "MARA", "SQ", "PLTR", "SOFI", "RIVN",
]


class MoversCollector(Collector):
    """Scans for pre-market movers based on gap and volume."""

    def __init__(
        self,
        universe: list[str] | None = None,
        gap_threshold: float = 1.5,
        max_results: int = 10,
    ) -> None:
        self._universe = universe or SCAN_UNIVERSE
        self._gap_threshold = gap_threshold
        self._max_results = max_results

    @property
    def name(self) -> str:
        return "movers"

    async def collect(self) -> CollectorResult:
        try:
            data = await asyncio.to_thread(self._scan)
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

    def _scan(self) -> dict:
        movers = []

        for symbol in self._universe:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                prev_close = info.get("regularMarketPreviousClose")
                pre_price = info.get("preMarketPrice")
                current = info.get("regularMarketPrice")
                volume = info.get("regularMarketVolume", 0)
                avg_volume = info.get("averageDailyVolume10Day", 1)

                price = pre_price or current
                if not price or not prev_close:
                    continue

                gap_pct = ((price - prev_close) / prev_close) * 100
                vol_ratio = volume / avg_volume if avg_volume else 0

                if abs(gap_pct) >= self._gap_threshold or vol_ratio >= 1.5:
                    movers.append({
                        "symbol": symbol,
                        "price": round(price, 2),
                        "prev_close": round(prev_close, 2),
                        "gap_pct": round(gap_pct, 2),
                        "volume": volume,
                        "avg_volume": avg_volume,
                        "vol_ratio": round(vol_ratio, 2),
                        "name": info.get("shortName", symbol),
                    })
            except Exception:
                continue

        # Sort by absolute gap percentage
        movers.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
        return {"movers": movers[: self._max_results]}
