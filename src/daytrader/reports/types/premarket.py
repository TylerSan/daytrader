"""Premarket type handler.

Flow per generate():
    fetch multi-TF bars (W/D/4H/1H for MES) → build prompt → call AI →
    validate output → return GenerationOutcome (caller persists / writes).

Plan extraction and persistence happen in the orchestrator, not here.
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
    """Generate the premarket report — fetch + AI + validate."""

    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbol: str = "MES",
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
    ) -> None:
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbol = symbol
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()

    def generate(
        self,
        context: ReportContext,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
    ) -> GenerationOutcome:
        bars_by_tf: dict[str, list[OHLCV]] = {}
        for tf in PREMARKET_TFS:
            bars_by_tf[tf] = self.ib_client.get_bars(
                symbol=self.symbol,
                timeframe=tf,
                bars=BARS_PER_TF[tf],
            )

        messages = self.prompt_builder.build_premarket(
            context=context,
            bars_by_tf=bars_by_tf,
            news_items=news_items or [],
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
        )

        ai_result = self.ai_analyst.call(
            messages=messages,
            max_tokens=8192,
        )
        validation = self.validator.validate(
            ai_result.text, report_type="premarket"
        )
        return GenerationOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
        )
