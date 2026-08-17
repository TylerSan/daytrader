"""Tests for Obsidian view writer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.models import (
    Checklist, ChecklistItems, DryRun, DryRunOutcome,
    JournalTrade, TradeMode, TradeSide,
)
from daytrader.journal.obsidian import ObsidianWriter


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_write_trade_view(tmp_vault: Path):
    w = ObsidianWriter(
        vault_root=tmp_vault,
        trades_folder="DayTrader/Trades",
        dry_runs_folder="DayTrader/DryRuns",
        checklists_folder="DayTrader/Daily",
    )
    t = JournalTrade(
        id="t01", checklist_id="c01",
        date=date(2026, 4, 20), symbol="MES",
        direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:35:00"),
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
        exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5010"),
        pnl_usd=Decimal("50"),
    )
    w.write_trade(t)
    p = tmp_vault / "DayTrader/Trades/2026-04-20-t01.md"
    assert p.exists()
    text = p.read_text()
    assert "entry_price: 5000" in text
    assert "stop_price: 4995" in text


def test_write_fails_silently_on_bad_vault(tmp_path: Path, capsys):
    # Read-only directory
    bad_vault = tmp_path / "readonly"
    bad_vault.mkdir(mode=0o555)
    w = ObsidianWriter(
        vault_root=bad_vault,
        trades_folder="DayTrader/Trades",
        dry_runs_folder="DayTrader/DryRuns",
        checklists_folder="DayTrader/Daily",
    )
    t = JournalTrade(
        id="t02", checklist_id="c02",
        date=date(2026, 4, 20), symbol="MES",
        direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:35:00"),
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
    )
    w.write_trade(t)  # should NOT raise
    err = capsys.readouterr().err
    assert "obsidian" in err.lower() or "warning" in err.lower()
