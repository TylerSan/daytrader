"""BaseCadenceGenerator — abstract template-method pattern for all cadences.

Phase 5.5 (2026-05-05): introduces a shared scaffold for the 4 new cadences
(intraday-4h-1, intraday-4h-2, night, asia). Premarket and EOD are explicitly
NOT migrated to this base class in this phase per user constraint
"不要影响已实现的功能". Phase 5.6 will retrofit them later.

Design: subclass overrides _build_prompt + report_type + tfs + bars_per_tf.
Optional hooks (_maybe_*) default to skip — subclass overrides only what
the cadence actually needs (e.g. retrospective only enabled in 4h-2 and EOD).
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient, OHLCV
from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult
from daytrader.reports.core.context_loader import ReportContext
from daytrader.reports.core.output_validator import OutputValidator, ValidationResult
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.futures_data.futures_section import (
    FuturesSection,
    build_futures_section,
)


@dataclass(frozen=True)
class CadenceOutcome:
    """Output of BaseCadenceGenerator.generate().

    Mirrors EODOutcome shape so orchestrator can use the same
    warnings → state.failures pipeline (I1 fix pattern).
    """
    report_text: str
    ai_result: AIResult
    validation: ValidationResult
    bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] | None = None
    warnings: tuple[str, ...] = ()


class BaseCadenceGenerator(ABC):
    """Common cadence generation pipeline.

    Subclasses MUST implement: report_type, tfs, bars_per_tf, _build_prompt.
    Subclasses MAY override: _maybe_fetch_sentiment, _maybe_read_plan,
        _maybe_fetch_trades, _maybe_compose_retrospective,
        _maybe_compose_tomorrow.
    """

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

    # --- abstract methods (subclass MUST implement) ---

    @property
    @abstractmethod
    def report_type(self) -> str:
        """Identifier for state.db reports table + validator dispatch."""

    @property
    @abstractmethod
    def tfs(self) -> tuple[str, ...]:
        """TFs to fetch for multi-TF analysis (e.g. ('1D', '4H', '1H'))."""

    @property
    @abstractmethod
    def bars_per_tf(self) -> dict[str, int]:
        """How many bars to fetch per TF (e.g. {'1D': 10, '4H': 12})."""

    @abstractmethod
    def _build_prompt(self, **inputs) -> list[dict[str, Any]]:
        """Build the AI message list. Cadence-specific."""

    # --- optional hooks (default = skip) ---

    def _maybe_fetch_sentiment(self) -> str:
        """Override to fetch fresh sentiment via Phase 4.5 SentimentSection.
        Default: return empty string (caller may pass premarket cache via
        sentiment_md kwarg)."""
        return ""

    def _maybe_read_plan(self, date_et: str) -> dict[str, str]:
        """Override to read today's premarket plan blocks per symbol.
        Default: return empty dict (no plan recheck needed)."""
        return {}

    def _maybe_fetch_trades(self, date_et: str) -> list[dict[str, Any]]:
        """Override to fetch today's trades from journal DB.
        Default: empty list (no trade reflection needed)."""
        return []

    def _maybe_compose_retrospective(
        self,
        plans: dict[str, str],
        trades: list[dict[str, Any]],
        date_et: str,
    ) -> str:
        """Override to run PlanRetrospective + persist + render markdown.
        Default: empty string (no retrospective for this cadence)."""
        return ""

    def _maybe_compose_tomorrow(self, **kwargs) -> str:
        """Override to build tomorrow's preliminary plan (EOD only).
        Default: empty string."""
        return ""

    # --- shared pipeline (template method) ---

    def generate(
        self,
        context: ReportContext,
        date_et: str,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
        sentiment_md: str = "",
    ) -> CadenceOutcome:
        """Run the cadence pipeline end-to-end.

        Steps: fetch bars → F section → news → sentiment (optional) →
        plan read (optional) → trades fetch (optional) → retrospective
        (optional) → tomorrow (optional) → AI call → validate.
        """
        warnings_list: list[str] = []

        # Step 1: fetch multi-TF bars per symbol.
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] = {}
        for symbol in self.symbols:
            bars_by_symbol_and_tf[symbol] = {}
            for tf in self.tfs:
                try:
                    bars_by_symbol_and_tf[symbol][tf] = self.ib_client.get_bars(
                        symbol=symbol, timeframe=tf,
                        bars=self.bars_per_tf[tf],
                    )
                except Exception as exc:
                    print(
                        f"[base_cadence] WARNING: bars fetch {symbol} {tf} failed: {exc}",
                        file=sys.stderr,
                    )
                    warnings_list.append(
                        f"bars: {symbol} {tf}: {type(exc).__name__}: {str(exc)[:120]}"
                    )
                    bars_by_symbol_and_tf[symbol][tf] = []

        # Step 2: F-section (basis + term + RTH-formed VP).
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
                f"[base_cadence] WARNING: F-section build failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"f_section: {type(exc).__name__}: {str(exc)[:120]}"
            )
            futures_data = None

        # Step 3: news (best-effort).
        if news_items is None:
            news_items = []
            if self.news_collector is not None:
                try:
                    news_items = self.news_collector()
                except Exception as exc:
                    print(
                        f"[base_cadence] WARNING: news fetch failed: {exc}",
                        file=sys.stderr,
                    )
                    warnings_list.append(
                        f"news: {type(exc).__name__}: {str(exc)[:120]}"
                    )

        # Step 4: sentiment (optional — caller may pass cache via kwarg).
        if not sentiment_md:
            try:
                sentiment_md = self._maybe_fetch_sentiment()
            except Exception as exc:
                print(
                    f"[base_cadence] WARNING: sentiment fetch failed: {exc}",
                    file=sys.stderr,
                )
                warnings_list.append(
                    f"sentiment: {type(exc).__name__}: {str(exc)[:120]}"
                )
                sentiment_md = ""

        # Step 5-7: plan read + trades + retrospective (optional hooks).
        try:
            plans = self._maybe_read_plan(date_et)
        except Exception as exc:
            print(
                f"[base_cadence] WARNING: plan_read failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"plan_read: {type(exc).__name__}: {str(exc)[:120]}"
            )
            plans = {}

        try:
            trades = self._maybe_fetch_trades(date_et)
        except Exception as exc:
            print(
                f"[base_cadence] WARNING: trades_fetch failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"trades_fetch: {type(exc).__name__}: {str(exc)[:120]}"
            )
            trades = []

        try:
            retrospective_md = self._maybe_compose_retrospective(
                plans, trades, date_et
            )
        except Exception as exc:
            print(
                f"[base_cadence] WARNING: retrospective failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"retrospective: {type(exc).__name__}: {str(exc)[:120]}"
            )
            retrospective_md = (
                "## 🔄 Plan Retrospective / 计划复盘\n\n"
                f"⚠️ retrospective composition failed: "
                f"{type(exc).__name__}: {str(exc)[:120]}"
            )

        try:
            tomorrow_md = self._maybe_compose_tomorrow(
                bars_by_symbol_and_tf=bars_by_symbol_and_tf,
                trades=trades,
                date_et=date_et,
            )
        except Exception as exc:
            print(
                f"[base_cadence] WARNING: tomorrow failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"tomorrow: {type(exc).__name__}: {str(exc)[:120]}"
            )
            tomorrow_md = ""

        # Step 8: build prompt (cadence-specific).
        messages = self._build_prompt(
            context=context,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            tradable_symbols=self.tradable_symbols,
            news_items=news_items,
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
            futures_data=futures_data,
            sentiment_md=sentiment_md,
            today_plan_blocks=plans,
            today_trades=trades,
            retrospective_md=retrospective_md,
            tomorrow_preliminary_md=tomorrow_md,
        )

        # Step 9: AI call + validate.
        ai_result = self.ai_analyst.call(messages=messages, max_tokens=12288)
        validation = self.validator.validate(
            ai_result.text, report_type=self.report_type
        )

        return CadenceOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            warnings=tuple(warnings_list),
        )
