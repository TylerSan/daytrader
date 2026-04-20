"""CLI smoke tests for journal commands."""

from __future__ import annotations


def test_journal_pre_trade_help():
    """Ensure pre-trade command is registered and --help works."""
    from daytrader.cli.main import cli
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "pre-trade", "--help"])
    assert result.exit_code == 0, result.output
    assert "pre-trade" in result.output.lower()


def test_journal_circuit_status_help():
    from daytrader.cli.main import cli
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "circuit", "--help"])
    assert result.exit_code == 0, result.output


def test_journal_post_trade_help():
    from daytrader.cli.main import cli
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "post-trade", "--help"])
    assert result.exit_code == 0, result.output


def test_journal_sanity_help():
    from daytrader.cli.main import cli
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "sanity", "--help"])
    assert result.exit_code == 0, result.output
