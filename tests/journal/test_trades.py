"""Tests for post-trade service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.checklist import ChecklistInput, ChecklistService
from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import Contract, TradeMode, TradeSide
from daytrader.journal.repository import JournalRepository
from daytrader.journal.trades import PostTradeInput, PostTradeService


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


def _open_trade(repo) -> str:
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(
        ChecklistInput(
            mode=TradeMode.REAL, symbol="MES", direction=TradeSide.LONG,
            setup_type="orb",
            entry_price=Decimal("5000"), stop_price=Decimal("4995"),
            target_price=Decimal("5010"), size=1, stop_at_broker=True,
        ),
        now=_dt("2026-04-20T13:35:00"),
    )
    return result.trade_id


def test_close_trade_at_target(repo):
    tid = _open_trade(repo)
    pt = PostTradeService(repo, CircuitService(repo))
    pt.close(PostTradeInput(
        trade_id=tid, exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5010"),
        was_stop=False,
        notes="target hit",
    ))
    t = repo.get_trade(tid)
    assert t.exit_price == Decimal("5010")
    assert t.pnl_usd == Decimal("50")  # (5010-5000)*5 = $50 on MES
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.trade_count == 1
    assert state.realized_r == Decimal("2")  # $50 / $25 risk = 2R


def test_close_trade_at_stop(repo):
    tid = _open_trade(repo)
    pt = PostTradeService(repo, CircuitService(repo))
    pt.close(PostTradeInput(
        trade_id=tid, exit_time=_dt("2026-04-20T13:45:00"),
        exit_price=Decimal("4995"),
        was_stop=True,
    ))
    t = repo.get_trade(tid)
    assert t.pnl_usd == Decimal("-25")
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.last_stop_time is not None
    assert state.realized_r == Decimal("-1")


def test_close_nonexistent_raises(repo):
    pt = PostTradeService(repo, CircuitService(repo))
    with pytest.raises(ValueError):
        pt.close(PostTradeInput(
            trade_id="nonexistent",
            exit_time=_dt("2026-04-20T14:00:00"),
            exit_price=Decimal("5010"),
            was_stop=False,
        ))
