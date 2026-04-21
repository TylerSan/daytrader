"""Tests for MFE/MAE helper used by the S2 ATR scan runner."""

from __future__ import annotations

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

# Add repo scripts/ to path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from _s2_scan_mfe_mae import compute_mfe_mae_r  # noqa: E402

from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


ET = ZoneInfo("America/New_York")


def _trade(direction, entry_price, stop_price, exit_price, entry_hm, exit_hm):
    entry = pd.Timestamp(f"2024-06-10 {entry_hm}", tz=ET).tz_convert("UTC")
    exit = pd.Timestamp(f"2024-06-10 {exit_hm}", tz=ET).tz_convert("UTC")
    return Trade(
        date="2024-06-10", symbol="SPY", direction=direction,
        entry_time=entry.to_pydatetime(), entry_price=entry_price,
        stop_price=stop_price, target_price=float("nan"),
        exit_time=exit.to_pydatetime(), exit_price=exit_price,
        outcome=TradeOutcome.EOD, r_multiple=0.0,
    )


def _bars(rows_hm_ohlc):
    ts = [
        pd.Timestamp(f"2024-06-10 {hm}", tz=ET).tz_convert("UTC")
        for hm, *_ in rows_hm_ohlc
    ]
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1}
         for _hm, o, h, l, c in rows_hm_ohlc],
        index=pd.DatetimeIndex(ts),
    )


def test_mfe_mae_long_basic():
    # Entry 100 @ 10:00, stop 96 (risk=4), exit 102 @ 10:30 EOD.
    # Over held bars: max high=105, min low=98.
    # MFE = 105 - 100 = 5 → 5/4 = 1.25 R
    # MAE = 100 - 98 = 2 → 2/4 = 0.5 R
    t = _trade("long", 100.0, 96.0, 102.0, "10:00", "10:30")
    bars = _bars([
        ("10:00", 100, 100, 100, 100),
        ("10:10", 100, 105, 98, 103),
        ("10:20", 103, 103, 99, 101),
        ("10:30", 101, 102, 98, 102),
    ])
    mfe, mae = compute_mfe_mae_r(t, bars)
    assert mfe == pytest.approx(1.25)
    assert mae == pytest.approx(0.5)


def test_mfe_mae_short_symmetric():
    # Entry 100 short, stop 104 (risk=4), exit 98.
    # Over held bars: min low=93 (MFE for short = 100-93=7, 7/4=1.75)
    #                 max high=102 (MAE for short = 102-100=2, 2/4=0.5)
    t = _trade("short", 100.0, 104.0, 98.0, "10:00", "10:30")
    bars = _bars([
        ("10:00", 100, 100, 100, 100),
        ("10:10", 100, 101, 93, 95),
        ("10:20", 95, 102, 94, 96),
        ("10:30", 96, 99, 96, 98),
    ])
    mfe, mae = compute_mfe_mae_r(t, bars)
    assert mfe == pytest.approx(1.75)
    assert mae == pytest.approx(0.5)


def test_mfe_mae_risk_zero_returns_zero():
    """Degenerate: entry == stop → risk=0, return 0,0 to avoid div-by-zero."""
    t = _trade("long", 100.0, 100.0, 100.0, "10:00", "10:30")
    bars = _bars([
        ("10:00", 100, 100, 100, 100),
        ("10:30", 100, 101, 99, 100),
    ])
    mfe, mae = compute_mfe_mae_r(t, bars)
    assert mfe == 0.0
    assert mae == 0.0


def test_mfe_mae_ignores_bars_outside_hold():
    """Bars before entry or after exit should not affect MFE/MAE."""
    t = _trade("long", 100.0, 96.0, 102.0, "10:10", "10:20")
    bars = _bars([
        ("10:00", 100, 200, 50, 100),
        ("10:10", 100, 101, 100, 101),
        ("10:20", 101, 103, 100, 102),
        ("10:30", 102, 999, 1, 102),
    ])
    mfe, mae = compute_mfe_mae_r(t, bars)
    # Held: 10:10..10:20. Max high=103, min low=100.
    # MFE = 103-100=3, 3/4=0.75. MAE = 100-100=0.
    assert mfe == pytest.approx(0.75)
    assert mae == pytest.approx(0.0)
