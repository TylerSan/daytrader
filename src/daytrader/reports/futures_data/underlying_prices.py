"""UnderlyingPriceFetcher — fetches spot prices for futures basis calculation.

Returns a dict[symbol, spot_price] suitable for `build_futures_section`'s
`underlying_prices` parameter. Used to compute Basis = Future - Spot.

Source strategy (verified 2026-05-03 via IB experiments):

| Future | Underlying source | Multiplier | Tracking |
|---|---|---|---|
| MES, ES | `Index('SPX', 'CBOE')` | 1.0 (exact) | exact S&P 500 spot |
| MNQ, NQ | `Index('NDX', 'NASDAQ')` | 1.0 (exact) | exact Nasdaq 100 spot |
| MGC, GC | `Stock('GLD', 'ARCA')` | ~10.95 (approx) | tracking error <0.5% |

Index prices for SPX / NDX are available without realtime market data
subscription (delayed/EOD via the basic IB account).

For gold, IB's `Index('XAUUSD', 'IDEALPRO')` returned 'security definition
not found' on the user's account — falling back to GLD ETF × 10.95.
The multiplier reflects GLD's NAV-tracking ratio (each GLD share ≈ 1/10.95
oz of gold; drifts ~0.4%/yr due to expense ratio). Acceptable for "is
futures premium positive?" decisions; not for arbitrage.

Failures (per-symbol, e.g. unqualified contract or empty bars) are logged
to stderr and the symbol is omitted from the result — graceful degradation
is the F-section's responsibility (basis=None is rendered as "不可得").
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daytrader.core.ib_client import IBClient


# Mapping: futures_symbol -> (kind, ib_args, multiplier)
# kind ∈ {"Index", "Stock"}
SYMBOL_TO_UNDERLYING: dict[str, tuple[str, tuple[str, str], float]] = {
    "MES": ("Index", ("SPX", "CBOE"), 1.0),
    "ES":  ("Index", ("SPX", "CBOE"), 1.0),
    "MNQ": ("Index", ("NDX", "NASDAQ"), 1.0),
    "NQ":  ("Index", ("NDX", "NASDAQ"), 1.0),
    "MGC": ("Stock", ("GLD", "ARCA"), 10.95),
    "GC":  ("Stock", ("GLD", "ARCA"), 10.95),
}


class UnderlyingPriceFetcher:
    """Callable that returns dict[futures_symbol, spot_price]."""

    def __init__(self, ib_client: "IBClient") -> None:
        self._ib = ib_client

    def __call__(self, symbols: list[str]) -> dict[str, float]:
        from ib_insync import Index, Stock

        out: dict[str, float] = {}
        for sym in symbols:
            if sym not in SYMBOL_TO_UNDERLYING:
                continue
            kind, args, multiplier = SYMBOL_TO_UNDERLYING[sym]
            try:
                if kind == "Index":
                    contract = Index(args[0], args[1])
                else:  # "Stock"
                    contract = Stock(args[0], args[1], "USD")
                close = self._ib.get_daily_close(contract)
                out[sym] = close * multiplier
            except Exception as e:
                print(
                    f"[underlying_prices] WARNING: {sym} via {kind}{args}: {e}",
                    file=sys.stderr,
                )
        return out
