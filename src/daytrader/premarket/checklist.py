"""Pre-market checklist engine — orchestrates collection and rendering."""

from __future__ import annotations

from datetime import date

from daytrader.premarket.analyzers.ai_analyst import build_analysis_prompt
from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer


class PremarketChecklist:
    def __init__(
        self,
        collector: MarketDataCollector,
        renderers: list | None = None,
    ) -> None:
        self._collector = collector
        self._renderers = renderers or []

    async def run(self, target_date: date | None = None) -> str:
        target_date = target_date or date.today()
        results = await self._collector.collect_all()

        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(results, date=target_date)
                renderer.render_and_save(results, date=target_date)

        return report

    async def run_with_prompt(self, target_date: date | None = None) -> tuple[str, str]:
        """Run collection and return (data_report, ai_prompt).

        The ai_prompt is designed to be fed to Claude Code for AI analysis.
        """
        target_date = target_date or date.today()
        results = await self._collector.collect_all()

        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(results, date=target_date)
                renderer.render_and_save(results, date=target_date)

        ai_prompt = build_analysis_prompt(results)
        return report, ai_prompt
