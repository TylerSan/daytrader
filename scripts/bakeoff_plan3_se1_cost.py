"""SE-1: cost sensitivity. Scan cost_per_trade ∈ {0.0, 0.5, 1.0} for S1a
and S1b on pure OOS. If only cost=0 passes Sharpe ≥ 1.0, the strategy's
edge is paper-thin vs. slippage.
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
