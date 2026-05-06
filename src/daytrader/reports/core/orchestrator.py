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

    def _make_intraday_fetcher(self):
        """Build the intraday_bar_fetcher closure for PlanRetrospective.

        PlanRetrospective.compose() calls ``fetcher(symbol, date_et)`` to
        get one full RTH session of 5m bars for the simulator. The closure
        pins ``end_time`` to ``date_et 16:00 ET`` (RTH cash close) so:

        1. Same-day 14:00 PT auto-fire (= 17:00 ET) sees a fully-closed
           RTH session ending at 16:00 ET.
        2. Backfill runs (e.g. Tuesday morning re-running Monday's failed
           EOD) still fetch Monday's session, NOT Tuesday morning's
           in-progress data. Pre-fix: end_time=None defaulted to "now"
           and silently corrupted plan_retrospective_daily on backfill.

        Caught 2026-05-05 by code-reviewer agent (C2). 78 5m bars covers
        6.5h × 12 bars/h = one full RTH session.
        """
        def _fetch(symbol: str, date_et: str):
            from datetime import time
            date = datetime.strptime(date_et, "%Y-%m-%d").date()
            end_time = datetime.combine(date, time(16, 0), tzinfo=ET)
            return self.ib_client.get_bars(
                symbol=symbol,
                timeframe="5m",
                bars=78,
                end_time=end_time,
            )
        return _fetch

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

            retrospective = PlanRetrospective(
                plan_parser=plan_parser,
                trade_simulator=simulate_level,
                intraday_bar_fetcher=self._make_intraday_fetcher(),
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

            # I1 fix 2026-05-05: surface non-fatal pipeline failures
            # (e.g. retrospective.compose() blew up but the report still
            # generated) to state.failures so the user can audit them
            # without re-reading the report markdown.
            for warning in outcome.warnings:
                stage, _, reason = warning.partition(": ")
                self.state_db.log_failure(
                    report_type="eod",
                    scheduled_at=run_at,
                    failure_stage=stage or "unknown",
                    failure_reason=reason or warning,
                    retry_count=0,
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

    # --- Phase 5.5 T9: intraday-4h cadences ---

    def _make_intraday_fetcher_for_cadence(self, end_time_et: str):
        """Build intraday_bar_fetcher closure with end_time pinned to
        a specific ET time (e.g. '11:00' for 4h-2, '14:00' for EOD).

        Generalizes _make_intraday_fetcher (which was hardcoded to 16:00 ET).
        Phase 5.5 T9 (2026-05-05).
        """
        def _fetch(symbol: str, date_et: str):
            from datetime import time as _time
            hh, mm = end_time_et.split(":")
            date = datetime.strptime(date_et, "%Y-%m-%d").date()
            end_time = datetime.combine(
                date, _time(int(hh), int(mm)), tzinfo=ET
            )
            return self.ib_client.get_bars(
                symbol=symbol,
                timeframe="5m",
                bars=78,
                end_time=end_time,
            )
        return _fetch

    def run_intraday_4h_1(self, run_at: datetime) -> PipelineResult:
        """Phase 5.5 T9: 07:00 PT cadence. Lightweight (no retrospective,
        no sentiment refresh — uses premarket cache for sentiment if
        available)."""
        from daytrader.reports.types.intraday_4h import (
            IntradayFourHConfig,
        )
        config = IntradayFourHConfig(
            cadence_label="intraday-4h-1",
            do_retrospective=False,
            sentiment_refresh=False,
            sentiment_time_window="",
            news_time_window="past 1h",
            intraday_end_time_et="10:00",
        )
        return self._run_cadence_intraday_4h(config, run_at, "0700PT-4H1")

    def run_intraday_4h_2(self, run_at: datetime) -> PipelineResult:
        """Phase 5.5 T9: 11:00 PT cadence with full retrospective +
        sentiment refresh."""
        from daytrader.reports.types.intraday_4h import (
            IntradayFourHConfig,
        )
        config = IntradayFourHConfig(
            cadence_label="intraday-4h-2",
            do_retrospective=True,
            sentiment_refresh=True,
            sentiment_time_window="past 5h",
            news_time_window="past 5h",
            intraday_end_time_et="14:00",
        )
        return self._run_cadence_intraday_4h(config, run_at, "1100PT-4H2")

    def _run_cadence_intraday_4h(
        self,
        config,
        run_at: datetime,
        time_label: str,
    ) -> PipelineResult:
        """Common pipeline for both 4h-1 and 4h-2 cadences.
        Mirrors run_eod but uses IntradayFourHGenerator + obsidian_writer.write_intraday_4h.
        """
        import sys

        start = time.perf_counter()

        run_at_utc = run_at if run_at.tzinfo else run_at.replace(tzinfo=timezone.utc)
        run_at_utc = run_at_utc.astimezone(timezone.utc)
        date_et = run_at_utc.astimezone(ET).date().isoformat()
        time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
        time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

        if self.state_db.already_generated_today(config.cadence_label, date_et):
            return PipelineResult(
                success=True, report_id=None, report_path=None,
                skipped_idempotent=True,
            )

        report_id = self.state_db.insert_report(
            report_type=config.cadence_label,
            date_et=date_et,
            time_pt=time_pt_str,
            time_et=time_et_str,
            status="pending",
            created_at=run_at_utc,
        )

        try:
            loader = ContextLoader(
                contract_path=self.contract_path,
                journal_db_path=self.journal_db_path,
            )
            context = loader.load()

            # Sentiment: 4h-1 reuses premarket; 4h-2 refreshes inside generator
            sentiment_md = ""
            if not config.sentiment_refresh:
                # Fetch the most recent successful premarket sentiment from
                # today's premarket report markdown if available.
                sentiment_md = self._read_today_premarket_sentiment(date_et)

            from daytrader.reports.eod.plan_reader import PremarketPlanReader
            from daytrader.reports.eod.plan_parser import PremarketPlanParser
            from daytrader.reports.eod.trade_simulator import simulate_level
            from daytrader.reports.eod.trades_query import TodayTradesQuery
            from daytrader.reports.eod.retrospective import PlanRetrospective
            from daytrader.reports.futures_data.term_prices import TermPricesFetcher
            from daytrader.reports.futures_data.underlying_prices import (
                UnderlyingPriceFetcher,
            )
            from daytrader.reports.types.intraday_4h import IntradayFourHGenerator

            plan_reader = PremarketPlanReader(
                vault_path=self.vault_root,
                daily_folder=self.daily_folder,
            )
            plan_parser = PremarketPlanParser()
            trades_query = TodayTradesQuery(self.journal_db_path)

            retrospective = None
            if config.do_retrospective:
                retrospective = PlanRetrospective(
                    plan_parser=plan_parser,
                    trade_simulator=simulate_level,
                    intraday_bar_fetcher=self._make_intraday_fetcher_for_cadence(
                        end_time_et=config.intraday_end_time_et,
                    ),
                    trades_query=trades_query,
                    state_db_path=self.state_db._path,
                )

            generator = IntradayFourHGenerator(
                config=config,
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
            )

            outcome = generator.generate(
                context=context,
                date_et=date_et,
                run_timestamp_pt=f"{time_pt_str} PT",
                run_timestamp_et=f"{time_et_str} ET",
                sentiment_md=sentiment_md,
            )

            for warning in outcome.warnings:
                stage, _, reason = warning.partition(": ")
                self.state_db.log_failure(
                    report_type=config.cadence_label,
                    scheduled_at=run_at_utc,
                    failure_stage=stage or "unknown",
                    failure_reason=reason or warning,
                    retry_count=0,
                )

            if not outcome.validation.ok:
                self.state_db.update_report_status(
                    report_id, status="failed",
                    failure_reason=(
                        f"validation missing: {outcome.validation.missing}"
                    ),
                    tokens_input=outcome.ai_result.input_tokens,
                    tokens_output=outcome.ai_result.output_tokens,
                    duration_seconds=time.perf_counter() - start,
                )
                return PipelineResult(
                    success=False, report_id=report_id, report_path=None,
                    failure_reason=(
                        f"validation: missing sections "
                        f"{outcome.validation.missing}"
                    ),
                )

            writer = ObsidianWriter(
                vault_root=self.vault_root,
                fallback_dir=self.fallback_dir,
                daily_folder=self.daily_folder,
            )
            write_result = writer.write_intraday_4h(
                date_iso=date_et,
                time_label=time_label,
                content=outcome.report_text,
            )

            # Best-effort delivery: charts, PDF, Telegram
            chart_paths: list[Path] = []
            if self.chart_renderer is not None and outcome.bars_by_symbol_and_tf:
                try:
                    artifacts = self.chart_renderer.render_all(
                        bars_by_symbol_and_tf=outcome.bars_by_symbol_and_tf,
                        today=date_et,
                    )
                    chart_paths = list(artifacts.tf_stack_paths.values())
                except Exception as e:
                    print(
                        f"[orchestrator] {config.cadence_label} chart render failed: {e}",
                        file=sys.stderr,
                    )

            pdf_path: Path | None = None
            if self.pdf_renderer is not None:
                try:
                    pdf_path = self.pdf_renderer.render_to_pdf(
                        markdown_text=outcome.report_text,
                        title=f"{config.cadence_label} {date_et}",
                        filename_stem=f"{date_et}-{time_label}",
                    )
                except Exception as e:
                    print(
                        f"[orchestrator] {config.cadence_label} PDF failed: {e}",
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
                    print(
                        f"[orchestrator] {config.cadence_label} telegram failed: {e}",
                        file=sys.stderr,
                    )

            duration = time.perf_counter() - start
            self.state_db.update_report_status(
                report_id, status="success",
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
                success=True, report_id=report_id,
                report_path=write_result.path,
            )

        except Exception as exc:
            duration = time.perf_counter() - start
            self.state_db.update_report_status(
                report_id, status="failed",
                failure_reason=f"{type(exc).__name__}: {exc}",
                duration_seconds=duration,
            )
            return PipelineResult(
                success=False, report_id=report_id, report_path=None,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )

    def _read_today_premarket_sentiment(self, date_et: str) -> str:
        """Read today's premarket report from Obsidian (or fallback) and
        extract the D. 情绪面 section verbatim. If not found, return ''."""
        candidates = [
            self.vault_root / self.daily_folder / f"{date_et}-premarket.md",
            self.fallback_dir / f"{date_et}-premarket.md",
        ]
        for p in candidates:
            if p.exists():
                content = p.read_text()
                # Find D. 情绪面 section (between "## D." and next "## ")
                import re
                m = re.search(
                    r"^## D\.\s*情绪面.*?(?=^## )",
                    content, re.MULTILINE | re.DOTALL,
                )
                if m:
                    return m.group(0).strip()
        return ""

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
