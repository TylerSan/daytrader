"""Tests for integrity auditor."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.auditor import Auditor
from daytrader.journal.models import (
    Checklist, ChecklistItems, CircuitState, Contract,
    JournalTrade, TradeMode, TradeSide,
)
from daytrader.journal.repository import JournalRepository


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    return r


def test_empty_db_no_issues(repo):
    audit = Auditor(repo)
    issues = audit.run_all()
    assert issues == []


def test_circuit_lock_inconsistency_detected(repo):
    # Realized -3R but flag=false → inconsistent
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"), daily_loss_limit_r=3,
        daily_loss_warning_r=2, max_trades_per_day=5,
        stop_cooloff_minutes=30,
    ))
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        realized_r=Decimal("-3.5"),
        no_trade_flag=False,  # <-- WRONG
    ))
    audit = Auditor(repo)
    issues = audit.run_all()
    assert any("circuit" in i.kind for i in issues)
