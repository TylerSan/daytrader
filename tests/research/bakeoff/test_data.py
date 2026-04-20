"""Tests for bakeoff data layer."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from daytrader.research.bakeoff.data import detect_rollover_skip_dates


def _frame(rows):
    """Helper: build a DataFrame with UTC-indexed timestamps."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(ts, tz="UTC") for ts, _iid in rows]
    )
    return pd.DataFrame(
        {"instrument_id": [iid for _ts, iid in rows]},
        index=idx,
    )


def test_detect_rollover_skip_dates_no_transitions():
    df = _frame([
        ("2024-06-10 13:30", 100),
        ("2024-06-10 14:00", 100),
        ("2024-06-11 13:30", 100),
    ])
    assert detect_rollover_skip_dates(df) == []


def test_detect_rollover_skip_dates_single_transition():
    df = _frame([
        ("2024-06-10 13:30", 100),   # MESM4
        ("2024-06-11 13:30", 100),
        ("2024-06-12 13:30", 101),   # rollover to MESU4 here
        ("2024-06-13 13:30", 101),
    ])
    # Rollover day + preceding day both skipped.
    assert detect_rollover_skip_dates(df) == [date(2024, 6, 11), date(2024, 6, 12)]


def test_detect_rollover_skip_dates_multiple_transitions():
    df = _frame([
        ("2024-03-14 13:30", 100),
        ("2024-03-15 13:30", 101),   # rollover 1
        ("2024-06-12 13:30", 101),
        ("2024-06-13 13:30", 102),   # rollover 2
    ])
    assert detect_rollover_skip_dates(df) == [
        date(2024, 3, 14), date(2024, 3, 15),
        date(2024, 6, 12), date(2024, 6, 13),
    ]


def test_detect_rollover_skip_dates_missing_column_raises():
    df = pd.DataFrame({"close": [1, 2]}, index=pd.DatetimeIndex(
        [pd.Timestamp("2024-06-10 13:30", tz="UTC"),
         pd.Timestamp("2024-06-11 13:30", tz="UTC")]
    ))
    with pytest.raises(ValueError, match="instrument_id"):
        detect_rollover_skip_dates(df)


def test_detect_rollover_skip_dates_empty_frame():
    df = pd.DataFrame(
        {"instrument_id": []},
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    assert detect_rollover_skip_dates(df) == []
