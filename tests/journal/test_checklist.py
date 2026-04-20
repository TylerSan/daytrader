"""Tests for ChecklistService (pre-trade orchestration)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.checklist import (
    ChecklistInput,
    ChecklistResult,
    ChecklistService,
)
from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import Contract, TradeMode, TradeSide
from daytrader.journal.repository import JournalRepository


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    r.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    return r


def _base_input() -> ChecklistInput:
    return ChecklistInput(
        mode=TradeMode.REAL,
        symbol="MES",
        direction=TradeSide.LONG,
        setup_type="orb",
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
        stop_at_broker=True,
    )


def test_all_pass_creates_trade(repo):
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(_base_input(), now=_dt("2026-04-20T13:35:00"))
    assert result.passed is True
    assert result.trade_id is not None
    assert repo.get_trade(result.trade_id) is not None


def test_stop_not_at_broker_blocks(repo):
    svc = ChecklistService(repo, CircuitService(repo))
    inp = _base_input()
    inp.stop_at_broker = False
    result = svc.run(inp, now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert result.trade_id is None
    assert "stop_at_broker" in (result.failure_reason or "")


def test_wrong_setup_blocks(repo):
    svc = ChecklistService(repo, CircuitService(repo))
    inp = _base_input()
    inp.setup_type = "some_other_setup"
    result = svc.run(inp, now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert "locked_setup" in (result.failure_reason or "")


def test_stop_distance_too_large_blocks(repo):
    """Risk exceeds 1R ($50) → block."""
    svc = ChecklistService(repo, CircuitService(repo))
    inp = _base_input()
    inp.stop_price = Decimal("4900")  # $500 risk on MES ($5/point)
    result = svc.run(inp, now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert "r_limit" in (result.failure_reason or "")


def test_circuit_locked_short_circuits(repo):
    from daytrader.journal.models import CircuitState
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        no_trade_flag=True, lock_reason="daily_loss_limit_hit",
    ))
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(_base_input(), now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert "daily_loss_limit_hit" in (result.failure_reason or "")
