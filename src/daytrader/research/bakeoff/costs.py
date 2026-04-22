"""Cost model for bake-off evaluation.

Two generations live side-by-side:

**MES helpers (Plan 1 legacy, unused in Plan 3):** tick-based round-trip
cost model keyed on exit kind (target / stop / EOD), per spec §2.3's
original MES framing. Preserved because existing tests depend on them.

**Plan 3 per-trade helpers (SPY, point-unit):** `trade_gross_pnl` /
`trade_net_pnl` / `apply_per_trade_cost`. Strategies emit Trade objects
carrying entry/exit in native point units ($1/point for SPY); Plan 3
applies a fixed `cost_per_trade` (default $0.50 per spec §3.1) by
subtraction. SE-1 scans cost × {0, 1, 2}.
"""

from __future__ import annotations

from typing import Iterable, Literal

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import Trade

# CME MES spec.
MES_TICK_SIZE: float = 0.25           # points per tick
MES_POINT_VALUE: float = 5.0          # USD per 1-point move, 1 contract

# Cost constants.
COMMISSION_PER_RT_CONTRACT: float = 4.0   # USD, round-trip
ENTRY_SLIPPAGE_TICKS: int = 1
STOP_SLIPPAGE_TICKS: int = 2
TARGET_SLIPPAGE_TICKS: int = 0

ExitKind = Literal["target", "stop", "eod"]


def tick_to_usd(ticks: int | float, contracts: int = 1) -> float:
    """Convert tick count to USD for N contracts."""
    return ticks * MES_TICK_SIZE * MES_POINT_VALUE * contracts


def entry_slippage_usd(contracts: int = 1) -> float:
    return tick_to_usd(ENTRY_SLIPPAGE_TICKS, contracts)


def stop_slippage_usd(contracts: int = 1) -> float:
    return tick_to_usd(STOP_SLIPPAGE_TICKS, contracts)


def target_slippage_usd(contracts: int = 1) -> float:
    return tick_to_usd(TARGET_SLIPPAGE_TICKS, contracts)


def round_trip_cost_usd(contracts: int, exit_kind: ExitKind) -> float:
    """Total cost for one round-trip = commission + entry slip + exit slip.

    EOD flat is modeled as a resting target fill (0 exit slip), conservative
    vs modeling it as a market-on-close (which would add ~1 tick).
    """
    if exit_kind == "target":
        exit_slip = target_slippage_usd(contracts)
    elif exit_kind == "stop":
        exit_slip = stop_slippage_usd(contracts)
    elif exit_kind == "eod":
        exit_slip = target_slippage_usd(contracts)
    else:
        raise ValueError(f"exit_kind must be target/stop/eod, got {exit_kind!r}")
    return COMMISSION_PER_RT_CONTRACT * contracts + entry_slippage_usd(contracts) + exit_slip


# === Plan 3 per-trade cost helpers ===


def trade_gross_pnl(trade: Trade) -> float:
    """Points of gross PnL for a single trade, sign per direction."""
    if trade.direction == "long":
        return trade.exit_price - trade.entry_price
    return trade.entry_price - trade.exit_price


def trade_net_pnl(trade: Trade, cost_per_trade: float) -> float:
    return trade_gross_pnl(trade) - cost_per_trade


def apply_per_trade_cost(
    trades: Iterable[Trade], cost_per_trade: float
) -> pd.Series:
    """Return a Series of net PnL values in trade order."""
    return pd.Series([trade_net_pnl(t, cost_per_trade) for t in trades])
