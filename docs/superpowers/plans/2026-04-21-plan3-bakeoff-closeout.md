# Plan 3: Bake-off Closeout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute spec §2.4 hard-gate evaluation on S1a + S1b over SPY 2018-05 → 2024-12 (replication + pure OOS), run all 4 sensitivity experiments, commit to spec §6 decision branch, and formally close out the W2 bake-off track.

**Architecture:** Two new library modules (`costs.py`, `metrics.py`) plus five scan scripts that reuse Plan 2c's pattern (load cache → loop → CSV + markdown). No pybroker. All metrics TDD'd against synthetic series with known answers before being run on real data. Four deliverable docs at Day 3: main run report, sensitivity report, findings (with §6 decision), retrospective.

**Tech Stack:** pandas, numpy, scipy.stats (for DSR/bootstrap). Pure Python, no new dependencies.

**Spec:** [`docs/superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md`](../specs/2026-04-21-plan3-bakeoff-closeout-design.md)

---

## File Structure

```
Create:
  src/daytrader/research/bakeoff/costs.py                    (existing stub; implement)
  src/daytrader/research/bakeoff/metrics.py
  tests/research/bakeoff/test_costs.py                       (existing stub; expand)
  tests/research/bakeoff/test_metrics.py
  scripts/bakeoff_plan3_main_run.py
  scripts/_plan3_trade_utils.py                              (shared helpers: flip_trades, filter_by_window)
  scripts/bakeoff_plan3_se1_cost.py
  scripts/bakeoff_plan3_se2_reversal.py
  scripts/bakeoff_plan3_se3_quarterly.py
  scripts/bakeoff_plan3_se4_or_duration.py
  tests/scripts/test_plan3_trade_utils.py
  docs/research/bakeoff/2026-04-21-plan3-main-report.md      (Day 1 output)
  docs/research/bakeoff/plan3_main_report.csv                (generated)
  docs/research/bakeoff/2026-04-21-plan3-sensitivity.md      (Day 2 output)
  docs/research/bakeoff/plan3_se1_cost.csv                   (generated)
  docs/research/bakeoff/plan3_se2_reversal.csv               (generated)
  docs/research/bakeoff/plan3_se3_quarterly.csv              (generated)
  docs/research/bakeoff/plan3_se4_or_duration.csv            (generated)
  docs/research/bakeoff/2026-04-21-plan3-findings.md         (Day 3 output)
  docs/research/bakeoff/2026-04-21-bakeoff-retrospective.md  (Day 3 output)

Modify: (none — S1 strategy code stays frozen)
```

The existing `costs.py` file in the repo is a minimal placeholder from Plan 1; we expand it, not create fresh.

---

## Task 1: Cost model

**Files:**
- Modify: `src/daytrader/research/bakeoff/costs.py`
- Modify: `tests/research/bakeoff/test_costs.py`

Pure-pandas helper applying a per-trade cost to a list of Trade objects and returning net PnL series.

### - [ ] Step 1: Look at existing stub

```bash
cd "/Users/tylersan/Projects/Day trading"
cat src/daytrader/research/bakeoff/costs.py
cat tests/research/bakeoff/test_costs.py
```

Note what's there before extending.

### - [ ] Step 2: Write failing tests

Append to `tests/research/bakeoff/test_costs.py` (or create if empty):

```python
from datetime import datetime, timezone

import pytest

from daytrader.research.bakeoff.costs import (
    apply_per_trade_cost, trade_gross_pnl, trade_net_pnl,
)
from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _trade(direction, entry_price, exit_price):
    ts = datetime(2024, 6, 10, 13, 35, tzinfo=timezone.utc)
    stop = entry_price - 10 if direction == "long" else entry_price + 10
    return Trade(
        date="2024-06-10", symbol="SPY", direction=direction,
        entry_time=ts, entry_price=entry_price,
        stop_price=stop, target_price=float("nan"),
        exit_time=ts, exit_price=exit_price,
        outcome=TradeOutcome.EOD, r_multiple=0.0,
    )


def test_trade_gross_pnl_long():
    assert trade_gross_pnl(_trade("long", 100.0, 105.0)) == pytest.approx(5.0)


def test_trade_gross_pnl_short():
    assert trade_gross_pnl(_trade("short", 100.0, 95.0)) == pytest.approx(5.0)


def test_trade_net_pnl_subtracts_cost():
    assert trade_net_pnl(_trade("long", 100.0, 105.0), cost_per_trade=0.5) == pytest.approx(4.5)


def test_apply_per_trade_cost_returns_series_of_net_pnl():
    trades = [
        _trade("long", 100.0, 105.0),   # gross +5, net +4.5
        _trade("long", 100.0, 98.0),    # gross -2, net -2.5
        _trade("short", 100.0, 95.0),   # gross +5, net +4.5
    ]
    nets = apply_per_trade_cost(trades, cost_per_trade=0.5)
    assert list(nets) == pytest.approx([4.5, -2.5, 4.5])


def test_apply_per_trade_cost_zero_cost_matches_gross():
    trades = [_trade("long", 100.0, 105.0), _trade("short", 100.0, 95.0)]
    gross = [trade_gross_pnl(t) for t in trades]
    net = list(apply_per_trade_cost(trades, cost_per_trade=0.0))
    assert net == pytest.approx(gross)
```

### - [ ] Step 3: Run tests — expect ImportError

```bash
.venv/bin/pytest tests/research/bakeoff/test_costs.py -v
```

