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


def test_reports_dry_run_all_types_succeed():
    """Each valid --type runs dry-run successfully."""
    runner = CliRunner()
    valid_types = [
        "premarket",
        "intraday-4h-1",
        "intraday-4h-2",
        "eod",
        "night",
        "asia",
        "weekly",
    ]
    for t in valid_types:
        result = runner.invoke(cli, ["reports", "dry-run", "--type", t])
        assert result.exit_code == 0, f"failed for type={t}: {result.output}"
        assert "dry-run complete" in result.output.lower()


def test_reports_run_command_registered():
    """`daytrader reports run --help` lists --type."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "run", "--help"])
    assert result.exit_code == 0
    assert "--type" in result.output


def test_reports_run_unknown_type_fails():
    """Unknown --type → non-zero exit."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "run", "--type", "bogus"])
    assert result.exit_code != 0


def test_reports_run_premarket_no_claude_cli_clearly_errors(monkeypatch, tmp_path):
    """Without claude CLI on PATH, run --type premarket exits non-zero with a clear message."""
    runner = CliRunner()
    # Strip PATH so `claude` cannot be found
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["reports", "run", "--type", "premarket"])
    assert result.exit_code != 0
    combined = (result.output or "").lower()
    assert "claude" in combined or "not found" in combined or "path" in combined
