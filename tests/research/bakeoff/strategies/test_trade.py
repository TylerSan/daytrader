"""Tests for Trade dataclass + TradeOutcome enum."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_trade_outcome_values():
    assert TradeOutcome.TARGET.value == "target"
    assert TradeOutcome.STOP.value == "stop"
    assert TradeOutcome.EOD.value == "eod"


def test_trade_construction():
    t = Trade(
        date="2024-06-10", symbol="MES", direction="long",
        entry_time=_ts("2024-06-10T13:35:00"), entry_price=5000.0,
        stop_price=4995.0, target_price=5050.0,
        exit_time=_ts("2024-06-10T14:30:00"), exit_price=5050.0,
        outcome=TradeOutcome.TARGET, r_multiple=10.0,
    )
    assert t.direction == "long"
    assert t.r_multiple == pytest.approx(10.0)
    assert t.outcome is TradeOutcome.TARGET


def test_trade_rejects_unknown_direction():
    with pytest.raises(ValueError, match="direction"):
        Trade(
            date="2024-06-10", symbol="MES", direction="flat",
            entry_time=_ts("2024-06-10T13:35:00"), entry_price=5000.0,
            stop_price=4995.0, target_price=5050.0,
            exit_time=_ts("2024-06-10T14:30:00"), exit_price=5050.0,
            outcome=TradeOutcome.TARGET, r_multiple=10.0,
        )


def test_trade_is_immutable():
    t = Trade(
        date="2024-06-10", symbol="MES", direction="long",
        entry_time=_ts("2024-06-10T13:35:00"), entry_price=5000.0,
        stop_price=4995.0, target_price=5050.0,
        exit_time=_ts("2024-06-10T14:30:00"), exit_price=5050.0,
        outcome=TradeOutcome.TARGET, r_multiple=10.0,
    )
    with pytest.raises((AttributeError, Exception)):
        t.r_multiple = 999.0
