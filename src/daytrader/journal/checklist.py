"""Pre-trade checklist orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type, datetime, timedelta
from decimal import Decimal
from typing import Optional

from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import (
    Checklist, ChecklistItems, JournalTrade, TradeMode, TradeSide,
)
from daytrader.journal.repository import JournalRepository


# USD per 1.0 price point, per 1 contract
INSTRUMENT_TICK_VALUE = {
    "MES": Decimal("5"),    # $5 per point (micro S&P)
    "MNQ": Decimal("2"),    # $2 per point (micro Nasdaq)
    "MGC": Decimal("10"),   # $10 per point (micro gold)
}


@dataclass
class ChecklistInput:
    mode: TradeMode
    symbol: str
    direction: TradeSide
    setup_type: str
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    size: int
    stop_at_broker: bool


@dataclass
class ChecklistResult:
    passed: bool
    checklist_id: Optional[str]
    trade_id: Optional[str] = None
    failure_reason: Optional[str] = None
    failed_items: list[str] = field(default_factory=list)


class ChecklistService:
    def __init__(
        self, repo: JournalRepository, circuit: CircuitService
    ) -> None:
        self.repo = repo
        self.circuit = circuit

    @staticmethod
    def _compute_risk_usd(inp: ChecklistInput) -> Decimal:
        mult = INSTRUMENT_TICK_VALUE.get(inp.symbol, Decimal("1"))
        distance = abs(inp.entry_price - inp.stop_price)
        return distance * mult * inp.size

    def _record_blocked_attempt(
        self,
        now: datetime,
        mode: TradeMode,
        contract_version: Optional[int],
        reason: str,
    ) -> str:
        """Save an audit-only Checklist record for a blocked attempt.

        Items are all False because the attempt never reached item evaluation.
        This makes every trade attempt visible in the audit log, including
        attempts blocked by the circuit or by a missing contract.
        """
        checklist_id = uuid.uuid4().hex[:12]
        items = ChecklistItems(
            item_stop_at_broker=False,
            item_within_r_limit=False,
            item_matches_locked_setup=False,
            item_within_daily_r=False,
            item_past_cooloff=False,
        )
        checklist = Checklist(
            id=checklist_id,
            timestamp=now,
            mode=mode,
            contract_version=contract_version or 0,
            items=items,
            passed=False,
            failure_reason=f"blocked:{reason}",
        )
        try:
            self.repo.save_checklist(checklist)
        except Exception:
            # If no contract exists yet, contract_version FK would normally
            # fail. Task 3 removed that FK, so this should succeed even with 0.
            # Keep fail-open: audit attempt is better-effort.
            import logging
            logging.getLogger(__name__).exception(
                "checklist: failed to save blocked-attempt audit record"
            )
        return checklist_id

    def run(self, inp: ChecklistInput, now: datetime) -> ChecklistResult:
        d = now.date()

        contract = self.repo.get_active_contract()
        if contract is None:
            cid = self._record_blocked_attempt(
                now=now, mode=inp.mode, contract_version=None,
                reason="no_active_contract",
            )
            return ChecklistResult(
                passed=False,
                checklist_id=cid,
                failure_reason="no_active_contract",
            )

        # 1. Circuit check (short-circuits the rest)
        decision = self.circuit.check_can_trade(on=d, now=now)
        if not decision.allowed:
            cid = self._record_blocked_attempt(
                now=now, mode=inp.mode,
                contract_version=contract.version,
                reason=decision.reason or "circuit_blocked",
            )
            return ChecklistResult(
                passed=False,
                checklist_id=cid,
                failure_reason=decision.reason,
            )

        # 2. Compute per-item booleans
        item_stop_at_broker = bool(inp.stop_at_broker)

        risk_usd = self._compute_risk_usd(inp)
        # Max loss per trade is exactly 1 R unit by contract rule.
        item_within_r_limit = risk_usd <= contract.r_unit_usd

        item_matches_locked_setup = (
            inp.setup_type == contract.locked_setup_name
        )

        state = self.repo.get_circuit_state(d)
        remaining_r = Decimal(contract.daily_loss_limit_r) + state.realized_r
        item_within_daily_r = remaining_r > 0

        if state.last_stop_time is None:
            item_past_cooloff = True
        else:
            delta = now - state.last_stop_time
            item_past_cooloff = delta >= timedelta(
                minutes=contract.stop_cooloff_minutes
            )

        items = ChecklistItems(
            item_stop_at_broker=item_stop_at_broker,
            item_within_r_limit=item_within_r_limit,
            item_matches_locked_setup=item_matches_locked_setup,
            item_within_daily_r=item_within_daily_r,
            item_past_cooloff=item_past_cooloff,
        )
        passed = items.all_passed()

        checklist_id = uuid.uuid4().hex[:12]
        failed = items.failed_items()
        failure_reason = None if passed else ",".join(failed)

        checklist = Checklist(
            id=checklist_id,
            timestamp=now,
            mode=inp.mode,
            contract_version=contract.version,
            items=items,
            passed=passed,
            failure_reason=failure_reason,
        )
        self.repo.save_checklist(checklist)

        trade_id: Optional[str] = None
        if passed and inp.mode == TradeMode.REAL:
            trade_id = uuid.uuid4().hex[:12]
            trade = JournalTrade(
                id=trade_id,
                checklist_id=checklist_id,
                date=d,
                symbol=inp.symbol,
                direction=inp.direction,
                setup_type=inp.setup_type,
                entry_time=now,
                entry_price=inp.entry_price,
                stop_price=inp.stop_price,
                target_price=inp.target_price,
                size=inp.size,
            )
            self.repo.save_trade(trade)

        return ChecklistResult(
            passed=passed,
            checklist_id=checklist_id,
            trade_id=trade_id,
            failure_reason=failure_reason,
            failed_items=failed,
        )
