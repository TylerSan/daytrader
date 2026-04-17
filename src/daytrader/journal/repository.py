"""JournalRepository — SQLite persistence for journal subsystem."""

from __future__ import annotations

import json
import sqlite3
from datetime import date as date_type, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from daytrader.journal.models import (
    Checklist, ChecklistItems, CircuitState, Contract,
    DryRun, DryRunOutcome, JournalTrade, SetupVerdict, TradeMode, TradeSide,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_contract (
    version INTEGER PRIMARY KEY,
    signed_date TEXT NOT NULL,
    active INTEGER NOT NULL,
    r_unit_usd TEXT NOT NULL,
    daily_loss_limit_r INTEGER NOT NULL,
    daily_loss_warning_r INTEGER NOT NULL,
    max_trades_per_day INTEGER NOT NULL,
    stop_cooloff_minutes INTEGER NOT NULL,
    locked_setup_name TEXT,
    locked_setup_file TEXT,
    lock_in_min_trades INTEGER NOT NULL DEFAULT 30,
    backup_setup_name TEXT,
    backup_setup_file TEXT,
    backup_setup_status TEXT NOT NULL DEFAULT 'benched'
);

CREATE TABLE IF NOT EXISTS journal_checklists (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('real','dry_run')),
    contract_version INTEGER NOT NULL,
    item_stop_at_broker INTEGER NOT NULL,
    item_within_r_limit INTEGER NOT NULL,
    item_matches_locked_setup INTEGER NOT NULL,
    item_within_daily_r INTEGER NOT NULL,
    item_past_cooloff INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    failure_reason TEXT
);

CREATE TABLE IF NOT EXISTS journal_trades (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol IN ('MES','MNQ','MGC')),
    direction TEXT NOT NULL CHECK (direction IN ('long','short')),
    setup_type TEXT NOT NULL,
    entry_time TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    stop_price TEXT NOT NULL,
    target_price TEXT NOT NULL,
    size INTEGER NOT NULL,
    exit_time TEXT,
    exit_price TEXT,
    pnl_usd TEXT,
    notes TEXT,
    violations TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (checklist_id) REFERENCES journal_checklists(id)
);

CREATE TABLE IF NOT EXISTS journal_dry_runs (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    identified_time TEXT NOT NULL,
    hypothetical_entry TEXT NOT NULL,
    hypothetical_stop TEXT NOT NULL,
    hypothetical_target TEXT NOT NULL,
    hypothetical_size INTEGER NOT NULL,
    outcome TEXT CHECK (outcome IN ('target_hit','stop_hit','rule_exit','no_trigger')),
    outcome_time TEXT,
    outcome_price TEXT,
    hypothetical_r_multiple TEXT,
    notes TEXT,
    FOREIGN KEY (checklist_id) REFERENCES journal_checklists(id)
);

CREATE TABLE IF NOT EXISTS journal_circuit_state (
    date TEXT PRIMARY KEY,
    realized_r TEXT NOT NULL DEFAULT '0',
    realized_usd TEXT NOT NULL DEFAULT '0',
    trade_count INTEGER NOT NULL DEFAULT 0,
    no_trade_flag INTEGER NOT NULL DEFAULT 0,
    lock_reason TEXT,
    last_stop_time TEXT
);

