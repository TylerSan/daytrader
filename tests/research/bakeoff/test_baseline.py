"""Tests for buy-and-hold MES baseline."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.baseline import buy_and_hold_mes_equity
from daytrader.research.bakeoff.costs import MES_POINT_VALUE, tick_to_usd


ET = ZoneInfo("America/New_York")


def _bars(rows):
    """rows: list of (ts_utc_str, close, iid)."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(ts, tz="UTC") for ts, _c, _i in rows]
    )
    return pd.DataFrame(
        {"open": [c for _t, c, _i in rows],
         "high": [c for _t, c, _i in rows],
         "low":  [c for _t, c, _i in rows],
         "close": [c for _t, c, _i in rows],
         "volume": [1] * len(rows),
         "instrument_id": [i for _t, _c, i in rows]},
        index=idx,
    )


def test_buy_and_hold_flat_price_zero_pnl():
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-10 15:59", 5000.0, 100),
        ("2024-06-11 13:30", 5000.0, 100),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    assert eq.iloc[0] == pytest.approx(10_000.0)
    assert eq.iloc[-1] == pytest.approx(10_000.0)


def test_buy_and_hold_price_up_gains_pnl():
    # Price rises 10 points → 10 * $5 = $50 gain on 1 contract.
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-10 15:59", 5010.0, 100),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    assert eq.iloc[-1] == pytest.approx(10_050.0)


def test_buy_and_hold_rollover_pays_2_ticks_cost():
    # On instrument_id change, pay 2 ticks (1 sell + 1 buy entry slippage) = $2.50.
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-11 13:30", 5000.0, 100),
        ("2024-06-12 13:30", 5000.0, 101),   # rollover — cost $2.50
        ("2024-06-13 13:30", 5000.0, 101),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    expected_end = 10_000.0 - tick_to_usd(2)   # 2 ticks = $2.50 roll cost
    assert eq.iloc[-1] == pytest.approx(expected_end)


def test_buy_and_hold_index_matches_bars():
    bars = _bars([
        ("2024-06-10 13:30", 5000.0, 100),
        ("2024-06-10 15:59", 5005.0, 100),
    ])
    eq = buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
    assert len(eq) == len(bars)
    assert (eq.index == bars.index).all()


def test_buy_and_hold_empty_bars_raises():
    bars = _bars([])
    with pytest.raises(ValueError, match="empty"):
        buy_and_hold_mes_equity(bars, starting_capital=10_000.0)
