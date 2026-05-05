"""Unit tests for simulate_level."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from daytrader.reports.eod.plan_dataclasses import PlanLevel
from daytrader.reports.eod.trade_simulator import simulate_level


@dataclass
class _FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


def _bar(t: str, o: float, h: float, l: float, c: float) -> _FakeBar:
    """Helper: t='HH:MM' → bar at 2026-05-04 HH:MM PT."""
    hh, mm = t.split(":")
    ts = datetime(2026, 5, 4, int(hh), int(mm), tzinfo=timezone.utc)
    return _FakeBar(timestamp=ts, open=o, high=h, low=l, close=c)


def test_short_fade_point_target_hit():
    """short_fade POINT at 7272.75:
    - entry @ 7272.75 (level)
    - stop @ 7273.25 (level + 2 ticks × 0.25 = +0.5pt)
    - R_distance = 0.5pt
    - target @ 7272.75 - 2 × 0.5 = 7271.75
    """
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:30", 7250.0, 7255.0, 7248.0, 7252.0),
        _bar("06:53", 7269.0, 7273.50, 7268.0, 7270.0),  # touch (high >= 7272.75)
        _bar("07:00", 7270.0, 7271.0, 7270.5, 7270.5),    # low=7270.5 < 7271.75 target
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.triggered is True
    assert out.outcome == "target"
    assert out.sim_r == pytest.approx(2.0)
    assert out.sim_entry == pytest.approx(7272.75)
    assert out.sim_stop == pytest.approx(7273.25)
    assert out.sim_target == pytest.approx(7271.75)


def test_short_fade_point_stop_hit():
    """short_fade where price gaps up through stop after touch."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.50, 7270.0, 7273.0),   # touch entry
        _bar("06:54", 7273.0, 7275.0, 7273.0, 7274.5),    # high=7275 >= 7273.25 stop
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.outcome == "stop"
    assert out.sim_r == pytest.approx(-1.0)


def test_long_fade_point_target_hit():
    """long_fade POINT at 7240.75:
    - entry @ 7240.75
    - stop @ 7240.25 (level - 2 ticks × 0.25)
    - target @ 7240.75 + 2 × 0.5 = 7241.75
    """
    level = PlanLevel(
        price=7240.75, level_type="POINT", source="D low", direction="long_fade"
    )
    bars = [
        _bar("11:30", 7242.0, 7242.0, 7240.0, 7240.5),    # low=7240 <= 7240.75 → touch
        _bar("11:35", 7240.5, 7242.0, 7240.5, 7241.5),    # high=7242 >= 7241.75 target
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.outcome == "target"
    assert out.sim_r == pytest.approx(2.0)


def test_zone_fade_uses_far_edge_for_stop():
    """ZONE short_fade at 7271-7279.5: entry @ near-edge (7271 for short),
    stop = far_edge + offset = 7279.5 + 0.5 = 7280, target = entry - 2 × R_distance."""
    level = PlanLevel(
        price=7275.0,
        level_type="ZONE",
        source="4H R zone",
        direction="short_fade",
        zone_low=7271.0,
        zone_high=7279.5,
    )
    bars = [
        _bar("07:00", 7268.0, 7275.0, 7268.0, 7272.0),    # high>=7271 (near edge for short fade)
        _bar("07:05", 7272.0, 7272.0, 7253.0, 7254.0),    # large drop
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.triggered is True
    # entry = 7271 (near-edge for short fade), stop = 7280, R_distance = 9.0pt
    # target = 7271 - 2*9 = 7253 → hit at 07:05 (low=7253)
    assert out.sim_entry == pytest.approx(7271.0)
    assert out.sim_stop == pytest.approx(7280.0)
    assert out.sim_target == pytest.approx(7253.0)
    assert out.outcome == "target"


def test_untriggered_when_price_never_touches_level():
    level = PlanLevel(
        price=7400.0, level_type="POINT", source="far high", direction="short_fade"
    )
    bars = [
        _bar("06:30", 7250.0, 7260.0, 7248.0, 7255.0),
        _bar("12:00", 7250.0, 7270.0, 7240.0, 7260.0),
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.triggered is False
    assert out.outcome == "untriggered"
    assert out.sim_r == 0.0


def test_open_at_session_end():
    """Triggered but neither stop nor target hit — sim_r is partial."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.0, 7269.0, 7272.0),    # touch
        _bar("13:00", 7272.0, 7272.5, 7272.0, 7272.0),    # neither stop nor target
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.outcome == "open"
    # sim_r should be partial — based on (entry - close) / R_distance
    # entry=7272.75, last close=7272.0, r_distance=0.5 → sim_r = 1.5R favorable
    assert -1.0 < out.sim_r < 2.0


def test_target_capped_by_next_key_level_short():
    """short_fade with next_key_level closer than 2R — target = next_key_level."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.0, 7269.0, 7272.0),    # touch
        _bar("07:00", 7272.0, 7272.0, 7271.9, 7271.95),
    ]
    # 2R target = 7271.75; next_key_level = 7272.00 (closer to entry, more conservative)
    # target = max(7271.75, 7272.00) for short = 7272.00 (less aggressive)
    out = simulate_level(
        level, bars, next_key_level=7272.0,
        tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0,
    )
    assert out.sim_target == pytest.approx(7272.0)


def test_mfe_mae_computed():
    """MFE and MAE in R units track favorable/adverse excursion during open trade."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.0, 7269.0, 7272.0),    # touch + favorable down to 7269
        _bar("07:00", 7272.0, 7272.5, 7271.9, 7272.0),    # mfe to 7271.9
    ]
    out = simulate_level(
        level, bars, next_key_level=None,
        tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0,
    )
    # entry=7272.75, R=0.5
    # mfe = (7272.75 - 7269.0) / 0.5 = 7.5R (favorable)
    # mae = (7272.75 - 7273.0) / 0.5 = -0.5R (adverse, brief touch above)
    assert out.mfe_r is not None and out.mfe_r > 0
    assert out.mae_r is not None and out.mae_r <= 0
