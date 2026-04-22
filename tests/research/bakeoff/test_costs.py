"""Tests for bakeoff cost model."""

from __future__ import annotations

import pytest

from daytrader.research.bakeoff.costs import (
    COMMISSION_PER_RT_CONTRACT,
    ENTRY_SLIPPAGE_TICKS,
    STOP_SLIPPAGE_TICKS,
    TARGET_SLIPPAGE_TICKS,
    MES_TICK_SIZE,
    MES_POINT_VALUE,
    entry_slippage_usd,
    stop_slippage_usd,
    target_slippage_usd,
    round_trip_cost_usd,
    tick_to_usd,
)


def test_mes_constants_match_cme_spec():
    assert MES_TICK_SIZE == 0.25
    assert MES_POINT_VALUE == 5.0


def test_tick_to_usd():
    assert tick_to_usd(1) == pytest.approx(1.25)   # 1 tick = 0.25 pts * $5 = $1.25
    assert tick_to_usd(2) == pytest.approx(2.50)
    assert tick_to_usd(0) == 0.0


def test_entry_slippage_is_1_tick():
    assert ENTRY_SLIPPAGE_TICKS == 1
    assert entry_slippage_usd(contracts=1) == pytest.approx(1.25)
    assert entry_slippage_usd(contracts=2) == pytest.approx(2.50)


def test_stop_slippage_is_2_ticks():
    assert STOP_SLIPPAGE_TICKS == 2
    assert stop_slippage_usd(contracts=1) == pytest.approx(2.50)


def test_target_slippage_is_zero_ticks():
    assert TARGET_SLIPPAGE_TICKS == 0
    assert target_slippage_usd(contracts=1) == 0.0
    assert target_slippage_usd(contracts=3) == 0.0


def test_commission_per_round_trip():
    assert COMMISSION_PER_RT_CONTRACT == pytest.approx(4.0)


def test_round_trip_cost_target_exit():
    # Commission + entry slippage + target slippage (0).
    cost = round_trip_cost_usd(contracts=1, exit_kind="target")
    assert cost == pytest.approx(4.0 + 1.25 + 0.0)


def test_round_trip_cost_stop_exit():
    # Commission + entry slippage + stop slippage (2 ticks).
    cost = round_trip_cost_usd(contracts=1, exit_kind="stop")
    assert cost == pytest.approx(4.0 + 1.25 + 2.50)


def test_round_trip_cost_eod_exit_treated_as_target():
    # EOD flat is a market order at close — conservative: model as target (resting).
    cost = round_trip_cost_usd(contracts=1, exit_kind="eod")
    assert cost == pytest.approx(4.0 + 1.25 + 0.0)


def test_round_trip_cost_unknown_exit_kind_raises():
    with pytest.raises(ValueError, match="exit_kind"):
        round_trip_cost_usd(contracts=1, exit_kind="bogus")


# --- Plan 3 per-trade cost helpers (SPY, point-unit) ---

from datetime import datetime, timezone

from daytrader.research.bakeoff.costs import (
    apply_per_trade_cost, trade_gross_pnl, trade_net_pnl,
)
from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _p3_trade(direction, entry_price, exit_price):
    ts = datetime(2024, 6, 10, 13, 35, tzinfo=timezone.utc)
    stop = entry_price - 10 if direction == "long" else entry_price + 10
    return Trade(
        date="2024-06-10", symbol="SPY", direction=direction,
        entry_time=ts, entry_price=entry_price,
        stop_price=stop, target_price=float("nan"),
        exit_time=ts, exit_price=exit_price,
        outcome=TradeOutcome.EOD, r_multiple=0.0,
    )


def test_trade_gross_pnl_long():
    assert trade_gross_pnl(_p3_trade("long", 100.0, 105.0)) == pytest.approx(5.0)


def test_trade_gross_pnl_short():
    assert trade_gross_pnl(_p3_trade("short", 100.0, 95.0)) == pytest.approx(5.0)


def test_trade_net_pnl_subtracts_cost():
    assert trade_net_pnl(_p3_trade("long", 100.0, 105.0), cost_per_trade=0.5) == pytest.approx(4.5)


def test_apply_per_trade_cost_returns_series_of_net_pnl():
    trades = [
        _p3_trade("long", 100.0, 105.0),
        _p3_trade("long", 100.0, 98.0),
        _p3_trade("short", 100.0, 95.0),
    ]
    nets = apply_per_trade_cost(trades, cost_per_trade=0.5)
    assert list(nets) == pytest.approx([4.5, -2.5, 4.5])


def test_apply_per_trade_cost_zero_cost_matches_gross():
    trades = [_p3_trade("long", 100.0, 105.0), _p3_trade("short", 100.0, 95.0)]
    gross = [trade_gross_pnl(t) for t in trades]
    net = list(apply_per_trade_cost(trades, cost_per_trade=0.0))
    assert net == pytest.approx(gross)
