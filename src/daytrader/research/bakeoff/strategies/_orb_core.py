"""Opening Range Breakout mechanical core.

Shared helpers for S1a and S1b. Pure functions on pandas DataFrames —
no I/O, no cost model. Cost application happens in the metrics layer
(Plan 3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import TradeOutcome


Direction = Literal["long", "short"]


@dataclass(frozen=True)
class OpeningRange:
    high: float
    low: float
    range_pts: float
    open_at_session_start: float
    close_at_or_end: float
    or_end_index: int


@dataclass(frozen=True)
class ExitInfo:
    exit_time: datetime
    exit_price: float
    outcome: TradeOutcome


def compute_opening_range(
    bars: pd.DataFrame,
    or_minutes: int,
    session_tz: str,
) -> OpeningRange:
    if len(bars) < or_minutes:
        raise ValueError(
            f"insufficient bars for OR: have {len(bars)}, need {or_minutes}"
        )
    or_bars = bars.iloc[:or_minutes]
    hi = float(or_bars["high"].max())
    lo = float(or_bars["low"].min())
    return OpeningRange(
        high=hi,
        low=lo,
        range_pts=hi - lo,
        open_at_session_start=float(or_bars["open"].iloc[0]),
        close_at_or_end=float(or_bars["close"].iloc[-1]),
        or_end_index=or_minutes - 1,
    )


def direction_from_first_bar(or_: OpeningRange) -> Optional[Direction]:
    delta = or_.close_at_or_end - or_.open_at_session_start
    if delta > 0:
        return "long"
    if delta < 0:
        return "short"
    return None


def walk_forward_to_exit(
    bars_after_entry: pd.DataFrame,
    direction: Direction,
    entry_price: float,
    stop_price: float,
    target_price: float,
    eod_exit_ts: pd.Timestamp,
) -> ExitInfo:
    """Walk forward bar-by-bar until stop, target, or EOD triggers.

    `bars_after_entry` must INCLUDE the entry bar as its first row; walk
    starts from the bar AFTER it. Stop wins over target in straddle bars.
    NaN target_price → target check skipped (S1b semantics).
    """
    has_target = not math.isnan(target_price)

    for ts, bar in bars_after_entry.iloc[1:].iterrows():
        hi = float(bar["high"])
        lo = float(bar["low"])

        if direction == "long":
            if lo <= stop_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop_price,
                    outcome=TradeOutcome.STOP,
                )
            if has_target and hi >= target_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=target_price,
                    outcome=TradeOutcome.TARGET,
                )
        else:
            if hi >= stop_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop_price,
                    outcome=TradeOutcome.STOP,
                )
            if has_target and lo <= target_price:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=target_price,
                    outcome=TradeOutcome.TARGET,
                )

    last_bar = bars_after_entry.iloc[-1]
    return ExitInfo(
        exit_time=eod_exit_ts.to_pydatetime(),
        exit_price=float(last_bar["close"]),
        outcome=TradeOutcome.EOD,
    )
