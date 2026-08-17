"""Runner: orchestrates data load + engine + verdict."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from daytrader.journal.models import SetupVerdict
from daytrader.journal.repository import JournalRepository
from daytrader.journal.sanity_floor.data_loader import (
    DataLoadError, HistoricalDataLoader,
)
from daytrader.journal.sanity_floor.engine import (
    SimulatedTrade, simulate_setup,
)
from daytrader.journal.sanity_floor.setup_yaml import (
    SetupDefinition, load_setup_yaml,
)


MIN_SAMPLES = 30


@dataclass
class RunnerConfig:
    data_window_days: int = 90
    interval: str = "1m"


def aggregate_and_write_verdict(
    repo: JournalRepository,
    setup_name: str,
    setup_version: str,
    run_date: date,
    symbol: str,
    data_window_days: int,
    trades: list[SimulatedTrade],
) -> SetupVerdict:
    n = len(trades)
    win_rate = sum(1 for t in trades if t.r_multiple > 0) / n if n else 0.0
    avg_r = sum(t.r_multiple for t in trades) / n if n else 0.0
    passed = (n >= MIN_SAMPLES) and (avg_r >= 0)
    v = SetupVerdict(
        setup_name=setup_name, setup_version=setup_version,
        run_date=run_date, symbol=symbol,
        data_window_days=data_window_days,
        n_samples=n, win_rate=win_rate, avg_r=avg_r, passed=passed,
    )
    repo.save_setup_verdict(v)
    return v


def run_setup_for_symbol(
    setup: SetupDefinition,
    symbol: str,
    loader: HistoricalDataLoader,
    repo: JournalRepository,
    run_date: date,
    config: RunnerConfig,
) -> SetupVerdict:
    start = run_date - timedelta(days=config.data_window_days)
    try:
        df = loader.load(symbol=symbol, interval=config.interval,
                         start=start, end=run_date)
    except DataLoadError as e:
        # Fail-loud: no verdict for missing data
        raise RuntimeError(
            f"sanity-floor for {setup.name}/{symbol}: {e}. "
            "Verdict not written (fail-loud per spec)."
        ) from e

    trades = simulate_setup(setup=setup, symbol=symbol, df=df)
    return aggregate_and_write_verdict(
        repo=repo, setup_name=setup.name, setup_version=setup.version,
        run_date=run_date, symbol=symbol,
        data_window_days=config.data_window_days,
        trades=trades,
    )
