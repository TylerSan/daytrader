"""StateDB `reports.data_source` column: fresh schema, migration, round-trip."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from daytrader.core.state import StateDB

# reports table exactly as created by the pre-data_source schema.
_OLD_REPORTS_DDL = """
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    date TEXT NOT NULL,
    time_pt TEXT NOT NULL,
    time_et TEXT NOT NULL,
    obsidian_path TEXT,
    pdf_path TEXT,
    telegram_msg_ids TEXT,
    status TEXT NOT NULL,
    failure_reason TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cache_hit_rate REAL,
    duration_seconds REAL,
    estimated_cost_usd REAL,
    created_at TEXT NOT NULL
);
"""


def _cols(path) -> list[str]:
    conn = sqlite3.connect(str(path))
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(reports)")]
    finally:
        conn.close()


def _insert(db: StateDB, **kw) -> int:
    return db.insert_report(
        report_type="asia",
        date_et="2026-10-09",
        time_pt="23:00",
        time_et="02:00",
        status="pending",
        created_at=datetime(2026, 10, 10, 6, tzinfo=timezone.utc),
        **kw,
    )


def test_fresh_db_has_data_source_column(tmp_state_db):
    db = StateDB(str(tmp_state_db))
    db.initialize()
    assert "data_source" in _cols(tmp_state_db)


def test_migration_from_old_schema_preserves_rows(tmp_state_db):
    conn = sqlite3.connect(str(tmp_state_db))
    conn.executescript(_OLD_REPORTS_DDL)
    conn.execute(
        "INSERT INTO reports (report_type, date, time_pt, time_et, status, created_at) "
        "VALUES ('eod','2026-05-04','14:00','17:00','success','2026-05-04T21:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    assert "data_source" not in _cols(tmp_state_db)

    db = StateDB(str(tmp_state_db))
    db.initialize()
    assert "data_source" in _cols(tmp_state_db)

    old_row = db.get_report_by_id(1)
    assert old_row["status"] == "success" and old_row["data_source"] is None
    rid = _insert(db, data_source="yfinance")
    assert db.get_report_by_id(rid)["data_source"] == "yfinance"
    assert db.already_generated_today("eod", "2026-05-04") is True


def test_double_initialize_is_safe(tmp_state_db):
    conn = sqlite3.connect(str(tmp_state_db))
    conn.executescript(_OLD_REPORTS_DDL)
    conn.close()
    db = StateDB(str(tmp_state_db))
    db.initialize()
    db.initialize()
    StateDB(str(tmp_state_db)).initialize()
    assert _cols(tmp_state_db).count("data_source") == 1


def test_insert_report_data_source_roundtrip_and_default(tmp_state_db):
    db = StateDB(str(tmp_state_db))
    db.initialize()
    yf_id = _insert(db, data_source="yfinance")
    ib_id = _insert(db, data_source="ib")
    legacy_id = _insert(db)
    assert db.get_report_by_id(yf_id)["data_source"] == "yfinance"
    assert db.get_report_by_id(ib_id)["data_source"] == "ib"
    assert db.get_report_by_id(legacy_id)["data_source"] is None
