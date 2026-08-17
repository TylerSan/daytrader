"""Bar-by-bar simulation engine.

Supports Opening Range Breakout mechanic out of the box. Other
trigger/stop/target combinations should raise NotImplementedError so the
backtester fails loud rather than produce garbage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

import pandas as pd
from zoneinfo import ZoneInfo

from daytrader.journal.sanity_floor.setup_yaml import SetupDefinition


# USD per 1.0 point (same as CLI)
INSTRUMENT_POINT_VALUE = {
    "MES": Decimal("5"), "MNQ": Decimal("2"), "MGC": Decimal("10"),
}

INSTRUMENT_TICK_SIZE = {
    "MES": 0.25, "MNQ": 0.25, "MGC": 0.10,
}


@dataclass
class SimulatedTrade:
    date: str
    symbol: str
    direction: str           # "long" | "short"
    entry_time: datetime
    entry_price: float
    stop_price: float
    target_price: float
    exit_time: datetime
    exit_price: float
    outcome: str             # "target" | "stop" | "session_end"
    r_multiple: float


def _parse_tz_time(s: str) -> tuple[time, ZoneInfo]:
    """'09:30 America/New_York' -> (time(9,30), ZoneInfo('America/New_York'))"""
    parts = s.strip().split(None, 1)
    hm = parts[0]
    tz = parts[1] if len(parts) > 1 else "UTC"
    h, m = hm.split(":")
    return time(int(h), int(m)), ZoneInfo(tz)


def _session_window_utc(
    local_date, session: dict
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Build UTC session window from a local date (datetime.date) + session dict.

    local_date must already be expressed in the session timezone (derived by
    converting a representative intra-day UTC timestamp to local, then taking
    .date() — NOT from midnight UTC which would roll back one day in US/ET).
    """
    start_t, tz = _parse_tz_time(session["start"])
    end_t, _ = _parse_tz_time(session["end"])
    s_local = datetime.combine(local_date, start_t).replace(tzinfo=tz)
    e_local = datetime.combine(local_date, end_t).replace(tzinfo=tz)
    return pd.Timestamp(s_local).tz_convert("UTC"), pd.Timestamp(e_local).tz_convert("UTC")


def _filter_value(filters: list[dict], key: str, default=None):
    for f in filters:
        if key in f:
            return f[key]
    return default


def simulate_setup(
    setup: SetupDefinition,
    symbol: str,
    df: pd.DataFrame,
    tick_size: float | None = None,
) -> list[SimulatedTrade]:
    """Simulate a setup over the entire DataFrame. Returns per-trade list."""
    if tick_size is None:
        tick_size = INSTRUMENT_TICK_SIZE.get(symbol, 0.25)

    trigger = setup.entry["trigger"]
    if trigger != "price_closes_beyond_or_by_ticks":
        raise NotImplementedError(f"trigger not supported yet: {trigger}")
    if setup.stop["rule"] != "opposite_side_of_or":
        raise NotImplementedError(f"stop rule not supported yet: {setup.stop['rule']}")
    if setup.target["rule"] != "multiple_of_or_range":
        raise NotImplementedError(f"target rule not supported yet: {setup.target['rule']}")
    if not setup.opening_range:
        raise ValueError("opening_range required for this setup")

    or_minutes = int(setup.opening_range["duration_minutes"])
    entry_ticks = int(setup.entry["ticks"])
    stop_offset_ticks = int(setup.stop["offset_ticks"])
    target_multiple = float(setup.target["multiple"])

    min_ticks = _filter_value(setup.filters, "min_or_range_ticks", 0)
    max_ticks = _filter_value(setup.filters, "max_or_range_ticks", 10_000)

    trades: list[SimulatedTrade] = []

    df = df.sort_index()

    # Derive unique days in the session timezone so that, e.g., 13:30 UTC on
    # 2026-04-01 correctly maps to local date 2026-04-01 ET rather than
    # 2026-03-31 ET (which midnight-UTC would produce).
    _, session_tz = _parse_tz_time(setup.session_window["start"])
    local_dates_series = df.index.tz_convert(session_tz)
    unique_days = sorted({ts.date() for ts in local_dates_series})

    for day in unique_days:
        s_utc, e_utc = _session_window_utc(day, setup.session_window)
        session_df = df[(df.index >= s_utc) & (df.index <= e_utc)]
        if session_df.empty:
            continue

        or_end = s_utc + pd.Timedelta(minutes=or_minutes)
        or_df = session_df[session_df.index < or_end]
        if or_df.empty:
            continue
        or_high = float(or_df["High"].max())
        or_low = float(or_df["Low"].min())
        or_range = or_high - or_low
        or_range_ticks = or_range / tick_size
        if or_range_ticks < min_ticks or or_range_ticks > max_ticks:
            continue

        after_or = session_df[session_df.index >= or_end]
        entered = False
        for ts, bar in after_or.iterrows():
            if entered:
                break
            close = float(bar["Close"])
            long_trigger = or_high + entry_ticks * tick_size
            short_trigger = or_low - entry_ticks * tick_size

            if close >= long_trigger:
                direction = "long"
                entry = close
                stop = or_low - stop_offset_ticks * tick_size
                target = entry + target_multiple * or_range
                trades.append(
                    _walk_forward(
                        symbol, day, direction, ts, entry, stop, target,
                        after_or.loc[ts:], tick_size,
                    )
                )
                entered = True
            elif close <= short_trigger:
                direction = "short"
                entry = close
                stop = or_high + stop_offset_ticks * tick_size
                target = entry - target_multiple * or_range
                trades.append(
                    _walk_forward(
                        symbol, day, direction, ts, entry, stop, target,
                        after_or.loc[ts:], tick_size,
                    )
                )
                entered = True

    return trades


def _walk_forward(
    symbol: str, day, direction: str,
    entry_ts, entry: float, stop: float, target: float,
    bars: pd.DataFrame, tick_size: float,
) -> SimulatedTrade:
    """Return the SimulatedTrade — exit at stop, target, or session end."""
    for ts, bar in bars.iterrows():
        if ts == entry_ts:
            continue
        hi = float(bar["High"])
        lo = float(bar["Low"])
        if direction == "long":
            if lo <= stop:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, stop, "stop", tick_size)
            if hi >= target:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, target, "target", tick_size)
        else:
            if hi >= stop:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, stop, "stop", tick_size)
            if lo <= target:
                return _make_trade(symbol, day, direction, entry_ts, entry,
                                    stop, target, ts, target, "target", tick_size)

    last_ts = bars.index[-1]
    last_close = float(bars["Close"].iloc[-1])
    return _make_trade(
        symbol, day, direction, entry_ts, entry, stop, target,
        last_ts, last_close, "session_end", tick_size,
    )


def _make_trade(
    symbol, day, direction, entry_ts, entry, stop, target,
    exit_ts, exit_price, outcome, tick_size,
) -> SimulatedTrade:
    risk = abs(entry - stop)
    if direction == "long":
        pnl = exit_price - entry
    else:
        pnl = entry - exit_price
    # Apply 1-tick slippage on stops (conservative)
    if outcome == "stop":
        pnl -= tick_size
    # Commission: $4 round-trip / contract, converted to points for simplicity
    # Skip in per-point pnl; factor into USD aggregation later.
    r = 0.0 if risk == 0 else pnl / risk
    return SimulatedTrade(
        date=str(day), symbol=symbol, direction=direction,
        entry_time=entry_ts.to_pydatetime(), entry_price=entry,
        stop_price=stop, target_price=target,
        exit_time=exit_ts.to_pydatetime(), exit_price=exit_price,
        outcome=outcome, r_multiple=r,
    )
