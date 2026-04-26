"""SQLite state DB for the reports system.

Stores: today's plans, report generation history, news dedup,
failure log, lock-in status snapshots, bar cache.

Separate from `core/db.py` (signals/trades) to avoid coupling.

See spec §4.4 for full schema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    date TEXT NOT NULL,
    instrument TEXT NOT NULL,
    setup_name TEXT,
    direction TEXT,
    entry REAL,
    stop REAL,
    target REAL,
    r_unit_dollars REAL,
    invalidations TEXT,
    raw_plan_text TEXT,
    created_at TEXT NOT NULL,
    source_report_path TEXT,
    PRIMARY KEY (date, instrument)
);

CREATE TABLE IF NOT EXISTS reports (
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

CREATE INDEX IF NOT EXISTS idx_reports_date_type ON reports(date, report_type);

CREATE TABLE IF NOT EXISTS news_seen (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT,
    title TEXT,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    impact_tag TEXT,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    failure_stage TEXT NOT NULL,
    failure_reason TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS lock_in_status (
    snapshot_at TEXT PRIMARY KEY,
    trades_done INTEGER NOT NULL,
    trades_target INTEGER NOT NULL,
    cumulative_r REAL,
    last_trade_date TEXT,
    last_trade_r REAL,
    streak TEXT,
    breakdown_mes INTEGER,
    breakdown_mnq INTEGER,
    breakdown_mgc INTEGER
);

CREATE TABLE IF NOT EXISTS bar_cache (
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (instrument, timeframe, bar_time)
);
"""


class StateDB:
    """SQLite wrapper for reports system state."""

    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create all tables. Idempotent (uses IF NOT EXISTS)."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
