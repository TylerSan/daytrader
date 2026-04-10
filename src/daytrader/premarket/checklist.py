"""Pre-market checklist engine — orchestrates collection and rendering."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from daytrader.premarket.analyzers.ai_analyst import build_analysis_prompt
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
