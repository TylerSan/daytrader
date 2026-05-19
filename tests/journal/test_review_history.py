"""Tests for the IBKR behavioral-review engine + CLI.

All data here is synthetic. Real statement CSVs are private and must never
enter the repo (keep them under git-ignored data/imports/).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.journal.review_history import (
    build_report,
    load_statements,
    parse_option_symbol,
    reconstruct,
)

_HEADER = (
    "Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,"
    "Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,"
    "Realized P/L,MTM P/L,Code"
)
_ROWS = [
    # AAA: clean intraday winner (+9)
    'Trades,Data,Order,Stocks,USD,AAA,"2025-01-02, 09:40:00",1,100,100,-100,-1,100,0,0,O',
    'Trades,Data,Order,Stocks,USD,AAA,"2025-01-02, 10:40:00",-1,110,110,110,-1,-100,9,0,C',
    # AAA: open then ADD LOWER (averaging down) then close for a loss (-10)
    'Trades,Data,Order,Stocks,USD,AAA,"2025-01-03, 09:40:00",1,100,100,-100,-1,100,0,0,O',
    'Trades,Data,Order,Stocks,USD,AAA,"2025-01-03, 09:50:00",1,90,90,-90,-1,90,0,0,O',
    'Trades,Data,Order,Stocks,USD,AAA,"2025-01-03, 10:00:00",-2,95,95,190,-1,-190,-10,0,C',
    # Long CALL option, closed for a loss (-100)
    'Trades,Data,Order,Equity and Index Options,USD,ZZZ 17JAN25 100 C,"2025-01-06, 09:40:00",1,2,2,-200,-1,200,0,0,O',
    'Trades,Data,Order,Equity and Index Options,USD,ZZZ 17JAN25 100 C,"2025-01-06, 14:00:00",-1,1,1,100,-1,-200,-100,0,C',
]
_TOTAL = "Total P/L for Statement Period,,,,,,,,,,,,-101,"


@pytest.fixture
def synthetic_statement(tmp_path: Path) -> Path:
    path = tmp_path / "U00000000_2025_2025.csv"
    path.write_text("\n".join([_HEADER, *_ROWS, _TOTAL]) + "\n")
    return path


def test_parse_option_symbol():
    und, exp, cp = parse_option_symbol("SPY 03MAR25 612 C")
    assert und == "SPY"
    assert cp == "C"
    assert exp is not None and exp.year == 2025 and exp.month == 3


def test_load_and_anchor(synthetic_statement: Path):
    fills, anchors = load_statements([synthetic_statement])
    assert len(fills) == 7
    assert anchors[synthetic_statement.name] == pytest.approx(-101.0)
    # quoted Date/Time with an embedded comma must parse, sorted by time
    assert fills[0].dt.year == 2025
    assert fills == sorted(fills, key=lambda f: f.dt)


def test_reconstruct_flags_averaging_down(synthetic_statement: Path):
    fills, _ = load_statements([synthetic_statement])
    rec = reconstruct(fills)
    assert rec.avg_down_events >= 1
    assert rec.avg_down_legs >= 1
    # three closing fills carry realized P/L (+9, -10, -100)
    assert len(rec.closings) == 3
    opt = [c for c in rec.closings if c.asset == "Equity and Index Options"]
    assert len(opt) == 1
    assert opt[0].direction == "LONG"
    assert opt[0].cp == "C"
    assert opt[0].dte == 11  # 2025-01-17 minus 2025-01-06


def test_build_report_sections(synthetic_statement: Path):
    fills, anchors = load_statements([synthetic_statement])
    text = build_report(fills, anchors, r_unit=50.0).text()
    assert "TRUTH ANCHORS" in text
    assert "CONTRACT COUNTERFACTUAL" in text
    assert "OPTIONS AUTOPSY" in text


def test_build_report_empty():
    rep = build_report([], {})
    assert "No data" in rep.text()


def test_cli_help():
    from click.testing import CliRunner

    from daytrader.cli.main import cli

    result = CliRunner().invoke(cli, ["journal", "review-history", "--help"])
    assert result.exit_code == 0, result.output
    assert "review-history" in result.output.lower()


def test_cli_run(synthetic_statement: Path, tmp_path: Path):
    from click.testing import CliRunner

    from daytrader.cli.main import cli

    out = tmp_path / "report.md"
    result = CliRunner().invoke(
        cli,
        [
            "journal", "review-history", str(synthetic_statement),
            "--r", "50", "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "TRUTH ANCHORS" in result.output
    assert out.exists()
    assert "machine-generated" in out.read_text()
