"""End-to-end integration test: smoke-test --help for all 7 journal subcommands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner


def test_cli_journal_help():
    """daytrader journal --help exits 0 and lists all subcommands."""
    from daytrader.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "--help"])
    assert result.exit_code == 0, result.output
    # Confirm all 7 subcommands appear
    for cmd in ("pre-trade", "post-trade", "circuit", "dry-run",
                "sanity", "resume-gate", "audit"):
        assert cmd in result.output, (
            f"'{cmd}' not found in `journal --help` output:\n{result.output}"
        )


@pytest.mark.parametrize("cmd", [
    "pre-trade",
    "post-trade",
    "circuit",
    "dry-run",
    "sanity",
    "resume-gate",
    "audit",
])
def test_journal_subcommand_help(cmd):
    """Each journal subcommand responds to --help with exit code 0."""
    from daytrader.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["journal", cmd, "--help"])
    assert result.exit_code == 0, (
        f"`daytrader journal {cmd} --help` exited {result.exit_code}:\n{result.output}"
    )
    # Every --help response must include the word "Usage"
    assert "Usage:" in result.output, (
        f"`daytrader journal {cmd} --help` output missing 'Usage:':\n{result.output}"
    )
