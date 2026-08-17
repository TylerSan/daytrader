"""Tests for Plan 3 trade utilities."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from _plan3_trade_utils import (  # noqa: E402
    daily_returns_from_pnl,
    equity_curve_from_pnl,
    filter_trades_by_window,
    flip_trades_direction,
)

from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _trade(d, direction, entry=100.0, exit=101.0):
    ts = datetime.fromisoformat(f"{d}T13:35:00+00:00")
    stop = entry - 10 if direction == "long" else entry + 10
    return Trade(
        date=d, symbol="SPY", direction=direction,
        entry_time=ts, entry_price=entry, stop_price=stop,
        target_price=float("nan"),
        exit_time=ts, exit_price=exit,
        outcome=TradeOutcome.EOD,
        r_multiple=(exit - entry) / 10 if direction == "long" else (entry - exit) / 10,
    )


def test_filter_trades_by_window_inclusive():
    trades = [
        _trade("2023-12-31", "long"),
        _trade("2024-01-01", "long"),
        _trade("2024-06-15", "long"),
        _trade("2024-12-31", "long"),
        _trade("2025-01-01", "long"),
    ]
    picked = filter_trades_by_window(trades, date(2024, 1, 1), date(2024, 12, 31))
    assert len(picked) == 3
    assert picked[0].date == "2024-01-01"
    assert picked[-1].date == "2024-12-31"


def test_flip_trades_direction_swaps_and_preserves_other_fields():
    t = _trade("2024-06-10", "long", entry=100, exit=105)
    flipped = flip_trades_direction([t])
    assert len(flipped) == 1
    f = flipped[0]
    assert f.direction == "short"
    assert f.entry_price == t.entry_price
    assert f.exit_price == t.exit_price
    assert f.symbol == t.symbol
    assert f.date == t.date


def test_flip_trades_direction_short_becomes_long():
    t = _trade("2024-06-10", "short", entry=100, exit=95)
    flipped = flip_trades_direction([t])
    assert flipped[0].direction == "long"


def test_equity_curve_from_pnl_cumulative():
    pnl = pd.Series([1.0, -0.5, 2.0, -0.2])
    starting = 10.0
    eq = equity_curve_from_pnl(pnl, starting_capital=starting)
    assert list(eq) == pytest.approx([11.0, 10.5, 12.5, 12.3])


def test_daily_returns_from_pnl_groups_by_trade_date():
    pnl = pd.Series([1.0, 2.0, -1.0])
    dates = [date(2024, 6, 10), date(2024, 6, 10), date(2024, 6, 11)]
    starting = 100.0
    dr = daily_returns_from_pnl(pnl, dates, starting_capital=starting)
    assert len(dr) == 2
    assert dr.iloc[0] == pytest.approx(0.03)
    assert dr.iloc[1] == pytest.approx(-1.0 / 103.0)
