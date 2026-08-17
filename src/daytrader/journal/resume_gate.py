"""Resume gate: machine-checked go/no-go for returning to live trading."""

from __future__ import annotations

from dataclasses import dataclass, field

from daytrader.journal.models import TradeMode
from daytrader.journal.repository import JournalRepository


@dataclass
class GateFailure:
    gate: str
    reason: str


@dataclass
class GateResult:
    passed: bool
    failed_gates: list[GateFailure] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


MIN_DRY_RUNS = 20


class ResumeGateService:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def check(self) -> GateResult:
        failed: list[GateFailure] = []
        metrics: dict = {}

        # Gate 1: active contract
        contract = self.repo.get_active_contract()
        if contract is None:
            failed.append(GateFailure("contract", "no active contract"))

        # Gate 2: at least 1 passed setup_verdict for the locked setup
        if contract and contract.locked_setup_name:
            verdicts = self.repo.list_setup_verdicts(
                setup_name=contract.locked_setup_name
            )
            passed_verdicts = [v for v in verdicts if v.passed]
            metrics["passed_verdicts"] = len(passed_verdicts)
            if not passed_verdicts:
                failed.append(GateFailure(
                    "sanity",
                    f"no passing sanity-floor verdict for "
                    f"{contract.locked_setup_name}",
                ))
        else:
            failed.append(GateFailure(
                "sanity", "no locked setup in contract"
            ))

        # Gate 3: >= MIN_DRY_RUNS with outcomes
        dry_runs_closed = [d for d in self.repo.list_dry_runs(only_with_outcome=True)]
        metrics["dry_runs_closed"] = len(dry_runs_closed)
        if len(dry_runs_closed) < MIN_DRY_RUNS:
            failed.append(GateFailure(
                "dry_run_count",
                f"need >={MIN_DRY_RUNS}, have {len(dry_runs_closed)}",
            ))

        # Gate 4: dry-run raw expectancy >= 0
        if dry_runs_closed:
            total_r = sum(
                float(d.hypothetical_r_multiple or 0) for d in dry_runs_closed
            )
            avg_r = total_r / len(dry_runs_closed)
            metrics["dry_run_avg_r"] = avg_r
            if avg_r < 0:
                failed.append(GateFailure(
                    "dry_run_expectancy",
                    f"avg_r = {avg_r:.3f} < 0",
                ))

        # Gate 5: checklist compliance 100% over dry-run period
        # Compliance rule: every dry_run mode checklist must have passed=True
        conn = self.repo._get_conn()
        rows = conn.execute(
            "SELECT id, passed FROM journal_checklists WHERE mode = 'dry_run'"
        ).fetchall()
        total = len(rows)
        pass_count = sum(1 for r in rows if r["passed"])
        metrics["dry_run_checklists_total"] = total
        metrics["dry_run_checklists_passed"] = pass_count
        if total > 0:
            compliance = pass_count / total
            metrics["dry_run_compliance"] = compliance
            if compliance < 1.0:
                failed.append(GateFailure(
                    "compliance",
                    f"dry-run checklist compliance "
                    f"{pass_count}/{total} = {compliance:.0%}",
                ))

        return GateResult(passed=not failed, failed_gates=failed, metrics=metrics)
