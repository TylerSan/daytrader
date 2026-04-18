"""Tests for dry-run service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.checklist import ChecklistInput, ChecklistService
from daytrader.journal.circuit import CircuitService
from daytrader.journal.dry_run import (
    DryRunStartInput, DryRunEndInput, DryRunService,
)
from daytrader.journal.models import (
    Contract, DryRunOutcome, TradeMode, TradeSide,
)
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


def _checklist_id(repo, now) -> str:
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(
        ChecklistInput(
            mode=TradeMode.DRY_RUN, symbol="MES",
            direction=TradeSide.LONG, setup_type="orb",
            entry_price=Decimal("5000"), stop_price=Decimal("4995"),
            target_price=Decimal("5010"), size=1, stop_at_broker=True,
        ),
        now=now,
    )
    return result.checklist_id


def test_start_and_end_dry_run_target(repo):
    now = _dt("2026-04-20T13:35:00")
    cid = _checklist_id(repo, now)
    dr_svc = DryRunService(repo)
    start = dr_svc.start(DryRunStartInput(
        checklist_id=cid, symbol="MES", direction=TradeSide.LONG,
        setup_type="orb",
        entry=Decimal("5000"), stop=Decimal("4995"), target=Decimal("5010"),
        size=1,
    ), now=now)
    assert start.dry_run_id is not None

    dr_svc.end(DryRunEndInput(
        dry_run_id=start.dry_run_id,
        outcome=DryRunOutcome.TARGET_HIT,
        outcome_time=_dt("2026-04-20T14:00:00"),
        outcome_price=Decimal("5010"),
        notes="target hit",
    ))
    dr = [d for d in repo.list_dry_runs() if d.id == start.dry_run_id][0]
    assert dr.outcome == DryRunOutcome.TARGET_HIT
    assert dr.hypothetical_r_multiple == Decimal("2")


def test_end_dry_run_stop(repo):
    now = _dt("2026-04-20T13:35:00")
    cid = _checklist_id(repo, now)
    dr_svc = DryRunService(repo)
    start = dr_svc.start(DryRunStartInput(
        checklist_id=cid, symbol="MES", direction=TradeSide.LONG,
        setup_type="orb", entry=Decimal("5000"),
        stop=Decimal("4995"), target=Decimal("5010"), size=1,
    ), now=now)
    dr_svc.end(DryRunEndInput(
        dry_run_id=start.dry_run_id,
        outcome=DryRunOutcome.STOP_HIT,
        outcome_time=_dt("2026-04-20T13:45:00"),
        outcome_price=Decimal("4995"),
    ))
    dr = [d for d in repo.list_dry_runs() if d.id == start.dry_run_id][0]
    assert dr.hypothetical_r_multiple == Decimal("-1")
