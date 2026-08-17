"""S1 known-answer test against Zarattini 2023 on SPY (skipped by default).

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> SPY_HISTORY_YEARS=paper \\
        pytest tests/research/bakeoff/strategies/test_s1_kat_spy.py -v

Data: reuses cached 6.5-year pull from 2018-05-01 → 2024-12-31
(~$0.88 one-time from ARCX.PILLAR per Plan 2b data-expansion branch).
This test slices the paper in-sample period 2018-05-01 → 2023-12-31
(1424 trading days); 2024 is reserved as pure OOS for Plan 3.

Paper: Zarattini & Aziz (2023), SSRN 4416622. SPY is secondary to their
QQQ/TQQQ headline; paper reports only Sharpe ~0.5-1.0 on SPY without
explicit trade-count or win-rate figures. Bands below are calibrated
against observed values on the 6.5y dataset (post S1-wrong-way-bug fix).

KAT anchors (spec §5.1):
1. S1a n_trades within ±15% of 1350 (observed 1353 on paper window)
2. S1a win rate in [0.15, 0.30] (observed 0.204)
3. S1a and S1b have identical trade count (entry logic is shared)
4. S1a and S1b direction balance near 50/50 (long count within 45-55%)

If #1 or #2 fail, stop and re-read Zarattini 2023 §3 before proceeding.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.strategies._known_answer import (
    compare_to_paper, summary_stats,
)
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
    and os.getenv("SPY_HISTORY_YEARS")
)

# Paper in-sample window. 2024+ reserved as pure OOS for Plan 3.
PAPER_START = date(2018, 5, 1)
PAPER_END = date(2023, 12, 31)


@pytest.fixture(scope="module")
def spy_bars_paper_window():
    cache = Path("data/cache/ohlcv_spy_kat")
    cache.mkdir(parents=True, exist_ok=True)
    # Pull full 6.5 years so the cache is shared with S2 KAT. This KAT
    # slices out the paper-window portion.
    ds = load_spy_1m(
        start=date(2018, 5, 1),
        end=date(2024, 12, 31),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache,
    )
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    mask = pd.Series(
        [t.tz_convert(et).date() <= PAPER_END for t in ds.bars.index],
        index=ds.bars.index,
    )
    return ds.bars[mask]


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="S1 KAT disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY + SPY_HISTORY_YEARS)",
)
def test_s1a_spy_paper_window_n_trades(spy_bars_paper_window):
    strat = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(spy_bars_paper_window)
    result = compare_to_paper(
        metric_name="n_trades",
        computed=float(len(trades)),
        paper_value=1350.0,
        tolerance_pct=15.0,
    )
    assert result.passed, (
        f"S1a SPY 2018-05 → 2023-12 n_trades {len(trades)} deviates "
        f"{result.deviation_pct:.1f}% from expected 1350 (tolerance 15%). "
        f"Likely causes: (a) wrong-way-entry guard regression, "
        f"(b) RTH filter wrong, (c) flat-day handling."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S1 KAT disabled")
def test_s1a_spy_paper_window_win_rate(spy_bars_paper_window):
    strat = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(spy_bars_paper_window)
    wr = summary_stats(trades, point_value_usd=1.0, starting_capital=10_000.0)["win_rate"]
    # 10× OR on unleveraged SPY rarely hits; low WR + high avg-R per winner
    # is the expected shape. 6.5y sample narrows the plausible band.
    assert 0.15 <= wr <= 0.30, (
        f"S1a SPY paper-window win rate {wr:.3f} outside plausible "
        "[0.15, 0.30] band. If too low: stop too tight or target too far. "
        "If too high: target logic bypassed or wrong-way guard broken. "
        "Re-read Zarattini 2023 §3."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S1 KAT disabled")
def test_s1a_and_s1b_identical_trade_count(spy_bars_paper_window):
    s1a = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    s1b = S1b_ORB_EODOnly(symbol="SPY", or_minutes=5)
    trades_a = s1a.generate_trades(spy_bars_paper_window)
    trades_b = s1b.generate_trades(spy_bars_paper_window)
    assert len(trades_a) == len(trades_b), (
        f"S1a {len(trades_a)} vs S1b {len(trades_b)} — must match "
        "because they share entry logic and only differ in exit rule."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S1 KAT disabled")
def test_s1a_direction_balance_near_50_50(spy_bars_paper_window):
    """Over 5+ years of SPY, OR direction should average near 50/50.
    Strong asymmetry would indicate a rule or data bug."""
    strat = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0)
    trades = strat.generate_trades(spy_bars_paper_window)
    n_long = sum(1 for t in trades if t.direction == "long")
    n_total = len(trades)
    long_pct = n_long / n_total
    assert 0.45 <= long_pct <= 0.55, (
        f"S1a long ratio {long_pct:.3f} outside [0.45, 0.55] over "
        f"{n_total} trades. Expected near-50/50 because OR direction "
        "is sign of close-open delta and should be roughly symmetric "
        "on a long equity sample. Strong skew suggests direction rule bug."
    )
