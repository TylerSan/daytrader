"""IntradayFourHGenerator — concrete BaseCadenceGenerator subclass.

Used by both intraday-4h-1 (07:00 PT) and intraday-4h-2 (11:00 PT).
Differentiated by IntradayFourHConfig:
  - 4h-1: do_retrospective=False, sentiment_refresh=False
  - 4h-2: do_retrospective=True, sentiment_refresh=True (past 5h window)

Phase 5.5 T7 (2026-05-05).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.reports.core.ai_analyst import AIAnalyst
from daytrader.reports.core.output_validator import OutputValidator
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.sentiment import SentimentSection
from daytrader.reports.types.base import BaseCadenceGenerator


@dataclass(frozen=True)
class IntradayFourHConfig:
    """Differentiates 4h-1 vs 4h-2 behavior. Same generator class, two configs."""
    cadence_label: str           # "intraday-4h-1" | "intraday-4h-2"
    do_retrospective: bool       # False (4h-1) | True (4h-2)
    sentiment_refresh: bool      # False (4h-1) | True (4h-2)
    sentiment_time_window: str   # "" (no refresh) | "past 5h"
    news_time_window: str        # "past 1h" (4h-1) | "past 5h" (4h-2)
    intraday_end_time_et: str    # "10:00" (4h-1) | "14:00" (4h-2) — for retrospective fetcher


class IntradayFourHGenerator(BaseCadenceGenerator):
    """Generates intraday-4h reports (both 4h-1 and 4h-2 cadences)."""

    def __init__(
        self,
        config: IntradayFourHConfig,
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
        # Cadence-specific deps:
        plan_reader=None,
        plan_parser=None,
        trades_query=None,
        retrospective=None,
    ) -> None:
        super().__init__(
            ib_client=ib_client,
            ai_analyst=ai_analyst,
            symbols=symbols,
            tradable_symbols=tradable_symbols,
            prompt_builder=prompt_builder,
            validator=validator,
            underlying_price_fetcher=underlying_price_fetcher,
            term_price_fetcher=term_price_fetcher,
            tick_sizes=tick_sizes,
            news_collector=news_collector,
        )
        self._config = config
        self.plan_reader = plan_reader
        self.plan_parser = plan_parser
        self.trades_query = trades_query
        self.retrospective = retrospective

    @property
    def report_type(self) -> str:
        return "intraday-4h"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("1D", "4H", "1H")

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"1D": 10, "4H": 12, "1H": 24}

    # --- hook overrides ---

    def _maybe_fetch_sentiment(self) -> str:
        if not self._config.sentiment_refresh:
            return ""
        try:
            section = SentimentSection(
                symbols=self.symbols,
                time_window=self._config.sentiment_time_window,
            )
            result = section.collect()
            return section.render(result)
        except Exception as exc:
            print(
                f"[intraday_4h] WARNING: sentiment refresh failed: {exc}",
                file=sys.stderr,
            )
            return ""

    def _maybe_read_plan(self, date_et: str) -> dict[str, str]:
        if self.plan_reader is None:
            return {}
        try:
            return self.plan_reader.read_today_plan(date_et)
        except Exception as exc:
            print(
                f"[intraday_4h] WARNING: plan read failed: {exc}",
                file=sys.stderr,
            )
            return {}

    def _maybe_fetch_trades(self, date_et: str) -> list[dict[str, Any]]:
        if self.trades_query is None:
            return []
        try:
            return self.trades_query.trades_for_date(date_et)
        except Exception as exc:
            print(
                f"[intraday_4h] WARNING: trades fetch failed: {exc}",
                file=sys.stderr,
            )
            return []

    def _maybe_compose_retrospective(
        self,
        plans: dict[str, str],
        trades: list[dict[str, Any]],
        date_et: str,
    ) -> str:
        if not self._config.do_retrospective:
            return ""
        if not plans:
            return ""
        if self.retrospective is None:
            return ""
        rows = self.retrospective.compose(
            plans=plans,
            symbols=self.symbols,
            date_et=date_et,
            tick_sizes=self.tick_sizes,
        )
        if not rows:
            return ""
        self.retrospective.persist(rows)
        return self._render_retrospective_block(rows)

    @staticmethod
    def _render_retrospective_block(rows) -> str:
        if not rows:
            return ""
        lines = ["## 🔄 Plan Retrospective / 计划复盘"]
        for symbol, row in rows.items():
            lines.append(f"\n### {symbol}")
            lines.append(
                f"- Levels triggered: {row.triggered_count}/{row.total_levels}"
            )
            lines.append(
                f"- sim total: {row.sim_total_r:+.2f}R, "
                f"actual: {row.actual_total_r:+.2f}R, "
                f"gap: {row.gap_r:+.2f}R"
            )
            if row.open_trades_count > 0:
                lines.append(
                    f"- ⚠️ {row.open_trades_count} open trade(s) "
                    "— unrealized R not in actual"
                )
        lines.append("")
        lines.append(
            "> 4h-2 retrospective covers RTH 06:30 PT → 11:00 PT. "
            "Full session retrospective in EOD 14:00 PT."
        )
        return "\n".join(lines)

    def _build_prompt(self, **inputs) -> list[dict[str, Any]]:
        return self.prompt_builder.build_intraday_4h(
            cadence_label=self._config.cadence_label, **inputs
        )
