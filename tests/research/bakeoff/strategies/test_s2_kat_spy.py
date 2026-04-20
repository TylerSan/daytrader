"""S2 known-answer test (Zarattini-Aziz-Barbon 2024) on SPY 2023.

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> SPY_HISTORY_YEARS=2023 \\
        pytest tests/research/bakeoff/strategies/test_s2_kat_spy.py -v

Data cost: reuses Plan 2a's cached SPY 1m (2023-04-03 → 2023-12-29) +
one new ARCX.PILLAR daily pull (2023-03-01 → 2023-12-29, ~$1-3).

Anchors (tolerance 15% per spec §5.1):
1. S2a n_trades within ±15% of 75 (≈ 170 trading days × 0.44 hit rate guess)
2. S2a win rate in [0.30, 0.65]
3. len(S2b trades) >= len(S2a trades) — strict (S2b only loosens cap)
4. |avg_R(S2b) - avg_R(S2a)| / |avg_R(S2a)| < 0.30

If #1 or #2 fail outside forgiveness, STOP and debug rules per spec §5
calibration policy before merging.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.data_spy_daily import load_spy_daily
from daytrader.research.bakeoff.strategies._known_answer import (
    compare_to_paper, summary_stats,
)
from daytrader.research.bakeoff.strategies.s2_intraday_momentum import (
    S2a_IntradayMomentum_Max1, S2b_IntradayMomentum_Max5,
)


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
    and os.getenv("SPY_HISTORY_YEARS")
)


@pytest.fixture(scope="module")
def s2_bars():
    cache_1m = Path("data/cache/ohlcv_spy_kat")
    cache_1d = Path("data/cache/ohlcv_spy_daily_kat")
    cache_1m.mkdir(parents=True, exist_ok=True)
    cache_1d.mkdir(parents=True, exist_ok=True)
    ds = load_spy_1m(
        start=date(2023, 4, 3),
        end=date(2023, 12, 29),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache_1m,
    )
    daily = load_spy_daily(
        start=date(2023, 3, 1),
        end=date(2023, 12, 29),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache_1d,
    )
    return ds.bars, daily


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="S2 KAT disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY + SPY_HISTORY_YEARS)",
)
def test_s2a_spy_2023_n_trades(s2_bars):
    bars_1m, bars_1d = s2_bars
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    result = compare_to_paper(
        metric_name="n_trades",
        computed=float(len(trades)),
        paper_value=75.0,
        tolerance_pct=15.0,
    )
    assert result.passed, (
        f"S2a n_trades {len(trades)} deviates {result.deviation_pct:.1f}% "
        f"from expected 75 (tolerance 15%). Likely causes: "
        f"(a) warmup skip off-by-one, (b) check-time local-tz mismatch, "
        f"(c) boundary calc wrong."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2a_spy_2023_win_rate(s2_bars):
    bars_1m, bars_1d = s2_bars
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    stats = summary_stats(trades, point_value_usd=1.0, starting_capital=10_000.0)
    wr = stats["win_rate"]
    assert 0.30 <= wr <= 0.65, (
        f"S2a SPY 2023 win rate {wr:.3f} outside plausible [0.30, 0.65] band. "
        f"Momentum + ATR trailing is typically 40-55% for liquid equities."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2b_count_at_least_s2a_count(s2_bars):
    bars_1m, bars_1d = s2_bars
    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    assert len(s2b) >= len(s2a), (
        f"S2b ({len(s2b)}) must have >= trades than S2a ({len(s2a)}); "
        "S2b only loosens the per-day cap, nothing else."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2a_and_s2b_avg_r_close(s2_bars):
    bars_1m, bars_1d = s2_bars
    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    if not s2a or not s2b:
        pytest.skip("need both S2a and S2b trades to compare")
    avg_r_a = sum(t.r_multiple for t in s2a) / len(s2a)
    avg_r_b = sum(t.r_multiple for t in s2b) / len(s2b)
    if avg_r_a == 0:
        pytest.skip("S2a avg R is exactly 0 — cannot compute relative gap")
    rel_gap = abs(avg_r_b - avg_r_a) / abs(avg_r_a)
    assert rel_gap < 0.30, (
        f"S2a avg_R {avg_r_a:.3f} vs S2b avg_R {avg_r_b:.3f} — gap "
        f"{rel_gap*100:.1f}% exceeds 30%. Same entries + same exits "
        "should give similar per-trade R."
    )
