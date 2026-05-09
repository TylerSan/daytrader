"""Unit tests for TodayTradesQuery."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.reports.eod.trades_query import TodayTradesQuery


def _init_journal_db(path: Path) -> sqlite3.Connection:
    """Create a minimal trades table matching the JournalTrade Pydantic shape."""
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE trades (
            id TEXT PRIMARY KEY,
            checklist_id TEXT,
            date TEXT,
            symbol TEXT,
            direction TEXT,
            setup_type TEXT,
            entry_time TEXT,
            entry_price REAL,
            stop_price REAL,
            target_price REAL,
            size INTEGER,
            exit_time TEXT,
            exit_price REAL,
            pnl_usd REAL,
            notes TEXT,
            violations TEXT,
            mode TEXT
        )"""
    )
    return conn


def _insert_trade(conn, **kwargs) -> None:
    defaults = {
        "id": "t1",
        "checklist_id": "c1",
        "date": "2026-05-04",
        "symbol": "MES",
        "direction": "short",
        "setup_type": "stacked_imbalance_reversal_at_level",
        "entry_time": "2026-05-04T13:30:00+00:00",
        "entry_price": 7272.75,
        "stop_price": 7273.25,
        "target_price": 7252.75,
        "size": 1,
        "exit_time": None,
        "exit_price": None,
        "pnl_usd": None,
        "notes": None,
        "violations": "[]",
        "mode": "real",
    }
    defaults.update(kwargs)
    conn.execute(
        """INSERT INTO trades (id, checklist_id, date, symbol, direction, setup_type,
            entry_time, entry_price, stop_price, target_price, size,
            exit_time, exit_price, pnl_usd, notes, violations, mode)
           VALUES (:id, :checklist_id, :date, :symbol, :direction, :setup_type,
            :entry_time, :entry_price, :stop_price, :target_price, :size,
            :exit_time, :exit_price, :pnl_usd, :notes, :violations, :mode)""",
        defaults,
    )
    conn.commit()


def test_returns_empty_for_no_trades(tmp_path):
    db = tmp_path / "journal.db"
    _init_journal_db(db).close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    assert trades == []


def test_returns_today_trades_only(tmp_path):
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t-today", date="2026-05-04")
    _insert_trade(conn, id="t-yesterday", date="2026-05-03")
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    assert len(trades) == 1
    assert trades[0]["id"] == "t-today"


def test_filters_to_real_mode_by_default(tmp_path):
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t-real", mode="real")
    _insert_trade(conn, id="t-dry", mode="dry_run")
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    ids = {t["id"] for t in trades}
    assert "t-real" in ids
    assert "t-dry" not in ids


def test_audit_summary_zero_trades(tmp_path):
    db = tmp_path / "journal.db"
    _init_journal_db(db).close()

    q = TodayTradesQuery(db)
    audit = q.audit_summary([])
    assert audit["count"] == 0
    assert audit["daily_r"] == 0.0
    assert audit["violations_total"] == 0
    assert audit["screenshots_complete"] == 0


def test_audit_summary_counts_violations(tmp_path):
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t1", violations='["ban_averaging_down"]', pnl_usd=-50.0)
    _insert_trade(conn, id="t2", violations="[]", pnl_usd=100.0)
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    audit = q.audit_summary(trades)
    assert audit["count"] == 2
    assert audit["violations_total"] == 1
    assert audit["daily_r"] == pytest.approx((-50.0 + 100.0) / 50.0)  # net 1R given R=$50


def test_audit_summary_screenshot_check_via_notes(tmp_path):
    """V1 placeholder: notes containing 'screenshots: yes' counts as
    §9-compliant (until JournalTrade model adds explicit fields)."""
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t1", notes="screenshots: yes")
    _insert_trade(conn, id="t2", notes="forgot to screenshot")
    _insert_trade(conn, id="t3", notes=None)
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    audit = q.audit_summary(trades)
    assert audit["screenshots_complete"] == 1


def test_handles_missing_db_gracefully(tmp_path):
    """If journal.db doesn't exist, return empty list (not a crash)."""
    q = TodayTradesQuery(tmp_path / "nonexistent.db")
    trades = q.trades_for_date("2026-05-04")
    assert trades == []
    audit = q.audit_summary(trades)
    assert audit["count"] == 0
