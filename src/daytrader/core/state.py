"""SQLite state DB for the reports system.

Stores: today's plans, report generation history, news dedup,
failure log, lock-in status snapshots, bar cache.

Separate from `core/db.py` (signals/trades) to avoid coupling.

See spec §4.4 for full schema.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
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

CREATE TABLE IF NOT EXISTS plan_retrospective_daily (
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

    # --- reports table ---

    def insert_report(
        self,
        report_type: str,
        date_et: str,
        time_pt: str,
        time_et: str,
        status: str,
        created_at: datetime,
    ) -> int:
        """Insert a pending/in-progress report row, return its id."""
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO reports
               (report_type, date, time_pt, time_et, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (report_type, date_et, time_pt, time_et, status,
             created_at.isoformat()),
        )
        conn.commit()
        return cur.lastrowid

    def get_report_by_id(self, report_id: int) -> sqlite3.Row | None:
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()

    def update_report_status(
        self,
        report_id: int,
        status: str,
        obsidian_path: str | None = None,
        pdf_path: str | None = None,
        telegram_msg_ids: str | None = None,
        failure_reason: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
        cache_hit_rate: float | None = None,
        duration_seconds: float | None = None,
        estimated_cost_usd: float | None = None,
    ) -> None:
        """Update status and metrics for an existing report row."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE reports SET
                 status = ?,
                 obsidian_path = COALESCE(?, obsidian_path),
                 pdf_path = COALESCE(?, pdf_path),
                 telegram_msg_ids = COALESCE(?, telegram_msg_ids),
                 failure_reason = COALESCE(?, failure_reason),
                 tokens_input = COALESCE(?, tokens_input),
                 tokens_output = COALESCE(?, tokens_output),
                 cache_hit_rate = COALESCE(?, cache_hit_rate),
                 duration_seconds = COALESCE(?, duration_seconds),
                 estimated_cost_usd = COALESCE(?, estimated_cost_usd)
               WHERE id = ?""",
            (status, obsidian_path, pdf_path, telegram_msg_ids,
             failure_reason, tokens_input, tokens_output, cache_hit_rate,
             duration_seconds, estimated_cost_usd, report_id),
        )
        conn.commit()

    # --- plans table ---

    def save_plan(
        self,
        date_et: str,
        instrument: str,
        setup_name: str,
        direction: str,
        entry: float,
        stop: float,
        target: float,
        r_unit_dollars: float,
        invalidations: list[str],
        raw_plan_text: str,
        source_report_path: str,
        created_at: datetime,
    ) -> None:
        """Insert or replace a plan for (date, instrument)."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO plans
               (date, instrument, setup_name, direction, entry, stop, target,
                r_unit_dollars, invalidations, raw_plan_text,
                created_at, source_report_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date_et, instrument, setup_name, direction,
             entry, stop, target, r_unit_dollars,
             json.dumps(invalidations), raw_plan_text,
             created_at.isoformat(), source_report_path),
        )
        conn.commit()

    def get_plan_for_date(
        self, date_et: str, instrument: str
    ) -> sqlite3.Row | None:
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM plans WHERE date = ? AND instrument = ?",
            (date_et, instrument),
        ).fetchone()

    # --- news_seen table ---

    def add_news(
        self,
        source: str,
        external_id: str,
        url: str | None,
        title: str | None,
        published_at: datetime | None,
        first_seen_at: datetime,
        impact_tag: str | None = None,
    ) -> bool:
        """Insert news row. Returns True if new, False if (source, external_id)
        already present."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT 1 FROM news_seen WHERE source = ? AND external_id = ? LIMIT 1",
            (source, external_id),
        ).fetchone()
        if existing is not None:
            return False
        conn.execute(
            """INSERT INTO news_seen
               (source, external_id, url, title, published_at,
                first_seen_at, impact_tag)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source, external_id, url, title,
             published_at.isoformat() if published_at else None,
             first_seen_at.isoformat(), impact_tag),
        )
        conn.commit()
        return True

    # --- failures table ---

    def log_failure(
        self,
        report_type: str,
        scheduled_at: datetime,
        failure_stage: str,
        failure_reason: str,
        retry_count: int,
    ) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO failures
               (report_type, scheduled_at, failure_stage,
                failure_reason, retry_count)
               VALUES (?, ?, ?, ?, ?)""",
            (report_type, scheduled_at.isoformat(),
             failure_stage, failure_reason, retry_count),
        )
        conn.commit()
        return cur.lastrowid

    def list_unresolved_failures(self) -> list[sqlite3.Row]:
        conn = self._get_conn()
        return list(conn.execute(
            "SELECT * FROM failures WHERE resolved_at IS NULL ORDER BY id"
        ).fetchall())

    def resolve_failure(self, failure_id: int, resolved_at: datetime) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE failures SET resolved_at = ? WHERE id = ?",
            (resolved_at.isoformat(), failure_id),
        )
        conn.commit()

    # --- lock_in_status table ---

    def save_lock_in_snapshot(
        self,
        snapshot_at: datetime,
        trades_done: int,
        trades_target: int,
        cumulative_r: float | None,
        last_trade_date: str | None,
        last_trade_r: float | None,
        streak: str | None,
        breakdown: dict[str, int],
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO lock_in_status
               (snapshot_at, trades_done, trades_target, cumulative_r,
                last_trade_date, last_trade_r, streak,
                breakdown_mes, breakdown_mnq, breakdown_mgc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_at.isoformat(),
                trades_done,
                trades_target,
                cumulative_r,
                last_trade_date,
                last_trade_r,
                streak,
                breakdown.get("MES", 0),
                breakdown.get("MNQ", 0),
                breakdown.get("MGC", 0),
            ),
        )
        conn.commit()

    def latest_lock_in_snapshot(self) -> sqlite3.Row | None:
        conn = self._get_conn()
        return conn.execute(
            "SELECT * FROM lock_in_status ORDER BY snapshot_at DESC LIMIT 1"
        ).fetchone()

    # --- bar_cache table ---

    def cache_bars(
        self,
        bars: list[tuple[str, str, str, float, float, float, float, float]],
    ) -> None:
        """Insert/replace cached bars. Each tuple:
        (instrument, timeframe, bar_time_iso, open, high, low, close, volume)
        """
        conn = self._get_conn()
        conn.executemany(
            """INSERT OR REPLACE INTO bar_cache
               (instrument, timeframe, bar_time, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            bars,
        )
        conn.commit()

    def load_cached_bars(
        self, instrument: str, timeframe: str
    ) -> list[sqlite3.Row]:
        conn = self._get_conn()
        return list(conn.execute(
            """SELECT * FROM bar_cache
               WHERE instrument = ? AND timeframe = ?
               ORDER BY bar_time ASC""",
            (instrument, timeframe),
        ).fetchall())

    def already_generated_today(self, report_type: str, date_et: str) -> bool:
        """Idempotency check: did a successful report of this type run today?"""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT 1 FROM reports
               WHERE report_type = ? AND date = ? AND status = 'success'
               LIMIT 1""",
            (report_type, date_et),
        ).fetchone()
        return row is not None