Expected: ImportError on the new symbols (if `costs.py` didn't already have them).

### - [ ] Step 4: Implement

Edit `src/daytrader/research/bakeoff/costs.py` to contain:

```python
"""Cost model for Plan 3 bake-off evaluation.

Applies a fixed per-trade round-trip cost (spec §3.1 locked at $0.50).
Strategies output gross PnL in point-units ($1/point for SPY); subtracting
`cost_per_trade` gives the net PnL per trade. No slippage modeling beyond
the fixed deduction (SPY is a liquid ETF; slippage is mostly inside the
$0.50 assumption).
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import Trade


def trade_gross_pnl(trade: Trade) -> float:
    """Points of gross PnL for a single trade, sign per direction."""
    if trade.direction == "long":
        return trade.exit_price - trade.entry_price
    return trade.entry_price - trade.exit_price


def trade_net_pnl(trade: Trade, cost_per_trade: float) -> float:
    return trade_gross_pnl(trade) - cost_per_trade


def apply_per_trade_cost(
    trades: Iterable[Trade], cost_per_trade: float
) -> pd.Series:
    """Return a Series of net PnL values in trade order."""
    return pd.Series([trade_net_pnl(t, cost_per_trade) for t in trades])
```

### - [ ] Step 5: Run tests — expect all PASS

```bash
.venv/bin/pytest tests/research/bakeoff/test_costs.py -v
```

Expected: all new tests pass; any pre-existing tests in that file also pass.

### - [ ] Step 6: Commit

```bash
git add src/daytrader/research/bakeoff/costs.py tests/research/bakeoff/test_costs.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): Plan 3 cost model — fixed per-trade subtraction

trade_gross_pnl, trade_net_pnl, apply_per_trade_cost. Pure functions
over the existing Trade wire format. SPY retail round-trip default is
\$0.50/trade per spec §3.1; caller passes the value explicitly so SE-1
can scan ×{0, 1, 2}.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Metrics — core six (Sharpe / Sortino / Calmar / MDD / PF / Expectancy)

**Files:**
- Create: `src/daytrader/research/bakeoff/metrics.py`
- Create: `tests/research/bakeoff/test_metrics.py`

Each metric tested against a synthetic series with a hand-computed known answer.

### - [ ] Step 1: Write failing tests

Create `tests/research/bakeoff/test_metrics.py`:

```python
"""Tests for metrics module. Each metric uses a hand-computable fixture."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from daytrader.research.bakeoff.metrics import (
    annualized_sharpe, annualized_sortino, calmar_ratio,
    expectancy_r, max_drawdown, longest_drawdown_duration,
    profit_factor,
)


# Synthetic daily-return series: 252 days, half +1%, half -0.5%.
# Annualized mean return = 252 * mean_daily = 252 * (0.005) = 126% (not annualized via compound; simple).
# That's nonsensical for a real strategy but gives a stable test fixture.
def _synthetic_daily_returns(seed=0):
    rng = np.random.default_rng(seed)
    # Use deterministic pattern, not random, for exact expectations.
    arr = np.array([0.01, -0.005] * 126)   # 252 days, alternating
    return pd.Series(arr)


# --- annualized Sharpe ---

def test_annualized_sharpe_zero_mean():
    s = pd.Series([0.01, -0.01, 0.01, -0.01] * 63)   # 252 days, zero mean
    # mean = 0, sharpe = 0
    assert annualized_sharpe(s) == pytest.approx(0.0)


def test_annualized_sharpe_positive_mean_positive_std():
    s = pd.Series([0.02, 0.00] * 126)   # mean=0.01, std ≠ 0
    # mean/std * sqrt(252) — just assert sign and order of magnitude.
    sh = annualized_sharpe(s)
    # mean=0.01, popstd=0.01 → unbiased std = 0.01 * sqrt(252/251); roughly sh ≈ sqrt(252) ≈ 15.87
    assert sh > 10


def test_annualized_sharpe_zero_std_returns_nan():
    s = pd.Series([0.005] * 252)   # constant → std=0
    assert math.isnan(annualized_sharpe(s))


# --- Sortino ---

def test_annualized_sortino_no_downside_returns_inf_or_nan():
    s = pd.Series([0.01, 0.02, 0.003] * 84)   # all positive, no downside
    sr = annualized_sortino(s)
    assert sr == float("inf") or math.isnan(sr)


def test_annualized_sortino_equal_up_and_down():
    s = pd.Series([0.01, -0.01] * 126)   # symmetric
    sr = annualized_sortino(s)
    # Mean = 0, numerator = 0, so sortino = 0 regardless of downside.
    assert sr == pytest.approx(0.0)


# --- max_drawdown + longest_drawdown_duration ---

def test_max_drawdown_no_loss_is_zero():
    eq = pd.Series([1.0, 1.01, 1.02, 1.03])
    assert max_drawdown(eq) == pytest.approx(0.0)


def test_max_drawdown_simple_peak_trough():
    eq = pd.Series([1.0, 1.20, 0.90, 1.10])
    # Peak = 1.20 at index 1, trough = 0.90 at index 2.
    # MDD = (0.90 - 1.20) / 1.20 = -0.25 → we return the positive fraction 0.25.
    assert max_drawdown(eq) == pytest.approx(0.25)


def test_longest_drawdown_duration_counts_bars():
    # Equity: 1.0, 1.5, 1.2, 1.1, 1.0, 1.3, 1.6 (recovers at idx 6).
    # Peak at idx 1 (1.5). Drawdown lasts from idx 2 through 5 (4 bars); recovery at 6.
    # Depending on convention: count bars from first-below-peak to last-below-peak = 4, or
    # bars from peak to recovery (inclusive) = 5.
    # We'll define: longest underwater stretch = contiguous bars with equity < running peak.
    # Under that definition: idx 2..5 = 4 bars.
    eq = pd.Series([1.0, 1.5, 1.2, 1.1, 1.0, 1.3, 1.6])
    assert longest_drawdown_duration(eq) == 4


def test_longest_drawdown_duration_unrecovered():
    eq = pd.Series([1.0, 1.5, 1.2, 1.1, 1.0])   # never recovers
    # Bars 2..4 underwater = 3 bars.
    assert longest_drawdown_duration(eq) == 3


# --- Calmar ---

def test_calmar_ratio_zero_drawdown_returns_nan():
    eq = pd.Series([1.0, 1.01, 1.02, 1.03])   # no DD
    assert math.isnan(calmar_ratio(eq, trading_days=252))


def test_calmar_ratio_typical():
    # 1-year equity going 1.0 → 1.10 → 0.99 → 1.12 → final 1.20, trading_days=4.
    # annual_return = (1.20/1.0)^(252/4) - 1 → huge number, use small check
    eq = pd.Series([1.0, 1.10, 0.99, 1.12, 1.20])
    # MDD = (0.99 - 1.10) / 1.10 = 0.10
    # annualized return = (1.20/1.0)^(252/4) - 1 — astronomical; just check > 0
    c = calmar_ratio(eq, trading_days=4)
    assert c > 0


# --- Profit factor ---

def test_profit_factor_all_wins_returns_inf():
    pnl = pd.Series([1.0, 2.0, 3.0])
    assert profit_factor(pnl) == float("inf")


def test_profit_factor_all_losses_returns_zero():
    pnl = pd.Series([-1.0, -2.0])
    assert profit_factor(pnl) == pytest.approx(0.0)


def test_profit_factor_mixed():
    pnl = pd.Series([3.0, -1.0, 2.0, -4.0])   # wins=5, losses=5
    assert profit_factor(pnl) == pytest.approx(1.0)


# --- Expectancy R ---

def test_expectancy_r_mean_of_r_multiples():
    r = pd.Series([1.0, -1.0, 0.5, -0.5])   # mean = 0
    assert expectancy_r(r) == pytest.approx(0.0)
```

### - [ ] Step 2: Run tests — expect ImportError

```bash
.venv/bin/pytest tests/research/bakeoff/test_metrics.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

### - [ ] Step 3: Implement

Create `src/daytrader/research/bakeoff/metrics.py`:

```python
"""Metrics for Plan 3 bake-off evaluation.

Each function takes a pandas Series (either daily returns or equity curve
or trade-level pnl or r_multiples, as appropriate) and returns a float.

Conventions:
- Drawdown is reported as a positive fraction (0.15 means 15% drop).
- Sharpe / Sortino are annualized with sqrt(252) (US RTH calendar).
- nan / inf edge cases are returned explicitly rather than raised; callers
  check with math.isnan / math.isinf.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def annualized_sharpe(daily_returns: pd.Series) -> float:
    """Mean / stdev of daily returns * sqrt(252). Zero std → NaN."""
    mean = float(daily_returns.mean())
    std = float(daily_returns.std(ddof=1))
    if std == 0 or math.isnan(std):
        return float("nan")
    return mean / std * math.sqrt(TRADING_DAYS_PER_YEAR)


def annualized_sortino(daily_returns: pd.Series) -> float:
    """Mean / downside-std * sqrt(252). No downside → inf."""
    mean = float(daily_returns.mean())
    downside = daily_returns[daily_returns < 0]
    if len(downside) == 0:
        return float("inf")
    std_d = float(downside.std(ddof=1))
    if std_d == 0 or math.isnan(std_d):
        return float("inf")
    return mean / std_d * math.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough drop as positive fraction of prior peak."""
    running_peak = equity.cummax()
    drawdowns = (running_peak - equity) / running_peak
    return float(drawdowns.max())


def longest_drawdown_duration(equity: pd.Series) -> int:
    """Longest contiguous stretch (in bars) with equity < running peak."""
    running_peak = equity.cummax()
    underwater = equity < running_peak
    if not underwater.any():
        return 0
    longest = 0
    current = 0
    for uw in underwater:
        if uw:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def calmar_ratio(equity: pd.Series, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized return / max drawdown. Zero DD → NaN."""
    if len(equity) < 2:
        return float("nan")
    total_return = float(equity.iloc[-1] / equity.iloc[0]) - 1
    years = len(equity) / trading_days
    annualized = (1 + total_return) ** (1 / years) - 1 if years > 0 else float("nan")
    mdd = max_drawdown(equity)
    if mdd == 0 or math.isnan(mdd):
        return float("nan")
    return annualized / mdd


def profit_factor(trade_pnl: pd.Series) -> float:
    """Sum(wins) / abs(sum(losses)). All-wins → inf, all-losses → 0."""
    wins = trade_pnl[trade_pnl > 0].sum()
    losses = trade_pnl[trade_pnl < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def expectancy_r(r_multiples: pd.Series) -> float:
    """Mean R-multiple. Empty series → NaN."""
    if len(r_multiples) == 0:
        return float("nan")
    return float(r_multiples.mean())
```

### - [ ] Step 4: Run tests — expect all PASS

```bash
.venv/bin/pytest tests/research/bakeoff/test_metrics.py -v
```

Expected: all 13 tests pass.

### - [ ] Step 5: Commit

```bash
git add src/daytrader/research/bakeoff/metrics.py tests/research/bakeoff/test_metrics.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): Plan 3 metrics core — Sharpe/Sortino/Calmar/MDD/PF/Expectancy

Six pure functions over pandas Series. Each TDD'd against a fixture with
a hand-computable answer. Edge cases (zero std, all wins, empty) return
nan/inf explicitly so the caller's reports can show them as "n/a" rather
than crash.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Metrics — DSR + Bootstrap CI

**Files:**
- Modify: `src/daytrader/research/bakeoff/metrics.py`
- Modify: `tests/research/bakeoff/test_metrics.py`

Deflated Sharpe Ratio (López de Prado 2014) and percentile bootstrap CI of Sharpe.

### - [ ] Step 1: Append failing tests

Append to `tests/research/bakeoff/test_metrics.py`:

```python
from daytrader.research.bakeoff.metrics import (
    deflated_sharpe_pvalue, bootstrap_sharpe_ci,
)
from scipy.stats import norm


# --- DSR ---

def test_dsr_pvalue_zero_sharpe_always_high():
    """Sharpe of 0 is never significant; p-value should be ~0.5 or higher."""
    returns = pd.Series([0.001, -0.001] * 126)   # SR ≈ 0
    p = deflated_sharpe_pvalue(returns, n_trials=2)
    assert p > 0.4


def test_dsr_pvalue_very_high_sharpe_is_significant():
    """SR way above the inflated null should give low p-value."""
    # Build a series with SR ≈ 2 annualized.
    # mean_daily = 2 / sqrt(252) * std → build returns with mean/std ratio.
    # Just hardcode a deterministic series.
    returns = pd.Series([0.002] * 126 + [0.001] * 126)   # mean=0.0015, std=0.0005
    p = deflated_sharpe_pvalue(returns, n_trials=2)
    assert p < 0.05


def test_dsr_pvalue_more_trials_makes_harder_to_pass():
    returns = pd.Series([0.0015] * 200 + [0.0005] * 52)   # mildly positive
    p2 = deflated_sharpe_pvalue(returns, n_trials=2)
    p100 = deflated_sharpe_pvalue(returns, n_trials=100)
    # More multiple-testing penalty → higher p-value for same data.
    assert p100 >= p2


# --- Bootstrap CI ---

def test_bootstrap_sharpe_ci_zero_mean_brackets_zero():
    """Zero-mean returns should have 95% CI that includes 0."""
    # Deterministic seed for reproducibility.
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0, 0.01, 252))
    lo, hi = bootstrap_sharpe_ci(returns, n_resamples=1000, seed=42)
    assert lo < 0 < hi


def test_bootstrap_sharpe_ci_positive_drift_positive_lower_bound():
    """Strong positive drift should give positive lower bound."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.005, 0.005, 500))   # huge SR
    lo, hi = bootstrap_sharpe_ci(returns, n_resamples=1000, seed=42)
    assert lo > 0
```

### - [ ] Step 2: Run — expect ImportError

```bash
.venv/bin/pytest tests/research/bakeoff/test_metrics.py -v
```

Expected: FAIL on the two new symbols.

### - [ ] Step 3: Append implementation

Append to `src/daytrader/research/bakeoff/metrics.py`:

```python
from scipy.stats import norm as _norm


_EULER_MASCHERONI = 0.5772156649015329


def _expected_max_sharpe(n_trials: int) -> float:
    """López de Prado's expected max of n i.i.d. standard-normal Sharpes.
    E[max] ≈ (1 - γ) · Φ⁻¹(1 - 1/n) + γ · Φ⁻¹(1 - 1/(n·e))
    where γ is Euler-Mascheroni.
    """
    if n_trials <= 1:
        return 0.0
    inv1 = _norm.ppf(1 - 1.0 / n_trials)
    inv2 = _norm.ppf(1 - 1.0 / (n_trials * math.e))
    return (1 - _EULER_MASCHERONI) * inv1 + _EULER_MASCHERONI * inv2


def deflated_sharpe_pvalue(
    daily_returns: pd.Series,
    n_trials: int,
) -> float:
    """Deflated Sharpe Ratio p-value (López de Prado 2014).

    Tests whether the observed Sharpe is significantly greater than the
    expected max Sharpe of `n_trials` i.i.d. null candidates. Higher
    n_trials → harder to pass.

    Returns p = P(DSR > observed | null). Small p is significant.
    """
    T = len(daily_returns)
    if T < 2:
        return float("nan")
    # Unadjusted Sharpe (non-annualized for variance calc).
    mean = float(daily_returns.mean())
    std = float(daily_returns.std(ddof=1))
    if std == 0:
        return float("nan")
    sr_hat = mean / std   # per-day Sharpe
    # Skew and excess kurtosis of daily returns.
    skew = float(((daily_returns - mean) ** 3).mean() / (std ** 3))
    # excess kurtosis
    kurt = float(((daily_returns - mean) ** 4).mean() / (std ** 4) - 3)
    # Estimated stdev of SR hat under the null.
    sr_var = (1 - skew * sr_hat + (kurt / 4) * sr_hat ** 2) / (T - 1)
    if sr_var <= 0:
        return float("nan")
    sr_std = math.sqrt(sr_var)
    # Expected max SR from n_trials independent candidates (per-day units).
    exp_max_sr = _expected_max_sharpe(n_trials)
    # Normalize by √T the way the paper does? The formula is:
    # DSR = (SR_hat - SR_0) / sr_std
    # then p-value = 1 - Φ(DSR)
    z = (sr_hat - exp_max_sr * sr_std) / sr_std
    return float(1 - _norm.cdf(z))


def bootstrap_sharpe_ci(
    daily_returns: pd.Series,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Percentile bootstrap CI for annualized Sharpe."""
    rng = np.random.default_rng(seed)
    n = len(daily_returns)
    values = daily_returns.to_numpy()
    sharpes = np.empty(n_resamples)
    for i in range(n_resamples):
        sample = rng.choice(values, size=n, replace=True)
        mean = sample.mean()
        std = sample.std(ddof=1)
        sharpes[i] = (mean / std * math.sqrt(TRADING_DAYS_PER_YEAR)) if std > 0 else 0.0
    lo_q = (1 - confidence) / 2
    hi_q = 1 - lo_q
    return float(np.quantile(sharpes, lo_q)), float(np.quantile(sharpes, hi_q))
```

### - [ ] Step 4: Run — expect all PASS

```bash
.venv/bin/pytest tests/research/bakeoff/test_metrics.py -v
```

Expected: all 18 tests pass.

### - [ ] Step 5: Commit

```bash
git add src/daytrader/research/bakeoff/metrics.py tests/research/bakeoff/test_metrics.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): Plan 3 metrics — DSR + bootstrap Sharpe CI

Deflated Sharpe p-value (López de Prado 2014 formula: observed SR minus
expected max SR of n_trials iid candidates, normalized by the variance
of SR_hat under skew+kurt). Bootstrap percentile CI for annualized
Sharpe, default 10k resamples.

Uses scipy.stats.norm (already installed). n_trials plumbed through for
Plan 3's n_trials=2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Trade utils helper (for SE scripts)

**Files:**
- Create: `scripts/_plan3_trade_utils.py`
- Create: `tests/scripts/test_plan3_trade_utils.py`

Shared helpers used by main run + SE scripts: `filter_trades_by_window`, `flip_trades_direction`, `equity_curve_from_pnl`, `daily_returns_from_trades`.

### - [ ] Step 1: Write failing tests

Create `tests/scripts/test_plan3_trade_utils.py`:

```python
"""Tests for Plan 3 trade utilities."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from _plan3_trade_utils import (  # noqa: E402
    daily_returns_from_pnl,
    equity_curve_from_pnl,
    filter_trades_by_window,
    flip_trades_direction,
)

from daytrader.research.bakeoff.strategies._trade import Trade, TradeOutcome


def _trade(d, direction, entry=100.0, exit=101.0):
    ts = datetime.fromisoformat(f"{d}T13:35:00+00:00")
    stop = entry - 10 if direction == "long" else entry + 10
    return Trade(
        date=d, symbol="SPY", direction=direction,
        entry_time=ts, entry_price=entry, stop_price=stop,
        target_price=float("nan"),
        exit_time=ts, exit_price=exit,
        outcome=TradeOutcome.EOD, r_multiple=(exit - entry) / 10 if direction == "long" else (entry - exit) / 10,
    )


def test_filter_trades_by_window_inclusive():
    trades = [
        _trade("2023-12-31", "long"),
        _trade("2024-01-01", "long"),
        _trade("2024-06-15", "long"),
        _trade("2024-12-31", "long"),
        _trade("2025-01-01", "long"),
    ]
    picked = filter_trades_by_window(trades, date(2024, 1, 1), date(2024, 12, 31))
    assert len(picked) == 3
    assert picked[0].date == "2024-01-01"
    assert picked[-1].date == "2024-12-31"


def test_flip_trades_direction_swaps_and_preserves_other_fields():
    t = _trade("2024-06-10", "long", entry=100, exit=105)
    flipped = flip_trades_direction([t])
    assert len(flipped) == 1
    f = flipped[0]
    assert f.direction == "short"
    # Signal reversal: a long @100 exit @105 (gross +5) becomes short @100 exit @105 (gross -5).
    # Under flip, we keep entry/exit prices, just swap direction label. The caller's pnl computation
    # (which is direction-aware) will flip the sign.
    assert f.entry_price == t.entry_price
    assert f.exit_price == t.exit_price
    assert f.symbol == t.symbol
    assert f.date == t.date


def test_flip_trades_direction_short_becomes_long():
    t = _trade("2024-06-10", "short", entry=100, exit=95)
    flipped = flip_trades_direction([t])
    assert flipped[0].direction == "long"


def test_equity_curve_from_pnl_cumulative():
    pnl = pd.Series([1.0, -0.5, 2.0, -0.2])
    starting = 10.0
    eq = equity_curve_from_pnl(pnl, starting_capital=starting)
    # Equity = 10 + cumulative pnl = [11, 10.5, 12.5, 12.3]
    assert list(eq) == pytest.approx([11.0, 10.5, 12.5, 12.3])


def test_daily_returns_from_pnl_groups_by_trade_date():
    """Two trades same day should combine before dividing by equity-at-start."""
    pnl = pd.Series([1.0, 2.0, -1.0])
    dates = [date(2024, 6, 10), date(2024, 6, 10), date(2024, 6, 11)]
    starting = 100.0
    dr = daily_returns_from_pnl(pnl, dates, starting_capital=starting)
    # Day 1: pnl = 3.0, equity at start = 100, return = 3.0/100 = 0.03
    # Day 2: pnl = -1.0, equity at start = 103, return = -1.0/103
    assert len(dr) == 2
    assert dr.iloc[0] == pytest.approx(0.03)
    assert dr.iloc[1] == pytest.approx(-1.0 / 103.0)
```

### - [ ] Step 2: Run — expect ImportError

```bash
.venv/bin/pytest tests/scripts/test_plan3_trade_utils.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

### - [ ] Step 3: Implement

Create `scripts/_plan3_trade_utils.py`:

```python
"""Shared trade utilities for Plan 3 scan scripts.

Lives in scripts/ (not the strategy package) because these helpers are
evaluation-specific and don't belong in the Trade wire format.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date as _date
from typing import Iterable, Sequence

import pandas as pd

from daytrader.research.bakeoff.strategies._trade import Trade


def filter_trades_by_window(
    trades: Iterable[Trade], start: _date, end: _date
) -> list[Trade]:
    """Inclusive on both ends using trade.date string."""
    start_s = start.isoformat()
    end_s = end.isoformat()
    return [t for t in trades if start_s <= t.date <= end_s]


def flip_trades_direction(trades: Iterable[Trade]) -> list[Trade]:
    """Return new Trade objects with direction swapped.

    Used for SE-2 signal reversal: runs the same entries with opposite
    signal sign. PnL calculation downstream is direction-aware, so flipping
    the label effectively flips the PnL sign.
    """
    out = []
    for t in trades:
        new_dir = "short" if t.direction == "long" else "long"
        # Frozen dataclass → use `replace` to get a new instance.
        out.append(replace(t, direction=new_dir))
    return out


def equity_curve_from_pnl(
    pnl: pd.Series, starting_capital: float
) -> pd.Series:
    """Cumulative equity given a per-trade PnL series."""
    return starting_capital + pnl.cumsum()


def daily_returns_from_pnl(
    pnl: pd.Series,
    trade_dates: Sequence[_date],
    starting_capital: float,
) -> pd.Series:
    """Aggregate trade-level PnL by date, compute daily fractional returns.

    Returns a Series indexed by date. Each day's return = sum(day's pnl)
    / equity-at-start-of-day.
    """
    df = pd.DataFrame({"pnl": list(pnl), "date": list(trade_dates)})
    daily_pnl = df.groupby("date")["pnl"].sum().sort_index()
    equity_at_day_start = starting_capital + daily_pnl.cumsum().shift(1).fillna(0)
    return daily_pnl / equity_at_day_start
```

### - [ ] Step 4: Run — expect all PASS

```bash
.venv/bin/pytest tests/scripts/test_plan3_trade_utils.py -v
```

Expected: 5 PASSED.

### - [ ] Step 5: Commit

```bash
git add scripts/_plan3_trade_utils.py tests/scripts/test_plan3_trade_utils.py
git commit -m "$(cat <<'EOF'
feat(bakeoff): Plan 3 shared trade utilities

filter_trades_by_window, flip_trades_direction (for SE-2),
equity_curve_from_pnl, daily_returns_from_pnl. Pure functions used by
main run + all 4 SE scripts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Main run script (Day 1 deliverable)

**Files:**
- Create: `scripts/bakeoff_plan3_main_run.py`
- Create: `docs/research/bakeoff/2026-04-21-plan3-main-report.md`
- Create: `docs/research/bakeoff/plan3_main_report.csv` (generated)

Runs S1a + S1b on replication + pure OOS windows, applies $0.50/trade cost, computes all metrics, emits markdown report + CSV.

### - [ ] Step 1: Create the script

Create `scripts/bakeoff_plan3_main_run.py`:

```python
"""Plan 3 Day 1: main run report for S1a + S1b on SPY.

Runs the two active candidates on replication (2018-05 → 2024-03) and
pure OOS (2024-04 → 2024-12) windows, applies the locked $0.50/trade
cost, computes all spec §2.4 metrics, writes markdown + CSV.

Usage:
    DATABENTO_API_KEY=<key> .venv/bin/python scripts/bakeoff_plan3_main_run.py
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan3_trade_utils import (
    daily_returns_from_pnl,
    equity_curve_from_pnl,
    filter_trades_by_window,
)

from daytrader.research.bakeoff.costs import apply_per_trade_cost, trade_gross_pnl
from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.metrics import (
    annualized_sharpe, annualized_sortino,
    bootstrap_sharpe_ci, calmar_ratio,
    deflated_sharpe_pvalue, expectancy_r,
    longest_drawdown_duration, max_drawdown, profit_factor,
)
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)

STARTING_CAPITAL = 10_000.0
COST_PER_TRADE = 0.50
N_TRIALS = 2
OUTPUT_DIR = Path("docs/research/bakeoff")


def _evaluate(trades, label):
    if not trades:
        return {"label": label, "n": 0}
    # Per-trade net PnL.
    net = apply_per_trade_cost(trades, COST_PER_TRADE)
    # r_multiple for expectancy — recompute on net basis is common, but spec §2.4 says
    # expectancy in R — use trade.r_multiple (which is pre-cost). Report gross R.
    r_mults = pd.Series([t.r_multiple for t in trades])
    # Daily returns aggregated.
    from datetime import date as _date
    trade_dates = [_date.fromisoformat(t.date) for t in trades]
    eq = equity_curve_from_pnl(net, starting_capital=STARTING_CAPITAL)
    dr = daily_returns_from_pnl(net, trade_dates, starting_capital=STARTING_CAPITAL)
    # Costs applied → recompute.
    sharpe = annualized_sharpe(dr)
    sortino = annualized_sortino(dr)
    calmar = calmar_ratio(eq, trading_days=252)
    mdd = max_drawdown(eq)
    dd_dur = longest_drawdown_duration(eq)
    pf = profit_factor(net)
    exp_r = expectancy_r(r_mults)
    dsr_p = deflated_sharpe_pvalue(dr, n_trials=N_TRIALS)
    ci_lo, ci_hi = bootstrap_sharpe_ci(dr, n_resamples=10_000, seed=42)
    return {
        "label": label,
        "n": len(trades),
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_dd": mdd,
        "longest_dd_days": dd_dur,
        "profit_factor": pf,
        "expectancy_r": exp_r,
        "dsr_pvalue": dsr_p,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "total_net_pnl": float(net.sum()),
    }


def _hard_gate_report(row):
    """Return a dict of {gate: 'PASS'/'FAIL'} using spec §2.4."""
    gates = {
        "sharpe ≥ 1.0": row.get("sharpe", float("nan")) >= 1.0,
        "max_dd ≤ 15%": row.get("max_dd", float("inf")) <= 0.15,
        "profit_factor ≥ 1.3": row.get("profit_factor", 0) >= 1.3,
        "n ≥ 100 (pure OOS)": row.get("n", 0) >= 100,
        "DSR p < 0.10": row.get("dsr_pvalue", float("inf")) < 0.10,
    }
    return {k: "PASS" if v else "FAIL" for k, v in gates.items()}


def main():
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print("DATABENTO_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    print("Loading SPY 1m (2018-05 → 2024-12) from cache...")
    ds = load_spy_1m(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key,
        cache_dir=Path("data/cache/ohlcv_spy_kat"),
    )
    bars_1m = ds.bars

    # Generate trades on the full window once; window-filter via date.
    print("Generating S1a / S1b trades over full window...")
    s1a_all = S1a_ORB_TargetAndEOD(symbol="SPY", or_minutes=5, target_multiple=10.0).generate_trades(bars_1m)
    s1b_all = S1b_ORB_EODOnly(symbol="SPY", or_minutes=5).generate_trades(bars_1m)

    cells = []
    for cand_name, trades_all in [("S1a", s1a_all), ("S1b", s1b_all)]:
        for win_name, start, end in [
            ("replication", date(2018, 5, 1), date(2024, 3, 31)),
            ("pure_oos", date(2024, 4, 1), date(2024, 12, 31)),
        ]:
            window_trades = filter_trades_by_window(trades_all, start, end)
            row = _evaluate(window_trades, f"{cand_name} ({win_name})")
            row["candidate"] = cand_name
            row["window"] = win_name
            cells.append(row)

    # Markdown report to stdout.
    print()
    print("=== Plan 3 Main Run Report ===")
    print(f"Cost/trade: ${COST_PER_TRADE}; starting capital: ${STARTING_CAPITAL}; n_trials={N_TRIALS}")
    print()
    header = ["label", "n", "sharpe", "sortino", "calmar", "max_dd", "longest_dd_days",
             "profit_factor", "expectancy_r", "dsr_pvalue", "ci_lo", "ci_hi", "total_net_pnl"]
    print(" | ".join(h.rjust(14) for h in header))
    for c in cells:
        vals = [str(c.get(k, "")) if not isinstance(c.get(k), float) else f"{c.get(k):.3f}" for k in header]
        print(" | ".join(v.rjust(14) for v in vals))

    # Hard-gate pass/fail on pure_oos rows only.
    print()
    print("=== Hard gates (pure OOS) ===")
    for c in cells:
        if c.get("window") != "pure_oos":
            continue
        gates = _hard_gate_report(c)
        overall = "PASS ALL" if all(v == "PASS" for v in gates.values()) else "FAIL"
        print(f"{c['candidate']}: {overall}")
        for gate, result in gates.items():
            print(f"  {gate:<28} {result}")

    # CSV.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "plan3_main_report.csv"
    pd.DataFrame(cells).to_csv(csv_path, index=False)
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
```

### - [ ] Step 2: Commit script

```bash
git add scripts/bakeoff_plan3_main_run.py
git commit -m "feat(bakeoff): Plan 3 main run script (Day 1 deliverable)

Loads cached SPY, runs S1a/S1b on replication + pure OOS, applies
\$0.50/trade cost, computes all spec §2.4 metrics, emits markdown + CSV
with hard-gate pass/fail summary.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### - [ ] Step 3: Execute the main run

```bash
cd "/Users/tylersan/Projects/Day trading"
source ~/.zshrc
.venv/bin/python scripts/bakeoff_plan3_main_run.py | tee /tmp/plan3_main_run.txt
```

Sanity-check output:
- Exactly 4 rows (2 candidates × 2 windows).
- Every metric field populated (no crashes, no blank cells).
- Hard-gate summary prints for both pure_oos rows.

### - [ ] Step 4: Commit generated CSV

```bash
git add docs/research/bakeoff/plan3_main_report.csv
git commit -m "data(bakeoff): Plan 3 main run CSV

Generated by scripts/bakeoff_plan3_main_run.py against cached SPY
2018-05 → 2024-12. Committed for findings reproducibility.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### - [ ] Step 5: Draft the main report markdown

Create `docs/research/bakeoff/2026-04-21-plan3-main-report.md` using this skeleton. Fill the tables from `/tmp/plan3_main_run.txt`.

```markdown
# Plan 3 Day 1 — Main Run Report

**Date:** 2026-04-21
**Spec:** [`docs/superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md`](../../superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md)
**Config:** SPY 2018-05 → 2024-12 ARCX.PILLAR cache; starting capital $10,000; cost $0.50/trade; `n_trials = 2`.
**Reproduce:** `.venv/bin/python scripts/bakeoff_plan3_main_run.py`

## Results

| candidate | window | n | sharpe | sortino | calmar | max_dd | longest_dd_days | profit_factor | expectancy_r | dsr_p | ci95 | net_pnl$ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
[... fill from /tmp/plan3_main_run.txt ...]

## Hard gates on pure OOS (spec §2.4)

Required to pass (all five):
1. Sharpe (net) ≥ 1.0
2. Max drawdown ≤ 15%
3. Profit factor ≥ 1.3
4. n_trades ≥ 100
5. DSR p-value < 0.10

### S1a (pure_oos)
[... PASS / FAIL per gate ...]

### S1b (pure_oos)
[... PASS / FAIL per gate ...]

## Interpretation

[2-3 paragraphs reading the numbers. At minimum: whether either candidate passed all 5, and the single biggest failure mode if not.]

## Next

Day 2: sensitivity experiments SE-1..SE-4 to confirm robustness (or fragility) of the Day 1 conclusion.
```

### - [ ] Step 6: Commit the main report

```bash
git add docs/research/bakeoff/2026-04-21-plan3-main-report.md
git commit -m "$(cat <<'EOF'
docs(bakeoff): Plan 3 Day 1 main run report

Hard-gate pass/fail evaluation of S1a + S1b on SPY pure OOS window.
Fills the §2.4 decision input for Plan 3's §6 framework.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Day 1 complete.** Confirm with user before starting Day 2.

---

## Task 6: SE-1 Cost sensitivity

**Files:**
- Create: `scripts/bakeoff_plan3_se1_cost.py`
- Create: `docs/research/bakeoff/plan3_se1_cost.csv` (generated)

Scan `cost_per_trade ∈ {0.0, 0.5, 1.0}` for S1a + S1b on pure OOS.

### - [ ] Step 1: Write the script

Create `scripts/bakeoff_plan3_se1_cost.py`:

```python
"""SE-1: cost sensitivity. Scan cost_per_trade ∈ {0.0, 0.5, 1.0} for S1a
and S1b on pure OOS. If only cost=0 passes Sharpe ≥ 1.0, the strategy's
edge is paper-thin vs. slippage — strong against the candidate.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan3_trade_utils import (
    daily_returns_from_pnl, equity_curve_from_pnl, filter_trades_by_window,
)

from daytrader.research.bakeoff.costs import apply_per_trade_cost
from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.metrics import (
    annualized_sharpe, max_drawdown, profit_factor,
)
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)


STARTING_CAPITAL = 10_000.0
OUTPUT_DIR = Path("docs/research/bakeoff")
COSTS = [0.0, 0.5, 1.0]
OOS_START = date(2024, 4, 1)
OOS_END = date(2024, 12, 31)


def main():
    api_key = os.environ["DATABENTO_API_KEY"]
    ds = load_spy_1m(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key, cache_dir=Path("data/cache/ohlcv_spy_kat"),
    )
    bars_1m = ds.bars

    s1a = filter_trades_by_window(
        S1a_ORB_TargetAndEOD(symbol="SPY").generate_trades(bars_1m),
        OOS_START, OOS_END,
    )
    s1b = filter_trades_by_window(
        S1b_ORB_EODOnly(symbol="SPY").generate_trades(bars_1m),
        OOS_START, OOS_END,
    )

    rows = []
    print(f"{'cand':>4} {'cost':>5} {'n':>4} {'sharpe':>8} {'max_dd':>7} {'pf':>6} {'net_pnl':>10}")
    for cand_name, trades in [("S1a", s1a), ("S1b", s1b)]:
        from datetime import date as _d
        trade_dates = [_d.fromisoformat(t.date) for t in trades]
        for cost in COSTS:
            net = apply_per_trade_cost(trades, cost)
            eq = equity_curve_from_pnl(net, STARTING_CAPITAL)
            dr = daily_returns_from_pnl(net, trade_dates, STARTING_CAPITAL)
            row = {
                "candidate": cand_name,
                "cost_per_trade": cost,
                "n": len(trades),
                "sharpe": annualized_sharpe(dr),
                "max_dd": max_drawdown(eq),
                "profit_factor": profit_factor(net),
                "net_pnl_usd": float(net.sum()),
            }
            rows.append(row)
            print(f"{cand_name:>4} {cost:>5.2f} {row['n']:>4} "
                  f"{row['sharpe']:>+8.3f} {row['max_dd']:>7.1%} "
                  f"{row['profit_factor']:>6.3f} {row['net_pnl_usd']:>+10.1f}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "plan3_se1_cost.csv", index=False)
    print(f"\nWrote {OUTPUT_DIR / 'plan3_se1_cost.csv'}")


if __name__ == "__main__":
    main()
```

### - [ ] Step 2: Run + commit

```bash
.venv/bin/python scripts/bakeoff_plan3_se1_cost.py | tee /tmp/plan3_se1.txt

git add scripts/bakeoff_plan3_se1_cost.py docs/research/bakeoff/plan3_se1_cost.csv
git commit -m "feat(bakeoff): Plan 3 SE-1 cost sensitivity

Scans cost/trade ∈ {0.0, 0.5, 1.0} on S1a/S1b pure OOS. Output to CSV
+ stdout for findings doc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: SE-2 Signal reversal

**Files:**
- Create: `scripts/bakeoff_plan3_se2_reversal.py`
- Create: `docs/research/bakeoff/plan3_se2_reversal.csv` (generated)

Flip S1a/S1b direction labels, compute metrics. If reversed also profits → long-bias β, not alpha → reject candidate per spec §3.4.

### - [ ] Step 1: Write the script

Create `scripts/bakeoff_plan3_se2_reversal.py`:

```python
"""SE-2: signal reversal. Flip every trade's direction label; if the
reversed strategy also has positive Sharpe / Sortino, the "edge" is
market beta (long-bias) not alpha. Reject per spec §3.4 SE-2 rule.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan3_trade_utils import (
    daily_returns_from_pnl, equity_curve_from_pnl, filter_trades_by_window,
    flip_trades_direction,
)

from daytrader.research.bakeoff.costs import apply_per_trade_cost
from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.metrics import (
    annualized_sharpe, annualized_sortino, profit_factor,
)
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)


