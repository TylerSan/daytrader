"""CLI command group `daytrader reports`.

Phase 1 provides a dry-run subcommand that exercises the foundation:
config load + IB connection (or skip in dry-run) + state DB init.

Generation logic (Phase 2+) will plug into report-type handlers later.
"""

from __future__ import annotations

import click


VALID_TYPES = (
    "premarket",
    "intraday-4h-1",
    "intraday-4h-2",
    "eod",
    "night",
    "asia",
    "weekly",
)


@click.group()
def reports() -> None:
    """Multi-cadence trading reports system."""


@reports.command("dry-run")
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(VALID_TYPES, case_sensitive=False),
    help="Report type to dry-run.",
)
def dry_run(report_type: str) -> None:
    """Dry-run a report-type pipeline (no network / file side effects).

    Phase 1 scope: prints the report type and exits successfully.
    Later phases plug in real fetch/AI/delivery steps with --no-side-effects flag.
    """
    click.echo(f"[dry-run] report_type={report_type}")
    click.echo("[dry-run] config load: OK (Phase 1 stub)")
    click.echo("[dry-run] state DB init: OK (Phase 1 stub)")
    click.echo("[dry-run] IB connection: skipped (Phase 1 stub)")
    click.echo("[dry-run] AI generation: skipped (Phase 1 stub)")
    click.echo("[dry-run] delivery: skipped (Phase 1 stub)")
    click.echo("[dry-run] dry-run complete")
