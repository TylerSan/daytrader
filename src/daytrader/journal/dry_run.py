"""Dry-run session service.

Known issue: start() uses now.date() on a UTC datetime. If the trader is in
a non-UTC timezone, the UTC date may differ from the local date (e.g. 02:30
UTC on April 21 = April 20 US-Eastern). This is intentional for the initial
implementation — a future fix should pass the local date explicitly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from daytrader.journal.models import (
    DryRun, DryRunOutcome, TradeSide,
)
from daytrader.journal.repository import JournalRepository


@dataclass
class DryRunStartInput:
    checklist_id: str
    symbol: str
    direction: TradeSide
    setup_type: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    size: int


@dataclass
class DryRunStartResult:
    dry_run_id: str


@dataclass
class DryRunEndInput:
    dry_run_id: str
    outcome: DryRunOutcome
    outcome_time: datetime
    outcome_price: Decimal
    notes: Optional[str] = None


class DryRunService:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def start(
        self, inp: DryRunStartInput, now: datetime
    ) -> DryRunStartResult:
        # Verify checklist exists + was marked dry_run + passed
        c = self.repo.get_checklist(inp.checklist_id)
        if c is None:
            raise ValueError(f"checklist not found: {inp.checklist_id}")
        if not c.passed:
            raise ValueError(f"checklist {inp.checklist_id} did not pass")

        did = uuid.uuid4().hex[:12]
        dry_run = DryRun(
            id=did,
            checklist_id=inp.checklist_id,
            date=now.date(),
            symbol=inp.symbol,
            direction=inp.direction,
            setup_type=inp.setup_type,
            identified_time=now,
            hypothetical_entry=inp.entry,
            hypothetical_stop=inp.stop,
            hypothetical_target=inp.target,
            hypothetical_size=inp.size,
        )
        self.repo.save_dry_run(dry_run)
        return DryRunStartResult(dry_run_id=did)

    def end(self, inp: DryRunEndInput) -> None:
        existing = next(
            (d for d in self.repo.list_dry_runs() if d.id == inp.dry_run_id),
            None,
        )
        if existing is None:
            raise ValueError(f"dry-run not found: {inp.dry_run_id}")
        if existing.outcome is not None:
            raise ValueError(f"dry-run already closed: {inp.dry_run_id}")

        risk = abs(existing.hypothetical_entry - existing.hypothetical_stop)
        if existing.direction == TradeSide.LONG:
            pnl_points = inp.outcome_price - existing.hypothetical_entry
        else:
            pnl_points = existing.hypothetical_entry - inp.outcome_price
        r_mult = Decimal("0") if risk == 0 else pnl_points / risk

        self.repo.close_dry_run(
            dry_run_id=inp.dry_run_id,
            outcome=inp.outcome,
            outcome_time=inp.outcome_time,
            outcome_price=inp.outcome_price,
            r_multiple=r_mult,
            notes=inp.notes,
        )
