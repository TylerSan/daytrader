"""MES cost model — shared by all 4 bake-off candidates.

Conservative:
- Commission at Topstep's high end ($4 RT, vs IBKR's ~$2.04)
- 1 tick slippage on entry (market-on-open-bar)
- 2 ticks slippage on stop (market-on-stop, MES liquidity < ES)
- 0 ticks slippage on target / EOD (resting limit fill)

See spec §2.3.
"""

from __future__ import annotations

from typing import Literal

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
