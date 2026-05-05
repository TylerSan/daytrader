"""Orchestrator: end-to-end pipeline for one report run.

Phase 2 supports premarket; Phase 5 (T10) adds EOD via :meth:`run_eod`. Other
cadences (intraday-4h, night, asia, weekly) follow in later phases via the
same per-type dispatch table.
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
from daytrader.reports.sentiment import SentimentSection
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
        symbols: list[str] | None = None,
        tradable_symbols: list[str] | None = None,
        chart_renderer=None,        # ChartRenderer | None
        pdf_renderer=None,          # PDFRenderer | None
        telegram_pusher=None,       # TelegramPusher | None
    ) -> None:
        if symbols is None:
            symbols = ["MES"]
        if tradable_symbols is None:
            tradable_symbols = list(symbols)
        self.state_db = state_db
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.contract_path = Path(contract_path)
        self.journal_db_path = Path(journal_db_path)
        self.vault_root = Path(vault_root)
        self.fallback_dir = Path(fallback_dir)
        self.daily_folder = daily_folder
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
        self.chart_renderer = chart_renderer
        self.pdf_renderer = pdf_renderer
        self.telegram_pusher = telegram_pusher

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

        try:
            # Load context
            loader = ContextLoader(
                contract_path=self.contract_path,
                journal_db_path=self.journal_db_path,
            )
            context = loader.load()

            # Sentiment section (Phase 4.5) — best-effort web/social fetch via
            # claude -p. Failures are translated to an "unavailable" markdown
            # block by SentimentSection itself; never raises here.
            sentiment_section = SentimentSection(symbols=self.symbols)
            try:
                sentiment_result = sentiment_section.collect()
                sentiment_md = sentiment_section.render(sentiment_result)
            except Exception as exc:
                import sys
                print(
                    f"[orchestrator] sentiment collect/render failed: {exc}",
                    file=sys.stderr,
                )
                sentiment_md = ""

            # Generate (includes IB fetch + AI call)
            # Phase 4 hooks (basis + term structure) — wire IB-backed fetchers.
            from daytrader.reports.futures_data.term_prices import TermPricesFetcher
            from daytrader.reports.futures_data.underlying_prices import (
                UnderlyingPriceFetcher,
            )

            generator = PremarketGenerator(
                ib_client=self.ib_client,
                ai_analyst=self.ai_analyst,
                symbols=self.symbols,
                tradable_symbols=self.tradable_symbols,
                underlying_price_fetcher=UnderlyingPriceFetcher(self.ib_client),
                term_price_fetcher=TermPricesFetcher(self.ib_client),
            )
            outcome = generator.generate(
                context=context,
                run_timestamp_pt=f"{time_pt_str} PT",
                run_timestamp_et=f"{time_et_str} ET",
                sentiment_md=sentiment_md,
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

            # Write to Obsidian first to capture the report path for plan rows
            writer = ObsidianWriter(
                vault_root=self.vault_root,
                fallback_dir=self.fallback_dir,
                daily_folder=self.daily_folder,
            )
            write_result = writer.write_premarket(
                date_iso=date_et,
                content=outcome.report_text,
            )

            # Persist per-tradable plans
            plans = PlanExtractor().extract_per_instrument(
                outcome.report_text, instruments=self.tradable_symbols
            )
            for symbol, plan in plans.items():
                self.state_db.save_plan(
                    date_et=date_et,
                    instrument=symbol,
                    setup_name=plan.setup_name,
                    direction=plan.direction,
                    entry=plan.entry,
                    stop=plan.stop,
                    target=plan.target,
                    r_unit_dollars=plan.r_unit_dollars,
                    invalidations=plan.invalidations,
                    raw_plan_text=plan.raw_text,
                    source_report_path=str(write_result.path),
                    created_at=run_at_utc,
                )

            # Phase 6 delivery: charts + PDF + Telegram (best-effort; failures
            # don't block the success path — Obsidian write is the source of truth).
            chart_paths: list[Path] = []
            if self.chart_renderer is not None and outcome.bars_by_symbol_and_tf:
                try:
                    artifacts = self.chart_renderer.render_all(
                        bars_by_symbol_and_tf=outcome.bars_by_symbol_and_tf,
                        today=date_et,
                    )
                    chart_paths = list(artifacts.tf_stack_paths.values())
                except Exception as e:
                    import sys
                    print(f"[orchestrator] chart render failed: {e}", file=sys.stderr)

            pdf_path: Path | None = None
            if self.pdf_renderer is not None:
                try:
                    pdf_path = self.pdf_renderer.render_to_pdf(
                        markdown_text=outcome.report_text,
                        title=f"Premarket {date_et}",
                        filename_stem=f"{date_et}-premarket",
                    )
                except Exception as e:
                    import sys
                    print(f"[orchestrator] PDF render failed: {e}", file=sys.stderr)

            if self.telegram_pusher is not None:
                try:
                    import asyncio
                    asyncio.run(self.telegram_pusher.push(
                        text_messages=[outcome.report_text],
                        chart_paths=chart_paths,
                        pdf_path=pdf_path,
                    ))
                except Exception as e:
                    import sys
                    print(f"[orchestrator] telegram push failed: {e}", file=sys.stderr)

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

        except Exception as exc:
            self.state_db.update_report_status(
                report_id,
                status="failed",
                failure_reason=f"{type(exc).__name__}: {exc}",
                duration_seconds=time.perf_counter() - start,
            )
            raise

        return PipelineResult(
            success=True,
            report_id=report_id,
            report_path=write_result.path,
        )

    def run_eod(self, run_at: datetime) -> PipelineResult:
        """Execute one EOD pipeline run (Phase 5 T10).

        Mirrors :meth:`run_premarket`: idempotency via ``state_db``, pending
        row insert, multi-symbol fetch + retrospective + AI inside
        :class:`EODGenerator`, validation handling, Obsidian write,
        success/failure status update, best-effort Telegram push.

        EOD differs from premarket in that the C section is retrospective
        (plan-vs-actual review for the day just ended), so no per-instrument
        plan extraction is performed on the output.
        """
        run_at_utc = run_at.astimezone(timezone.utc)
        date_et = run_at_utc.astimezone(ET).date().isoformat()
        time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
        time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

        # Idempotency check
        if self.state_db.already_generated_today("eod", date_et):
            return PipelineResult(
                success=True,
                report_id=None,
                report_path=None,
                skipped_idempotent=True,
            )

        # Insert pending report row
        report_id = self.state_db.insert_report(
            report_type="eod",
            date_et=date_et,
            time_pt=time_pt_str,
            time_et=time_et_str,
            status="pending",
            created_at=run_at_utc,
        )

        start = time.perf_counter()

        try:
            # Load context (contract + journal) — same loader as premarket.
            loader = ContextLoader(
                contract_path=self.contract_path,
                journal_db_path=self.journal_db_path,
            )
            context = loader.load()

            # Sentiment with shorter window for EOD (8h covers RTH session).
            sentiment_section = SentimentSection(
                symbols=self.symbols,
                time_window="past 8h",
            )
            sentiment_md = ""
            try:
                sentiment_result = sentiment_section.collect()
                sentiment_md = sentiment_section.render(sentiment_result)
            except Exception as exc:
                import sys
                print(
                    f"[orchestrator] EOD sentiment collect/render failed: {exc}",
                    file=sys.stderr,
                )

            # EOD-specific deps.
            from daytrader.reports.eod.plan_parser import PremarketPlanParser
            from daytrader.reports.eod.plan_reader import PremarketPlanReader
            from daytrader.reports.eod.retrospective import PlanRetrospective
            from daytrader.reports.eod.tomorrow_plan import (
                TomorrowPreliminaryPlan,
            )
            from daytrader.reports.eod.trade_simulator import simulate_level
            from daytrader.reports.eod.trades_query import TodayTradesQuery
            from daytrader.reports.futures_data.term_prices import (
                TermPricesFetcher,
            )
            from daytrader.reports.futures_data.underlying_prices import (
                UnderlyingPriceFetcher,
            )
            from daytrader.reports.types.eod import EODGenerator

            plan_reader = PremarketPlanReader(
                vault_path=self.vault_root,
                daily_folder=self.daily_folder,
            )
            plan_parser = PremarketPlanParser()
            trades_query = TodayTradesQuery(self.journal_db_path)

            # CRITICAL adapter: PlanRetrospective expects
            # ``intraday_bar_fetcher(symbol, date_et) -> list[OHLCV]`` but
            # IBClient.get_bars takes ``(symbol, timeframe, bars)``. 78 5m
            # bars covers a full RTH session (6.5h × 12 bars/h).
            retrospective = PlanRetrospective(
                plan_parser=plan_parser,
                trade_simulator=simulate_level,
                intraday_bar_fetcher=lambda sym, d: self.ib_client.get_bars(
                    symbol=sym, timeframe="5m", bars=78,
                ),
                trades_query=trades_query,
                state_db_path=self.state_db._path,
            )
            tomorrow_planner = TomorrowPreliminaryPlan()

            generator = EODGenerator(
                ib_client=self.ib_client,
                ai_analyst=self.ai_analyst,
                symbols=self.symbols,
                tradable_symbols=self.tradable_symbols,
                underlying_price_fetcher=UnderlyingPriceFetcher(self.ib_client),
                term_price_fetcher=TermPricesFetcher(self.ib_client),
                plan_reader=plan_reader,
                plan_parser=plan_parser,
                trades_query=trades_query,
                retrospective=retrospective,
                tomorrow_planner=tomorrow_planner,
            )

            outcome = generator.generate(
                context=context,
                date_et=date_et,
                run_timestamp_pt=f"{time_pt_str} PT",
                run_timestamp_et=f"{time_et_str} ET",
                sentiment_md=sentiment_md,
            )

            if not outcome.validation.ok:
                self.state_db.update_report_status(
                    report_id,
                    status="failed",
                    failure_reason=(
                        f"validation missing: {outcome.validation.missing}"
                    ),
                    tokens_input=outcome.ai_result.input_tokens,
                    tokens_output=outcome.ai_result.output_tokens,
                    duration_seconds=time.perf_counter() - start,
                )
                return PipelineResult(
                    success=False,
                    report_id=report_id,
                    report_path=None,
                    failure_reason=(
                        f"validation: missing sections "
                        f"{outcome.validation.missing}"
                    ),
                )

            # Write to Obsidian (EOD: Daily/<date>-eod.md).
            writer = ObsidianWriter(
                vault_root=self.vault_root,
                fallback_dir=self.fallback_dir,
                daily_folder=self.daily_folder,
            )
            write_result = writer.write_eod(
                date_iso=date_et,
                content=outcome.report_text,
            )

            # NOTE: EOD's C section is retrospective (plan vs PA review for the
            # day just ended), not forward-looking — so we do NOT run
            # PlanExtractor or save per-instrument plan rows. The retrospective
            # is already persisted to plan_retrospective_daily by
            # PlanRetrospective.persist() inside EODGenerator.

            # Phase 6 delivery: charts + PDF + Telegram (best-effort).
            chart_paths: list[Path] = []
            if self.chart_renderer is not None and outcome.bars_by_symbol_and_tf:
                try:
                    artifacts = self.chart_renderer.render_all(
                        bars_by_symbol_and_tf=outcome.bars_by_symbol_and_tf,
                        today=date_et,
                    )
                    chart_paths = list(artifacts.tf_stack_paths.values())
                except Exception as e:
                    import sys
                    print(
                        f"[orchestrator] EOD chart render failed: {e}",
                        file=sys.stderr,
                    )

            pdf_path: Path | None = None
            if self.pdf_renderer is not None:
                try:
                    pdf_path = self.pdf_renderer.render_to_pdf(
                        markdown_text=outcome.report_text,
                        title=f"EOD {date_et}",
                        filename_stem=f"{date_et}-eod",
                    )
                except Exception as e:
                    import sys
                    print(
                        f"[orchestrator] EOD PDF render failed: {e}",
                        file=sys.stderr,
                    )

            if self.telegram_pusher is not None:
                try:
                    import asyncio
                    asyncio.run(self.telegram_pusher.push(
                        text_messages=[outcome.report_text],
                        chart_paths=chart_paths,
                        pdf_path=pdf_path,
                    ))
                except Exception as e:
                    import sys
                    print(
                        f"[orchestrator] EOD telegram push failed: {e}",
                        file=sys.stderr,
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

        except Exception as exc:
            self.state_db.update_report_status(
                report_id,
                status="failed",
                failure_reason=f"{type(exc).__name__}: {exc}",
                duration_seconds=time.perf_counter() - start,
            )
            raise

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
