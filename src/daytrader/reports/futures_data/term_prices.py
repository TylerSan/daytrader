"""TermPricesFetcher — fetches front / next / far month closes per symbol.

Returns dict[symbol, (front_close, next_close, far_close)] suitable for
`build_futures_section`'s `term_prices` parameter. The downstream
`compute_term_structure` consumes these to compute spreads + contango flag.

Strategy:
  1. `IBClient.get_contract_chain(symbol)` returns sorted-by-expiry Future details
  2. Take first 3 (front, next, far)
  3. `IBClient.get_daily_close(contract)` for each → 3 floats
  4. Return tuple

Failures (per-symbol, e.g. fewer than 3 contracts available, IB error)
are logged to stderr and the symbol is omitted from the result —
graceful degradation; F-section renders as "term structure 不可得" for that
symbol.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daytrader.core.ib_client import IBClient


class TermPricesFetcher:
    """Callable returning dict[symbol, (front, next, far) close prices]."""

    def __init__(self, ib_client: "IBClient") -> None:
        self._ib = ib_client

    def __call__(
        self, symbols: list[str]
    ) -> dict[str, tuple[float, float, float]]:
        out: dict[str, tuple[float, float, float]] = {}
        for sym in symbols:
            try:
                chain = self._ib.get_contract_chain(sym)
                # Anchor to the LIQUIDITY-active front (matches ContFuture).
                # For monthlies (MGC) the chronologically-earliest contract may
                # be a near-expiry low-volume month that ContFuture has already
                # rolled past — using its expiry to find the right index in the
                # chain prevents that mis-anchoring.
                active_expiry = self._ib.get_active_front_expiry(sym)
                active_idx = next(
                    (
                        i
                        for i, d in enumerate(chain)
                        if d.contract.lastTradeDateOrContractMonth == active_expiry
                    ),
                    None,
                )
                if active_idx is None:
                    print(
                        f"[term_prices] WARNING: {sym}: active expiry "
                        f"{active_expiry} not in chain — skipping",
                        file=sys.stderr,
                    )
                    continue
                if active_idx + 2 >= len(chain):
                    print(
                        f"[term_prices] WARNING: {sym}: insufficient months "
                        f"past active expiry {active_expiry} (need 2 more, "
                        f"chain has {len(chain) - active_idx - 1})",
                        file=sys.stderr,
                    )
                    continue
                front_close = self._ib.get_daily_close(chain[active_idx].contract)
                next_close = self._ib.get_daily_close(chain[active_idx + 1].contract)
                far_close = self._ib.get_daily_close(chain[active_idx + 2].contract)
                out[sym] = (front_close, next_close, far_close)
            except Exception as e:
                print(
                    f"[term_prices] WARNING: {sym}: {e}",
                    file=sys.stderr,
                )
        return out
