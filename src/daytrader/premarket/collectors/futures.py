"""Futures, index, and VIX data collector using yfinance.

Collects current prices AND overnight session data (globex high/low).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from daytrader.premarket.collectors.base import Collector, CollectorResult


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder-style ATR via simple rolling mean of True Range."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def compute_indicators(daily: pd.DataFrame) -> dict:
    """Compute ATR / SMA / range / trend indicators from a daily OHLC frame.

    The AI analyst previously had to eyeball multi-timeframe structure from raw
    prices; these fields give it computed numbers instead.

    Returns ``{}`` when the frame is empty or missing OHLC columns. Individual
    indicators are omitted when there aren't enough bars to compute them, so a
    short history still yields whatever is available.
    """
    if daily is None or getattr(daily, "empty", True):
        return {}
    if not {"High", "Low", "Close"}.issubset(daily.columns):
        return {}

    close = daily["Close"]
    last = float(close.iloc[-1])
    out: dict = {}

    def _r(x) -> float | None:
        return round(float(x), 2) if x is not None and not pd.isna(x) else None

    # Daily ATR(14) — day-trading stop width & expected daily range.
    if len(daily) >= 15:
        atr14 = _atr(daily, 14).iloc[-1]
        out["atr_14"] = _r(atr14)
        out["atr_14_pct"] = _r(atr14 / last * 100) if last else None

    # Weekly ATR(14) — swing stop width & expected weekly range.
    weekly = (
        daily.resample("W")
        .agg({"High": "max", "Low": "min", "Close": "last"})
        .dropna()
    )
    if len(weekly) >= 15:
        watr = _atr(weekly, 14).iloc[-1]
        out["atr_14_weekly"] = _r(watr)
        out["atr_14_weekly_pct"] = _r(watr / last * 100) if last else None

    # Moving averages + distance of price from them.
    sma20 = sma50 = None
    if len(close) >= 20:
        sma20 = float(close.rolling(20).mean().iloc[-1])
        out["sma_20"] = _r(sma20)
        out["dist_sma20_pct"] = _r((last / sma20 - 1) * 100) if sma20 else None
    if len(close) >= 50:
        sma50 = float(close.rolling(50).mean().iloc[-1])
        out["sma_50"] = _r(sma50)
        out["dist_sma50_pct"] = _r((last / sma50 - 1) * 100) if sma50 else None

    # 20-day range and where price sits within it (0% = low, 100% = high).
    if len(daily) >= 20:
        hi20 = float(daily["High"].rolling(20).max().iloc[-1])
        lo20 = float(daily["Low"].rolling(20).min().iloc[-1])
        out["range_20d_high"] = _r(hi20)
        out["range_20d_low"] = _r(lo20)
        span = hi20 - lo20
        out["range_position_pct"] = _r((last - lo20) / span * 100) if span else None

    # Trend classification from price/SMA alignment.
    if sma20 is not None and sma50 is not None:
        if last > sma20 > sma50:
            out["trend"] = "up"
        elif last < sma20 < sma50:
            out["trend"] = "down"
        else:
            out["trend"] = "mixed"

    # Momentum.
    if len(close) >= 6:
        out["change_5d_pct"] = _r((last / float(close.iloc[-6]) - 1) * 100)
    if len(close) >= 21:
        out["change_20d_pct"] = _r((last / float(close.iloc[-21]) - 1) * 100)

    return out


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
                if not hist.empty:
                    entry["overnight_high"] = round(float(hist["High"].max()), 2)
                    entry["overnight_low"] = round(float(hist["Low"].min()), 2)
                    entry["overnight_range"] = round(
                        entry["overnight_high"] - entry["overnight_low"], 2
                    )

                    # Split into approximate Asia (18:00-02:00 ET) and Europe (02:00-08:00 ET) sessions
                    # yfinance returns times in exchange timezone
                    if hasattr(hist.index, 'tz'):
                        hours = hist.index.hour
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

                # Daily indicators (ATR / SMA / 20d range / trend / momentum).
                # 4mo of daily bars covers the 50-day SMA and 14-week ATR.
                try:
                    daily = ticker.history(period="4mo", interval="1d")
                    indicators = compute_indicators(daily)
                    if indicators:
                        entry["indicators"] = indicators
                except Exception:
                    pass

                result[symbol] = entry
            except Exception:
                result[symbol] = {"price": None, "change_pct": None, "prev_close": None}
        return result
