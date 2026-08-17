"""Tests for backtest engine with synthetic data (no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from daytrader.journal.sanity_floor.engine import (
    SimulatedTrade, simulate_setup,
)
from daytrader.journal.sanity_floor.setup_yaml import load_setup_yaml


def _synthetic_orb_winner_df() -> pd.DataFrame:
    """One trading day, OR 09:30-09:45 = 5000-5003.
    At 09:50, close crosses 5003+2ticks (5003.5) -> long entry.
    Price walks up to hit target (2*OR_range=2*3=6, entry+6=5009.7).
    Use 1-minute bars in UTC."""
    times = pd.date_range("2026-04-01 13:30", "2026-04-01 15:30",
                          freq="min", tz="UTC")
    # 13:30 UTC = 09:30 ET during EDT
    rows = []
    for t in times:
        hh, mm = t.hour, t.minute
        if (hh, mm) < (13, 45):
            o, h, l, c = 5000.5, 5003.0, 5000.0, 5002.0
        elif (hh, mm) == (13, 50):
            o, h, l, c = 5002.5, 5003.8, 5002.5, 5003.7  # breakout close
        elif (hh, mm) < (15, 0):
            o = 5003.7 + (mm * 0.1)
            h = 5004.5 + mm * 0.1
            l = 5003.5 + mm * 0.1
            c = 5004.0 + mm * 0.1
        else:
            # force target hit
            o, h, l, c = 5009.5, 5010.0, 5009.0, 5009.8
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 100})
    return pd.DataFrame(rows, index=times)


def test_orb_winner_detected(tmp_path: Path):
    yaml_text = """
name: orb
version: v1
symbols: [MES]
session_window:
  start: "09:30 America/New_York"
  end: "11:30 America/New_York"
opening_range:
  duration_minutes: 15
entry:
  direction: long_if_above_or_short_if_below
  trigger: price_closes_beyond_or_by_ticks
  ticks: 2
stop:
  rule: opposite_side_of_or
  offset_ticks: 2
target:
  rule: multiple_of_or_range
  multiple: 2.0
filters: []
"""
    p = tmp_path / "orb.yaml"
    p.write_text(yaml_text)
    setup = load_setup_yaml(p)
    df = _synthetic_orb_winner_df()
    trades = simulate_setup(setup=setup, symbol="MES", df=df, tick_size=0.25)
    assert len(trades) == 1, f"Expected 1 trade, got {len(trades)}"
    t = trades[0]
    assert t.direction == "long"
    assert t.r_multiple > 0


def test_no_trades_when_range_too_small():
    # Flat day: OR range = 0 → no breakout possible
    times = pd.date_range("2026-04-01 13:30", "2026-04-01 15:30",
                          freq="min", tz="UTC")
    df = pd.DataFrame(
        {"Open": 5000.0, "High": 5000.0, "Low": 5000.0,
         "Close": 5000.0, "Volume": 100},
        index=times,
    )
    from daytrader.journal.sanity_floor.setup_yaml import (
        SetupDefinition,
    )
    setup = SetupDefinition(
        name="orb", version="v1", symbols=["MES"],
        session_window={"start": "09:30 America/New_York",
                         "end": "11:30 America/New_York"},
        opening_range={"duration_minutes": 15},
        entry={"direction": "long_if_above_or_short_if_below",
                "trigger": "price_closes_beyond_or_by_ticks", "ticks": 2},
        stop={"rule": "opposite_side_of_or", "offset_ticks": 2},
        target={"rule": "multiple_of_or_range", "multiple": 2.0},
        filters=[{"min_or_range_ticks": 8}],
        raw={},
    )
    trades = simulate_setup(setup=setup, symbol="MES", df=df, tick_size=0.25)
    assert len(trades) == 0
