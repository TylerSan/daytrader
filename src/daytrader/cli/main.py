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
