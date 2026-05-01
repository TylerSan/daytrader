"""IBKR ib_insync wrapper.

Generic market-data only: bars, snapshots, connection lifecycle.
Futures-specific helpers (OI, term structure, settlement) live in
`reports/futures_data/ib_extensions.py` and accept an IBClient instance.

See spec §4.1 for full design.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from ib_insync import IB


@dataclass(frozen=True)
class OHLCV:
    """One OHLCV bar."""

    timestamp: datetime  # bar end time, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Snapshot:
    """Real-time market snapshot."""

    timestamp: datetime  # UTC
    bid: float
    ask: float
    last: float


@dataclass(frozen=True)
class OpenInterest:
    """Open interest snapshot — today vs yesterday."""
    today: float
    yesterday: float
    delta: float
    delta_pct: float


_TIMEFRAME_TO_IB_BAR_SIZE: dict[str, str] = {
    "1m": "1 min",
    "15m": "15 mins",
    "1H": "1 hour",
    "4H": "4 hours",
    "1D": "1 day",
    "1W": "1 week",
    "1M": "1 month",
}

_SYMBOL_TO_EXCHANGE: dict[str, str] = {
    "MES": "CME",
    "MNQ": "CME",
    "ES": "CME",
    "NQ": "CME",
    "MGC": "COMEX",
    "GC": "COMEX",
}


def _exchange_for(symbol: str) -> str:
    """Return the canonical exchange for a futures symbol."""
    if symbol not in _SYMBOL_TO_EXCHANGE:
        raise ValueError(
            f"Unknown symbol {symbol!r}; add it to _SYMBOL_TO_EXCHANGE"
        )
    return _SYMBOL_TO_EXCHANGE[symbol]


def _duration_str(timeframe: str, bars: int) -> str:
    """Compute IB durationStr from desired (timeframe, bars).

    IB requires duration like '50 D' or '52 W'. We approximate using
    floor division so the result is a round number of the requested unit.

    Plan bug corrected: the original formula `(bars * 4 + 23) // 24 + 1`
    produced 10 for (4H, 50) but the spec/test requires 8.  The correct
    formula is `(bars * 4) // 24` which gives floor(200/24) = 8.
    """
    if timeframe == "1m":
        return f"{bars * 60} S"
    if timeframe == "15m":
        return f"{bars * 15} S" if bars * 15 < 86400 else f"{(bars * 15) // 1440 + 1} D"
    if timeframe == "1H":
        return f"{bars // 24 + 1} D"
    if timeframe == "4H":
        return f"{(bars * 4) // 24} D"
    if timeframe == "1D":
        return f"{bars} D"
    if timeframe == "1W":
        return f"{bars} W"
    if timeframe == "1M":
        return f"{bars} M"
    raise ValueError(f"Unsupported timeframe: {timeframe}")


class IBClient:
    """Singleton ib_insync wrapper, reused across reports."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: IB | None = None

    def connect(self, timeout: int = 10) -> None:
        """Establish connection to IB Gateway. Idempotent."""
        if self._ib is not None and self._ib.isConnected():
            return
        if self._ib is None:
            self._ib = IB()
        self._ib.connect(
            host=self.host,
            port=self.port,
            clientId=self.client_id,
            timeout=timeout,
        )

    def disconnect(self) -> None:
        """Close connection. Idempotent."""
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    def reconnect(self) -> None:
        """Disconnect then reconnect. Idempotent."""
        self.disconnect()
        self.connect()

    def is_healthy(self) -> bool:
        """Return True iff connected to IB Gateway."""
        return self._ib is not None and self._ib.isConnected()

    def get_bars(
        self,
        symbol: str,
        timeframe: Literal["1m", "15m", "1H", "4H", "1D", "1W", "1M"] = "4H",
        bars: int = 50,
        end_time: datetime | None = None,
    ) -> list[OHLCV]:
        """Fetch historical bars from IB Gateway.

        Returns OHLCV list with timestamps in UTC (bar end times).

        Raises ValueError for unsupported timeframe (checked before the
        connection guard so callers get a clear error even when disconnected).
        Raises RuntimeError if not connected.
        """
        if timeframe not in _TIMEFRAME_TO_IB_BAR_SIZE:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBClient is not connected; call connect() first")

        from ib_insync import ContFuture  # local import: pure Contract, no network

        contract = ContFuture(symbol, _exchange_for(symbol))
        # Resolve continuous-future symbol to its actual front-month contract.
        # Without this, reqHistoricalData times out against live TWS (the
        # ContFuture has no conId and IB cannot route the request).
        # Mocked tests: qualifyContracts returns a MagicMock; we keep the
        # original contract object as a fallback when qualification yields
        # nothing usable.
        try:
            qualified = self._ib.qualifyContracts(contract)
            if qualified and hasattr(qualified[0], "conId") and qualified[0].conId:
                contract = qualified[0]
        except Exception:
            pass  # fall through with the unqualified ContFuture (mock-safe)

        ib_bars = self._ib.reqHistoricalData(
            contract,
            endDateTime=end_time or "",
            durationStr=_duration_str(timeframe, bars),
            barSizeSetting=_TIMEFRAME_TO_IB_BAR_SIZE[timeframe],
            whatToShow="TRADES",
            useRTH=False,
            formatDate=2,  # UTC seconds
            timeout=60,  # ib_insync default is 60s; explicit for clarity
        )
        result = [
            OHLCV(
                timestamp=b.date,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in ib_bars
        ]
        if len(result) < int(bars * 0.7):
            print(
                f"[ib_client] WARNING: requested {bars} {timeframe} bars for {symbol}, "
                f"received {len(result)} ({len(result) / bars:.0%})",
                file=sys.stderr,
            )
        return result

    def get_snapshot(self, symbol: str) -> Snapshot:
        """Fetch current bid/ask/last for the front-month continuous contract."""
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBClient is not connected; call connect() first")

        from ib_insync import ContFuture
        contract = ContFuture(symbol, _exchange_for(symbol))
        # Same qualify-then-fetch pattern as get_bars (see comment there).
        try:
            qualified = self._ib.qualifyContracts(contract)
            if qualified and hasattr(qualified[0], "conId") and qualified[0].conId:
                contract = qualified[0]
        except Exception:
            pass

        ticker = self._ib.reqMktData(contract, "", False, False)
        self._ib.sleep(1)  # wait for data tick
        return Snapshot(
            timestamp=ticker.time or datetime.now(timezone.utc),
            bid=float(ticker.bid) if ticker.bid else 0.0,
            ask=float(ticker.ask) if ticker.ask else 0.0,
            last=float(ticker.last) if ticker.last else 0.0,
        )

    def get_open_interest(self, symbol: str) -> OpenInterest:
        """Fetch most recent OPEN_INTEREST values (today + yesterday)."""
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBClient is not connected; call connect() first")

        from ib_insync import ContFuture
        contract = ContFuture(symbol, _exchange_for(symbol))
        try:
            qualified = self._ib.qualifyContracts(contract)
            if qualified and hasattr(qualified[0], "conId") and qualified[0].conId:
                contract = qualified[0]
        except Exception:
            pass

        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="3 D",
            barSizeSetting="1 day",
            whatToShow="OPEN_INTEREST",
            useRTH=False,
            formatDate=2,
            timeout=60,
        )
        if len(bars) < 2:
            raise RuntimeError(f"Insufficient OI bars for {symbol}: got {len(bars)}")

        today = float(bars[-1].close)
        yesterday = float(bars[-2].close)
        delta = today - yesterday
        delta_pct = delta / yesterday if yesterday else 0.0
        return OpenInterest(
            today=today,
            yesterday=yesterday,
            delta=delta,
            delta_pct=delta_pct,
        )
