"""Plan 2c: Scan S2 atr_multiplier ∈ {1.0, 1.5, 2.0, 2.5, 3.0} × {S2a, S2b}
on SPY 2018-05-01 → 2023-12-31, writing per-run summary + per-year CSVs
and a markdown summary table to stdout.

Usage:
    DATABENTO_API_KEY=<key> .venv/bin/python scripts/bakeoff_s2_atr_scan.py

Requires existing Databento cache at data/cache/ohlcv_spy_kat/ and
data/cache/ohlcv_spy_daily_kat/ (from Plan 2b data expansion).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _s2_scan_mfe_mae import compute_mfe_mae_r

from daytrader.research.bakeoff.data_spy import load_spy_1m
from daytrader.research.bakeoff.data_spy_daily import load_spy_daily
from daytrader.research.bakeoff.strategies._trade import TradeOutcome
from daytrader.research.bakeoff.strategies.s2_intraday_momentum import (
    S2a_IntradayMomentum_Max1,
    S2b_IntradayMomentum_Max5,
)


PAPER_START = date(2018, 5, 1)
PAPER_END = date(2023, 12, 31)
MULTIPLIERS = [1.0, 1.5, 2.0, 2.5, 3.0]
OUTPUT_DIR = Path("docs/research/bakeoff")


def _run_one(strat, bars_1m, bars_1d):
    """Run a strategy, collect summary + per-year metrics."""
    trades = strat.generate_trades(bars_1m, bars_1d)
    n = len(trades)
    if n == 0:
        return {"n_trades": 0}, []

    wins = sum(1 for t in trades if (
        (t.direction == "long" and t.exit_price > t.entry_price) or
        (t.direction == "short" and t.exit_price < t.entry_price)
    ))
    stops = sum(1 for t in trades if t.outcome is TradeOutcome.STOP)
    longs = sum(1 for t in trades if t.direction == "long")
    shorts = n - longs

    pnl_by_trade = []
    for t in trades:
        pts = (t.exit_price - t.entry_price) if t.direction == "long" \
            else (t.entry_price - t.exit_price)
        pnl_by_trade.append(pts)
    total_pnl = sum(pnl_by_trade)

    r_list = [t.r_multiple for t in trades]

    mfes, maes = [], []
    for t in trades:
        mfe, mae = compute_mfe_mae_r(t, bars_1m)
        mfes.append(mfe)
        maes.append(mae)

    summary = {
        "n_trades": n,
        "win_rate": wins / n,
        "avg_R": sum(r_list) / n,
        "total_pnl_usd": total_pnl,
        "stop_hit_rate": stops / n,
        "long_count": longs,
        "short_count": shorts,
        "avg_mfe_R": sum(mfes) / n,
        "avg_mae_R": sum(maes) / n,
    }

    by_year_rows = []
    for year in range(PAPER_START.year, PAPER_END.year + 1):
        year_trades = [(t, pts, r) for t, pts, r in zip(trades, pnl_by_trade, r_list)
                       if int(t.date[:4]) == year]
        if not year_trades:
            continue
        y_n = len(year_trades)
        y_wins = sum(1 for t, pts, _ in year_trades if pts > 0)
        y_pnl = sum(pts for _, pts, _ in year_trades)
        y_avg_r = sum(r for _, _, r in year_trades) / y_n
        by_year_rows.append({
            "year": year,
            "n_trades": y_n,
            "win_rate": y_wins / y_n,
            "avg_R": y_avg_r,
            "total_pnl_usd": y_pnl,
        })
    return summary, by_year_rows


def main():
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print("DATABENTO_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    print(f"Loading SPY 1m + daily from cache ({PAPER_START} → {PAPER_END})...")
    ds = load_spy_1m(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key,
        cache_dir=Path("data/cache/ohlcv_spy_kat"),
    )
    daily = load_spy_daily(
        start=date(2018, 5, 1), end=date(2024, 12, 31),
        api_key=api_key,
        cache_dir=Path("data/cache/ohlcv_spy_daily_kat"),
    )

    et = ZoneInfo("America/New_York")
    mask_1m = pd.Series(
        [t.tz_convert(et).date() <= PAPER_END for t in ds.bars.index],
        index=ds.bars.index,
    )
    bars_1m = ds.bars[mask_1m]
    bars_1d = daily[daily.index.date <= PAPER_END]

    summary_rows = []
    by_year_rows = []
    print()
    print(f"{'mult':>5} {'strat':>5} {'n':>5} {'wr':>5} {'avg_R':>7} {'pnl$':>9} "
          f"{'stop%':>6} {'L/S':>9} {'MFE':>6} {'MAE':>6}")
    for mult in MULTIPLIERS:
        for name, cls in [("S2a", S2a_IntradayMomentum_Max1),
                          ("S2b", S2b_IntradayMomentum_Max5)]:
            strat = cls(symbol="SPY", atr_multiplier=mult)
            summary, year_rows = _run_one(strat, bars_1m, bars_1d)
            summary["atr_multiplier"] = mult
            summary["strategy"] = name
            summary_rows.append(summary)
            for yr in year_rows:
                yr["atr_multiplier"] = mult
                yr["strategy"] = name
                by_year_rows.append(yr)
            if summary["n_trades"] > 0:
                print(f"{mult:>5.1f} {name:>5} {summary['n_trades']:>5d} "
                      f"{summary['win_rate']:>.3f} {summary['avg_R']:>+.3f} "
                      f"{summary['total_pnl_usd']:>+9.1f} "
                      f"{summary['stop_hit_rate']*100:>5.1f}% "
                      f"{summary['long_count']}/{summary['short_count']:<3} "
                      f"{summary['avg_mfe_R']:>+.2f} {summary['avg_mae_R']:>+.2f}")

    print()
    print("=== S2b vs S2a deltas ===")
    print(f"{'mult':>5} {'n_delta':>8} {'pct':>6} {'pnl_delta':>10}")
    by_mult = {}
    for r in summary_rows:
        by_mult.setdefault(r["atr_multiplier"], {})[r["strategy"]] = r
    for mult in MULTIPLIERS:
        a = by_mult[mult].get("S2a", {"n_trades": 0, "total_pnl_usd": 0.0})
        b = by_mult[mult].get("S2b", {"n_trades": 0, "total_pnl_usd": 0.0})
        n_delta = b["n_trades"] - a["n_trades"]
        pct = (n_delta / a["n_trades"] * 100.0) if a["n_trades"] else 0.0
        pnl_delta = b["total_pnl_usd"] - a["total_pnl_usd"]
        print(f"{mult:>5.1f} {n_delta:>8d} {pct:>5.1f}% {pnl_delta:>+10.1f}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df[[
        "atr_multiplier", "strategy", "n_trades", "win_rate", "avg_R",
        "total_pnl_usd", "stop_hit_rate", "long_count", "short_count",
        "avg_mfe_R", "avg_mae_R",
    ]]
    summary_path = OUTPUT_DIR / "s2_atr_scan_results.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\nWrote {summary_path}")

    by_year_df = pd.DataFrame(by_year_rows)
    by_year_df = by_year_df[[
        "atr_multiplier", "strategy", "year",
        "n_trades", "win_rate", "avg_R", "total_pnl_usd",
    ]]
    by_year_path = OUTPUT_DIR / "s2_atr_scan_results_by_year.csv"
    by_year_df.to_csv(by_year_path, index=False)
    print(f"Wrote {by_year_path}")


if __name__ == "__main__":
    main()
