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

import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def annualized_sharpe(daily_returns: pd.Series) -> float:
    mean = float(daily_returns.mean())
    std = float(daily_returns.std(ddof=1))
    if std == 0 or math.isnan(std):
        return float("nan")
    return mean / std * math.sqrt(TRADING_DAYS_PER_YEAR)


def annualized_sortino(daily_returns: pd.Series) -> float:
    mean = float(daily_returns.mean())
    downside = daily_returns[daily_returns < 0]
    if len(downside) == 0:
        # No downside observations — arbitrarily good if mean > 0, zero if mean == 0.
        return float("inf") if mean > 0 else 0.0
    std_d = float(downside.std(ddof=1))
    if math.isnan(std_d) or std_d == 0:
        # Downside has no variance — fall back on sign of mean.
        if mean > 0:
            return float("inf")
        if mean < 0:
            return float("-inf")
        return 0.0
    return mean / std_d * math.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(equity: pd.Series) -> float:
    running_peak = equity.cummax()
    drawdowns = (running_peak - equity) / running_peak
    return float(drawdowns.max())


def longest_drawdown_duration(equity: pd.Series) -> int:
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
    if len(equity) < 2:
        return float("nan")
    total_return = float(equity.iloc[-1] / equity.iloc[0]) - 1
    years = len(equity) / trading_days
    if years <= 0:
        return float("nan")
    annualized = (1 + total_return) ** (1 / years) - 1
    mdd = max_drawdown(equity)
    if mdd == 0 or math.isnan(mdd):
        return float("nan")
    return annualized / mdd


def profit_factor(trade_pnl: pd.Series) -> float:
    wins = trade_pnl[trade_pnl > 0].sum()
    losses = trade_pnl[trade_pnl < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def expectancy_r(r_multiples: pd.Series) -> float:
    if len(r_multiples) == 0:
        return float("nan")
    return float(r_multiples.mean())


# === DSR + bootstrap ===


import numpy as np
from scipy.stats import norm as _norm


_EULER_MASCHERONI = 0.5772156649015329


def _expected_max_sharpe(n_trials: int) -> float:
    """López de Prado's expected max of n iid standard-normal Sharpes.
    E[max] ≈ (1 - γ)·Φ⁻¹(1 - 1/n) + γ·Φ⁻¹(1 - 1/(n·e)) where γ is Euler-Mascheroni.
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
    expected max Sharpe of `n_trials` iid null candidates. Higher n_trials
    → harder to pass. Small p is significant.
    """
    T = len(daily_returns)
    if T < 2:
        return float("nan")
    mean = float(daily_returns.mean())
    std = float(daily_returns.std(ddof=1))
    if std == 0:
        return float("nan")
    sr_hat = mean / std   # per-period Sharpe
    # Skew and excess kurtosis.
    skew = float(((daily_returns - mean) ** 3).mean() / (std ** 3))
    kurt = float(((daily_returns - mean) ** 4).mean() / (std ** 4) - 3)
    sr_var = (1 - skew * sr_hat + (kurt / 4) * sr_hat ** 2) / (T - 1)
    if sr_var <= 0:
        return float("nan")
    sr_std = math.sqrt(sr_var)
    exp_max_sr = _expected_max_sharpe(n_trials)
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
