"""Orchestrator: end-to-end pipeline for one report run.

Phase 2 supports premarket only. Phase 5 will add other report types via
a per-type dispatch table.
"""

from __future__ import annotations

import time
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.core.state import StateDB
from daytrader.reports.core.ai_analyst import AIAnalyst
from daytrader.reports.core.context_loader import ContextLoader
from daytrader.reports.core.plan_extractor import PlanExtractor
from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
from daytrader.reports.types.premarket import PremarketGenerator


PT = zoneinfo.ZoneInfo("America/Los_Angeles")
ET = zoneinfo.ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PipelineResult:
    success: bool
    report_id: int | None
    report_path: Path | None
    failure_reason: str | None = None
    skipped_idempotent: bool = False


class Orchestrator:
    """Coordinate one end-to-end report run for premarket."""

    def __init__(
        self,
        state_db: StateDB,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        contract_path: Path,
        journal_db_path: Path,
        vault_root: Path,
        fallback_dir: Path,
        daily_folder: str = "Daily",
        symbol: str = "MES",
    ) -> None:
        self.state_db = state_db
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.contract_path = Path(contract_path)
        self.journal_db_path = Path(journal_db_path)
        self.vault_root = Path(vault_root)
        self.fallback_dir = Path(fallback_dir)
        self.daily_folder = daily_folder
        self.symbol = symbol

    def run_premarket(self, run_at: datetime) -> PipelineResult:
        """Execute one premarket pipeline run."""
        run_at_utc = run_at.astimezone(timezone.utc)
        date_et = run_at_utc.astimezone(ET).date().isoformat()
        time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
        time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

        # Idempotency check
        if self.state_db.already_generated_today("premarket", date_et):
            return PipelineResult(
                success=True,
                report_id=None,
                report_path=None,
                skipped_idempotent=True,
            )

        # Insert pending report row
        report_id = self.state_db.insert_report(
            report_type="premarket",
            date_et=date_et,
            time_pt=time_pt_str,
            time_et=time_et_str,
            status="pending",
            created_at=run_at_utc,
        )

        start = time.perf_counter()

        # Load context
        loader = ContextLoader(
            contract_path=self.contract_path,
            journal_db_path=self.journal_db_path,
        )
        context = loader.load()

        # Generate
        generator = PremarketGenerator(
            ib_client=self.ib_client,
            ai_analyst=self.ai_analyst,
            symbol=self.symbol,
        )
        outcome = generator.generate(
            context=context,
            run_timestamp_pt=f"{time_pt_str} PT",
            run_timestamp_et=f"{time_et_str} ET",
        )

        if not outcome.validation.ok:
            self.state_db.update_report_status(
                report_id,
                status="failed",
                failure_reason=f"validation missing: {outcome.validation.missing}",
                tokens_input=outcome.ai_result.input_tokens,
                tokens_output=outcome.ai_result.output_tokens,
                duration_seconds=time.perf_counter() - start,
            )
            return PipelineResult(
                success=False,
                report_id=report_id,
                report_path=None,
                failure_reason=(
                    f"validation: missing sections {outcome.validation.missing}"
                ),
            )

        # Persist plan if extractable
        plan = PlanExtractor().extract(outcome.report_text)
        if plan is not None:
            self.state_db.save_plan(
                date_et=date_et,
                instrument=self.symbol,
                setup_name=plan.setup_name,
                direction=plan.direction,
                entry=plan.entry,
                stop=plan.stop,
                target=plan.target,
                r_unit_dollars=plan.r_unit_dollars,
                invalidations=plan.invalidations,
                raw_plan_text=plan.raw_text,
                source_report_path="",  # filled below
                created_at=run_at_utc,
            )

        # Write to Obsidian
        writer = ObsidianWriter(
            vault_root=self.vault_root,
            fallback_dir=self.fallback_dir,
            daily_folder=self.daily_folder,
        )
        write_result = writer.write_premarket(
            date_iso=date_et,
            content=outcome.report_text,
        )

        duration = time.perf_counter() - start
        self.state_db.update_report_status(
            report_id,
            status="success",
            obsidian_path=str(write_result.path),
            tokens_input=outcome.ai_result.input_tokens,
            tokens_output=outcome.ai_result.output_tokens,
            cache_hit_rate=(
                outcome.ai_result.cache_read_tokens
                / max(outcome.ai_result.input_tokens, 1)
            ),
            duration_seconds=duration,
            estimated_cost_usd=self._estimate_cost(outcome.ai_result),
        )

        return PipelineResult(
            success=True,
            report_id=report_id,
            report_path=write_result.path,
        )

    @staticmethod
    def _estimate_cost(ai_result: Any) -> float:
        """Rough Opus 4.7 cost estimate, USD.

        Returns 0.0 in CLI mode (token counts are 0). API backend in future
        phases will compute non-zero values.
        """
        # $15/M input (uncached); $1.50/M cache read; $18.75/M cache write; $75/M output
        in_uncached = (
            ai_result.input_tokens
            - ai_result.cache_read_tokens
            - ai_result.cache_creation_tokens
        )
        return (
            in_uncached / 1_000_000 * 15.0
            + ai_result.cache_creation_tokens / 1_000_000 * 18.75
            + ai_result.cache_read_tokens / 1_000_000 * 1.50
            + ai_result.output_tokens / 1_000_000 * 75.0
        )
