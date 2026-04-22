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

from daytrader.research.bakeoff.costs import apply_per_trade_cost
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
    net = apply_per_trade_cost(trades, COST_PER_TRADE)
    r_mults = pd.Series([t.r_multiple for t in trades])
    from datetime import date as _date
    trade_dates = [_date.fromisoformat(t.date) for t in trades]
    eq = equity_curve_from_pnl(net, starting_capital=STARTING_CAPITAL)
    dr = daily_returns_from_pnl(net, trade_dates, starting_capital=STARTING_CAPITAL)
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
    """Return {gate: 'PASS'/'FAIL'} using spec §2.4 (5 hard gates)."""
    import math
    def _ge(v, t):
        return isinstance(v, (int, float)) and not math.isnan(v) and v >= t
    def _le(v, t):
        return isinstance(v, (int, float)) and not math.isnan(v) and v <= t
    def _lt(v, t):
        return isinstance(v, (int, float)) and not math.isnan(v) and v < t
    gates = {
        "sharpe ≥ 1.0": _ge(row.get("sharpe", float("nan")), 1.0),
        "max_dd ≤ 15%": _le(row.get("max_dd", float("inf")), 0.15),
        "profit_factor ≥ 1.3": _ge(row.get("profit_factor", 0), 1.3),
        "n ≥ 100": row.get("n", 0) >= 100,
        "DSR p < 0.10": _lt(row.get("dsr_pvalue", float("inf")), 0.10),
    }
    return {k: "PASS" if v else "FAIL" for k, v in gates.items()}


def _fmt(v):
    import math
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        return f"{v:.3f}"
    return str(v)


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

    print()
    print("=== Plan 3 Main Run Report ===")
    print(f"Cost/trade: ${COST_PER_TRADE}; starting capital: ${STARTING_CAPITAL}; n_trials={N_TRIALS}")
    print()
    header = ["label", "n", "sharpe", "sortino", "calmar", "max_dd", "longest_dd_days",
             "profit_factor", "expectancy_r", "dsr_pvalue", "ci_lo", "ci_hi", "total_net_pnl"]
    print(" | ".join(h.rjust(16) for h in header))
    for c in cells:
        vals = [_fmt(c.get(k, "")) for k in header]
        print(" | ".join(v.rjust(16) for v in vals))

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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "plan3_main_report.csv"
    pd.DataFrame(cells).to_csv(csv_path, index=False)
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
