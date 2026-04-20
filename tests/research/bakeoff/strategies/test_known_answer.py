"""Tests for known-answer utilities."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.research.bakeoff.strategies._known_answer import (
    KnownAnswerResult, compare_to_paper, summary_stats,
)
from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _t(direction, entry_price, exit_price, outcome):
    ts = datetime(2024, 6, 10, 13, 35, tzinfo=timezone.utc)
    stop = entry_price - 10 if direction == "long" else entry_price + 10
    risk = abs(entry_price - stop)
    pnl = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
    return Trade(
        date="2024-06-10", symbol="SPY", direction=direction,
        entry_time=ts, entry_price=entry_price,
        stop_price=stop,
        target_price=entry_price + 20 if direction == "long" else entry_price - 20,
        exit_time=ts, exit_price=exit_price,
        outcome=outcome, r_multiple=pnl / risk if risk else 0.0,
    )


def test_summary_stats_empty():
    out = summary_stats([], point_value_usd=1.0, starting_capital=10_000.0)
    assert out["n_trades"] == 0
    assert out["win_rate"] == 0.0
    assert out["total_return_pct"] == 0.0


def test_summary_stats_mixed_outcomes():
    trades = [
        _t("long", 450.0, 470.0, TradeOutcome.TARGET),
        _t("long", 460.0, 440.0, TradeOutcome.STOP),
        _t("short", 455.0, 445.0, TradeOutcome.TARGET),
    ]
    out = summary_stats(trades, point_value_usd=1.0, starting_capital=1_000.0)
    assert out["n_trades"] == 3
    assert out["total_pnl_usd"] == pytest.approx(10.0)
    assert out["total_return_pct"] == pytest.approx(1.0)
    assert out["win_rate"] == pytest.approx(2 / 3)


def test_compare_to_paper_within_tolerance():
    result = compare_to_paper(
        metric_name="total_return_pct",
        computed=105.0,
        paper_value=100.0,
        tolerance_pct=15.0,
    )
    assert isinstance(result, KnownAnswerResult)
    assert result.passed is True
    assert result.deviation_pct == pytest.approx(5.0)


def test_compare_to_paper_outside_tolerance():
    result = compare_to_paper(
        metric_name="sharpe",
        computed=2.8,
        paper_value=2.0,
        tolerance_pct=15.0,
    )
    assert result.passed is False
    assert result.deviation_pct == pytest.approx(40.0)


def test_compare_to_paper_zero_paper_value_raises():
    with pytest.raises(ValueError, match="zero"):
        compare_to_paper("x", computed=1.0, paper_value=0.0, tolerance_pct=10.0)
