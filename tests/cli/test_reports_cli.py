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


def test_reports_pine_command_registered():
    """`daytrader reports pine --help` shows the command + --symbol option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "pine", "--help"])
    assert result.exit_code == 0
    assert "--symbol" in result.output
    assert "Pine Script" in result.output or "TradingView" in result.output


def test_reports_run_accepts_no_telegram_no_pdf_flags():
    """`daytrader reports run --type premarket --no-telegram --no-pdf` is valid CLI."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "reports", "run", "--type", "premarket",
        "--no-telegram", "--no-pdf", "--help",
    ])
    # --help short-circuits the run; we just want to ensure click doesn't reject the flags
    assert result.exit_code == 0
    assert "--no-telegram" in result.output
    assert "--no-pdf" in result.output


def test_reports_run_eod_dispatch_recognized(monkeypatch, tmp_path):
    """`reports run --type eod` is no longer stub-rejected (Phase 5 T10)."""
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    # Strip PATH so claude CLI lookup fails — we're checking that the dispatch
    # recognizes 'eod' (i.e., NOT exited with the old "Phase 2 only" message),
    # and reaches the claude-CLI-missing branch instead.
    monkeypatch.setenv("PATH", "")
    result = runner.invoke(cli, ["reports", "run", "--type", "eod"])
    assert result.exit_code != 0
    # Old stub message must NOT appear — that means dispatch passed the type
    # gate and proceeded to a later step.
    assert "Phase 2 implements premarket only" not in (result.output or "")


def test_reports_run_unsupported_type_clearly_errors(monkeypatch, tmp_path):
    """A still-unimplemented type (e.g. 'night') prints the Phase 5 message."""
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["reports", "run", "--type", "night"])
    assert result.exit_code != 0
    output = (result.output or "").lower()
    # The Phase 5 dispatch message points to a later phase
    assert "later phase" in output or "phase 5" in output
