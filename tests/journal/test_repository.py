"""Tests for JournalRepository."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.models import (
    Checklist, ChecklistItems, CircuitState, Contract,
    DryRun, DryRunOutcome, JournalTrade, SetupVerdict, TradeMode, TradeSide,
)
from daytrader.journal.repository import JournalRepository


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    return r


def _make_trade(**overrides) -> JournalTrade:
    defaults = dict(
        id="t01", checklist_id="c01",
        date=date(2026, 4, 20), symbol="MES",
        direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:35:00"),
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
    )
    defaults.update(overrides)
    return JournalTrade(**defaults)


def _make_checklist(passed: bool = True, mode: TradeMode = TradeMode.REAL) -> Checklist:
    items = ChecklistItems(
        item_stop_at_broker=passed, item_within_r_limit=passed,
        item_matches_locked_setup=passed, item_within_daily_r=passed,
        item_past_cooloff=passed,
    )
    return Checklist(
        id="c01", timestamp=_dt("2026-04-20T13:34:00"),
        mode=mode, contract_version=1,
        items=items, passed=items.all_passed(),
    )


def test_initialize_creates_all_tables(repo: JournalRepository):
    tables = repo.list_tables()
    assert "journal_contract" in tables
    assert "journal_checklists" in tables
    assert "journal_trades" in tables
    assert "journal_dry_runs" in tables
    assert "journal_circuit_state" in tables
    assert "journal_setup_verdicts" in tables


def test_save_and_get_checklist(repo: JournalRepository):
    c = _make_checklist()
    repo.save_checklist(c)
    got = repo.get_checklist("c01")
    assert got is not None
    assert got.passed is True


def test_save_trade_requires_existing_checklist(repo: JournalRepository):
    # Trade references non-existent checklist → FK failure
    with pytest.raises(Exception):
        repo.save_trade(_make_trade(checklist_id="nonexistent"))


def test_save_trade_with_valid_checklist(repo: JournalRepository):
    repo.save_checklist(_make_checklist())
    repo.save_trade(_make_trade())
    got = repo.get_trade("t01")
    assert got is not None
    assert got.stop_price == Decimal("4995")


def test_stop_price_not_null_enforced(repo: JournalRepository):
    """Direct SQL INSERT without stop_price must fail."""
    import sqlite3
    conn = repo._get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journal_trades "
            "(id, checklist_id, date, symbol, direction, setup_type, "
            " entry_time, entry_price, target_price, size) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("t02", "c01", "2026-04-20", "MES", "long", "orb",
             "2026-04-20T13:35:00", "5000", "5010", 1),
        )


def test_post_trade_update(repo: JournalRepository):
    repo.save_checklist(_make_checklist())
    repo.save_trade(_make_trade())
    repo.close_trade(
        trade_id="t01",
        exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5005"),
        pnl_usd=Decimal("25"),
        notes="target hit",
    )
    got = repo.get_trade("t01")
    assert got.exit_price == Decimal("5005")
    assert got.notes == "target hit"


def test_close_trade_raises_on_nonexistent(repo: JournalRepository):
    with pytest.raises(RuntimeError, match="not found or already closed"):
        repo.close_trade(
            trade_id="ghost",
            exit_time=_dt("2026-04-20T14:00:00"),
            exit_price=Decimal("5005"),
            pnl_usd=Decimal("0"),
        )


def test_close_trade_raises_on_double_close(repo: JournalRepository):
    repo.save_checklist(_make_checklist())
    repo.save_trade(_make_trade())
    repo.close_trade(
        trade_id="t01",
        exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5005"),
        pnl_usd=Decimal("25"),
    )
    with pytest.raises(RuntimeError, match="already closed"):
        repo.close_trade(
            trade_id="t01",
            exit_time=_dt("2026-04-20T14:30:00"),
            exit_price=Decimal("5020"),
            pnl_usd=Decimal("100"),
        )


def test_close_dry_run_raises_on_nonexistent(repo: JournalRepository):
    from daytrader.journal.models import DryRunOutcome
    with pytest.raises(RuntimeError, match="not found or already closed"):
        repo.close_dry_run(
            dry_run_id="ghost",
            outcome=DryRunOutcome.TARGET_HIT,
            outcome_time=_dt("2026-04-20T14:00:00"),
            outcome_price=Decimal("5010"),
            r_multiple=Decimal("2"),
        )


def test_list_dry_runs_filters_by_date(repo: JournalRepository):
    from daytrader.journal.models import DryRun
    repo.save_checklist(_make_checklist())
    d1 = DryRun(
        id="d01", checklist_id="c01", date=date(2026, 4, 20),
        symbol="MES", direction=TradeSide.LONG, setup_type="orb",
        identified_time=_dt("2026-04-20T13:35:00"),
        hypothetical_entry=Decimal("5000"), hypothetical_stop=Decimal("4995"),
        hypothetical_target=Decimal("5010"), hypothetical_size=1,
    )
    d2 = DryRun(
        id="d02", checklist_id="c01", date=date(2026, 4, 21),
        symbol="MES", direction=TradeSide.LONG, setup_type="orb",
        identified_time=_dt("2026-04-21T13:35:00"),
        hypothetical_entry=Decimal("5020"), hypothetical_stop=Decimal("5015"),
        hypothetical_target=Decimal("5030"), hypothetical_size=1,
    )
    repo.save_dry_run(d1)
    repo.save_dry_run(d2)
    got = repo.list_dry_runs(on_date=date(2026, 4, 20))
    assert len(got) == 1
    assert got[0].id == "d01"


def test_get_circuit_state_default(repo: JournalRepository):
    state = repo.get_circuit_state(date(2026, 4, 20))
    # returns a fresh unlocked state if missing
    assert state.no_trade_flag is False
    assert state.trade_count == 0


def test_upsert_circuit_state(repo: JournalRepository):
    repo.upsert_circuit_state(
        CircuitState(
            date=date(2026, 4, 20),
            realized_r=Decimal("-1"),
            realized_usd=Decimal("-50"),
            trade_count=1,
            no_trade_flag=False,
        )
    )
    s = repo.get_circuit_state(date(2026, 4, 20))
    assert s.realized_r == Decimal("-1")
    assert s.trade_count == 1


def test_save_setup_verdict(repo: JournalRepository):
    v = SetupVerdict(
        setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 20), symbol="MES",
        data_window_days=90, n_samples=45,
        win_rate=0.6, avg_r=0.2, passed=True,
    )
    repo.save_setup_verdict(v)
    got = repo.list_setup_verdicts(setup_name="orb")
    assert len(got) == 1
    assert got[0].passed is True


def test_save_contract_and_get_active(repo: JournalRepository):
    c = Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    )
    repo.save_contract(c)
    got = repo.get_active_contract()
    assert got is not None
    assert got.version == 1
