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

        messages = self.prompt_builder.build_premarket(
            context=context,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            tradable_symbols=self.tradable_symbols,
            news_items=news_items or [],
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
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