CREATE TABLE IF NOT EXISTS journal_setup_verdicts (
    setup_name TEXT NOT NULL,
    setup_version TEXT NOT NULL,
    run_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    data_window_days INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_r REAL NOT NULL,
    passed INTEGER NOT NULL,
    PRIMARY KEY (setup_name, setup_version, run_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_journal_trades_date ON journal_trades(date);
CREATE INDEX IF NOT EXISTS idx_journal_dry_runs_date ON journal_dry_runs(date);
"""


def _to_int(b: bool) -> int:
    return 1 if b else 0


def _to_bool(i: int) -> bool:
    return bool(i)


class JournalRepository:
    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def list_tables(self) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r["name"] for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Contract ---

    def save_contract(self, c: Contract) -> None:
        conn = self._get_conn()
        if c.active:
            conn.execute("UPDATE journal_contract SET active = 0")
        conn.execute(
            """INSERT OR REPLACE INTO journal_contract
               (version, signed_date, active, r_unit_usd,
                daily_loss_limit_r, daily_loss_warning_r, max_trades_per_day,
                stop_cooloff_minutes, locked_setup_name, locked_setup_file,
                lock_in_min_trades, backup_setup_name, backup_setup_file,
                backup_setup_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.version, c.signed_date.isoformat(), _to_int(c.active),
             str(c.r_unit_usd), c.daily_loss_limit_r, c.daily_loss_warning_r,
             c.max_trades_per_day, c.stop_cooloff_minutes,
             c.locked_setup_name, c.locked_setup_file, c.lock_in_min_trades,
             c.backup_setup_name, c.backup_setup_file, c.backup_setup_status),
        )
        conn.commit()

    def get_active_contract(self) -> Optional[Contract]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_contract WHERE active = 1 "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Contract(
            version=row["version"],
            signed_date=date_type.fromisoformat(row["signed_date"]),
            active=_to_bool(row["active"]),
            r_unit_usd=Decimal(row["r_unit_usd"]),
            daily_loss_limit_r=row["daily_loss_limit_r"],
            daily_loss_warning_r=row["daily_loss_warning_r"],
            max_trades_per_day=row["max_trades_per_day"],
            stop_cooloff_minutes=row["stop_cooloff_minutes"],
            locked_setup_name=row["locked_setup_name"],
            locked_setup_file=row["locked_setup_file"],
            lock_in_min_trades=row["lock_in_min_trades"],
            backup_setup_name=row["backup_setup_name"],
            backup_setup_file=row["backup_setup_file"],
            backup_setup_status=row["backup_setup_status"],
        )

    # --- Checklists ---

    def save_checklist(self, c: Checklist) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO journal_checklists
               (id, timestamp, mode, contract_version,
                item_stop_at_broker, item_within_r_limit,
                item_matches_locked_setup, item_within_daily_r, item_past_cooloff,
                passed, failure_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (c.id, c.timestamp.isoformat(),
             c.mode.value if hasattr(c.mode, "value") else c.mode,
             c.contract_version,
             _to_int(c.items.item_stop_at_broker),
             _to_int(c.items.item_within_r_limit),
             _to_int(c.items.item_matches_locked_setup),
             _to_int(c.items.item_within_daily_r),
             _to_int(c.items.item_past_cooloff),
             _to_int(c.passed), c.failure_reason),
        )
        conn.commit()

    def get_checklist(self, cid: str) -> Optional[Checklist]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_checklists WHERE id = ?", (cid,)
        ).fetchone()
        if not row:
            return None
        return Checklist(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            mode=TradeMode(row["mode"]),
            contract_version=row["contract_version"],
            items=ChecklistItems(
                item_stop_at_broker=_to_bool(row["item_stop_at_broker"]),
                item_within_r_limit=_to_bool(row["item_within_r_limit"]),
                item_matches_locked_setup=_to_bool(row["item_matches_locked_setup"]),
                item_within_daily_r=_to_bool(row["item_within_daily_r"]),
                item_past_cooloff=_to_bool(row["item_past_cooloff"]),
            ),
            passed=_to_bool(row["passed"]),
            failure_reason=row["failure_reason"],
        )

    # --- Trades ---

    def save_trade(self, t: JournalTrade) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO journal_trades
               (id, checklist_id, date, symbol, direction, setup_type,
                entry_time, entry_price, stop_price, target_price, size,
                exit_time, exit_price, pnl_usd, notes, violations)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t.id, t.checklist_id, t.date.isoformat(), t.symbol,
             t.direction.value, t.setup_type,
             t.entry_time.isoformat(), str(t.entry_price),
             str(t.stop_price), str(t.target_price), t.size,
             t.exit_time.isoformat() if t.exit_time else None,
             str(t.exit_price) if t.exit_price is not None else None,
             str(t.pnl_usd) if t.pnl_usd is not None else None,
             t.notes, json.dumps(t.violations)),
        )
        conn.commit()

    def close_trade(
        self, trade_id: str, exit_time: datetime, exit_price: Decimal,
        pnl_usd: Decimal, notes: Optional[str] = None,
        violations: Optional[list[str]] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE journal_trades
               SET exit_time=?, exit_price=?, pnl_usd=?,
                   notes=COALESCE(?, notes), violations=?
               WHERE id=?""",
            (exit_time.isoformat(), str(exit_price), str(pnl_usd),
             notes, json.dumps(violations or []), trade_id),
        )
        conn.commit()

    def get_trade(self, tid: str) -> Optional[JournalTrade]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_trades WHERE id = ?", (tid,)
        ).fetchone()
        if not row:
            return None
        return JournalTrade(
            id=row["id"], checklist_id=row["checklist_id"],
            date=date_type.fromisoformat(row["date"]),
            symbol=row["symbol"], direction=TradeSide(row["direction"]),
            setup_type=row["setup_type"],
            entry_time=datetime.fromisoformat(row["entry_time"]),
            entry_price=Decimal(row["entry_price"]),
            stop_price=Decimal(row["stop_price"]),
            target_price=Decimal(row["target_price"]),
            size=row["size"],
            exit_time=datetime.fromisoformat(row["exit_time"]) if row["exit_time"] else None,
            exit_price=Decimal(row["exit_price"]) if row["exit_price"] else None,
            pnl_usd=Decimal(row["pnl_usd"]) if row["pnl_usd"] else None,
            notes=row["notes"],
            violations=json.loads(row["violations"] or "[]"),
        )

    def list_trades_on_date(self, d: date_type) -> list[JournalTrade]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id FROM journal_trades WHERE date = ? ORDER BY entry_time",
            (d.isoformat(),),
        ).fetchall()
        return [self.get_trade(r["id"]) for r in rows]

    # --- Dry runs ---

    def save_dry_run(self, d: DryRun) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO journal_dry_runs
               (id, checklist_id, date, symbol, direction, setup_type,
                identified_time, hypothetical_entry, hypothetical_stop,
                hypothetical_target, hypothetical_size,
                outcome, outcome_time, outcome_price,
                hypothetical_r_multiple, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.id, d.checklist_id, d.date.isoformat(), d.symbol,
             d.direction.value, d.setup_type,
             d.identified_time.isoformat(),
             str(d.hypothetical_entry), str(d.hypothetical_stop),
             str(d.hypothetical_target), d.hypothetical_size,
             d.outcome.value if d.outcome else None,
             d.outcome_time.isoformat() if d.outcome_time else None,
             str(d.outcome_price) if d.outcome_price else None,
             str(d.hypothetical_r_multiple) if d.hypothetical_r_multiple else None,
             d.notes),
        )
        conn.commit()

    def close_dry_run(
        self, dry_run_id: str, outcome: DryRunOutcome,
        outcome_time: datetime, outcome_price: Decimal,
        r_multiple: Decimal, notes: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE journal_dry_runs
               SET outcome=?, outcome_time=?, outcome_price=?,
                   hypothetical_r_multiple=?, notes=COALESCE(?, notes)
               WHERE id=?""",
            (outcome.value, outcome_time.isoformat(), str(outcome_price),
             str(r_multiple), notes, dry_run_id),
        )
        conn.commit()

    def list_dry_runs(self, only_with_outcome: bool = False) -> list[DryRun]:
        conn = self._get_conn()
        q = "SELECT * FROM journal_dry_runs"
        if only_with_outcome:
            q += " WHERE outcome IS NOT NULL"
        q += " ORDER BY identified_time"
        rows = conn.execute(q).fetchall()
        out = []
        for row in rows:
            out.append(DryRun(
                id=row["id"], checklist_id=row["checklist_id"],
                date=date_type.fromisoformat(row["date"]),
                symbol=row["symbol"], direction=TradeSide(row["direction"]),
                setup_type=row["setup_type"],
                identified_time=datetime.fromisoformat(row["identified_time"]),
                hypothetical_entry=Decimal(row["hypothetical_entry"]),
                hypothetical_stop=Decimal(row["hypothetical_stop"]),
                hypothetical_target=Decimal(row["hypothetical_target"]),
                hypothetical_size=row["hypothetical_size"],
                outcome=DryRunOutcome(row["outcome"]) if row["outcome"] else None,
                outcome_time=datetime.fromisoformat(row["outcome_time"]) if row["outcome_time"] else None,
                outcome_price=Decimal(row["outcome_price"]) if row["outcome_price"] else None,
                hypothetical_r_multiple=Decimal(row["hypothetical_r_multiple"]) if row["hypothetical_r_multiple"] else None,
                notes=row["notes"],
            ))
        return out

    # --- Circuit state ---

    def get_circuit_state(self, d: date_type) -> CircuitState:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_circuit_state WHERE date = ?",
            (d.isoformat(),),
        ).fetchone()
        if not row:
            return CircuitState(date=d)
        return CircuitState(
            date=date_type.fromisoformat(row["date"]),
            realized_r=Decimal(row["realized_r"]),
            realized_usd=Decimal(row["realized_usd"]),
            trade_count=row["trade_count"],
            no_trade_flag=_to_bool(row["no_trade_flag"]),
            lock_reason=row["lock_reason"],
            last_stop_time=datetime.fromisoformat(row["last_stop_time"]) if row["last_stop_time"] else None,
        )

    def upsert_circuit_state(self, s: CircuitState) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO journal_circuit_state
               (date, realized_r, realized_usd, trade_count,
                no_trade_flag, lock_reason, last_stop_time)
               VALUES (?,?,?,?,?,?,?)""",
            (s.date.isoformat(), str(s.realized_r), str(s.realized_usd),
             s.trade_count, _to_int(s.no_trade_flag),
             s.lock_reason,
             s.last_stop_time.isoformat() if s.last_stop_time else None),
        )
        conn.commit()

    # --- Setup verdicts ---

    def save_setup_verdict(self, v: SetupVerdict) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO journal_setup_verdicts
               (setup_name, setup_version, run_date, symbol,
                data_window_days, n_samples, win_rate, avg_r, passed)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (v.setup_name, v.setup_version, v.run_date.isoformat(),
             v.symbol, v.data_window_days, v.n_samples,
             v.win_rate, v.avg_r, _to_int(v.passed)),
        )
        conn.commit()

    def list_setup_verdicts(
        self, setup_name: Optional[str] = None
    ) -> list[SetupVerdict]:
        conn = self._get_conn()
        if setup_name:
            rows = conn.execute(
                "SELECT * FROM journal_setup_verdicts WHERE setup_name = ? "
                "ORDER BY run_date DESC",
                (setup_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM journal_setup_verdicts ORDER BY run_date DESC"
            ).fetchall()
        return [
            SetupVerdict(
                setup_name=r["setup_name"], setup_version=r["setup_version"],
                run_date=date_type.fromisoformat(r["run_date"]),
                symbol=r["symbol"], data_window_days=r["data_window_days"],
                n_samples=r["n_samples"], win_rate=r["win_rate"],
                avg_r=r["avg_r"], passed=_to_bool(r["passed"]),
            )
            for r in rows
        ]
