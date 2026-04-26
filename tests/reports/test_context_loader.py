"""Tests for ContextLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.core.context_loader import (
    ContextLoader,
    ContractStatus,
    ReportContext,
)


def test_context_loader_missing_contract_returns_not_started(tmp_path):
    """When Contract.md doesn't exist, status is NOT_CREATED."""
    loader = ContextLoader(
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.NOT_CREATED
    assert ctx.contract_text is None
    assert ctx.lock_in_trades_done == 0


def test_context_loader_empty_contract_returns_skeletal(tmp_path):
    """When Contract.md exists but has no parseable content, status is SKELETAL."""
    contract = tmp_path / "Contract.md"
    contract.write_text("# Contract\n\n*not yet filled*\n")
    loader = ContextLoader(
        contract_path=contract,
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.SKELETAL
    assert ctx.contract_text == "# Contract\n\n*not yet filled*\n"


def test_context_loader_handles_missing_journal_db(tmp_path):
    """Missing journal DB → trades_done = 0, no error."""
    loader = ContextLoader(
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.lock_in_trades_done == 0
    assert ctx.lock_in_target == 30


import sqlite3


def _populate_minimal_journal_db(db_path: Path, trade_count: int) -> None:
    """Create a minimal journal DB with N closed trades for testing."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            symbol TEXT,
            side TEXT,
            entry_price TEXT,
            exit_price TEXT,
            stop_price TEXT,
            size INTEGER,
            entry_time TEXT,
            exit_time TEXT,
            signal_id TEXT,
            source TEXT,
            prop_firm TEXT,
            tags TEXT,
            extra TEXT
        );
    """)
    for i in range(trade_count):
        conn.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"t{i}", "MES", "long", "5240", "5246", "5232", 1,
             "2026-04-23T13:00:00", "2026-04-23T14:00:00",
             None, "manual", None, "[]", "{}"),
        )
    conn.commit()
    conn.close()


def test_context_loader_lock_in_active(tmp_path):
    """Contract.md filled + 7 trades done → LOCK_IN_ACTIVE."""
    contract = tmp_path / "Contract.md"
    contract.write_text(
        "# Contract\n\n## Setup\n- name: ORB long\n## R unit\n- amount: $25\n"
        + ("## Detail\n" * 30)  # padding to exceed skeletal threshold
    )
    db_path = tmp_path / "journal.db"
    _populate_minimal_journal_db(db_path, trade_count=7)

    loader = ContextLoader(contract_path=contract, journal_db_path=db_path)
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.LOCK_IN_ACTIVE
    assert ctx.lock_in_trades_done == 7


def test_context_loader_lock_in_complete(tmp_path):
    """30+ trades → LOCK_IN_COMPLETE."""
    contract = tmp_path / "Contract.md"
    contract.write_text(
        "# Contract\n\n## Setup\nfilled\n" + ("## Detail\n" * 30)
    )
    db_path = tmp_path / "journal.db"
    _populate_minimal_journal_db(db_path, trade_count=32)

    loader = ContextLoader(contract_path=contract, journal_db_path=db_path)
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.LOCK_IN_COMPLETE
    assert ctx.lock_in_trades_done == 32


def test_context_loader_lock_in_not_started(tmp_path):
    """Contract.md filled + 0 trades → LOCK_IN_NOT_STARTED."""
    contract = tmp_path / "Contract.md"
    contract.write_text(
        "# Contract\n\n## Setup\nfilled\n" + ("## Detail\n" * 30)
    )
    loader = ContextLoader(
        contract_path=contract,
        journal_db_path=tmp_path / "missing.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.LOCK_IN_NOT_STARTED
    assert ctx.lock_in_trades_done == 0
