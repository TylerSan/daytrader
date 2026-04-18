"""Tests for CircuitService."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.circuit import CircuitDecision, CircuitService
from daytrader.journal.models import CircuitState, Contract
from daytrader.journal.repository import JournalRepository


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _contract(**kw) -> Contract:
    defaults = dict(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    )
    defaults.update(kw)
    return Contract(**defaults)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    r.save_contract(_contract())
    return r


def test_allows_trade_when_no_state(repo):
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:35:00"))
    assert d.allowed is True


def test_blocks_when_daily_limit_hit(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        realized_r=Decimal("-3"),
        no_trade_flag=True,
        lock_reason="daily_loss_limit_hit",
    ))
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T14:00:00"))
    assert d.allowed is False
    assert d.reason == "daily_loss_limit_hit"


def test_blocks_in_cooloff_after_stop(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        trade_count=1,
        last_stop_time=_dt("2026-04-20T13:30:00"),
    ))
    svc = CircuitService(repo)
    # 15 minutes after stop → still cool-off (requires 30)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:45:00"))
    assert d.allowed is False
    assert d.reason == "within_cooloff"


def test_allows_after_cooloff(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        trade_count=1,
        last_stop_time=_dt("2026-04-20T13:00:00"),
    ))
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:35:00"))
    assert d.allowed is True


def test_blocks_when_max_trades_reached(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        trade_count=5,
    ))
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T15:00:00"))
    assert d.allowed is False
    assert d.reason == "max_trades_per_day_reached"


def test_register_trade_outcome_updates_state(repo):
    svc = CircuitService(repo)
    svc.register_trade_outcome(
        on=date(2026, 4, 20),
        r_multiple=Decimal("-1"),
        pnl_usd=Decimal("-50"),
        was_stop=True,
        now=_dt("2026-04-20T13:40:00"),
    )
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.realized_r == Decimal("-1")
    assert state.trade_count == 1
    assert state.last_stop_time is not None
    assert state.no_trade_flag is False  # -1R not at limit


def test_register_stop_at_limit_sets_lock(repo):
    svc = CircuitService(repo)
    # cumulative hit -3R → should lock
    svc.register_trade_outcome(
        on=date(2026, 4, 20),
        r_multiple=Decimal("-3"),
        pnl_usd=Decimal("-150"),
        was_stop=True,
        now=_dt("2026-04-20T14:00:00"),
    )
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.no_trade_flag is True
    assert state.lock_reason == "daily_loss_limit_hit"


def test_consecutive_stops_day_end(repo):
    """2 consecutive stops ends day even if under -3R."""
    svc = CircuitService(repo)
    # First stop
    svc.register_trade_outcome(
        on=date(2026, 4, 20), r_multiple=Decimal("-1"),
        pnl_usd=Decimal("-50"), was_stop=True,
        now=_dt("2026-04-20T13:30:00"),
    )
    # Pre-populate a corresponding closed losing trade so list_trades_on_date sees it
    from daytrader.journal.models import (
        Checklist, ChecklistItems, JournalTrade, TradeMode, TradeSide,
    )
    items = ChecklistItems(
        item_stop_at_broker=True, item_within_r_limit=True,
        item_matches_locked_setup=True, item_within_daily_r=True,
        item_past_cooloff=True,
    )
    c = Checklist(
        id="c01", timestamp=_dt("2026-04-20T13:00:00"),
        mode=TradeMode.REAL, contract_version=1,
        items=items, passed=True,
    )
    repo.save_checklist(c)
    t = JournalTrade(
        id="t01", checklist_id="c01", date=date(2026, 4, 20),
        symbol="MES", direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:15:00"),
        entry_price=Decimal("5000"), stop_price=Decimal("4995"),
        target_price=Decimal("5010"), size=1,
    )
    repo.save_trade(t)
    repo.close_trade(
        trade_id="t01", exit_time=_dt("2026-04-20T13:30:00"),
        exit_price=Decimal("4995"), pnl_usd=Decimal("-50"),
    )

    # Second stop — heuristic should now see prior losing trade and lock
    svc.register_trade_outcome(
        on=date(2026, 4, 20), r_multiple=Decimal("-1"),
        pnl_usd=Decimal("-50"), was_stop=True,
        now=_dt("2026-04-20T14:30:00"),
    )
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.no_trade_flag is True
    assert state.lock_reason == "consecutive_stops"


def test_default_lock_when_state_missing_or_corrupt(repo, tmp_path):
    """If state file unreadable, must default to no-trade (fail-safe)."""
    svc = CircuitService(repo)
    # simulate corrupt: delete DB mid-flight
    broken = JournalRepository(str(tmp_path / "nonexistent.db"))
    # without initialize, any query fails
    svc_broken = CircuitService(broken)
    d = svc_broken.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:00:00"))
    assert d.allowed is False
    assert d.reason == "circuit_state_unavailable"
