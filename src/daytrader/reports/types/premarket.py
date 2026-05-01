"""Premarket type handler (multi-instrument).

Flow per generate():
    For each symbol: fetch multi-TF bars (W/D/4H/1H).
    Build single integrated prompt with per-symbol bars + tradable list.
    AI call → validate → return GenerationOutcome.

Plan extraction (per tradable instrument) and persistence happen in the
orchestrator, not here.
"""

from __future__ import annotations

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
from daytrader.reports.futures_data.futures_section import (
    FuturesSection, build_futures_section,
)


@dataclass(frozen=True)
class GenerationOutcome:
    report_text: str
    ai_result: AIResult
    validation: ValidationResult


PREMARKET_TFS = ("1W", "1D", "4H", "1H")
BARS_PER_TF: dict[str, int] = {"1W": 52, "1D": 200, "4H": 50, "1H": 24}


class PremarketGenerator:
    """Generate the premarket report — multi-symbol fetch + AI + validate."""

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
                raise ValueError(f"tradable symbol {s!r} not in symbols list {symbols}")
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()
        self.underlying_price_fetcher = underlying_price_fetcher
        self.term_price_fetcher = term_price_fetcher
        self.tick_sizes = tick_sizes
        self.news_collector = news_collector

    def generate(
        self,
        context: ReportContext,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
    ) -> GenerationOutcome:
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] = {}
        for symbol in self.symbols:
            bars_by_symbol_and_tf[symbol] = {}
            for tf in PREMARKET_TFS:
                bars_by_symbol_and_tf[symbol][tf] = self.ib_client.get_bars(
                    symbol=symbol,
                    timeframe=tf,
                    bars=BARS_PER_TF[tf],
                )

        # Build F-section data (best-effort; per-symbol failures captured inside)
        futures_data: FuturesSection | None = None
        try:
            tick_sizes = self.tick_sizes or {s: 0.25 for s in self.symbols}
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
                tick_sizes=tick_sizes,
            )
        except Exception as exc:
            import sys
            print(
                f"[premarket_generator] WARNING: F-section build failed: {exc}",
                file=sys.stderr,
            )
            futures_data = None

        # Fetch news (best-effort)
        if news_items is None:
            news_items = []
            if self.news_collector is not None:
                try:
                    news_items = self.news_collector()
                except Exception as exc:
                    import sys
                    print(
                        f"[premarket_generator] WARNING: news fetch failed: {exc}",
                        file=sys.stderr,
                    )
                    news_items = []

        messages = self.prompt_builder.build_premarket(
            context=context,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            tradable_symbols=self.tradable_symbols,
            news_items=news_items or [],
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
            futures_data=futures_data,
        )

        ai_result = self.ai_analyst.call(
            messages=messages,
            max_tokens=12288,
        )
        validation = self.validator.validate(
            ai_result.text, report_type="premarket"
        )
        return GenerationOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
        )
