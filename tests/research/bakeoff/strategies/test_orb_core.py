"""Tests for ORB mechanical core (opening range + entry + walk-forward)."""

from __future__ import annotations

import math
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._orb_core import (
    compute_opening_range,
    direction_from_first_bar,
    walk_forward_to_exit,
    OpeningRange,
)
from daytrader.research.bakeoff.strategies._trade import TradeOutcome


ET = ZoneInfo("America/New_York")


def _bar_row(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": 1}


def _make_day_bars(rows_with_et_time, ticker_iid=100):
    timestamps_utc = [
        pd.Timestamp(f"2024-06-10 {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows_with_et_time
    ]
    data = [_bar_row(o, h, l, c) for _hm, o, h, l, c in rows_with_et_time]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps_utc))
    df["instrument_id"] = ticker_iid
    return df


def test_opening_range_high_low_from_first_five_bars():
    bars = _make_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5002, 5008),
        ("09:35", 5008, 5012, 5007, 5010),
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert or_.high == pytest.approx(5010.0)
    assert or_.low == pytest.approx(4998.0)
    assert or_.range_pts == pytest.approx(12.0)
    assert or_.close_at_or_end == pytest.approx(5008.0)
    assert or_.open_at_session_start == pytest.approx(5000.0)
    assert or_.or_end_index == 4


def test_opening_range_raises_if_insufficient_bars():
    bars = _make_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
    ])
    with pytest.raises(ValueError, match="insufficient"):
        compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")


def test_direction_long_when_or_close_above_open():
    bars = _make_day_bars([
        ("09:30", 5000, 5005, 4998, 5002),
        ("09:31", 5002, 5008, 5001, 5006),
        ("09:32", 5006, 5010, 5004, 5004),
        ("09:33", 5004, 5007, 5003, 5007),
        ("09:34", 5007, 5009, 5002, 5008),
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert direction_from_first_bar(or_) == "long"


def test_direction_short_when_or_close_below_open():
    bars = _make_day_bars([
        ("09:30", 5000, 5002, 4990, 4992),
        ("09:31", 4992, 4993, 4985, 4988),
        ("09:32", 4988, 4990, 4982, 4984),
        ("09:33", 4984, 4985, 4980, 4982),
        ("09:34", 4982, 4983, 4975, 4978),
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert direction_from_first_bar(or_) == "short"


def test_direction_none_when_flat():
    bars = _make_day_bars([
        ("09:30", 5000, 5002, 4999, 5001),
        ("09:31", 5001, 5002, 5000, 5000),
        ("09:32", 5000, 5001, 4999, 5000),
        ("09:33", 5000, 5001, 4999, 5000),
        ("09:34", 5000, 5001, 4999, 5000),
    ])
    or_ = compute_opening_range(bars, or_minutes=5, session_tz="America/New_York")
    assert direction_from_first_bar(or_) is None


def test_walk_forward_long_hits_target():
    post_or = _make_day_bars([
        ("09:35", 5010, 5015, 5009, 5014),
        ("09:36", 5014, 5020, 5013, 5019),
        ("09:37", 5019, 5051, 5018, 5050),
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=5050.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.TARGET
    assert exit.exit_price == pytest.approx(5050.0)


def test_walk_forward_long_hits_stop_first():
    post_or = _make_day_bars([
        ("09:35", 5010, 5012, 5011, 5011),
        ("09:36", 5011, 5013, 4995, 4998),
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=5050.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(5000.0)


def test_walk_forward_short_hits_target():
    post_or = _make_day_bars([
        ("09:35", 4990, 4995, 4985, 4988),
        ("09:36", 4988, 4989, 4948, 4950),
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="short",
        entry_price=4990.0,
        stop_price=5000.0,
        target_price=4950.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.TARGET
    assert exit.exit_price == pytest.approx(4950.0)


def test_walk_forward_eod_when_neither_hit():
    post_or = _make_day_bars([
        ("09:35", 5010, 5012, 5005, 5008),
        ("15:59", 5008, 5011, 5005, 5009),
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=5050.0,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.EOD
    assert exit.exit_price == pytest.approx(5009.0)


def test_walk_forward_nan_target_treated_as_eod_only():
    post_or = _make_day_bars([
        ("09:35", 5010, 5100, 5005, 5099),
        ("15:59", 5099, 5101, 5098, 5100),
    ])
    exit = walk_forward_to_exit(
        bars_after_entry=post_or,
        direction="long",
        entry_price=5010.0,
        stop_price=5000.0,
        target_price=math.nan,
        eod_exit_ts=post_or.index[-1],
    )
    assert exit.outcome is TradeOutcome.EOD
    assert exit.exit_price == pytest.approx(5100.0)
