"""Tests for ChartRenderer (matplotlib tf-stack + context)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.delivery.chart_renderer import (
    ChartRenderer,
    ChartArtifacts,
)


def _bar(t: datetime, c: float) -> OHLCV:
    return OHLCV(timestamp=t, open=c, high=c + 2, low=c - 2, close=c, volume=1000)


def test_render_tf_stack_creates_png(tmp_path):
    bars_by_tf = {
        "1W": [_bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240)],
        "1D": [_bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246)],
        "4H": [_bar(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
        "1H": [_bar(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
    }
    renderer = ChartRenderer(output_dir=tmp_path)
    path = renderer.render_tf_stack(symbol="MES", bars_by_tf=bars_by_tf, today="2026-04-26")
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 100


def test_render_full_artifacts_returns_per_symbol_paths(tmp_path):
    bars_by_symbol = {
        "MES": {
            "1W": [_bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240)],
            "1D": [_bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246)],
            "4H": [], "1H": [],
        },
        "MGC": {
            "1W": [_bar(datetime(2026, 4, 18, tzinfo=timezone.utc), 2340)],
            "1D": [_bar(datetime(2026, 4, 24, tzinfo=timezone.utc), 2342)],
            "4H": [], "1H": [],
        },
    }
    renderer = ChartRenderer(output_dir=tmp_path)
    artifacts = renderer.render_all(
        bars_by_symbol_and_tf=bars_by_symbol,
        today="2026-04-26",
    )
    assert isinstance(artifacts, ChartArtifacts)
    assert "MES" in artifacts.tf_stack_paths
    assert "MGC" in artifacts.tf_stack_paths
    assert artifacts.tf_stack_paths["MES"].exists()


def test_chart_renderer_handles_empty_bars_gracefully(tmp_path):
    bars_by_tf = {tf: [] for tf in ("1W", "1D", "4H", "1H")}
    renderer = ChartRenderer(output_dir=tmp_path)
    path = renderer.render_tf_stack(symbol="MES", bars_by_tf=bars_by_tf, today="2026-04-26")
    assert path.exists()
