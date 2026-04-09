"""Weekly plan CLI commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.collectors.futures import FuturesCollector
from daytrader.premarket.collectors.sectors import SectorCollector
from daytrader.premarket.collectors.levels import LevelsCollector
from daytrader.premarket.weekly import WeeklyPlanGenerator


def _build_weekly_generator(output_dir: str = "data/exports") -> WeeklyPlanGenerator:
    collector = MarketDataCollector()
    collector.register(FuturesCollector())
    collector.register(SectorCollector())
    collector.register(LevelsCollector())
    return WeeklyPlanGenerator(collector=collector, output_dir=output_dir)


@click.command("run")
@click.option("--push", is_flag=True, help="Push plan to notification channels")
def weekly_run(push: bool) -> None:
    """Generate weekly trading plan (data overview)."""
    generator = _build_weekly_generator()
    data_report, _ = asyncio.run(generator.generate())
    click.echo(data_report)


@click.command("analyze")
def weekly_analyze() -> None:
    """Generate data + save AI analysis prompt for weekly plan."""
    generator = _build_weekly_generator()
    data_report, ai_prompt = asyncio.run(generator.generate())

    prompt_path = Path("data/exports/weekly-ai-prompt.md")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(ai_prompt)

    click.echo(data_report)
    click.echo(f"\nAI weekly prompt saved to: {prompt_path}")
    click.echo('发送 "执行周计划AI分析" 获取完整智能周度计划。')


@click.command("save")
def weekly_save() -> None:
    """Generate and save weekly plan to file."""
    generator = _build_weekly_generator()
    path = asyncio.run(generator.generate_and_save())
    click.echo(f"Weekly plan saved to: {path}")
