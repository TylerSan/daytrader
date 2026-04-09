"""Pre-market checklist engine — orchestrates collection, AI analysis, and rendering."""

from __future__ import annotations

from datetime import date

from daytrader.premarket.analyzers.ai_analyst import AIAnalyst
from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer


class PremarketChecklist:
    def __init__(
        self,
        collector: MarketDataCollector,
        renderers: list | None = None,
        ai_analyst: AIAnalyst | None = None,
    ) -> None:
        self._collector = collector
        self._renderers = renderers or []
        self._ai_analyst = ai_analyst

    async def run(self, target_date: date | None = None) -> str:
        target_date = target_date or date.today()

        # Phase 1: Collect all market data
        results = await self._collector.collect_all()

        # Phase 2: AI Analysis (if enabled)
        ai_analysis = ""
        if self._ai_analyst:
            ai_analysis = await self._ai_analyst.analyze(results)

        # Phase 3: Render report
        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(
                    results, date=target_date, ai_analysis=ai_analysis
                )
                renderer.render_and_save(
                    results, date=target_date, ai_analysis=ai_analysis
                )

        return report
