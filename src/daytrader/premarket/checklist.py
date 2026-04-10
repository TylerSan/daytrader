"""Pre-market checklist engine — orchestrates collection and rendering."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from daytrader.premarket.analyzers.ai_analyst import (
    build_analysis_prompt,
    invoke_claude_analysis,
    translate_headlines,
)
from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.renderers.cards import CardGenerator
from daytrader.premarket.renderers.markdown import MarkdownRenderer

_log = logging.getLogger(__name__)


class PremarketChecklist:
    def __init__(
        self,
        collector: MarketDataCollector,
        renderers: list | None = None,
        obsidian_daily_path: Path | None = None,
        cards_output_dir: str = "data/exports/images",
    ) -> None:
        self._collector = collector
        self._renderers = renderers or []
        self._obsidian_path = obsidian_daily_path
        self._card_generator = CardGenerator(output_dir=cards_output_dir)

    def _generate_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        """Generate info cards, returning successfully created paths. Never raises."""
        try:
            return self._card_generator.generate_premarket_cards(results, target_date)
        except Exception as e:
            _log.warning("Card generation failed: %s", e)
            return []

    def _translate_news(self, results: dict[str, CollectorResult]) -> None:
        """Translate English news headlines to Chinese in-place. Never raises."""
        news = results.get("news")
        if not news or not news.success or not news.data.get("headlines"):
            return

        headlines = [item.get("title", "") for item in news.data["headlines"]]
        headlines = [h for h in headlines if h]
        if not headlines:
            return

        _log.info("Translating %d news headlines to Chinese...", len(headlines))
        translations = translate_headlines(headlines)
        if not translations:
            _log.warning("News translation unavailable; showing English only")
            return

        for item in news.data["headlines"]:
            title = item.get("title", "")
            if title in translations:
                item["title_zh"] = translations[title]

    async def run(self, target_date: date | None = None) -> str:
        target_date = target_date or date.today()
        results = await self._collector.collect_all()
        card_images = self._generate_cards(results, target_date)

        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(
                    results, date=target_date, card_images=card_images
                )
                renderer.render_and_save(
                    results,
                    date=target_date,
                    obsidian_path=self._obsidian_path,
                    card_images=card_images,
                )

        return report

    async def run_full(self, target_date: date | None = None) -> str:
        """Run full pipeline: data + cards + AI analysis, rendered into one report.

        Invokes Claude CLI to generate AI analysis. If AI invocation fails or
        times out, the report is still saved (without AI section).
        """
        target_date = target_date or date.today()
        results = await self._collector.collect_all()
        card_images = self._generate_cards(results, target_date)

        # Translate news headlines to Chinese (best-effort)
        self._translate_news(results)

        # Invoke AI analysis (best-effort, may return "" on failure)
        ai_prompt = build_analysis_prompt(results)
        _log.info("Invoking Claude for AI analysis (this may take a few minutes)...")
        ai_analysis = invoke_claude_analysis(ai_prompt)
        if ai_analysis:
            _log.info("AI analysis received (%d chars)", len(ai_analysis))
        else:
            _log.warning("AI analysis unavailable; report will be saved without it")

        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(
                    results,
                    date=target_date,
                    ai_analysis=ai_analysis,
                    card_images=card_images,
                )
                renderer.render_and_save(
                    results,
                    date=target_date,
                    ai_analysis=ai_analysis,
                    obsidian_path=self._obsidian_path,
                    card_images=card_images,
                )

        return report

    async def run_with_prompt(self, target_date: date | None = None) -> tuple[str, str]:
        """Run collection and return (data_report, ai_prompt)."""
        target_date = target_date or date.today()
        results = await self._collector.collect_all()
        card_images = self._generate_cards(results, target_date)

        report = ""
        for renderer in self._renderers:
            if isinstance(renderer, MarkdownRenderer):
                report = renderer.render(
                    results, date=target_date, card_images=card_images
                )
                renderer.render_and_save(
                    results,
                    date=target_date,
                    obsidian_path=self._obsidian_path,
                    card_images=card_images,
                )

        ai_prompt = build_analysis_prompt(results)
        return report, ai_prompt
