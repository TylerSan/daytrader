"""Tests for sanity-floor runner."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from daytrader.journal.repository import JournalRepository
from daytrader.journal.sanity_floor.engine import SimulatedTrade
from daytrader.journal.sanity_floor.runner import (
    RunnerConfig, aggregate_and_write_verdict,
)


def test_passed_with_good_stats(tmp_journal_db: Path):
    repo = JournalRepository(str(tmp_journal_db))
    repo.initialize()

    # Build 40 trades with mean r = 0.2
    trades = [SimulatedTrade(
        date="2026-04-01", symbol="MES", direction="long",
        entry_time=None, entry_price=5000, stop_price=4995, target_price=5010,
        exit_time=None, exit_price=5005, outcome="target",
        r_multiple=0.2,
    ) for i in range(40)]

    verdict = aggregate_and_write_verdict(
        repo=repo, setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 16), symbol="MES",
        data_window_days=90, trades=trades,
    )
    assert verdict.passed is True
    assert verdict.n_samples == 40
    assert abs(verdict.avg_r - 0.2) < 0.0001


def test_failed_with_insufficient_samples(tmp_journal_db: Path):
    repo = JournalRepository(str(tmp_journal_db))
    repo.initialize()
    trades = [SimulatedTrade(
        date="2026-04-01", symbol="MES", direction="long",
        entry_time=None, entry_price=5000, stop_price=4995, target_price=5010,
        exit_time=None, exit_price=5005, outcome="target",
        r_multiple=0.5,
    ) for _ in range(20)]
    verdict = aggregate_and_write_verdict(
        repo=repo, setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 16), symbol="MES",
        data_window_days=90, trades=trades,
    )
    assert verdict.passed is False


def test_failed_with_negative_expectancy(tmp_journal_db: Path):
    repo = JournalRepository(str(tmp_journal_db))
    repo.initialize()
    trades = [SimulatedTrade(
        date="2026-04-01", symbol="MES", direction="long",
        entry_time=None, entry_price=5000, stop_price=4995, target_price=5010,
        exit_time=None, exit_price=4995, outcome="stop",
        r_multiple=-1.0,
    ) for _ in range(40)]
    verdict = aggregate_and_write_verdict(
        repo=repo, setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 16), symbol="MES",
        data_window_days=90, trades=trades,
    )
    assert verdict.passed is False
