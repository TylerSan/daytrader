"""EODGenerator — multi-symbol EOD report generation pipeline.

Mirrors PremarketGenerator pattern. Composes:
  - Multi-TF bars (W/D/4H per symbol) freshly fetched from IB
  - FuturesSection (basis + term + RTH-formed VP, today's close)
  - SentimentSection result (passed in as ``sentiment_md`` by orchestrator)
  - PremarketPlanReader -> PremarketPlanParser -> Plan
  - TodayTradesQuery -> trade ledger + audit
  - PlanRetrospective.compose -> per-symbol retrospective + persist
  - TomorrowPreliminaryPlan.build_input_data
  - PromptBuilder.build_eod -> messages
  - AIAnalyst.call(messages) -> markdown report
  - OutputValidator.validate

Plan extraction (per tradable instrument) and persistence happen in the
orchestrator (Phase 5 T10), not here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient, OHLCV
from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult
from daytrader.reports.core.context_loader import ReportContext
from daytrader.reports.core.output_validator import (
    OutputValidator,
    ValidationResult,
)
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
from daytrader.reports.futures_data.futures_section import (
    FuturesSection,
    build_futures_section,
)


# EOD uses W/D/4H per symbol per spec §6 / template (no 1H — daily review only).
EOD_TFS = ("1W", "1D", "4H")
BARS_PER_TF: dict[str, int] = {"1W": 52, "1D": 200, "4H": 50}


@dataclass(frozen=True)
class EODOutcome:
    """Output of EODGenerator.generate()."""
    report_text: str
    ai_result: AIResult
    validation: ValidationResult
    retrospective_rows: dict[str, RetrospectiveRow]
    bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] | None = None


class EODGenerator:
    """Generate the EOD report — multi-symbol fetch + retrospective + AI + validate."""

    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher=None,
        term_price_fetcher=None,
        tick_sizes: dict[str, float] | None = None,
        news_collector=None,
        # EOD-specific deps:
        plan_reader=None,
        plan_parser=None,
        trades_query=None,
        retrospective=None,
        tomorrow_planner=None,
    ) -> None:
        if not symbols:
            raise ValueError("symbols must be non-empty")
        for s in tradable_symbols:
            if s not in symbols:
                raise ValueError(
                    f"tradable symbol {s!r} not in symbols list {symbols}"
                )
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()
        self.underlying_price_fetcher = underlying_price_fetcher
        self.term_price_fetcher = term_price_fetcher
        self.tick_sizes = tick_sizes or {s: 0.25 for s in symbols}
        self.news_collector = news_collector
        self.plan_reader = plan_reader
        self.plan_parser = plan_parser
        self.trades_query = trades_query
        self.retrospective = retrospective
        self.tomorrow_planner = tomorrow_planner

    def generate(
        self,
        context: ReportContext,
        date_et: str,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
        sentiment_md: str = "",
    ) -> EODOutcome:
        """Run the EOD pipeline end-to-end and return the outcome."""

        # Step 1: fetch multi-TF bars per symbol (W/D/4H).
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] = {}
        for symbol in self.symbols:
            bars_by_symbol_and_tf[symbol] = {}
            for tf in EOD_TFS:
                bars_by_symbol_and_tf[symbol][tf] = self.ib_client.get_bars(
                    symbol=symbol,
                    timeframe=tf,
                    bars=BARS_PER_TF[tf],
                )

        # Step 2: F-section (today's post-cash-close basis + term + VP).
        futures_data: FuturesSection | None = None
        try:
            underlying_prices = (
                self.underlying_price_fetcher(self.symbols)
                if self.underlying_price_fetcher else {}
            )
            term_prices = (
                self.term_price_fetcher(self.symbols)
                if self.term_price_fetcher else {}
            )
            futures_data = build_futures_section(
                ib_client=self.ib_client,
                symbols=self.symbols,
                underlying_prices=underlying_prices,
                term_prices=term_prices,
                tick_sizes=self.tick_sizes,
            )
        except Exception as exc:
            print(
                f"[eod_generator] WARNING: F-section build failed: {exc}",
                file=sys.stderr,
            )
            futures_data = None

        # Step 3: news (best-effort, mirrors PremarketGenerator).
        if news_items is None:
            news_items = []
            if self.news_collector is not None:
                try:
                    news_items = self.news_collector()
                except Exception as exc:
                    print(
                        f"[eod_generator] WARNING: news fetch failed: {exc}",
                        file=sys.stderr,
                    )
                    news_items = []

        # Step 4: read today's premarket plan blocks (verbatim per symbol).
        today_plan_blocks: dict[str, str] = {}
        if self.plan_reader is not None:
            try:
                today_plan_blocks = self.plan_reader.read_today_plan(date_et)
            except Exception as exc:
                print(
                    f"[eod_generator] WARNING: plan_reader failed: {exc}",
                    file=sys.stderr,
                )
                today_plan_blocks = {}

        # Step 5: query today's trades + audit.
        trades: list[dict[str, Any]] = []
        trades_audit: dict[str, Any] = {
            "count": 0,
            "daily_r": 0.0,
            "violations_total": 0,
            "screenshots_complete": 0,
            "per_trade_violations": {},
        }
        if self.trades_query is not None:
            try:
                trades = self.trades_query.trades_for_date(date_et)
                trades_audit = self.trades_query.audit_summary(trades)
            except Exception as exc:
                print(
                    f"[eod_generator] WARNING: trades_query failed: {exc}",
                    file=sys.stderr,
                )

        today_trades_md = self._render_trades_block(trades, trades_audit)

        # Step 6: plan retrospective + persist.
        retrospective_rows: dict[str, RetrospectiveRow] = {}
        retrospective_md = ""
        if self.retrospective is not None and today_plan_blocks:
            try:
                retrospective_rows = self.retrospective.compose(
                    plans=today_plan_blocks,
                    symbols=self.symbols,
                    date_et=date_et,
                    tick_sizes=self.tick_sizes,
                )
                self.retrospective.persist(retrospective_rows)
                retrospective_md = self._render_retrospective_block(
                    retrospective_rows
                )
            except Exception as exc:
                print(
                    f"[eod_generator] WARNING: retrospective failed: {exc}",
                    file=sys.stderr,
                )
                retrospective_md = (
                    "## 🔄 Plan Retrospective / 计划复盘\n\n"
                    f"⚠️ retrospective composition failed: {exc}"
                )
        else:
            retrospective_md = (
                "## 🔄 Plan Retrospective / 计划复盘\n\n"
                "⚠️ 今日 premarket plan 未找到 (premarket 可能 fail) — "
                "无法做 plan vs PA 复盘"
            )

        # Step 7: tomorrow preliminary input grounding.
        tomorrow_md = ""
        if self.tomorrow_planner is not None:
            try:
                tomorrow_md = self.tomorrow_planner.build_input_data(
                    today_bars=bars_by_symbol_and_tf,
                    today_retrospective=retrospective_rows,
                    sentiment_md=sentiment_md,
                )
            except Exception as exc:
                print(
                    f"[eod_generator] WARNING: tomorrow_planner failed: {exc}",
                    file=sys.stderr,
                )
                tomorrow_md = ""

        # Step 8: build prompt.
        messages = self.prompt_builder.build_eod(
            context=context,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            tradable_symbols=self.tradable_symbols,
            news_items=news_items or [],
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
            futures_data=futures_data,
            sentiment_md=sentiment_md,
            today_plan_blocks=today_plan_blocks,
            retrospective_md=retrospective_md,
            today_trades_md=today_trades_md,
            tomorrow_preliminary_md=tomorrow_md,
        )

        # Step 9: call AI + validate.
        ai_result = self.ai_analyst.call(
            messages=messages,
            max_tokens=12288,
        )
        validation = self.validator.validate(ai_result.text, report_type="eod")

        return EODOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
            retrospective_rows=retrospective_rows,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
        )

    @staticmethod
    def _render_trades_block(
        trades: list[dict[str, Any]],
        audit: dict[str, Any],
    ) -> str:
        if not trades:
            return (
                "## 今日交易档案 / Today's Trade Archive\n\n"
                "今天没交易（0/3）。\n\n"
                "**原因分析**: AI 应在此评估 — 是 setup 真不满足"
                "（discipline ✓），还是没在屏幕前（execution gap）？"
                "参考 🔄 Plan Retrospective 段对比。\n"
            )
        lines = [
            "## 今日交易档案 / Today's Trade Archive\n",
            "| # | symbol | side | entry | exit | pnl | violations | screenshots |",
            "|---|---|---|---|---|---|---|---|",
        ]
        per_trade_violations = audit.get("per_trade_violations", {}) or {}
        for i, t in enumerate(trades, start=1):
            notes = (t.get("notes") or "").lower()
            screenshots_done = "yes" if "screenshots: yes" in notes else "no"
            violations = per_trade_violations.get(t.get("id"), [])
            lines.append(
                f"| {i} | {t.get('symbol')} | {t.get('direction')} | "
                f"{t.get('entry_price')} | {t.get('exit_price') or '-'} | "
                f"{t.get('pnl_usd') if t.get('pnl_usd') is not None else '-'} | "
                f"{violations} | {screenshots_done} |"
            )
        lines.append("")
        lines.append(
            f"**Audit summary**: {audit.get('count', 0)} trades, "
            f"daily R={audit.get('daily_r', 0.0):+.2f}, "
            f"violations={audit.get('violations_total', 0)}, "
            f"screenshots complete="
            f"{audit.get('screenshots_complete', 0)}/{audit.get('count', 0)}"
        )
        return "\n".join(lines)

    @staticmethod
    def _render_retrospective_block(
        rows: dict[str, RetrospectiveRow],
    ) -> str:
        if not rows:
            return (
                "## 🔄 Plan Retrospective / 计划复盘\n\n"
                "(no retrospective available)"
            )
        lines = ["## 🔄 Plan Retrospective / 计划复盘"]
        for symbol, row in rows.items():
            lines.append(f"\n### {symbol}")
            lines.append(
                "| # | level | type | direction | triggered? | touch | "
                "sim entry | sim stop | sim target | outcome | sim R |"
            )
            lines.append(
                "|---|---|---|---|---|---|---|---|---|---|---|"
            )
            for i, (lvl, out) in enumerate(row.per_level_outcomes, start=1):
                triggered = "✅" if out.triggered else "❌"
                lines.append(
                    f"| {i} | {lvl.price} ({lvl.source}) | {lvl.level_type} | "
                    f"{lvl.direction} | {triggered} | "
                    f"{out.touch_time_pt or '-'} | "
                    f"{out.sim_entry if out.sim_entry is not None else '-'} | "
                    f"{out.sim_stop if out.sim_stop is not None else '-'} | "
                    f"{out.sim_target if out.sim_target is not None else '-'} | "
                    f"{out.outcome} | {out.sim_r:+.2f} |"
                )
            lines.append(
                f"\n**{symbol} summary**: "
                f"{row.triggered_count}/{row.total_levels} triggered, "
                f"sim total {row.sim_total_r:+.2f}R, "
                f"actual {row.actual_total_r:+.2f}R, "
                f"gap {row.gap_r:+.2f}R"
            )
        lines.append("")
        lines.append(
            "> Caveat: simulator assumes 'level touched = setup triggered'. "
            "v1 has no footprint Level 3 / 5:1 / volume verification — "
            "treat sim outcomes as upper-bound. v2 will integrate "
            "MotiveWave footprint replay."
        )
        return "\n".join(lines)
