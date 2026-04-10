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


def _get_obsidian_weekly_path() -> Path | None:
    from daytrader.core.config import load_config
    try:
        cfg = load_config(
            default_config=Path(__file__).resolve().parents[3] / "config" / "default.yaml",
            user_config=Path(__file__).resolve().parents[3] / "config" / "user.yaml",
        )
        if cfg.obsidian.enabled:
            vault = Path(cfg.obsidian.vault_path).expanduser()
            return vault / cfg.obsidian.weekly_folder
    except Exception:
        pass
    return None


def _build_weekly_generator(output_dir: str = "data/exports") -> WeeklyPlanGenerator:
    collector = MarketDataCollector()
    collector.register(FuturesCollector())
    collector.register(SectorCollector())
    collector.register(LevelsCollector())
    return WeeklyPlanGenerator(
        collector=collector,
        output_dir=output_dir,
        obsidian_weekly_path=_get_obsidian_weekly_path(),
    )


@click.command("run")
@click.option("--push", is_flag=True, help="Push plan to notification channels")
@click.option(
    "--ai",
    is_flag=True,
    help="Also invoke Claude CLI for AI weekly plan analysis (slow, ~1-3 min)",
)
def weekly_run(push: bool, ai: bool) -> None:
    """Generate weekly trading plan (data + info cards, optionally + AI)."""
    generator = _build_weekly_generator()
    if ai:
        click.echo("Running full weekly analysis with AI (this may take 1-3 minutes)...", err=True)
        report = asyncio.run(generator.generate_full())
    else:
        report, _ = asyncio.run(generator.generate())
    click.echo(report)

    if push:
        click.echo("\n[Push notifications not yet configured]")


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


@click.command("cards")
@click.option("--date", "target_date", default=None, help="Date in YYYY-MM-DD format")
def weekly_cards(target_date: str | None) -> None:
    """Generate info-card images for a weekly report."""
    from datetime import date as date_cls
    from daytrader.premarket.renderers.cards import CardGenerator

    d = date_cls.fromisoformat(target_date) if target_date else date_cls.today()
    generator = _build_weekly_generator()
    results = asyncio.run(generator._collector.collect_all())

    gen = CardGenerator()
    paths = gen.generate_weekly_cards(results, d)
    if paths:
        click.echo(f"Generated {len(paths)} card(s):")
        for p in paths:
            click.echo(f"  {p}")
    else:
        click.echo("No cards generated (data may be unavailable or generation failed).")


@click.command("save")
def weekly_save() -> None:
    """Generate and save weekly plan to file."""
    generator = _build_weekly_generator()
    path = asyncio.run(generator.generate_and_save())
    click.echo(f"Weekly plan saved to: {path}")
