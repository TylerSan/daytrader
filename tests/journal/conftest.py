"""Shared fixtures for journal tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_journal_db(tmp_path: Path) -> Path:
    """Return path to a temp SQLite file (not yet created)."""
    return tmp_path / "journal.db"


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Return path to a fake Obsidian vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


@pytest.fixture
def sample_contract_md(tmp_path: Path) -> Path:
    """A valid Contract.md for tests."""
    p = tmp_path / "Contract.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** 2026-04-20
**Active:** true

## 1. Account & R Unit
- R unit (USD): $50

## 3. Daily Risk
- daily_loss_limit_r: 3
- daily_loss_warning_r: 2
- max_trades_per_day: 5

## 4. Setup Lock-In
- locked_setup_name: opening_range_breakout
- locked_setup_file: docs/trading/setups/opening_range_breakout.yaml
- lock_in_min_trades: 30
- backup_setup_status: benched

## 7. Cool-off
- stop_cooloff_minutes: 30
"""
    )
    return p

