"""SE-2: signal reversal. Flip direction label on all OOS trades; if the
reversed strategy also has positive Sharpe → edge is market beta, not alpha.
Reject per spec §3.4 SE-2 rule.
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
        return {"label": label, "n": 0, "sharpe": float("nan"),
                "sortino": float("nan"), "profit_factor": float("nan"),
                "net_pnl_usd": 0.0}
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
        reject = (original["sharpe"] > 0 and reversed_["sharpe"] > 0)
        rows.append({**original, "reject_for_long_bias": reject})
        rows.append({**reversed_, "reject_for_long_bias": reject})
        print(f"{cand_name}: original sharpe {original['sharpe']:+.3f}, "
              f"reversed {reversed_['sharpe']:+.3f}, "
              f"reject={'YES' if reject else 'no'}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "plan3_se2_reversal.csv", index=False)
    print(f"\nWrote {OUTPUT_DIR / 'plan3_se2_reversal.csv'}")


if __name__ == "__main__":
    main()
