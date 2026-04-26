"""Unit tests for daytrader.core.state.StateDB."""

from __future__ import annotations

import sqlite3

import pytest

from daytrader.core.state import StateDB


def test_statedb_initializes_schema(tmp_state_db):
    """StateDB.initialize() creates all required tables."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    conn = sqlite3.connect(str(tmp_state_db))
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    conn.close()

    expected = {
        "plans",
        "reports",
        "news_seen",
        "failures",
        "lock_in_status",
        "bar_cache",
    }
    assert expected.issubset(tables)


def test_statedb_initialize_idempotent(tmp_state_db):
    """Calling initialize() twice does not error."""
    db = StateDB(str(tmp_state_db))
    db.initialize()
    db.initialize()  # second call must not raise


def test_statedb_creates_parent_directory(tmp_path):
    """StateDB creates parent directory if missing."""
    nested = tmp_path / "subdir" / "state.db"
    db = StateDB(str(nested))
    db.initialize()
    assert nested.exists()


from datetime import datetime, timezone


def test_statedb_insert_report_and_get(tmp_state_db):
    """insert_report() stores a row, get_report_by_id() retrieves it."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    rid = db.insert_report(
        report_type="premarket",
        date_et="2026-04-25",
        time_pt="06:00",
        time_et="09:00",
        status="pending",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )
    assert isinstance(rid, int)
    assert rid > 0

    row = db.get_report_by_id(rid)
    assert row["report_type"] == "premarket"
    assert row["date"] == "2026-04-25"
    assert row["status"] == "pending"


def test_statedb_update_report_status(tmp_state_db):
    """update_report_status() records final state and metrics."""
    db = StateDB(str(tmp_state_db))
    db.initialize()
    rid = db.insert_report(
        report_type="premarket",
        date_et="2026-04-25",
        time_pt="06:00",
        time_et="09:00",
        status="pending",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )

    db.update_report_status(
        rid,
        status="success",
        obsidian_path="/path/to/file.md",
        tokens_input=14000,
        tokens_output=5000,
        duration_seconds=18.4,
        estimated_cost_usd=0.55,
    )

    row = db.get_report_by_id(rid)
    assert row["status"] == "success"
    assert row["obsidian_path"] == "/path/to/file.md"
    assert row["tokens_input"] == 14000
    assert row["duration_seconds"] == pytest.approx(18.4)


def test_statedb_already_generated_today(tmp_state_db):
    """already_generated_today() supports idempotency check."""
    db = StateDB(str(tmp_state_db))
    db.initialize()

    assert db.already_generated_today("premarket", "2026-04-25") is False

    db.insert_report(
        report_type="premarket",
        date_et="2026-04-25",
        time_pt="06:00",
        time_et="09:00",
        status="success",
        created_at=datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc),
    )

    assert db.already_generated_today("premarket", "2026-04-25") is True
    assert db.already_generated_today("eod", "2026-04-25") is False