STARTING_CAPITAL = 10_000.0
COST = 0.50
OUTPUT_DIR = Path("docs/research/bakeoff")
OOS_START = date(2024, 4, 1)
OOS_END = date(2024, 12, 31)


def _metrics(trades, label):
    if not trades:
        return {"label": label, "n": 0}
    from datetime import date as _d
    dates = [_d.fromisoformat(t.date) for t in trades]
    net = apply_per_trade_cost(trades, COST)
    eq = equity_curve_from_pnl(net, STARTING_CAPITAL)
    dr = daily_returns_from_pnl(net, dates, STARTING_CAPITAL)
    return {
        "label": label,
        "n": len(trades),
        "sharpe": annualized_sharpe(dr),
        "sortino": annualized_sortino(dr),
        "profit_factor": profit_factor(net),
        "net_pnl_usd": float(net.sum()),
    }


def main():
    api_key = os.environ["DATABENTO_API_KEY"]
    ds = load_spy_1m(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key, cache_dir=Path("data/cache/ohlcv_spy_kat"),
    )
    bars_1m = ds.bars

    s1a = filter_trades_by_window(
        S1a_ORB_TargetAndEOD(symbol="SPY").generate_trades(bars_1m),
        OOS_START, OOS_END,
    )
    s1b = filter_trades_by_window(
        S1b_ORB_EODOnly(symbol="SPY").generate_trades(bars_1m),
        OOS_START, OOS_END,
    )

    rows = []
    for cand_name, trades in [("S1a", s1a), ("S1b", s1b)]:
        original = _metrics(trades, f"{cand_name} original")
        reversed_ = _metrics(flip_trades_direction(trades), f"{cand_name} reversed")
        # Reject flag: original and reversed both positive → long-bias β.
        reject = (original.get("sharpe", 0) > 0 and reversed_.get("sharpe", 0) > 0)
        rows.append({**original, "reject_for_long_bias": reject})
        rows.append({**reversed_, "reject_for_long_bias": reject})
        print(f"{cand_name}: original sharpe {original.get('sharpe', 0):+.3f}, "
              f"reversed {reversed_.get('sharpe', 0):+.3f}, "
              f"reject={'YES' if reject else 'no'}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "plan3_se2_reversal.csv", index=False)


if __name__ == "__main__":
    main()
```

### - [ ] Step 2: Run + commit

```bash
.venv/bin/python scripts/bakeoff_plan3_se2_reversal.py | tee /tmp/plan3_se2.txt

git add scripts/bakeoff_plan3_se2_reversal.py docs/research/bakeoff/plan3_se2_reversal.csv
git commit -m "feat(bakeoff): Plan 3 SE-2 signal reversal — long-bias check

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: SE-3 Quarterly OOS stability

**Files:**
- Create: `scripts/bakeoff_plan3_se3_quarterly.py`
- Create: `docs/research/bakeoff/plan3_se3_quarterly.csv`

Split pure OOS (2024-04 → 2024-12) into Q2/Q3/Q4, compute per-quarter equity, flag any quarter < −3% equity.

### - [ ] Step 1: Write the script

Create `scripts/bakeoff_plan3_se3_quarterly.py`:

```python
"""SE-3: OOS quarterly stability. Split pure OOS into Q2/Q3/Q4 2024,
compute per-quarter PnL and equity change. Any quarter < -3% flagged.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan3_trade_utils import filter_trades_by_window

from daytrader.research.bakeoff.costs import apply_per_trade_cost
from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.strategies.s1_orb import (
    S1a_ORB_TargetAndEOD, S1b_ORB_EODOnly,
)


STARTING_CAPITAL = 10_000.0
COST = 0.50
OUTPUT_DIR = Path("docs/research/bakeoff")
QUARTERS = [
    ("2024Q2", date(2024, 4, 1), date(2024, 6, 30)),
    ("2024Q3", date(2024, 7, 1), date(2024, 9, 30)),
    ("2024Q4", date(2024, 10, 1), date(2024, 12, 31)),
]


def main():
    api_key = os.environ["DATABENTO_API_KEY"]
    ds = load_spy_1m(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key, cache_dir=Path("data/cache/ohlcv_spy_kat"),
    )
    bars_1m = ds.bars

    s1a = S1a_ORB_TargetAndEOD(symbol="SPY").generate_trades(bars_1m)
    s1b = S1b_ORB_EODOnly(symbol="SPY").generate_trades(bars_1m)

    rows = []
    print(f"{'cand':>4} {'quarter':>8} {'n':>4} {'net_pnl$':>10} {'equity_pct':>10} {'flag':>5}")
    for cand_name, trades_all in [("S1a", s1a), ("S1b", s1b)]:
        for q_name, start, end in QUARTERS:
            q_trades = filter_trades_by_window(trades_all, start, end)
            net = apply_per_trade_cost(q_trades, COST)
            pnl = float(net.sum())
            eq_pct = pnl / STARTING_CAPITAL
            fragile = eq_pct < -0.03
            rows.append({
                "candidate": cand_name,
                "quarter": q_name,
                "n": len(q_trades),
                "net_pnl_usd": pnl,
                "equity_pct": eq_pct,
                "fragile_flag": fragile,
            })
            print(f"{cand_name:>4} {q_name:>8} {len(q_trades):>4} "
                  f"{pnl:>+10.1f} {eq_pct:>+10.2%} {'YES' if fragile else '':>5}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "plan3_se3_quarterly.csv", index=False)


if __name__ == "__main__":
    main()
```

### - [ ] Step 2: Run + commit

```bash
.venv/bin/python scripts/bakeoff_plan3_se3_quarterly.py | tee /tmp/plan3_se3.txt

git add scripts/bakeoff_plan3_se3_quarterly.py docs/research/bakeoff/plan3_se3_quarterly.csv
git commit -m "feat(bakeoff): Plan 3 SE-3 OOS quarterly stability

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: SE-4 OR duration scan

**Files:**
- Create: `scripts/bakeoff_plan3_se4_or_duration.py`
- Create: `docs/research/bakeoff/plan3_se4_or_duration.csv`

Run S1a with `or_minutes ∈ {5, 10, 15, 30}` on pure OOS.

### - [ ] Step 1: Write the script

Create `scripts/bakeoff_plan3_se4_or_duration.py`:

```python
"""SE-4: OR duration sensitivity. Run S1a with or_minutes ∈ {5, 10, 15, 30}
on pure OOS. If only 5 passes → overfit to indicator choice.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan3_trade_utils import (
    daily_returns_from_pnl, equity_curve_from_pnl, filter_trades_by_window,
)

from daytrader.research.bakeoff.costs import apply_per_trade_cost
from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.metrics import (
    annualized_sharpe, max_drawdown, profit_factor,
)
from daytrader.research.bakeoff.strategies.s1_orb import S1a_ORB_TargetAndEOD


STARTING_CAPITAL = 10_000.0
COST = 0.50
OUTPUT_DIR = Path("docs/research/bakeoff")
OR_MINUTES = [5, 10, 15, 30]
OOS_START = date(2024, 4, 1)
OOS_END = date(2024, 12, 31)


def main():
    api_key = os.environ["DATABENTO_API_KEY"]
    ds = load_spy_1m(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key, cache_dir=Path("data/cache/ohlcv_spy_kat"),
    )
    bars_1m = ds.bars

    rows = []
    print(f"{'or_min':>7} {'n':>4} {'sharpe':>8} {'max_dd':>7} {'pf':>6} {'net_pnl':>10}")
    for or_min in OR_MINUTES:
        trades_all = S1a_ORB_TargetAndEOD(
            symbol="SPY", or_minutes=or_min, target_multiple=10.0
        ).generate_trades(bars_1m)
        trades = filter_trades_by_window(trades_all, OOS_START, OOS_END)
        from datetime import date as _d
        dates = [_d.fromisoformat(t.date) for t in trades]
        net = apply_per_trade_cost(trades, COST)
        eq = equity_curve_from_pnl(net, STARTING_CAPITAL)
        dr = daily_returns_from_pnl(net, dates, STARTING_CAPITAL) if trades else pd.Series(dtype=float)
        row = {
            "or_minutes": or_min,
            "n": len(trades),
            "sharpe": annualized_sharpe(dr) if len(dr) else float("nan"),
            "max_dd": max_drawdown(eq) if len(eq) else float("nan"),
            "profit_factor": profit_factor(net) if len(net) else float("nan"),
            "net_pnl_usd": float(net.sum()) if len(net) else 0.0,
        }
        rows.append(row)
        print(f"{or_min:>7} {row['n']:>4} {row['sharpe']:>+8.3f} "
              f"{row['max_dd']:>7.1%} {row['profit_factor']:>6.3f} "
              f"{row['net_pnl_usd']:>+10.1f}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "plan3_se4_or_duration.csv", index=False)


if __name__ == "__main__":
    main()
```

### - [ ] Step 2: Run + commit

```bash
.venv/bin/python scripts/bakeoff_plan3_se4_or_duration.py | tee /tmp/plan3_se4.txt

git add scripts/bakeoff_plan3_se4_or_duration.py docs/research/bakeoff/plan3_se4_or_duration.csv
git commit -m "feat(bakeoff): Plan 3 SE-4 OR duration sensitivity

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Sensitivity report (Day 2 deliverable)

**Files:**
- Create: `docs/research/bakeoff/2026-04-21-plan3-sensitivity.md`

Compile all 4 SE outputs into one readable document.

### - [ ] Step 1: Write the document

Create `docs/research/bakeoff/2026-04-21-plan3-sensitivity.md` using this template. Fill tables from `/tmp/plan3_se*.txt`.

```markdown
# Plan 3 Day 2 — Sensitivity Experiments

**Date:** 2026-04-21
**Scope:** SE-1..SE-4 per parent spec §3.4 (SE-5/6 deferred with S2).
**Window:** Pure OOS 2024-04 → 2024-12, unless noted.

## SE-1 Cost sensitivity

Scan `cost_per_trade ∈ {0.0, 0.5, 1.0}`. If only cost=0 passes Sharpe ≥ 1.0 → edge is paper-thin.

| candidate | cost/trade | n | sharpe | max_dd | profit_factor | net_pnl $ |
|---|---:|---:|---:|---:|---:|---:|
[... fill from plan3_se1_cost.csv / /tmp/plan3_se1.txt ...]

**Interpretation:** [1 sentence.]

## SE-2 Signal reversal

Flip direction label on all OOS trades. If reversed also profits → long-bias β.

| candidate | variant | n | sharpe | sortino | profit_factor | net_pnl $ |
|---|---|---:|---:|---:|---:|---:|
[... fill ...]

**Reject flag:** [which candidates have both original AND reversed with positive Sharpe.]

## SE-3 OOS quarterly stability

Split 2024-04..2024-12 into Q2/Q3/Q4.

| candidate | quarter | n | net_pnl $ | equity % | fragile (< −3%) |
|---|---|---:|---:|---:|:---:|
[... fill ...]

## SE-4 OR duration scan (S1a)

`or_minutes ∈ {5, 10, 15, 30}` on pure OOS.

| or_minutes | n | sharpe | max_dd | profit_factor | net_pnl $ |
|---:|---:|---:|---:|---:|---:|
[... fill ...]

**Interpretation:** Does only or_minutes=5 pass, or is the behavior monotone / stable across durations?

## Next

Day 3: findings doc reads Day 1 + Day 2 + commits to spec §6 decision branch.
```

### - [ ] Step 2: Commit

```bash
git add docs/research/bakeoff/2026-04-21-plan3-sensitivity.md
git commit -m "$(cat <<'EOF'
docs(bakeoff): Plan 3 Day 2 sensitivity report (SE-1..SE-4)

Compiled results from the 4 sensitivity scans against S1a/S1b on SPY
pure OOS 2024. Feeds the findings doc's robustness section.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Day 2 complete.** Confirm with user before Day 3.

---

## Task 11: Findings doc + §6 decision (Day 3)

**Files:**
- Create: `docs/research/bakeoff/2026-04-21-plan3-findings.md`

Read Day 1 + Day 2 outputs, apply spec §6 decision table, commit to one branch.

### - [ ] Step 1: Determine the decision branch

Walk the three-row table from spec §6 top-to-bottom:

| Row | Condition | Action if matched |
|---|---|---|
| 1 | Both S1a and S1b fail ≥ 1 hard gate on pure OOS | Branch 1: "No Contract signed" (expected) |
| 2 | Exactly one candidate passes all 5 hard gates + survives SE-2 (reversed negative) + SE-3 (no fragile quarter) | Branch 2: lock as `locked_setup` — STOP plan execution and surface to user |
| 3 | Both pass | Branch 3: higher Sharpe → `locked_setup`; runner-up → `backup_setup` — STOP and surface |

The Day 1 report's "Hard gates" section gives row 1 immediately. Reports that are ambiguous (e.g., one gate edge-case) resolve to row 1 (conservative).

### - [ ] Step 2: Draft the findings doc

Create `docs/research/bakeoff/2026-04-21-plan3-findings.md`:

```markdown
# Plan 3 Findings — W2 Bake-off Closeout

**Date:** 2026-04-21
**Spec:** [`docs/superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md`](../../superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md)
**Parent spec:** [`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../../superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md)

---

## TL;DR

**Branch [N]**: [one-sentence verdict from §6.]

## Evidence summary

### Day 1 (main run, pure OOS 2024-04 → 2024-12, cost $0.50/trade)

Hard-gate pass/fail:

| Candidate | Sharpe ≥ 1.0 | Max DD ≤ 15% | PF ≥ 1.3 | n ≥ 100 | DSR p < 0.10 | Overall |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| S1a | ... | ... | ... | ... | ... | ... |
| S1b | ... | ... | ... | ... | ... | ... |

Data: [`plan3_main_report.csv`](plan3_main_report.csv). Detail in [`2026-04-21-plan3-main-report.md`](2026-04-21-plan3-main-report.md).

### Day 2 (sensitivity)

- SE-1 cost: [summary — did cost=0 pass while cost=0.5 failed?]
- SE-2 reversal: [did reversed candidates also Sharpe > 0 → long-bias β?]
- SE-3 quarterly: [any fragile quarter (< −3% equity)?]
- SE-4 OR duration: [only 5 works, or stable across?]

Detail in [`2026-04-21-plan3-sensitivity.md`](2026-04-21-plan3-sensitivity.md).

## Decision (per Plan 3 spec §6)

[Walk the three conditions top-to-bottom; state which matched and why.]

## Next action

[Based on branch:
- Branch 1: bake-off track closes. User chooses among: (a) explore new strategy families via fresh brainstorm, (b) pause research and start live discretionary trading with journal discipline guardrails, (c) pause entirely.
- Branch 2/3: stop Plan 3 here; open a new spec for `promote` CLI + YAML v2 + Contract.md filling before any live usage.]

## Limitations

- Evaluated on SPY only; MES (user's actual trading instrument) untested. Any "pass" here would still need MES validation before live.
- `n_trials = 2` is the most favorable DSR setting; any candidate that barely passes DSR on n=2 would likely fail with a larger family re-introduced.
- Pure OOS window is 9 months. Smaller than ideal; spec accepted this as the "actually available" independent set.
- Cost model is coarse ($0.50/trade fixed). Actual SPY retail costs vary by broker, position size, and spread; SE-1 partially addresses this.
```

### - [ ] Step 3: Commit

```bash
git add docs/research/bakeoff/2026-04-21-plan3-findings.md
git commit -m "$(cat <<'EOF'
docs(bakeoff): Plan 3 findings — bake-off closeout decision

Walks parent Plan 3 spec §6 decision table against Day 1 + Day 2 evidence.
Commits to branch [N] and names the next action per that branch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### - [ ] Step 4: STOP and surface if branch 2 or 3

If the decision is branch 2 or 3 (a candidate passes all gates), STOP executing. Do NOT merge to main. Do NOT start `promote` CLI work. Report to user: "Plan 3 landed on branch [N]; next step is a new scope discussion for `promote`/YAML v2 because the predicted 'no Contract' outcome did not materialize."

If branch 1 (expected), continue to Task 12.

---

## Task 12: Retrospective + merge (Day 3 close)

**Files:**
- Create: `docs/research/bakeoff/2026-04-21-bakeoff-retrospective.md`

Captures the whole bake-off arc (Plans 2a → 2b → 2c → 3), what infrastructure is preserved, what known gaps remain.

### - [ ] Step 1: Draft the retrospective

Create `docs/research/bakeoff/2026-04-21-bakeoff-retrospective.md`:

```markdown
# W2 Setup Gate Bake-off — Retrospective

**Date:** 2026-04-21
**Parent spec:** [`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../../superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md)

## Timeline

- **Plan 2a**: S1 ORB family implemented + SPY 1m data + KAT harness. Shipped PR #1.
- **Plan 2b**: S2 Intraday Momentum implemented + ARCX.PILLAR daily loader + S2 KAT. Shipped locally via branch merge.
- **S1 wrong-way fix**: PR #2. Caught via critical audit (hand-check of win-rate vs outcome counts).
- **Data expansion**: PR #3. Swapped DBEQ.BASIC (9 months) → ARCX.PILLAR (6.5 years). $0.88 one-time spend validated via Databento pre-flight cost API.
- **Plan 2c**: S2 ATR multiplier diagnostic. Decision: S2 deferred for redesign (branch 1 of Plan 2c spec §3.5). MFE/MAE helper preserved.
- **S2 deferral spec revision**: parent spec §3.1 candidate matrix updated; `n_trials` dropped from 4 to 2.
- **Plan 3**: this plan. [Outcome branch from findings doc.]

## What worked

- **TDD + frequent commits** made each step individually bisectable. When the S1 wrong-way bug surfaced in Plan 2b, reverting or patching was trivial because each strategy + test pair was its own commit.
- **Critical audits between plans** (at user's request) caught two real issues (S1 wrong-way, S2≡S2b degeneracy) that happy-path TDD did not. Build this habit into future projects.
- **Databento pre-flight cost API** (`client.metadata.get_cost`) gave exact $ estimate before pulling. My pre-pull estimates were 10-20× too high; the API was accurate to the cent. Always pre-flight before committing to a window.
- **Pre-committed decision frameworks** (Plan 2c §3.5 five branches, Plan 3 §6 three rows) prevented "move the bar" temptation when results came in ambiguous.
- **Strategy layer kept plain Python** with no pybroker dependency through Plan 2a-2c. Made auditing easy and made Plan 3 trivially skip pybroker without architectural pain.

## What didn't

- **Spec drift**: parent spec was written for MES, data turned out to be SPY, and the drift was only patched cosmetically. MES is still untested — if the user ever wants to trade MES on these rules, there's a full re-run needed.
- **KAT methodology was circular**: every KAT threshold was calibrated against observed values on the same dataset we were "validating". KAT passing was mostly "code matches itself", not "code matches paper". True independent validation would have needed either paper's SPY numbers (unavailable) or a second instrument (QQQ, which would have doubled n_trials).
- **Negative-space testing gap**: 14 happy-path S1 unit tests missed the wrong-way entry edge case entirely. Future plans should deliberately include "ways the rule could be misinterpreted" tests alongside the "ways the rule normally fires" tests.
- **Premature refactoring**: S2 code + S2 KAT + MFE/MAE helper were built before we knew S2 wouldn't survive Plan 2c. Not wasted (infrastructure is reusable), but the decision to ship S2 fully could have been a lighter "prototype + scan" exercise. The parameterized `atr_multiplier` refactor retroactively turned out to be the right shape, but only because Plan 2c rescued it.

## Preserved infrastructure (reusable for any future bake-off)

- **Data loaders** (`data_spy.py`, `data_spy_daily.py`) — ARCX.PILLAR + caching + multi-publisher-safe. Extensible to other instruments by swapping the dataset string.
- **`Trade` wire format** and `TradeOutcome` enum — strategy-agnostic.
- **Known-answer harness** (`strategies/_known_answer.py`) — summary_stats + compare_to_paper.
- **ORB mechanical core** (`strategies/_orb_core.py`) — reusable for other opening-range variants.
- **S2 mechanical core** (`strategies/_s2_core.py`) — noise boundary + ATR + Chandelier trailing, parameterized. If we ever revisit momentum families, this is ready.
- **MFE/MAE helper** (`scripts/_s2_scan_mfe_mae.py`) — diagnostic for any entry-signal quality question.
- **Cost model** (`costs.py`) — simple, per-trade subtraction; extensible to tiered or per-size models.
- **Metrics module** (`metrics.py`) — Sharpe/Sortino/Calmar/MDD/PF/Expectancy/DSR/bootstrap. Paper-referenced DSR formula.
- **Scan runner pattern** — Plan 2c + Plan 3 SE scripts all follow the same "load cache → loop params → CSV + markdown" shape.

## Known gaps (if bake-off track re-opens)

- MES instrument support: needs rollover handling, different session calendar, different cost tier.
- Walk-forward with rolling windows: we used a single train/OOS split; true walk-forward would re-fit parameters in expanding windows.
- Multi-asset: currently one symbol at a time.
- Intra-trade metrics beyond MFE/MAE (e.g., time-in-trade distribution, mid-trade unrealized PnL).
- Real transaction cost integration (not just fixed per-trade): queue position, spread adaptation, commission tiers.

## Decision log

Key choices made during the project with rationale:

| Decision | Why | Where in repo |
|---|---|---|
| Strategies as plain Python, no pybroker | Insulates correctness from engine lifecycle risk (spec §1.4 R5); makes plans trivially adjustable | Plan 2a onwards |
| SPY instead of MES | Zarattini papers use SPY/QQQ; MES data has rollover complexity we skipped | Plan 2a |
| DBEQ.BASIC → ARCX.PILLAR | NYSE Arca is SPY primary listing; single publisher (no consolidation); 6.5y history vs 9 months | PR #3 |
| S2 deferred | Plan 2c: no multiplier produces positive edge; avg_MFE universally < 1R | Plan 2c findings |
| No pybroker in Plan 3 | Only 2 active candidates; direct pandas is simpler and faster | Plan 3 spec §2 |
| No `promote` CLI | Predicted "no Contract" outcome; if wrong, add trivially | Plan 3 spec §2 |
```

### - [ ] Step 2: Commit

```bash
git add docs/research/bakeoff/2026-04-21-bakeoff-retrospective.md
git commit -m "$(cat <<'EOF'
docs(bakeoff): retrospective for W2 Setup Gate bake-off track

Arc from Plan 2a → 2b → 2c → 3. Captures what worked (TDD + critical
audits + pre-committed frameworks + pre-flight cost API), what didn't
(spec drift MES↔SPY, circular KAT, negative-space test gap, premature
S2 refactoring), what infrastructure is preserved, and what gaps
remain if the bake-off track reopens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### - [ ] Step 3: Final suite verification

```bash
.venv/bin/pytest tests/ -q
```

Expected: 255+ passed (baseline 232 + costs +4 + metrics core +13 + metrics DSR/bootstrap +5 + trade utils +5 = 259 ± a couple depending on exact test counts). Adjust expected number to whatever you actually added.

### - [ ] Step 4: Directory structure check

```bash
find src/daytrader/research/bakeoff/costs.py \
     src/daytrader/research/bakeoff/metrics.py \
     scripts/bakeoff_plan3_*.py \
     scripts/_plan3_trade_utils.py \
     docs/research/bakeoff/2026-04-21-plan3-*.md \
     docs/research/bakeoff/plan3_*.csv \
     docs/research/bakeoff/2026-04-21-bakeoff-retrospective.md \
     -type f 2>/dev/null | sort
```

Expected: ~15 files.

### - [ ] Step 5: Journal untouched

```bash
git log main..HEAD --name-only --pretty=format: -- src/daytrader/journal/ tests/journal/ | sort -u | grep -v '^$'
```

Expected: empty.

### - [ ] Step 6: Open single closing PR

```bash
git push -u origin feat/plan3-bakeoff-closeout
gh pr create --base main --head feat/plan3-bakeoff-closeout --title "Plan 3: W2 bake-off closeout" --body "$(cat <<'EOF'
## Summary
- Day 1 main run: S1a/S1b on SPY pure OOS 2024; all spec §2.4 hard gates evaluated with $0.50/trade cost.
- Day 2: four sensitivity experiments (SE-1 cost, SE-2 reversal, SE-3 quarterly, SE-4 OR duration).
- Day 3: findings doc committing to spec §6 decision branch; retrospective documenting the Plan 2a → 2b → 2c → 3 arc.
- New library: `costs.py`, `metrics.py` (Sharpe, Sortino, Calmar, MDD, PF, expectancy, DSR, bootstrap CI), `_plan3_trade_utils.py`.

## Decision
[Branch N per findings. Most likely "no Contract signed" (branch 1).]

## Test Plan
- [x] Unit suite green (costs + metrics + trade utils = ~27 new tests)
- [x] All 5 scan scripts run end-to-end on cached data
- [x] Findings doc links to source CSVs
- [x] Retrospective covers the full arc with preserved infra + known gaps

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### - [ ] Step 7: Merge + delete branch

```bash
gh pr merge --merge --delete-branch
git checkout main
git pull
```

**Plan 3 + W2 bake-off closeout complete.**

---

## Self-Review

**Spec coverage (Plan 3 spec `2026-04-21-plan3-bakeoff-closeout-design.md`):**

| Spec section | Covered by |
|---|---|
| §3.1 cost = $0.50/trade locked | Task 1 (hardcoded default in `costs.py`), Task 5 (main run passes explicitly) |
| §3.2 data split (replication + pure OOS) | Task 5 `_evaluate` loops over both windows |
| §3.3 metrics 11-column table | Tasks 2 + 3 implement all; Task 5 reports all |
| §3.4 SE-1..SE-4 each executed | Tasks 6-9 one script each |
| §4.1 file layout | Matches the "File Structure" section at top of this plan |
| §4.3 CSV-first discipline | Every scan writes CSV; markdown docs reference CSV as source |
| §5 day-by-day timebox | Task 5 = Day 1; Tasks 6-10 = Day 2; Tasks 11-12 = Day 3 |
| §6 decision table pre-committed | Task 11 walks the table explicitly in §6 order |
| §7 success criteria (6 items) | All met across Tasks 11-12 |

**Placeholder scan:** Bracketed `[... fill from ...]` sections in Tasks 5 Step 5, 10 Step 1, 11 Step 2, and 12 Step 1 are instructions to the executor with explicit data sources. Not leftover TBDs — each cites which CSV/stdout file to read.

**Type consistency:**
- `trade_gross_pnl(trade) → float`, `trade_net_pnl(trade, cost_per_trade) → float`, `apply_per_trade_cost(trades, cost_per_trade) → pd.Series` — defined Task 1, used Tasks 5-9.
- `annualized_sharpe`, `max_drawdown`, `profit_factor`, etc. — defined Tasks 2-3, used Tasks 5-9.
- `filter_trades_by_window`, `flip_trades_direction`, `equity_curve_from_pnl`, `daily_returns_from_pnl` — defined Task 4, used Tasks 5-9.
- All scan runners import from the same `_plan3_trade_utils` module via `sys.path.insert(0, str(Path(__file__).resolve().parent))` — consistent pattern.

**Scope / timebox:** 12 tasks covering 3 days. Task 5 Step 3 runs live Databento (but uses cached data, so ~fast). Tasks 6-9 each run in < 1 min. Tasks 11-12 are doc-only. The plan fits the 3-day box provided no surprise regressions.
