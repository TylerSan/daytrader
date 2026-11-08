"""yfinance-backed drop-in replacement for `IBClient` (market data only).

Used as a fallback when TWS / IB Gateway is unreachable so a report can
still be produced. Exposes the same method surface as
`daytrader.core.ib_client.IBClient` and returns the same `OHLCV` /
`Snapshot` dataclasses, so callers and prompt_builder need no changes.

Known differences vs IB data (callers/prompt should treat as degraded):
  - Quotes are delayed (~10-15 min for CME futures on Yahoo) and are not
    tick-accurate; `get_snapshot` is synthesised from the last 1m bar
    (bid == ask == last == close).
  - Micro contracts map to their full-size Yahoo continuous tickers
    (MES -> ES=F, MNQ -> NQ=F, MGC -> GC=F). Prices match the micro to
    within rounding, but VOLUME is the full-size contract's volume.
  - No open interest, no contract chain, no per-month futures prices:
    those methods raise `YFDataUnavailable` (a RuntimeError subclass, so
    existing `except Exception` handlers degrade gracefully).
  - 4H bars are aggregated from 1h bars on UTC 4-hour boundaries
    (00/04/08/12/16/20 UTC). IB aligns 4H bars to the CME session open,
    so bucket edges differ. Partial buckets (e.g. around the daily
    maintenance break or the still-forming current bucket) are kept.
  - yfinance intraday history limits: 1m <= ~7 days, 5m/15m <= 60 days,
    1h <= 730 days. Lookback windows are clamped below these.

Timestamps are bar START times in UTC (as IB returns with formatDate=2).
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from daytrader.core.ib_client import OHLCV, Snapshot


class YFDataUnavailable(RuntimeError):
    """Raised for data yfinance cannot provide (OI, contract chain, specific contract months)."""


YF_TICKERS: dict[str, str] = {
    "MES": "ES=F",
    "ES": "ES=F",
    "MNQ": "NQ=F",
    "NQ": "NQ=F",
    "MGC": "GC=F",
    "GC": "GC=F",
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "GLD": "GLD",
}

# timeframe -> yfinance download interval (4H is aggregated from 1h).
_TIMEFRAME_TO_YF_INTERVAL: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1H": "1h",
    "4H": "1h",
    "1D": "1d",
    "1W": "1wk",
    "1M": "1mo",
}

# Max lookback (calendar days) per yfinance interval, kept slightly under
# Yahoo's hard limits (1m: 8d/request within 30d; 5m/15m: 60d; 1h: 730d).
_MAX_LOOKBACK_DAYS: dict[str, float] = {
    "1m": 6.0,
    "5m": 59.0,
    "15m": 59.0,
    "1h": 729.0,
}


def _ticker_for(symbol: str) -> str:
    """Map a DayTrader symbol to its Yahoo ticker. Unknown -> ValueError."""
    if symbol not in YF_TICKERS:
        raise ValueError(f"Unknown symbol {symbol!r}; add it to YF_TICKERS")
    return YF_TICKERS[symbol]


def _lookback_days(timeframe: str, bars: int) -> float:
    """Calendar-day window generous enough to yield `bars` bars, clamped."""
    # Intraday pads +4 days (not +2) so a run on a Sunday / Monday morning
    # or after a holiday still reaches back past the weekend close.
    if timeframe == "1m":
        days = bars / 60 / 23 + 4
    elif timeframe == "5m":
        days = bars * 5 / 60 / 23 + 4
    elif timeframe == "15m":
        days = bars * 15 / 60 / 23 + 4
    elif timeframe == "1H":
        days = bars / 23 + 3
    elif timeframe == "4H":
        days = bars * 4 / 23 + 3
    elif timeframe == "1D":
        days = bars * 1.5 + 5
    elif timeframe == "1W":
        days = bars * 7 * 1.1 + 7
    elif timeframe == "1M":
        days = bars * 31 + 10
    else:  # pragma: no cover - guarded by caller
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    cap = _MAX_LOOKBACK_DAYS.get(_TIMEFRAME_TO_YF_INTERVAL[timeframe])
    if cap is not None:
        days = min(days, cap)
    return days


def _normalize_frame(df: Any) -> Any:
    """Flatten MultiIndex columns, drop NaN closes, make index UTC-aware."""
    import pandas as pd

    if df is None or len(df) == 0:
        return None
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance >= 0.2 returns (Price, Ticker) columns even for one ticker.
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    if "Close" not in df.columns:
        return None
    df = df[df["Close"].notna()]
    if len(df) == 0:
        return None
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df.index = idx
    return df.sort_index()


def _f(value: Any) -> float:
    """float() that maps NaN/None to 0.0 (e.g. index volume)."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out


def _rows_to_ohlcv(df: Any) -> list[OHLCV]:
    out: list[OHLCV] = []
    has_vol = "Volume" in df.columns
    for ts, row in df.iterrows():
        out.append(
            OHLCV(
                timestamp=ts.to_pydatetime(),
                open=_f(row["Open"]),
                high=_f(row["High"]),
                low=_f(row["Low"]),
                close=_f(row["Close"]),
                volume=_f(row["Volume"]) if has_vol else 0.0,
            )
        )
    return out


