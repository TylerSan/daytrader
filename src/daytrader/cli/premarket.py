"""Pre-market CLI commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from daytrader.premarket.checklist import PremarketChecklist
from daytrader.premarket.collectors.base import MarketDataCollector
from daytrader.premarket.collectors.futures import FuturesCollector
from daytrader.premarket.collectors.sectors import SectorCollector
from daytrader.premarket.collectors.levels import LevelsCollector
from daytrader.premarket.collectors.news import NewsCollector
from daytrader.premarket.collectors.movers import MoversCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer
from daytrader.premarket.renderers.pinescript import PineScriptRenderer


def _build_checklist(output_dir: str = "data/exports") -> PremarketChecklist:
    collector = MarketDataCollector()
    collector.register(FuturesCollector())
    collector.register(SectorCollector())
    collector.register(LevelsCollector())
    collector.register(NewsCollector())
    collector.register(MoversCollector())
    renderers = [MarkdownRenderer(output_dir=output_dir)]
    return PremarketChecklist(collector=collector, renderers=renderers)


@click.command("run")
@click.option("--push", is_flag=True, help="Push report to notification channels")
@click.option("--ai", is_flag=True, help="Also output AI analysis prompt for Claude Code")
@click.pass_context
def pre_run(ctx: click.Context, push: bool, ai: bool) -> None:
    """Run full pre-market analysis."""
    checklist = _build_checklist()

    if ai:
        report, ai_prompt = asyncio.run(checklist.run_with_prompt())
        click.echo(report)
        click.echo("\n---\n")
        click.echo("## AI 分析提示词（请将以下内容发送给 Claude 进行分析）\n")
        click.echo(ai_prompt)
    else:
        report = asyncio.run(checklist.run())
        click.echo(report)

    if push:
        click.echo("\n[Push notifications not yet configured]")


@click.command("analyze")
@click.pass_context
def pre_analyze(ctx: click.Context) -> None:
    """Collect data and save AI analysis prompt to file."""
    checklist = _build_checklist()
    report, ai_prompt = asyncio.run(checklist.run_with_prompt())

    # Save prompt to file for easy access
    prompt_path = Path("data/exports/ai-analysis-prompt.md")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(ai_prompt)

    click.echo(report)
    click.echo(f"\nAI analysis prompt saved to: {prompt_path}")
    click.echo("Paste the prompt content to Claude Code for AI-powered analysis.")


@click.command("pine")
@click.argument("symbol", default="SPY")
@click.pass_context
def pre_pine(ctx: click.Context, symbol: str) -> None:
    """Generate Pine Script for key levels (works with ETFs and futures)."""
    from daytrader.premarket.collectors.base import CollectorResult
    from datetime import datetime, timezone

    collector = MarketDataCollector()
    collector.register(LevelsCollector(symbols=[symbol]))
    collector.register(FuturesCollector(symbols=[symbol]))
    results = asyncio.run(collector.collect_all())

    # Merge futures data into levels format if levels is empty for this symbol
    levels_result = results.get("levels")
    futures_result = results.get("futures")

    if (not levels_result or symbol not in levels_result.data or not levels_result.data[symbol]) \
            and futures_result and futures_result.success and symbol in futures_result.data:
        fd = futures_result.data[symbol]
        merged_levels = {}
        if fd.get("prev_close"):
            merged_levels["prior_day_close"] = fd["prev_close"]
        if fd.get("day_high"):
            merged_levels["day_high"] = fd["day_high"]
        if fd.get("day_low"):
            merged_levels["day_low"] = fd["day_low"]
        if fd.get("overnight_high"):
            merged_levels["overnight_high"] = fd["overnight_high"]
        if fd.get("overnight_low"):
            merged_levels["overnight_low"] = fd["overnight_low"]
        if fd.get("asia_high"):
            merged_levels["asia_session_high"] = fd["asia_high"]
        if fd.get("asia_low"):
            merged_levels["asia_session_low"] = fd["asia_low"]
        if fd.get("europe_high"):
            merged_levels["europe_session_high"] = fd["europe_high"]
        if fd.get("europe_low"):
            merged_levels["europe_session_low"] = fd["europe_low"]

        results["levels"] = CollectorResult(
            collector_name="levels",
            timestamp=datetime.now(timezone.utc),
            data={symbol: merged_levels},
            success=True,
        )

    renderer = PineScriptRenderer()
    code = renderer.render(results, symbol=symbol)
    if not code:
        click.echo(f"No level data available for {symbol}")
        return
    path = renderer.render_and_save(results, symbol=symbol)
    click.echo(f"Pine Script saved to: {path}")
    click.echo(code)
