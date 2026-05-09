"""Tests for volume profile (POC, VAH, VAL)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.futures_data.volume_profile import (
    VolumeProfile,
    compute_volume_profile,
)


def _bar(t: datetime, o: float, h: float, l: float, c: float, v: float) -> OHLCV:
    return OHLCV(timestamp=t, open=o, high=h, low=l, close=c, volume=v)


def test_compute_volume_profile_basic():
    bars = [
        _bar(datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc), 5240, 5246, 5238, 5244, 1000),
    ]
    vp = compute_volume_profile(bars, tick_size=0.25, value_area_pct=0.7)
    assert isinstance(vp, VolumeProfile)
    assert 5238 <= vp.poc <= 5246
    assert vp.val <= vp.poc <= vp.vah
    assert vp.total_volume == pytest.approx(1000.0)


def test_compute_volume_profile_aggregates_multiple_bars():
    bars = [
        _bar(datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc), 5240, 5246, 5238, 5244, 1000),
        _bar(datetime(2026, 4, 25, 14, 1, tzinfo=timezone.utc), 5244, 5248, 5242, 5246, 2000),
        _bar(datetime(2026, 4, 25, 14, 2, tzinfo=timezone.utc), 5246, 5250, 5244, 5248, 1500),
    ]
    vp = compute_volume_profile(bars, tick_size=0.25, value_area_pct=0.7)
    assert 5244 <= vp.poc <= 5246
    assert vp.total_volume == pytest.approx(4500.0)
    assert vp.val < vp.vah


def test_compute_volume_profile_empty_bars_raises():
    with pytest.raises(ValueError, match="empty"):
        compute_volume_profile([], tick_size=0.25)