def _aggregate_4h(bars_1h: list[OHLCV]) -> list[OHLCV]:
    """Aggregate hourly bars into 4H bars on UTC 4-hour boundaries.

    bucket = (UTC date, hour // 4). Each output bar: open = first open,
    high = max, low = min, close = last close, volume = sum, timestamp =
    first contributing bar's timestamp (bar start, like IB). Partial
    buckets (fewer than 4 hourly bars) are kept — any bucket with >= 1
    bar is emitted. NOTE: IB aligns 4H bars to the CME session, so bucket
    edges differ from IB's.
    """
    out: list[OHLCV] = []
    group: list[OHLCV] = []
    current_key = None
    for b in bars_1h:
        key = (b.timestamp.date(), b.timestamp.hour // 4)
        if current_key is not None and key != current_key and group:
            out.append(_merge(group))
            group = []
        current_key = key
        group.append(b)
    if group:
        out.append(_merge(group))
    return out


def _merge(group: list[OHLCV]) -> OHLCV:
    return OHLCV(
        timestamp=group[0].timestamp,
        open=group[0].open,
        high=max(b.high for b in group),
        low=min(b.low for b in group),
        close=group[-1].close,
        volume=sum(b.volume for b in group),
    )


def _default_download(*args: Any, **kwargs: Any) -> Any:
    import yfinance as yf

    return yf.download(*args, **kwargs)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class YFClient:
    """yfinance-backed client with IBClient's market-data method surface."""

    source_name: str = "yfinance"

    def __init__(
        self,
        download: Callable[..., Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._download = download or _default_download
        self._now = now or _default_now

    # -- lifecycle (no-ops; kept for IBClient parity) ----------------------

    def connect(self, timeout: int = 10) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def reconnect(self) -> None:
        return None

    def is_healthy(self) -> bool:
        return True

    # -- data --------------------------------------------------------------

    def _fetch(
        self,
        ticker: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> Any:
        df = self._download(
            ticker,
            interval=interval,
            start=start,
            end=end,
            prepost=True,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        return _normalize_frame(df)

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "4H",
        bars: int = 50,
        end_time: datetime | None = None,
    ) -> list[OHLCV]:
        """Fetch historical bars from Yahoo Finance.

        Raises ValueError for unsupported timeframe / unknown symbol before
        any download. Returns [] if Yahoo returns no data.
        """
        if timeframe not in _TIMEFRAME_TO_YF_INTERVAL:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        ticker = _ticker_for(symbol)
        interval = _TIMEFRAME_TO_YF_INTERVAL[timeframe]

        if end_time is not None and end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        ref = end_time if end_time is not None else self._now()
        start = ref - timedelta(days=_lookback_days(timeframe, bars))
        # yfinance `end` is exclusive; pad so the latest bar is included.
        if interval in ("1d", "1wk", "1mo"):
            end = ref + timedelta(days=1)
        else:
            end = ref + timedelta(hours=1)

        df = self._fetch(ticker, interval, start, end)
        if df is None:
            result: list[OHLCV] = []
        else:
            if end_time is not None:
                df = df[df.index <= end_time]
            result = _rows_to_ohlcv(df)
            if timeframe == "4H":
                result = _aggregate_4h(result)
            result = result[-bars:] if bars > 0 else []

        if len(result) < int(bars * 0.7):
            pct = len(result) / bars if bars else 0.0
            print(
                f"[yf_client] WARNING: requested {bars} {timeframe} bars for {symbol}, "
                f"received {len(result)} ({pct:.0%})",
                file=sys.stderr,
            )
        return result

    def get_daily_close(self, contract: Any) -> float:
        """Latest daily close for an Index/Stock/ContFuture-like object.

        Specific futures months (non-empty lastTradeDateOrContractMonth)
        raise YFDataUnavailable — Yahoo has no per-month contracts we trust.
        """
        if getattr(contract, "lastTradeDateOrContractMonth", ""):
            raise YFDataUnavailable(
                f"yfinance has no per-month futures data for {contract!r}"
            )
        ticker = _ticker_for(getattr(contract, "symbol", ""))
        ref = self._now()
        df = self._fetch(
            ticker, "1d", ref - timedelta(days=10), ref + timedelta(days=1)
        )
        if df is None:
            raise YFDataUnavailable(f"No daily bars returned for {ticker}")
        return float(df["Close"].iloc[-1])

    def get_snapshot(self, symbol: str) -> Snapshot:
        """Synthesise a snapshot from the last available 1m bar (delayed)."""
        bars = self.get_bars(symbol, "1m", 5)
        if not bars:
            raise YFDataUnavailable(f"No 1m bars available for {symbol}")
        last = bars[-1]
        return Snapshot(
            timestamp=last.timestamp,
            bid=last.close,
            ask=last.close,
            last=last.close,
        )

    def get_open_interest(self, symbol: str):
        raise YFDataUnavailable(f"yfinance does not provide open interest ({symbol})")

    def get_contract_chain(self, symbol: str):
        raise YFDataUnavailable(f"yfinance does not provide a contract chain ({symbol})")

    def get_active_front_expiry(self, symbol: str):
        raise YFDataUnavailable(f"yfinance does not provide front expiry ({symbol})")
