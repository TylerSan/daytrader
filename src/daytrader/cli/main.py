"""DayTrader CLI — unified entry point."""

from __future__ import annotations

from pathlib import Path

import click

from daytrader import __version__
from daytrader.core.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/daytrader/cli -> project root


@click.group()
@click.version_option(__version__, prog_name="daytrader")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """DayTrader — self-evolving day trading platform."""
    ctx.ensure_object(dict)
    cfg = load_config(
        default_config=PROJECT_ROOT / "config" / "default.yaml",
        user_config=PROJECT_ROOT / "config" / "user.yaml",
    )
    ctx.obj["config"] = cfg
    ctx.obj["project_root"] = PROJECT_ROOT


# Placeholder groups — each will be fleshed out in their module's plan

@cli.group()
def pre() -> None:
    """Pre-market daily analysis."""


@cli.group()
def weekly() -> None:
    """Weekly trading plan."""


from daytrader.cli.premarket import pre_run, pre_pine, pre_analyze, pre_cards

pre.add_command(pre_run)
pre.add_command(pre_pine)
pre.add_command(pre_analyze)
pre.add_command(pre_cards)

from daytrader.cli.weekly_cmd import weekly_run, weekly_save, weekly_analyze, weekly_cards

weekly.add_command(weekly_run)
weekly.add_command(weekly_save)
weekly.add_command(weekly_analyze)
weekly.add_command(weekly_cards)


@cli.group()
def bt() -> None:
    """Strategy backtesting."""


@cli.group()
def evo() -> None:
    """Autonomous evolution engine."""


@cli.group()
def prop() -> None:
    """Prop firm account management."""


@cli.group()
def psych() -> None:
    """Trading psychology system."""


@cli.group()
def learn() -> None:
    """Learning & content curation."""


@cli.group()
def stats() -> None:
    """Instrument statistical edge."""


@cli.group()
def kb() -> None:
    """Knowledge base management."""


@cli.group()
def publish() -> None:
    """Content publishing pipeline."""


@cli.group()
def book() -> None:
    """Book manuscript builder."""


@cli.group()
def journal() -> None:
    """Trade journal & import."""


from daytrader.cli.journal_cmd import pre_trade, post_trade, circuit_group, sanity_group, dry_run_group, resume_gate_group, audit_cmd  # noqa: E402

journal.add_command(pre_trade)
journal.add_command(post_trade)
journal.add_command(circuit_group)
journal.add_command(sanity_group)
journal.add_command(dry_run_group)
journal.add_command(resume_gate_group)
journal.add_command(audit_cmd)
