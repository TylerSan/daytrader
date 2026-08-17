"""S1 family — 5-min Opening Range Breakout (Zarattini et al.).

Two variants:
- S1a: exit at N × OR range profit target OR end-of-day (whichever first)
- S1b: exit at end-of-day only (no profit target)

Both use `_orb_core` for mechanical rules. They differ only in how they
compute `target_price`. Per spec §3.2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd

from daytrader.research.bakeoff.strategies._orb_core import (
    Direction, OpeningRange,
    compute_opening_range, direction_from_first_bar, walk_forward_to_exit,
)
from daytrader.research.bakeoff.strategies._trade import Trade


SESSION_TZ = "America/New_York"


def _group_by_local_date(bars: pd.DataFrame, tz: str) -> dict:
    zoneinfo = ZoneInfo(tz)
    local_dates = bars.index.tz_convert(zoneinfo).date
    df = bars.copy()
    df["_local_date"] = local_dates
    return {d: g.drop(columns=["_local_date"]) for d, g in df.groupby("_local_date")}


def _build_trade_from_day(
    symbol: str,
    day_bars: pd.DataFrame,
    or_minutes: int,
    target_price_fn,
) -> list[Trade]:
    if len(day_bars) < or_minutes + 1:
        return []

    or_ = compute_opening_range(day_bars, or_minutes=or_minutes, session_tz=SESSION_TZ)
    direction = direction_from_first_bar(or_)
    if direction is None:
        return []

    entry_bar = day_bars.iloc[or_minutes]
    entry_time = day_bars.index[or_minutes]
    entry_price = float(entry_bar["close"])

    if direction == "long":
        stop_price = or_.low
    else:
        stop_price = or_.high

    # Wrong-way-entry guard: OR direction says long but post-OR bar already
    # closed at or below OR low (or short with close at/above OR high) →
    # entry <= stop, trade makes no sense. Skip silently. Without this guard,
    # a "STOP outcome" at stop_price > entry_price would be recorded as a
    # winning trade, inflating win rate.
    if direction == "long" and entry_price <= stop_price:
        return []
    if direction == "short" and entry_price >= stop_price:
        return []

    target_price = target_price_fn(or_, direction, entry_price)

    bars_from_entry = day_bars.iloc[or_minutes:]
    exit = walk_forward_to_exit(
        bars_after_entry=bars_from_entry,
        direction=direction,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        eod_exit_ts=day_bars.index[-1],
    )

    risk = abs(entry_price - stop_price)
    if direction == "long":
        pnl = exit.exit_price - entry_price
    else:
        pnl = entry_price - exit.exit_price
    r_multiple = 0.0 if risk == 0 else pnl / risk

    trade = Trade(
        date=str(day_bars.index[0].tz_convert(SESSION_TZ).date()),
        symbol=symbol,
        direction=direction,
        entry_time=entry_time.to_pydatetime(),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        exit_time=exit.exit_time,
        exit_price=exit.exit_price,
        outcome=exit.outcome,
        r_multiple=r_multiple,
    )
    return [trade]


@dataclass
class S1a_ORB_TargetAndEOD:
    """S1a: 5-min ORB with profit target = N × OR range (default 10×) or EOD."""
    symbol: str
    or_minutes: int = 5
    target_multiple: float = 10.0

    def generate_trades(self, bars: pd.DataFrame) -> list[Trade]:
        out: list[Trade] = []
        for _day, day_bars in _group_by_local_date(bars, SESSION_TZ).items():
            out.extend(_build_trade_from_day(
                self.symbol, day_bars, self.or_minutes,
                target_price_fn=self._target_fn,
            ))
        return out

    def _target_fn(self, or_: OpeningRange, direction: Direction, entry_price: float) -> float:
        if direction == "long":
            return entry_price + self.target_multiple * or_.range_pts
        return entry_price - self.target_multiple * or_.range_pts


@dataclass
class S1b_ORB_EODOnly:
    """S1b: 5-min ORB, EOD-only exit (no profit target)."""
    symbol: str
    or_minutes: int = 5

    def generate_trades(self, bars: pd.DataFrame) -> list[Trade]:
        out: list[Trade] = []
        for _day, day_bars in _group_by_local_date(bars, SESSION_TZ).items():
            out.extend(_build_trade_from_day(
                self.symbol, day_bars, self.or_minutes,
                target_price_fn=self._target_fn,
            ))
        return out

    @staticmethod
    def _target_fn(or_: OpeningRange, direction: Direction, entry_price: float) -> float:
        return math.nan
