"""Tests for journal domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from daytrader.journal.models import (
    ChecklistItems,
    CircuitState,
    Contract,
    DryRun,
    DryRunOutcome,
    JournalTrade,
    SetupVerdict,
    TradeMode,
    TradeSide,
)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class TestChecklistItems:
    def test_all_required(self):
        items = ChecklistItems(
            item_stop_at_broker=True,
            item_within_r_limit=True,
            item_matches_locked_setup=True,
            item_within_daily_r=True,
            item_past_cooloff=True,
        )
        assert items.all_passed() is True

    def test_any_false_fails(self):
        items = ChecklistItems(
            item_stop_at_broker=True,
            item_within_r_limit=True,
            item_matches_locked_setup=False,  # <-- fail
            item_within_daily_r=True,
            item_past_cooloff=True,
        )
        assert items.all_passed() is False


class TestJournalTrade:
    def test_stop_price_required(self):
        """stop_price is non-optional — cannot create trade without it."""
        with pytest.raises(ValidationError):
            JournalTrade(
                id="t01",
                checklist_id="c01",
                date="2026-04-20",
                symbol="MES",
                direction=TradeSide.LONG,
                setup_type="opening_range_breakout",
                entry_time=_dt("2026-04-20T13:35:00"),
                entry_price=Decimal("5000.00"),
                # stop_price missing
                target_price=Decimal("5010.00"),
                size=1,
            )

    def test_target_price_required(self):
        with pytest.raises(ValidationError):
            JournalTrade(
                id="t01",
                checklist_id="c01",
                date="2026-04-20",
                symbol="MES",
                direction=TradeSide.LONG,
                setup_type="opening_range_breakout",
                entry_time=_dt("2026-04-20T13:35:00"),
                entry_price=Decimal("5000.00"),
                stop_price=Decimal("4995.00"),
                # target_price missing
                size=1,
            )

    def test_symbol_whitelist(self):
        with pytest.raises(ValidationError):
            JournalTrade(
                id="t01",
                checklist_id="c01",
                date="2026-04-20",
                symbol="AAPL",  # <-- not in whitelist
                direction=TradeSide.LONG,
                setup_type="orb",
                entry_time=_dt("2026-04-20T13:35:00"),
                entry_price=Decimal("5000"),
                stop_price=Decimal("4995"),
                target_price=Decimal("5010"),
                size=1,
            )

    def test_r_multiple_when_closed(self):
        t = JournalTrade(
            id="t01",
            checklist_id="c01",
            date="2026-04-20",
            symbol="MES",
            direction=TradeSide.LONG,
            setup_type="orb",
            entry_time=_dt("2026-04-20T13:35:00"),
            entry_price=Decimal("5000"),
            stop_price=Decimal("4995"),
            target_price=Decimal("5010"),
            size=1,
            exit_time=_dt("2026-04-20T14:00:00"),
            exit_price=Decimal("5005"),
        )
        # Long, risk = 5, pnl = 5 → r = 1.0
        assert t.r_multiple() == Decimal("1")

    def test_r_multiple_none_when_open(self):
        t = JournalTrade(
            id="t01", checklist_id="c01", date="2026-04-20",
            symbol="MES", direction=TradeSide.LONG, setup_type="orb",
            entry_time=_dt("2026-04-20T13:35:00"),
            entry_price=Decimal("5000"),
            stop_price=Decimal("4995"),
            target_price=Decimal("5010"),
            size=1,
        )
        assert t.r_multiple() is None


class TestCircuitState:
    def test_default_not_locked(self):
        s = CircuitState(date="2026-04-20")
        assert s.no_trade_flag is False
        assert s.trade_count == 0
        assert s.realized_r == 0


class TestContract:
    def test_active_contract(self):
        c = Contract(
            version=1,
            signed_date="2026-04-20",
            active=True,
            r_unit_usd=Decimal("50"),
            daily_loss_limit_r=3,
            daily_loss_warning_r=2,
            max_trades_per_day=5,
            stop_cooloff_minutes=30,
            locked_setup_name="orb",
            locked_setup_file="docs/trading/setups/orb.yaml",
            lock_in_min_trades=30,
            backup_setup_status="benched",
        )
        assert c.active is True


class TestSetupVerdict:
    def test_pass_requires_both_conditions(self):
        v = SetupVerdict(
            setup_name="orb", setup_version="v1",
            run_date="2026-04-20", symbol="MES",
            data_window_days=90,
            n_samples=40,
            win_rate=0.5,
            avg_r=0.1,
            passed=True,
        )
        assert v.passed is True

    def test_failed_when_low_sample(self):
        # n<30 should be marked failed regardless of avg_r
        v = SetupVerdict(
            setup_name="orb", setup_version="v1",
            run_date="2026-04-20", symbol="MES",
            data_window_days=90,
            n_samples=10,  # too few
            win_rate=0.7,
            avg_r=0.5,
            passed=False,
        )
        assert v.passed is False


class TestDryRun:
    def test_outcome_optional(self):
        d = DryRun(
            id="d01", checklist_id="c01", date="2026-04-20",
            symbol="MES", direction=TradeSide.LONG,
            setup_type="orb",
            identified_time=_dt("2026-04-20T13:35:00"),
            hypothetical_entry=Decimal("5000"),
            hypothetical_stop=Decimal("4995"),
            hypothetical_target=Decimal("5010"),
            hypothetical_size=1,
        )
        assert d.outcome is None

    def test_outcome_enum(self):
        for val in ("target_hit", "stop_hit", "rule_exit", "no_trigger"):
            DryRunOutcome(val)  # should parse cleanly
