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


def test_s1a_skips_wrong_way_long_entry_below_or_low():
    """If direction=long (OR close > OR open) but post-OR bar closes AT OR
    BELOW OR low, entry <= stop — nonsense long. Must skip (no trade)."""
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),   # OR close 5008 > open 5000 → long
        # Post-OR bar gaps down and closes at 4995 (< OR low 4998).
        ("09:35", 5000, 5002, 4994, 4995),
        ("15:59", 4995, 4997, 4993, 4994),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    assert strat.generate_trades(bars) == []
    strat_b = S1b_ORB_EODOnly(symbol="MES", or_minutes=5)
    assert strat_b.generate_trades(bars) == []


def test_s1a_skips_wrong_way_short_entry_above_or_high():
    """Mirror: direction=short but post-OR close >= OR high → skip."""
    bars = _one_day_bars([
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),   # OR close 4978 < open 5000 → short
        # Post-OR bar gaps UP above OR high 5002.
        ("09:35", 4978, 5010, 4977, 5005),   # close 5005 >= OR high 5002
        ("15:59", 5005, 5008, 5003, 5007),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    assert strat.generate_trades(bars) == []


def test_s1a_accepts_long_entry_exactly_above_or_low():
    """Boundary: entry strictly > OR low → valid long trade."""
    bars = _one_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        # Post-OR close at 4999 — just above OR low 4998 → entry > stop, valid.
        ("09:35", 5000, 5005, 4997, 4999),
        ("15:59", 4999, 5001, 4996, 4998),   # EOD just barely below entry → loss
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert len(trades) == 1
    assert trades[0].entry_price == pytest.approx(4999.0)


def _multiday_bars(days):
    frames = []
    for d_str, rows in days:
        ts = [
            pd.Timestamp(f"{d_str} {hm}", tz=ET).tz_convert("UTC")
            for hm, *_ in rows
        ]
        df = pd.DataFrame(
            [{"open": o, "high": h, "low": l, "close": c, "volume": 1,
              "instrument_id": 100}
             for _hm, o, h, l, c in rows],
            index=pd.DatetimeIndex(ts),
        )
        frames.append(df)
    return pd.concat(frames).sort_index()


def test_s1a_across_5_days():
    day1 = [
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5014),
        ("10:00", 5014, 5200, 5013, 5190),
        ("15:59", 5190, 5195, 5188, 5192),
    ]
    day2 = [
        ("09:30", 5000, 5001, 4999, 5000),
        ("09:31", 5000, 5001, 4999, 5000),
        ("09:32", 5000, 5001, 4999, 5000),
        ("09:33", 5000, 5001, 4999, 5000),
        ("09:34", 5000, 5001, 4999, 5000),
        ("09:35", 5000, 5001, 4999, 5000),
        ("15:59", 5000, 5001, 4999, 5000),
    ]
    day3 = [
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),
        ("09:35", 4978, 4980, 4975, 4976),
        ("10:00", 4976, 5005, 4970, 5003),
        ("15:59", 5003, 5005, 5000, 5002),
    ]
    day4 = [
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5000, 5008),
        ("09:35", 5008, 5015, 5007, 5010),
        ("15:59", 5010, 5020, 5005, 5015),
    ]
    day5 = [
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),
        ("09:35", 4978, 4980, 4975, 4976),
        ("10:00", 4976, 4978, 4700, 4706),
        ("15:59", 4706, 4710, 4700, 4705),
    ]
    bars = _multiday_bars([
        ("2024-06-10", day1),
        ("2024-06-11", day2),
        ("2024-06-12", day3),
        ("2024-06-13", day4),
        ("2024-06-14", day5),
    ])
    strat = S1a_ORB_TargetAndEOD(symbol="MES", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(bars)
    assert len(trades) == 4
    outcomes = [t.outcome for t in trades]
    assert outcomes.count(TradeOutcome.TARGET) == 2
    assert outcomes.count(TradeOutcome.STOP) == 1
    assert outcomes.count(TradeOutcome.EOD) == 1
    dates = [t.date for t in trades]
    assert dates == ["2024-06-10", "2024-06-12", "2024-06-13", "2024-06-14"]
