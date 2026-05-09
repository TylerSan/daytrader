"""Tests for Pine Script renderer (key levels for TradingView)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.delivery.pine_renderer import (
    KeyLevels,
    LevelExtractor,
    PineScriptRenderer,
)


def _bar(t: datetime, o: float, h: float, l: float, c: float, v: float = 1000) -> OHLCV:
    return OHLCV(timestamp=t, open=o, high=h, low=l, close=c, volume=v)


# ---------- LevelExtractor ----------

def test_level_extractor_pulls_pdh_pdl_pdc_from_daily_bars():
    """LevelExtractor takes the most-recent COMPLETED daily bar as 'prior day'."""
    fake_ib = MagicMock()
    # Two daily bars: first = 2 days ago, last = yesterday (most recent completed)
    fake_ib.get_bars.side_effect = [
        # 1D — chronological order, most recent last
        [
            _bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 7100, 7150, 7080, 7120),
            _bar(datetime(2026, 4, 25, tzinfo=timezone.utc), 7120, 7200, 7110, 7195),
        ],
        # 1W
        [
            _bar(datetime(2026, 4, 11, tzinfo=timezone.utc), 6800, 6900, 6750, 6850),
            _bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 6850, 7200, 6800, 7195),
        ],
    ]

    extractor = LevelExtractor(ib_client=fake_ib)
    levels = extractor.extract(symbol="MES")

    assert isinstance(levels, KeyLevels)
    assert levels.prior_day_high == pytest.approx(7200)
    assert levels.prior_day_low == pytest.approx(7110)
    assert levels.prior_day_close == pytest.approx(7195)
    assert levels.weekly_high == pytest.approx(7200)
    assert levels.weekly_low == pytest.approx(6800)


def test_level_extractor_handles_empty_bars_gracefully():
    """Empty bar lists → KeyLevels with NaN fields (not a crash)."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = []

    extractor = LevelExtractor(ib_client=fake_ib)
    levels = extractor.extract(symbol="MES")

    # All fields None for empty data
    assert levels.prior_day_high is None
    assert levels.prior_day_low is None
    assert levels.weekly_high is None


# ---------- PineScriptRenderer ----------

def test_pine_renderer_emits_v5_indicator_header():
    """Output begins with '//@version=5' and has the indicator() declaration."""
    levels = KeyLevels(
        prior_day_high=7200, prior_day_low=7110, prior_day_close=7195,
        weekly_high=7200, weekly_low=6800,
    )
    renderer = PineScriptRenderer(output_dir=Path("/tmp"))
    code = renderer.render(levels=levels, symbol="MES", today=date(2026, 4, 26))

    assert code.startswith("//@version=5")
    assert 'indicator("DayTrader Levels — MES (2026-04-26)"' in code
    assert "overlay=true" in code


def test_pine_renderer_emits_hline_per_present_level():
    """Each non-None KeyLevels field gets one hline() call with the right price."""
    levels = KeyLevels(
        prior_day_high=7200, prior_day_low=7110, prior_day_close=7195,
        weekly_high=7200, weekly_low=6800,
    )
    renderer = PineScriptRenderer(output_dir=Path("/tmp"))
    code = renderer.render(levels=levels, symbol="MES", today=date(2026, 4, 26))

    # 5 hline() calls, one per level
    assert code.count("hline(") == 5
    # Each price appears as a number in the source
    assert "7200" in code
    assert "7110" in code
    assert "7195" in code
    assert "6800" in code


def test_pine_renderer_skips_none_levels():
    """If only PDH/PDL are known, only 2 hline() calls emitted."""
    levels = KeyLevels(
        prior_day_high=7200, prior_day_low=7110,
        prior_day_close=None, weekly_high=None, weekly_low=None,
    )
    renderer = PineScriptRenderer(output_dir=Path("/tmp"))
    code = renderer.render(levels=levels, symbol="MES", today=date(2026, 4, 26))

    assert code.count("hline(") == 2
    assert "7200" in code
    assert "7110" in code


def test_pine_renderer_save_writes_file(tmp_path):
    levels = KeyLevels(
        prior_day_high=7200, prior_day_low=7110, prior_day_close=7195,
        weekly_high=None, weekly_low=None,
    )
    renderer = PineScriptRenderer(output_dir=tmp_path)
    path = renderer.render_and_save(
        levels=levels, symbol="MES", today=date(2026, 4, 26)
    )
    assert path.exists()
    assert "levels-MES-2026-04-26.pine" in path.name
    content = path.read_text()
    assert content.startswith("//@version=5")
