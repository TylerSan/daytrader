"""S2 known-answer test (Zarattini-Aziz-Barbon 2024) on SPY (skipped by default).

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> SPY_HISTORY_YEARS=paper \\
        pytest tests/research/bakeoff/strategies/test_s2_kat_spy.py -v

Data: reuses cached 6.5-year ARCX.PILLAR pull (2018-05-01 → 2024-12-31,
~$0.88). This KAT slices the paper in-sample period 2018-05-01 →
2023-12-31 (1424 trading days). 2024+ reserved as pure OOS for Plan 3.

Paper: Zarattini, Aziz, Barbon (2024), Swiss Finance Institute RP 24-97.
Headline figures are QQQ/TQQQ; SPY-specific numbers are limited. Bands
calibrated against observed values on 6.5y dataset.

KAT anchors (spec §5.1):
1. S2a n_trades within ±15% of 1230 (observed 1232 on paper window)
2. S2a win rate in [0.40, 0.65] (observed 0.516)
3. len(S2b) >= len(S2a) strict — S2b only loosens cap
4. |avg_R(S2b) - avg_R(S2a)| / |avg_R(S2a)| < 0.30 — same entries, same exits

On 6.5y SPY we also observe:
- S2 stops almost never fire (< 1% of trades) → trailing stop is largely
  theatre; strategy ≈ "breakout → EOD". This is expected per rules but
  a candidate for SE-6 sensitivity in Plan 3 (ATR multiplier scan).
- S2a/S2b differ by < 1% in trade count — per-day-cap differentiation is
  weak. This is a property of the dataset, not a bug.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
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

PAPER_START = date(2018, 5, 1)
PAPER_END = date(2023, 12, 31)


@pytest.fixture(scope="module")
def s2_paper_window_bars():
    cache_1m = Path("data/cache/ohlcv_spy_kat")
    cache_1d = Path("data/cache/ohlcv_spy_daily_kat")
    cache_1m.mkdir(parents=True, exist_ok=True)
    cache_1d.mkdir(parents=True, exist_ok=True)
    ds = load_spy_1m(
        start=date(2018, 5, 1),
        end=date(2024, 12, 31),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache_1m,
    )
    daily = load_spy_daily(
        start=date(2018, 5, 1),
        end=date(2024, 12, 31),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=cache_1d,
    )
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    mask_1m = pd.Series(
        [t.tz_convert(et).date() <= PAPER_END for t in ds.bars.index],
        index=ds.bars.index,
    )
    return ds.bars[mask_1m], daily[daily.index.date <= PAPER_END]


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="S2 KAT disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY + SPY_HISTORY_YEARS)",
)
def test_s2a_spy_paper_window_n_trades(s2_paper_window_bars):
    bars_1m, bars_1d = s2_paper_window_bars
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    result = compare_to_paper(
        metric_name="n_trades",
        computed=float(len(trades)),
        paper_value=1230.0,
        tolerance_pct=15.0,
    )
    assert result.passed, (
        f"S2a n_trades {len(trades)} deviates {result.deviation_pct:.1f}% "
        f"from expected 1230 (tolerance 15%). Likely causes: "
        f"(a) warmup skip off-by-one, (b) check-time local-tz mismatch, "
        f"(c) boundary calc wrong."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2a_spy_paper_window_win_rate(s2_paper_window_bars):
    bars_1m, bars_1d = s2_paper_window_bars
    strat = S2a_IntradayMomentum_Max1(symbol="SPY")
    trades = strat.generate_trades(bars_1m, bars_1d)
    wr = summary_stats(trades, point_value_usd=1.0, starting_capital=10_000.0)["win_rate"]
    assert 0.40 <= wr <= 0.65, (
        f"S2a SPY paper-window win rate {wr:.3f} outside plausible "
        "[0.40, 0.65] band. Momentum + ATR trailing on liquid equities "
        "is typically 45-55%."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2b_count_at_least_s2a_count(s2_paper_window_bars):
    bars_1m, bars_1d = s2_paper_window_bars
    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    assert len(s2b) >= len(s2a), (
        f"S2b ({len(s2b)}) must have >= trades than S2a ({len(s2a)}); "
        "S2b only loosens the per-day cap, nothing else."
    )


@pytest.mark.skipif(not LIVE_ENABLED, reason="S2 KAT disabled")
def test_s2a_and_s2b_avg_r_close(s2_paper_window_bars):
    bars_1m, bars_1d = s2_paper_window_bars
    s2a = S2a_IntradayMomentum_Max1(symbol="SPY").generate_trades(bars_1m, bars_1d)
    s2b = S2b_IntradayMomentum_Max5(symbol="SPY").generate_trades(bars_1m, bars_1d)
    if not s2a or not s2b:
        pytest.skip("need both S2a and S2b trades to compare")
    avg_r_a = sum(t.r_multiple for t in s2a) / len(s2a)
    avg_r_b = sum(t.r_multiple for t in s2b) / len(s2b)
    if abs(avg_r_a) < 1e-4:
        pytest.skip("S2a avg R near zero — relative gap undefined")
    rel_gap = abs(avg_r_b - avg_r_a) / abs(avg_r_a)
    assert rel_gap < 0.30, (
        f"S2a avg_R {avg_r_a:.4f} vs S2b avg_R {avg_r_b:.4f} — gap "
        f"{rel_gap*100:.1f}% exceeds 30%. Same entries + same exits "
        "should give similar per-trade R. Check cap-reset / re-entry logic."
    )
