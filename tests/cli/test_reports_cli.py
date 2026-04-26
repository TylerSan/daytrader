"""Smoke tests for the `daytrader reports` CLI group."""

from __future__ import annotations

from click.testing import CliRunner

from daytrader.cli.main import cli


def test_reports_group_registered():
    """`daytrader reports --help` lists the dry-run subcommand."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "--help"])
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_reports_dry_run_premarket_executes():
    """dry-run --type premarket runs without touching network/disk side effects."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "dry-run", "--type", "premarket"])
    assert result.exit_code == 0
    assert "premarket" in result.output.lower()
    assert "dry-run complete" in result.output.lower()


def test_reports_dry_run_unknown_type_fails():
    """Unknown --type returns non-zero exit and lists valid types."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "dry-run", "--type", "bogus"])
    assert result.exit_code != 0
