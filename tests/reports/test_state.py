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
