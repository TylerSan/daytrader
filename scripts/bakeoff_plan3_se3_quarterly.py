"""SE-3: OOS quarterly stability. Split pure OOS (2024-04 → 2024-12) into
Q2/Q3/Q4; compute per-quarter net PnL and equity % change. Any quarter
< -3% equity flagged as regime fragility.
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
    print(f"\nWrote {OUTPUT_DIR / 'plan3_se3_quarterly.csv'}")


if __name__ == "__main__":
    main()
