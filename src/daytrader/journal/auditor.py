"""Integrity auditor — detects SQLite tampering or inconsistent state."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from daytrader.journal.repository import JournalRepository


@dataclass
class AuditIssue:
    kind: str
    detail: str


class Auditor:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def run_all(self) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        issues += self._check_trades_have_checklists()
        issues += self._check_circuit_consistency()
        issues += self._check_stop_price_not_null()
        return issues

    def _check_trades_have_checklists(self) -> list[AuditIssue]:
        conn = self.repo._get_conn()
        rows = conn.execute(
            """SELECT t.id AS tid FROM journal_trades t
               LEFT JOIN journal_checklists c ON c.id = t.checklist_id
               WHERE c.id IS NULL"""
        ).fetchall()
        return [
            AuditIssue("trade_without_checklist",
                       f"trade {r['tid']} has no checklist record")
            for r in rows
        ]

    def _check_circuit_consistency(self) -> list[AuditIssue]:
        contract = self.repo.get_active_contract()
        if contract is None:
            return []
        conn = self.repo._get_conn()
        rows = conn.execute(
            "SELECT date, realized_r, no_trade_flag FROM journal_circuit_state"
        ).fetchall()
        issues = []
        limit = -Decimal(contract.daily_loss_limit_r)
        for r in rows:
            realized = Decimal(r["realized_r"])
            if realized <= limit and not r["no_trade_flag"]:
                issues.append(AuditIssue(
                    "circuit_inconsistent",
                    f"{r['date']}: realized_r={realized} "
                    f"<= limit {limit} but no_trade_flag=false",
                ))
        return issues

    def _check_stop_price_not_null(self) -> list[AuditIssue]:
        conn = self.repo._get_conn()
        rows = conn.execute(
            "SELECT id FROM journal_trades WHERE stop_price IS NULL"
        ).fetchall()
        return [
            AuditIssue("trade_missing_stop", f"trade {r['id']} has NULL stop")
            for r in rows
        ]
