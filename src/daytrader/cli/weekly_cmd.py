"""Weekly plan CLI commands."""

from __future__ import annotations

import asyncio

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
    """Generate full weekly trading plan."""
    generator = _build_weekly_generator()
    report = asyncio.run(generator.generate())
    click.echo(report)


@click.command("save")
def weekly_save() -> None:
    """Generate and save weekly plan to file."""
    generator = _build_weekly_generator()
    path = asyncio.run(generator.generate_and_save())
    click.echo(f"Weekly plan saved to: {path}")
