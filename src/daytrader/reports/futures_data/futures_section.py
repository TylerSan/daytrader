"""FuturesSection aggregator.

Builds the F. 期货结构 section data bundle per symbol: OI delta, basis,
term structure, volume profile. Each field becomes None on per-fetch failure
(warning to stderr) so the prompt always has something to include.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from daytrader.core.ib_client import IBClient, OpenInterest
from daytrader.reports.futures_data.basis import BasisResult, compute_basis
from daytrader.reports.futures_data.term_structure import (
    TermStructure,
    compute_term_structure,
)
from daytrader.reports.futures_data.volume_profile import (
    VolumeProfile,
    compute_volume_profile,
)


@dataclass(frozen=True)
class SymbolFuturesData:
    symbol: str
    open_interest: OpenInterest | None
    basis: BasisResult | None
    term_structure: TermStructure | None
    volume_profile: VolumeProfile | None


@dataclass(frozen=True)
class FuturesSection:
    per_symbol: dict[str, SymbolFuturesData]


def build_futures_section(
    ib_client: IBClient,
    symbols: list[str],
    underlying_prices: dict[str, float],
    term_prices: dict[str, tuple[float, float, float]],
    tick_sizes: dict[str, float],
) -> FuturesSection:
    per_symbol: dict[str, SymbolFuturesData] = {}

    for symbol in symbols:
        # OI
        oi: OpenInterest | None
        try:
            oi = ib_client.get_open_interest(symbol=symbol)
        except Exception as e:
            print(
                f"[futures_section] WARNING: get_open_interest({symbol}) failed: {e}",
                file=sys.stderr,
            )
            oi = None

        # Basis
        basis: BasisResult | None = None
        if symbol in underlying_prices:
            try:
                front_price = term_prices[symbol][0] if symbol in term_prices else None
                if front_price is not None:
                    basis = compute_basis(
                        future_price=front_price,
                        underlying_price=underlying_prices[symbol],
                    )
            except Exception as e:
                print(
                    f"[futures_section] WARNING: basis({symbol}) failed: {e}",
                    file=sys.stderr,
                )
                basis = None

        # Term structure
        term: TermStructure | None = None
        if symbol in term_prices:
            try:
                front, mid, far = term_prices[symbol]
                term = compute_term_structure(front, mid, far)
            except Exception as e:
                print(
                    f"[futures_section] WARNING: term_structure({symbol}) failed: {e}",
                    file=sys.stderr,
                )
                term = None

        # Volume profile from 1m bars
        vp: VolumeProfile | None
        try:
            bars_1m = ib_client.get_bars(symbol=symbol, timeframe="1m", bars=390)
            if bars_1m:
                vp = compute_volume_profile(
                    bars=bars_1m,
                    tick_size=tick_sizes.get(symbol, 0.25),
                    value_area_pct=0.7,
                )
            else:
                vp = None
        except Exception as e:
            print(
                f"[futures_section] WARNING: volume_profile({symbol}) failed: {e}",
                file=sys.stderr,
            )
            vp = None

        per_symbol[symbol] = SymbolFuturesData(
            symbol=symbol,
            open_interest=oi,
            basis=basis,
            term_structure=term,
            volume_profile=vp,
        )

    return FuturesSection(per_symbol=per_symbol)
