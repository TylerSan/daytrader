"""Unit tests for TomorrowPreliminaryPlan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
from daytrader.reports.eod.tomorrow_plan import TomorrowPreliminaryPlan


@dataclass
class _FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


def test_renders_today_levels_per_symbol():
    today_bars = {
        "MES": {
            "1D": [_FakeBar(datetime(2026, 5, 4), 7250, 7280, 7240, 7260)],
        },
        "MGC": {
            "1D": [_FakeBar(datetime(2026, 5, 4), 4530, 4550, 4515, 4535)],
        },
    }
    today_retros = {}  # empty for this test
    sentiment_md = "## D. 情绪面\n+1 / 10\n"

    planner = TomorrowPreliminaryPlan()
    md = planner.build_input_data(today_bars, today_retros, sentiment_md)

    # Should mention each symbol's today H/L/C
    assert "MES" in md
    assert "7280" in md   # today high
    assert "7240" in md   # today low
    assert "MGC" in md
    assert "4550" in md


def test_includes_retrospective_insight_when_available():
    today_bars = {"MES": {"1D": [_FakeBar(datetime(2026, 5, 4), 7250, 7280, 7240, 7260)]}}
    today_retros = {
        "MES": RetrospectiveRow(
            symbol="MES", date_et="2026-05-04",
            total_levels=4, triggered_count=2,
            sim_total_r=3.5, actual_total_r=0.0, gap_r=3.5,
            per_level_outcomes=[],
        )
    }
    planner = TomorrowPreliminaryPlan()
    md = planner.build_input_data(today_bars, today_retros, "")

    # Should reference today's plan accuracy
    assert "2/4" in md or "50" in md or "trigger" in md.lower()
    assert "3.5" in md or "+3" in md  # sim total R


def test_empty_inputs_produce_minimal_output():
    """Defensive: empty bars and empty retrospective shouldn't crash."""
    planner = TomorrowPreliminaryPlan()
    md = planner.build_input_data({}, {}, "")
    # Should produce at least a header / placeholder, not crash
    assert isinstance(md, str)
    assert len(md) > 0  # some minimal markdown
