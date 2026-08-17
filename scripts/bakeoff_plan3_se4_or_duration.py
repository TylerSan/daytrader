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
    print(f"\nWrote {OUTPUT_DIR / 'plan3_se4_or_duration.csv'}")


if __name__ == "__main__":
    main()
