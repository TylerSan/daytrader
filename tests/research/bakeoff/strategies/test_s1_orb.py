"""Unit tests for S1a + S1b ORB strategy classes."""

from __future__ import annotations

import math
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._trade import TradeOutcome
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD,
    S1b_ORB_EODOnly,
)


ET = ZoneInfo("America/New_York")


def _one_day_bars(rows):
    ts = [
        pd.Timestamp(f"2024-06-10 {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows
    ]
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1,
          "instrument_id": 100}
         for _hm, o, h, l, c in rows],
        index=pd.DatetimeIndex(ts),
    )
    return df


def test_s1a_long_hits_target():
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5014),
        ("10:00", 5014, 5140, 5013, 5135),
        ("15:59", 5135, 5140, 5130, 5138),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.outcome is TradeOutcome.TARGET
    assert t.exit_price == pytest.approx(5134.0)
    assert t.entry_price == pytest.approx(5014.0)
    assert t.r_multiple == pytest.approx(7.5)


def test_s1a_long_eod_when_neither_hit():
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5010),
        ("15:59", 5010, 5020, 5005, 5015),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert trades[0].outcome is TradeOutcome.EOD
    assert trades[0].exit_price == pytest.approx(5015.0)


def test_s1a_flat_day_produces_no_trade():
    bars = _one_day_bars([
        ("09:30", 5000, 5002, 4999, 5001),
        ("09:31", 5001, 5002, 5000, 5000),
        ("09:32", 5000, 5001, 4999, 5000),
        ("09:33", 5000, 5001, 4999, 5000),
        ("09:34", 5000, 5001, 4999, 5000),
        ("09:35", 5000, 5002, 4998, 5001),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    assert strat.generate_trades(bars) == []


def test_s1b_long_always_exits_at_eod_even_when_high_exceeds_10x_or():
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5014),
        ("10:00", 5014, 5140, 5013, 5135),
        ("15:59", 5135, 5140, 5130, 5138),
    ])
    strat = S1b_ORB_EODOnly(symbol="MES", or_minutes=5)
    trades = strat.generate_trades(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.outcome is TradeOutcome.EOD
    assert t.exit_price == pytest.approx(5138.0)
    assert math.isnan(t.target_price)


def test_s1b_stops_trump_eod():
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5014),
        ("10:30", 5014, 5015, 4995, 4996),
        ("15:59", 4996, 4998, 4990, 4995),
    ])
    strat = S1b_ORB_EODOnly(symbol="MES", or_minutes=5)
    trades = strat.generate_trades(bars)
    assert trades[0].outcome is TradeOutcome.STOP
    assert trades[0].exit_price == pytest.approx(4998.0)
