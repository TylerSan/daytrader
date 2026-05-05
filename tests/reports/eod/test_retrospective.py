"""Unit tests for PlanRetrospective composition + persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from daytrader.reports.eod.plan_dataclasses import PlanLevel, SimOutcome
from daytrader.reports.eod.retrospective import PlanRetrospective


@dataclass
class _FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


def _init_state_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE plan_retrospective_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            total_levels INTEGER NOT NULL,
            triggered_count INTEGER NOT NULL,
            sim_total_r REAL NOT NULL,
            actual_total_r REAL NOT NULL,
            gap_r REAL NOT NULL,
            retrospective_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(date, symbol)
        )"""
    )
    conn.commit()
    conn.close()


def test_compose_and_persist_writes_one_row_per_symbol(tmp_path):
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)

    fake_parser = MagicMock()
    fake_parser.parse.return_value = MagicMock(
        symbol="MES",
        levels=[
            PlanLevel(price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"),
        ],
        raw_block_md="...",
        parse_warnings=[],
        stop_offset_ticks=2,
        target_r_multiple=2.0,
    )

    fake_simulator = MagicMock()
    fake_simulator.return_value = SimOutcome(
        triggered=True, touch_time_pt="06:53",
        touch_bar_high=7273.5, touch_bar_low=7268.0,
        sim_entry=7272.75, sim_stop=7273.25, sim_target=7271.75,
        outcome="target", sim_r=2.0, mfe_r=2.0, mae_r=-0.4,
    )

    fake_bars = [
        _FakeBar(datetime(2026, 5, 4, 6, 53, tzinfo=timezone.utc), 7269, 7273.5, 7268, 7270),
    ]
    fake_bar_fetcher = MagicMock(return_value=fake_bars)

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {"daily_r": 0.0}

    retrospective = PlanRetrospective(
        plan_parser=fake_parser,
        trade_simulator=fake_simulator,
        intraday_bar_fetcher=fake_bar_fetcher,
        trades_query=fake_trades_query,
        state_db_path=db_path,
    )

    rows = retrospective.compose(
        plans={"MES": "raw block content"},
        symbols=["MES"],
        date_et="2026-05-04",
        tick_sizes={"MES": 0.25},
    )
    retrospective.persist(rows)

    # Verify row written to DB
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT date, symbol, total_levels, triggered_count, sim_total_r FROM plan_retrospective_daily")
    row = cur.fetchone()
    assert row is not None
    assert row == ("2026-05-04", "MES", 1, 1, 2.0)
    conn.close()


def test_aggregate_stats_match_outcomes(tmp_path):
    """gap_r = sim_total_r - actual_total_r."""
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)

    fake_parser = MagicMock()
    fake_parser.parse.return_value = MagicMock(
        symbol="MES",
        levels=[
            PlanLevel(price=7272.75, level_type="POINT", source="P1", direction="short_fade"),
            PlanLevel(price=7240.75, level_type="POINT", source="P2", direction="long_fade"),
        ],
        raw_block_md="", parse_warnings=[],
        stop_offset_ticks=2, target_r_multiple=2.0,
    )

    fake_simulator = MagicMock()
    fake_simulator.side_effect = [
        SimOutcome(True, "06:53", 7273, 7268, 7272.75, 7273.25, 7271.75, "target", 2.0, 2.0, -0.4),
        SimOutcome(True, "11:30", 7242, 7240, 7240.75, 7240.25, 7241.75, "stop", -1.0, 0.5, -1.0),
    ]
    fake_bar_fetcher = MagicMock(return_value=[])

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {"daily_r": 0.0}

    retrospective = PlanRetrospective(
        plan_parser=fake_parser, trade_simulator=fake_simulator,
        intraday_bar_fetcher=fake_bar_fetcher, trades_query=fake_trades_query,
        state_db_path=db_path,
    )
    rows = retrospective.compose(
        plans={"MES": "raw"},
        symbols=["MES"],
        date_et="2026-05-04",
        tick_sizes={"MES": 0.25},
    )
    row = rows["MES"]
    assert row.total_levels == 2
    assert row.triggered_count == 2
    assert row.sim_total_r == pytest.approx(2.0 + (-1.0))  # +1R net
    assert row.actual_total_r == 0.0
    assert row.gap_r == pytest.approx(1.0)


def test_no_plan_returns_empty_retrospective(tmp_path):
    """If plans dict is empty (premarket file missing), no rows."""
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)
    retrospective = PlanRetrospective(
        plan_parser=MagicMock(), trade_simulator=MagicMock(),
        intraday_bar_fetcher=MagicMock(), trades_query=MagicMock(),
        state_db_path=db_path,
    )
    rows = retrospective.compose(plans={}, symbols=["MES"], date_et="2026-05-04", tick_sizes={"MES": 0.25})
    assert rows == {}


def test_persist_idempotent_for_same_date_symbol(tmp_path):
    """If retrospective for (date, symbol) already exists, replace not duplicate."""
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)

    retrospective = PlanRetrospective(
        plan_parser=MagicMock(), trade_simulator=MagicMock(),
        intraday_bar_fetcher=MagicMock(), trades_query=MagicMock(),
        state_db_path=db_path,
    )
    from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
    row = RetrospectiveRow(
        symbol="MES", date_et="2026-05-04", total_levels=1, triggered_count=0,
        sim_total_r=0.0, actual_total_r=0.0, gap_r=0.0, per_level_outcomes=[],
    )
    retrospective.persist({"MES": row})
    retrospective.persist({"MES": row})  # second call

    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT COUNT(*) FROM plan_retrospective_daily WHERE date='2026-05-04' AND symbol='MES'")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 1  # not 2
