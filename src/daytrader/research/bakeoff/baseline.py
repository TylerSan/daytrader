"""Buy-and-hold MES baseline for bake-off comparison (spec §2.4).

Holds 1 contract of the front-month MES continuously across the data window.
On instrument_id transitions (rollover), pays 2 ticks of slippage (sell
front + buy next). No commission modeled on rolls — Databento continuous
contract splicing is back-office, not retail-initiated.
"""

from __future__ import annotations

import pandas as pd

from daytrader.research.bakeoff.costs import MES_POINT_VALUE, tick_to_usd


def buy_and_hold_mes_equity(
    bars: pd.DataFrame,
    starting_capital: float,
    contracts: int = 1,
) -> pd.Series:
    """Return an equity curve Series, UTC-indexed, same length as `bars`.

    Args:
        bars: UTC-indexed DataFrame with `close` and `instrument_id`.
        starting_capital: USD at bars.index[0].
        contracts: position size (default 1).

    PnL accrues mark-to-market bar by bar on `close`. At instrument_id
    transitions, deducts `2 * tick_to_usd(1, contracts)` as roll cost.
    """
    if bars.empty:
        raise ValueError("bars must not be empty")

    closes = bars["close"].to_numpy()
    iids = bars["instrument_id"].to_numpy()

    # Mark-to-market PnL per bar (contracts * point_value * close_diff).
    equity = [starting_capital]
    for i in range(1, len(bars)):
        pnl = (closes[i] - closes[i - 1]) * MES_POINT_VALUE * contracts
        roll_cost = 0.0
        if iids[i] != iids[i - 1]:
            roll_cost = tick_to_usd(2, contracts)  # 2 ticks total = sell + buy
        equity.append(equity[-1] + pnl - roll_cost)

    return pd.Series(equity, index=bars.index, name="buy_and_hold_equity")
