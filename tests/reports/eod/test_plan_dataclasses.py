"""Unit tests for EOD plan dataclasses."""

from __future__ import annotations

import pytest

from daytrader.reports.eod.plan_dataclasses import (
    Plan,
    PlanLevel,
    RetrospectiveRow,
    SimOutcome,
)


def test_plan_level_point_construction():
    pl = PlanLevel(
        price=7272.75,
        level_type="POINT",
        source="4H POC",
        direction="short_fade",
    )
    assert pl.price == 7272.75
    assert pl.level_type == "POINT"
    assert pl.zone_low is None
    assert pl.zone_high is None


def test_plan_level_zone_construction():
    pl = PlanLevel(
        price=7190.0,
        level_type="ZONE",
        source="W demand zone",
        direction="long_fade",
        zone_low=7185.0,
        zone_high=7195.0,
    )
    assert pl.zone_low == 7185.0
    assert pl.zone_high == 7195.0


def test_plan_level_is_frozen():
    pl = PlanLevel(price=1.0, level_type="POINT", source="x", direction="long_fade")
    with pytest.raises(Exception):  # FrozenInstanceError
        pl.price = 2.0  # type: ignore[misc]


def test_plan_construction():
    levels = [
        PlanLevel(price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"),
        PlanLevel(price=7240.75, level_type="POINT", source="D low", direction="long_fade"),
    ]
    p = Plan(symbol="MES", levels=levels)
    assert p.symbol == "MES"
    assert len(p.levels) == 2
    assert p.stop_offset_ticks == 2  # default
    assert p.target_r_multiple == 2.0  # default
    assert p.parse_warnings == []  # default empty


def test_plan_with_warnings():
    p = Plan(
        symbol="MES",
        levels=[],
        parse_warnings=["could not parse 'Stretch short' label"],
    )
    assert "could not parse" in p.parse_warnings[0]


def test_sim_outcome_untriggered_factory():
    s = SimOutcome.untriggered()
    assert s.triggered is False
    assert s.outcome == "untriggered"
    assert s.sim_r == 0.0
    assert s.touch_time_pt is None
    assert s.sim_entry is None


def test_sim_outcome_target_hit():
    s = SimOutcome(
        triggered=True,
        touch_time_pt="06:53",
        touch_bar_high=7273.5,
        touch_bar_low=7271.0,
        sim_entry=7272.75,
        sim_stop=7273.25,
        sim_target=7252.75,
        outcome="target",
        sim_r=2.0,
        mfe_r=2.0,
        mae_r=-0.4,
    )
    assert s.outcome == "target"
    assert s.sim_r == 2.0
    assert s.mfe_r == 2.0


def test_retrospective_row_construction():
    levels = [PlanLevel(price=7272.75, level_type="POINT", source="4H POC", direction="short_fade")]
    outcomes = [(levels[0], SimOutcome.untriggered())]
    row = RetrospectiveRow(
        symbol="MES",
        date_et="2026-05-04",
        total_levels=1,
        triggered_count=0,
        sim_total_r=0.0,
        actual_total_r=0.0,
        gap_r=0.0,
        per_level_outcomes=outcomes,
    )
    assert row.symbol == "MES"
    assert row.total_levels == 1
    assert row.triggered_count == 0
    assert len(row.per_level_outcomes) == 1
