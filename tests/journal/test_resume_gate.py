"""Tests for resume-gate service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.models import (
    Contract, DryRunOutcome, SetupVerdict,
)
from daytrader.journal.repository import JournalRepository
from daytrader.journal.resume_gate import ResumeGateService


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    return r


def test_fail_when_no_contract(repo):
    svc = ResumeGateService(repo)
    res = svc.check()
    assert res.passed is False
    assert any("contract" in f.reason for f in res.failed_gates)


def test_fail_when_no_verdict(repo):
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    svc = ResumeGateService(repo)
    res = svc.check()
    assert res.passed is False
    assert any("sanity" in f.reason.lower() for f in res.failed_gates)


def test_pass_when_all_green(repo, tmp_path):
    # contract
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    # verdict
    repo.save_setup_verdict(SetupVerdict(
        setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 25), symbol="MES",
        data_window_days=90,
        n_samples=40, win_rate=0.5, avg_r=0.1, passed=True,
    ))
    # 20+ dry runs, all outcome, 100% compliance
    from daytrader.journal.models import (
        Checklist, ChecklistItems, DryRun, TradeMode, TradeSide,
    )
    for i in range(22):
        items = ChecklistItems(
            item_stop_at_broker=True, item_within_r_limit=True,
            item_matches_locked_setup=True, item_within_daily_r=True,
            item_past_cooloff=True,
        )
        c = Checklist(
            id=f"c{i:02d}",
            timestamp=_dt(f"2026-04-{(i % 30)+1:02d}T13:35:00"),
            mode=TradeMode.DRY_RUN, contract_version=1,
            items=items, passed=True,
        )
        repo.save_checklist(c)
        d = DryRun(
            id=f"d{i:02d}", checklist_id=f"c{i:02d}",
            date=date(2026, 4, 20 + (i % 5)), symbol="MES",
            direction=TradeSide.LONG, setup_type="orb",
            identified_time=_dt(f"2026-04-{(i % 30)+1:02d}T13:35:00"),
            hypothetical_entry=Decimal("5000"),
            hypothetical_stop=Decimal("4995"),
            hypothetical_target=Decimal("5010"),
            hypothetical_size=1,
            outcome=DryRunOutcome.TARGET_HIT,
            outcome_time=_dt(f"2026-04-{(i % 30)+1:02d}T14:00:00"),
            outcome_price=Decimal("5010"),
            hypothetical_r_multiple=Decimal("2"),
        )
        repo.save_dry_run(d)

    svc = ResumeGateService(repo)
    res = svc.check()
    assert res.passed is True, res.failed_gates


def test_fail_when_compliance_not_100(repo):
    # Scenario: 20 passed checklists BUT 1 failed checklist also present
    from daytrader.journal.models import (
        Checklist, ChecklistItems, TradeMode,
    )
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    repo.save_setup_verdict(SetupVerdict(
        setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 25), symbol="MES",
        data_window_days=90, n_samples=40, win_rate=0.5,
        avg_r=0.1, passed=True,
    ))
    # Add one FAILED checklist in dry_run mode
    bad_items = ChecklistItems(
        item_stop_at_broker=False, item_within_r_limit=True,
        item_matches_locked_setup=True, item_within_daily_r=True,
        item_past_cooloff=True,
    )
    repo.save_checklist(Checklist(
        id="cbad", timestamp=_dt("2026-04-22T13:00:00"),
        mode=TradeMode.DRY_RUN, contract_version=1,
        items=bad_items, passed=False,
        failure_reason="item_stop_at_broker",
    ))

    svc = ResumeGateService(repo)
    res = svc.check()
    # Compliance < 100% should fail the gate
    assert res.passed is False
