"""Pre-market CLI commands."""

from __future__ import annotations

import asyncio

import click

from daytrader.premarket.checklist import PremarketChecklist
from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.collectors.futures import FuturesCollector
from daytrader.premarket.collectors.sectors import SectorCollector
from daytrader.premarket.collectors.levels import LevelsCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer
from daytrader.premarket.renderers.pinescript import PineScriptRenderer


def _build_checklist(output_dir: str = "data/exports") -> PremarketChecklist:
    collector = MarketDataCollector()
    collector.register(FuturesCollector())
    collector.register(SectorCollector())
    collector.register(LevelsCollector())
    renderers = [MarkdownRenderer(output_dir=output_dir)]
    return PremarketChecklist(collector=collector, renderers=renderers)


@click.command("run")
@click.option("--push", is_flag=True, help="Push report to notification channels")
@click.pass_context
def pre_run(ctx: click.Context, push: bool) -> None:
    """Run full pre-market analysis."""
    checklist = _build_checklist()
    report = asyncio.run(checklist.run())
    click.echo(report)
    if push:
        click.echo("\n[Push notifications not yet configured]")


@click.command("pine")
@click.argument("symbol", default="SPY")
@click.pass_context
def pre_pine(ctx: click.Context, symbol: str) -> None:
    """Generate Pine Script for key levels."""
    collector = MarketDataCollector()
    collector.register(LevelsCollector(symbols=[symbol]))
    results = asyncio.run(collector.collect_all())
    renderer = PineScriptRenderer()
    path = renderer.render_and_save(results, symbol=symbol)
    click.echo(f"Pine Script saved to: {path}")
