"""ContextLoader: load Contract.md + journal trade stats + last reports.

Read-only with respect to journal/ subsystem. Provides graceful degradation
per spec §4.5 Contract.md state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class ContractStatus(str, Enum):
    NOT_CREATED = "not_created"      # Contract.md file doesn't exist
    SKELETAL = "skeletal"             # File exists but lacks key fields
    LOCK_IN_NOT_STARTED = "lock_in_not_started"  # Filled but trades_done == 0
    LOCK_IN_ACTIVE = "lock_in_active"
    LOCK_IN_COMPLETE = "lock_in_complete"


@dataclass(frozen=True)
class ReportContext:
    """Context bundle passed to PromptBuilder."""
    contract_status: ContractStatus
    contract_text: str | None
    lock_in_trades_done: int
    lock_in_target: int
    cumulative_r: float | None
    last_trade_date: str | None
    last_trade_r: float | None
    streak: str | None
    breakdown: dict[str, int] = field(default_factory=dict)


class ContextLoader:
    """Load all Phase 2 context into a single ReportContext."""

    def __init__(
        self,
        contract_path: Path,
        journal_db_path: Path,
        lock_in_target: int = 30,
    ) -> None:
        self.contract_path = Path(contract_path)
        self.journal_db_path = Path(journal_db_path)
        self.lock_in_target = lock_in_target

    def load(self) -> ReportContext:
        # Contract.md
        if not self.contract_path.exists():
            return ReportContext(
                contract_status=ContractStatus.NOT_CREATED,
                contract_text=None,
                lock_in_trades_done=0,
                lock_in_target=self.lock_in_target,
                cumulative_r=None,
                last_trade_date=None,
                last_trade_r=None,
                streak=None,
            )

        contract_text = self.contract_path.read_text()
        # Skeletal heuristic: file is too short or contains "not yet filled"
        if len(contract_text) < 200 or "not yet filled" in contract_text.lower():
            status = ContractStatus.SKELETAL
        else:
            status = ContractStatus.LOCK_IN_NOT_STARTED  # refined below if trades exist

        # Journal trade stats — gracefully degrade if DB missing
        trades_done = 0
        if self.journal_db_path.exists():
            # Phase 2: simple count via direct sqlite query rather than
            # importing journal.repository to avoid coupling on internal API.
            import sqlite3
            try:
                conn = sqlite3.connect(str(self.journal_db_path))
                cur = conn.execute(
                    "SELECT COUNT(*) FROM trades WHERE exit_time IS NOT NULL"
                )
                trades_done = cur.fetchone()[0]
                conn.close()
            except sqlite3.Error:
                trades_done = 0

        if status != ContractStatus.SKELETAL:
            if trades_done == 0:
                status = ContractStatus.LOCK_IN_NOT_STARTED
            elif trades_done >= self.lock_in_target:
                status = ContractStatus.LOCK_IN_COMPLETE
            else:
                status = ContractStatus.LOCK_IN_ACTIVE

        return ReportContext(
            contract_status=status,
            contract_text=contract_text,
            lock_in_trades_done=trades_done,
            lock_in_target=self.lock_in_target,
            cumulative_r=None,
            last_trade_date=None,
            last_trade_r=None,
            streak=None,
        )
