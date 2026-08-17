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


# --- annualized Sharpe ---

def test_annualized_sharpe_zero_mean():
    s = pd.Series([0.01, -0.01, 0.01, -0.01] * 63)
    assert annualized_sharpe(s) == pytest.approx(0.0)


def test_annualized_sharpe_positive_mean_positive_std():
    s = pd.Series([0.02, 0.00] * 126)
    sh = annualized_sharpe(s)
    assert sh > 10


def test_annualized_sharpe_zero_std_returns_nan():
    s = pd.Series([0.005] * 252)
    assert math.isnan(annualized_sharpe(s))


# --- Sortino ---

def test_annualized_sortino_no_downside_returns_inf_or_nan():
    s = pd.Series([0.01, 0.02, 0.003] * 84)
    sr = annualized_sortino(s)
    assert sr == float("inf") or math.isnan(sr)


def test_annualized_sortino_equal_up_and_down():
    s = pd.Series([0.01, -0.01] * 126)
    sr = annualized_sortino(s)
    assert sr == pytest.approx(0.0)


# --- max_drawdown + longest_drawdown_duration ---

def test_max_drawdown_no_loss_is_zero():
    eq = pd.Series([1.0, 1.01, 1.02, 1.03])
    assert max_drawdown(eq) == pytest.approx(0.0)


def test_max_drawdown_simple_peak_trough():
    eq = pd.Series([1.0, 1.20, 0.90, 1.10])
    assert max_drawdown(eq) == pytest.approx(0.25)


def test_longest_drawdown_duration_counts_bars():
    eq = pd.Series([1.0, 1.5, 1.2, 1.1, 1.0, 1.3, 1.6])
    assert longest_drawdown_duration(eq) == 4


def test_longest_drawdown_duration_unrecovered():
    eq = pd.Series([1.0, 1.5, 1.2, 1.1, 1.0])
    assert longest_drawdown_duration(eq) == 3


# --- Calmar ---

def test_calmar_ratio_zero_drawdown_returns_nan():
    eq = pd.Series([1.0, 1.01, 1.02, 1.03])
    assert math.isnan(calmar_ratio(eq, trading_days=252))


def test_calmar_ratio_typical():
    eq = pd.Series([1.0, 1.10, 0.99, 1.12, 1.20])
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
    pnl = pd.Series([3.0, -1.0, 2.0, -4.0])
    assert profit_factor(pnl) == pytest.approx(1.0)


# --- Expectancy R ---

def test_expectancy_r_mean_of_r_multiples():
    r = pd.Series([1.0, -1.0, 0.5, -0.5])
    assert expectancy_r(r) == pytest.approx(0.0)


# --- DSR + bootstrap CI ---

from daytrader.research.bakeoff.metrics import (
    bootstrap_sharpe_ci, deflated_sharpe_pvalue,
)


def test_dsr_pvalue_zero_sharpe_always_high():
    returns = pd.Series([0.001, -0.001] * 126)
    p = deflated_sharpe_pvalue(returns, n_trials=2)
    assert p > 0.4


def test_dsr_pvalue_very_high_sharpe_is_significant():
    # Realistic high-SR series with noise so skew/kurt stay well-behaved.
    np.random.seed(7)
    returns = pd.Series(np.random.normal(0.002, 0.005, 500))   # SR ≈ +6.3 annualized
    p = deflated_sharpe_pvalue(returns, n_trials=2)
    assert p < 0.05


def test_dsr_pvalue_more_trials_makes_harder_to_pass():
    np.random.seed(11)
    returns = pd.Series(np.random.normal(0.0008, 0.01, 500))   # mild positive SR
    p2 = deflated_sharpe_pvalue(returns, n_trials=2)
    p100 = deflated_sharpe_pvalue(returns, n_trials=100)
    assert p100 >= p2


def test_bootstrap_sharpe_ci_zero_mean_brackets_zero():
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0, 0.01, 252))
    lo, hi = bootstrap_sharpe_ci(returns, n_resamples=1000, seed=42)
    assert lo < 0 < hi


def test_bootstrap_sharpe_ci_positive_drift_positive_lower_bound():
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.005, 0.005, 500))
    lo, hi = bootstrap_sharpe_ci(returns, n_resamples=1000, seed=42)
    assert lo > 0
