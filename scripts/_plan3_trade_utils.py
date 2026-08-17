"""Shared trade utilities for Plan 3 scan scripts.

Lives in scripts/ (not the strategy package) because these helpers are
evaluation-specific and don't belong in the Trade wire format.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date as _date
from typing import Iterable, Sequence

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import Trade


def filter_trades_by_window(
    trades: Iterable[Trade], start: _date, end: _date
) -> list[Trade]:
    """Inclusive on both ends using trade.date string (YYYY-MM-DD)."""
    start_s = start.isoformat()
    end_s = end.isoformat()
    return [t for t in trades if start_s <= t.date <= end_s]


def flip_trades_direction(trades: Iterable[Trade]) -> list[Trade]:
    """Return new Trade objects with direction swapped.

    Used for SE-2 signal reversal: runs the same entries with opposite
    signal sign. PnL calculation downstream is direction-aware, so flipping
    the label effectively flips the PnL sign.
    """
    out = []
    for t in trades:
        new_dir = "short" if t.direction == "long" else "long"
        out.append(replace(t, direction=new_dir))
    return out


def equity_curve_from_pnl(
    pnl: pd.Series, starting_capital: float
) -> pd.Series:
    """Cumulative equity given a per-trade PnL series."""
    return starting_capital + pnl.cumsum()


def daily_returns_from_pnl(
    pnl: pd.Series,
    trade_dates: Sequence[_date],
    starting_capital: float,
) -> pd.Series:
    """Aggregate trade-level PnL by date, compute daily fractional returns.

    Each day's return = sum(day's pnl) / equity-at-start-of-day.
    """
    df = pd.DataFrame({"pnl": list(pnl), "date": list(trade_dates)})
    daily_pnl = df.groupby("date")["pnl"].sum().sort_index()
    equity_at_day_start = starting_capital + daily_pnl.cumsum().shift(1).fillna(0)
    return daily_pnl / equity_at_day_start
