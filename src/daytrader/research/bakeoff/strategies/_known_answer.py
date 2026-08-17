"""Known-answer test utilities for paper replication (spec §5.1).

A "known-answer test" (KAT) runs our implementation against the same
dataset the paper used and compares against paper-reported figures.
Spec's pass bar: deviation < 15% on 2-3 reported metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from daytrader.research.bakeoff.strategies._trade import Trade


@dataclass(frozen=True)
class KnownAnswerResult:
    metric_name: str
    computed: float
    paper_value: float
    deviation_pct: float
    tolerance_pct: float
    passed: bool


def summary_stats(
    trades: Iterable[Trade],
    point_value_usd: float,
    starting_capital: float,
) -> dict:
    """Paper-compatible summary statistics. Gross of transaction costs."""
    trades = list(trades)
    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "total_pnl_usd": 0.0,
            "total_return_pct": 0.0,
        }

    pnl_usd = 0.0
    wins = 0
    for t in trades:
        if t.direction == "long":
            pts = t.exit_price - t.entry_price
        else:
            pts = t.entry_price - t.exit_price
        pnl_usd += pts * point_value_usd
        if pts > 0:
            wins += 1

    return {
        "n_trades": len(trades),
        "win_rate": wins / len(trades),
        "total_pnl_usd": pnl_usd,
        "total_return_pct": (pnl_usd / starting_capital) * 100.0,
    }


def compare_to_paper(
    metric_name: str,
    computed: float,
    paper_value: float,
    tolerance_pct: float,
) -> KnownAnswerResult:
    if paper_value == 0.0:
        raise ValueError(
            f"paper_value for {metric_name!r} is zero; cannot compute "
            "relative deviation"
        )
    deviation_pct = abs(computed - paper_value) / abs(paper_value) * 100.0
    return KnownAnswerResult(
        metric_name=metric_name,
        computed=computed,
        paper_value=paper_value,
        deviation_pct=deviation_pct,
        tolerance_pct=tolerance_pct,
        passed=deviation_pct < tolerance_pct,
    )
