"""Tests for S2 Intraday Momentum mechanical core."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from daytrader.research.bakeoff.strategies._s2_core import (
    atr_14,
    avg_intraday_return_14d,
    compute_noise_boundary,
    daily_true_range,
    walk_forward_with_trailing,
)
from daytrader.research.bakeoff.strategies._trade import TradeOutcome


ET = ZoneInfo("America/New_York")


def _daily(rows):
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c}
         for _d, o, h, l, c in rows],
        index=pd.DatetimeIndex([r[0] for r in rows]).normalize(),
    )
    df.index.name = "date"
    return df


def _intraday(date_str, rows_hm_ohlc):
    ts = [
        pd.Timestamp(f"{date_str} {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows_hm_ohlc
    ]
    df = pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1}
         for _hm, o, h, l, c in rows_hm_ohlc],
        index=pd.DatetimeIndex(ts),
    )
    return df


# --- daily_true_range ---

def test_daily_true_range_first_row_is_nan():
    d = _daily([
        ("2024-06-10", 100, 102, 99, 101),
        ("2024-06-11", 101, 104, 100, 103),
    ])
    tr = daily_true_range(d)
    assert np.isnan(tr.iloc[0])
    assert tr.iloc[1] == pytest.approx(4.0)


def test_daily_true_range_uses_prev_close_for_gap():
    d = _daily([
        ("2024-06-10", 100, 102, 99, 101),
        ("2024-06-11", 105, 106, 104, 105),
    ])
    tr = daily_true_range(d)
    assert tr.iloc[1] == pytest.approx(5.0)


# --- atr_14 ---

def test_atr_14_is_nan_until_14_days_accumulated_then_shifted_by_one():
    # TR[0] is NaN (no prev close), so the first valid rolling-14 mean with
    # 14 non-NaN values ends at TR[14] = mean(TR[1..14]). After shift(1), that
    # lands at atr_14 index 15.
    rows = []
    for i in range(16):
        tr = i + 1
        rows.append((f"2024-06-{i+1:02d}", 100, 100 + tr, 100, 100))
    d = _daily(rows)
    a = atr_14(d)
    assert np.isnan(a.iloc[13])
    assert np.isnan(a.iloc[14])
    # mean(TR[1..14]) = mean(2, 3, ..., 15) = sum(2..15)/14 = 119/14 = 8.5
    assert a.iloc[15] == pytest.approx(8.5)


# --- avg_intraday_return_14d ---

def test_avg_intraday_return_14d_single_checktime_rolls_14_days():
    frames = []
    for k in range(15):
        d_str = f"2024-06-{k+1:02d}"
        frames.append(_intraday(d_str, [
            ("09:30", 100, 100, 100, 100),
            ("10:00", 100, 100 + 0.1 * k, 100, 100 + 0.1 * k),
        ]))
    bars = pd.concat(frames).sort_index()
    avg = avg_intraday_return_14d(
        bars, check_times_et=["10:00"], tz="America/New_York"
    )
    last_date = avg.index[-1]
    assert avg.loc[last_date, "10:00"] == pytest.approx(0.0065, abs=1e-9)


def test_avg_intraday_return_14d_raises_on_missing_0930():
    bars = _intraday("2024-06-10", [
        ("09:31", 100, 101, 99, 100),
        ("10:00", 100, 101, 99, 100),
    ])
    with pytest.raises(ValueError, match="09:30"):
        avg_intraday_return_14d(
            bars, check_times_et=["10:00"], tz="America/New_York"
        )


# --- compute_noise_boundary ---

def test_noise_boundary_no_gap_is_symmetric():
    row = pd.Series({"10:00": 0.003, "10:30": 0.005})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=0.0, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3)
    assert lower["10:00"] == pytest.approx(99.7)


def test_noise_boundary_up_gap_shifts_lower_down():
    row = pd.Series({"10:00": 0.003})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=+0.5, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3)
    assert lower["10:00"] == pytest.approx(99.7 - 0.5)


def test_noise_boundary_down_gap_shifts_upper_up():
    row = pd.Series({"10:00": 0.003})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=-0.4, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3 + 0.4)
    assert lower["10:00"] == pytest.approx(99.7)


def test_noise_boundary_uses_absolute_value_of_return():
    row = pd.Series({"10:00": -0.003})
    upper, lower = compute_noise_boundary(
        daily_open=100.0, overnight_gap=0.0, avg_intra_return_row=row
    )
    assert upper["10:00"] == pytest.approx(100.3)
    assert lower["10:00"] == pytest.approx(99.7)


# --- walk_forward_with_trailing ---

def test_trailing_long_ratchets_stop_up_then_hits():
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 105, 100, 105),
        ("10:02", 105, 110, 105, 110),
        ("10:03", 110, 110, 104, 105),
        ("15:55", 105, 106, 105, 106),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(106.0)


def test_trailing_long_stop_never_moves_down():
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 108, 100, 108),
        ("10:02", 108, 108, 105, 105),
        ("10:03", 105, 105, 103, 103),
        ("15:55", 103, 104, 103, 104),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(104.0)


def test_trailing_short_symmetric():
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 100, 95, 95),
        ("10:02", 95, 95, 92, 92),
        ("10:03", 92, 97, 92, 97),
        ("15:55", 97, 97, 96, 96),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="short",
        entry_price=100.0,
        initial_stop=104.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(96.0)


def test_trailing_eod_when_never_stopped():
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 101, 100, 101),
        ("15:55", 101, 102, 100.5, 101.5),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.EOD
    assert exit.exit_price == pytest.approx(101.5)


def test_trailing_initial_stop_hits_on_first_bar():
    post = _intraday("2024-06-10", [
        ("10:00", 100, 100, 100, 100),
        ("10:01", 100, 100, 95, 95),
        ("15:55", 95, 96, 95, 96),
    ])
    exit = walk_forward_with_trailing(
        bars_after_entry=post,
        direction="long",
        entry_price=100.0,
        initial_stop=96.0,
        atr_14_d=2.0,
        eod_cutoff_ts=post.index[-1],
    )
    assert exit.outcome is TradeOutcome.STOP
    assert exit.exit_price == pytest.approx(96.0)
