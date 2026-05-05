"""PlanRetrospective — compose Plan + simulator outcomes + actual trades into
per-symbol RetrospectiveRow; persist to state.db's plan_retrospective_daily table."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from daytrader.reports.eod.plan_dataclasses import (
    Plan,
    PlanLevel,
    RetrospectiveRow,
    SimOutcome,
)


class PlanRetrospective:
    """Orchestrate plan parsing → simulation → audit → persist."""

    def __init__(
        self,
        plan_parser: Any,                    # has .parse(raw_md, symbol) -> Plan
        trade_simulator: Callable,           # simulate_level signature
        intraday_bar_fetcher: Callable,      # (symbol, date_et) -> list[OHLCV]
        trades_query: Any,                   # has .trades_for_date / .audit_summary
        state_db_path: Path,
    ) -> None:
        self._plan_parser = plan_parser
        self._simulate = trade_simulator
        self._fetch_bars = intraday_bar_fetcher
        self._trades_query = trades_query
        self._db_path = Path(state_db_path)

    def compose(
        self,
        plans: dict[str, str],         # raw markdown blocks per symbol from PremarketPlanReader
        symbols: list[str],
        date_et: str,
        tick_sizes: dict[str, float],
    ) -> dict[str, RetrospectiveRow]:
        """Return {symbol: RetrospectiveRow} for each symbol whose plan was found."""
        if not plans:
            return {}

        # Today's actual trades for the actual_total_r computation
        actual_trades = self._trades_query.trades_for_date(date_et)
        # Note: audit_summary returns a dict with daily_r but we need per-symbol R below.

        out: dict[str, RetrospectiveRow] = {}
        for symbol in symbols:
            raw_md = plans.get(symbol)
            if not raw_md:
                continue
            plan: Plan = self._plan_parser.parse(raw_md, symbol)
            if not plan.levels:
                continue

            intraday_bars = self._fetch_bars(symbol, date_et)
            tick_size = tick_sizes.get(symbol, 0.25)

            outcomes: list[tuple[PlanLevel, SimOutcome]] = []
            sim_total = 0.0
            triggered = 0
            for i, level in enumerate(plan.levels):
                # Find next key level for target cap (next level in same direction)
                next_kl = self._find_next_key_level(level, plan.levels, exclude_idx=i)
                outcome = self._simulate(
                    level, intraday_bars, next_kl,
                    tick_size, plan.stop_offset_ticks, plan.target_r_multiple,
                )
                outcomes.append((level, outcome))
                sim_total += outcome.sim_r
                if outcome.triggered:
                    triggered += 1

            # Actual R for this symbol from journal
            symbol_actual_r = sum(
                (float(t.get("pnl_usd", 0) or 0) / 50.0)
                for t in actual_trades
                if t.get("symbol") == symbol
            )

            out[symbol] = RetrospectiveRow(
                symbol=symbol,
                date_et=date_et,
                total_levels=len(plan.levels),
                triggered_count=triggered,
                sim_total_r=sim_total,
                actual_total_r=symbol_actual_r,
                gap_r=sim_total - symbol_actual_r,
                per_level_outcomes=outcomes,
            )

        return out

    def persist(self, rows: dict[str, RetrospectiveRow]) -> None:
        """Insert / replace rows in plan_retrospective_daily table."""
        if not rows:
            return
        if not self._db_path.exists():
            return
        conn = sqlite3.connect(self._db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            for symbol, row in rows.items():
                serialized = json.dumps([
                    {
                        "level_price": pl.price,
                        "level_type": pl.level_type,
                        "source": pl.source,
                        "direction": pl.direction,
                        "outcome": so.outcome,
                        "sim_r": so.sim_r,
                        "touch_time_pt": so.touch_time_pt,
                    }
                    for pl, so in row.per_level_outcomes
                ])
                conn.execute(
                    """INSERT INTO plan_retrospective_daily
                       (date, symbol, total_levels, triggered_count,
                        sim_total_r, actual_total_r, gap_r,
                        retrospective_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(date, symbol) DO UPDATE SET
                         total_levels=excluded.total_levels,
                         triggered_count=excluded.triggered_count,
                         sim_total_r=excluded.sim_total_r,
                         actual_total_r=excluded.actual_total_r,
                         gap_r=excluded.gap_r,
                         retrospective_json=excluded.retrospective_json,
                         created_at=excluded.created_at""",
                    (
                        row.date_et, row.symbol,
                        row.total_levels, row.triggered_count,
                        row.sim_total_r, row.actual_total_r, row.gap_r,
                        serialized, now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _find_next_key_level(
        level: PlanLevel,
        all_levels: list[PlanLevel],
        exclude_idx: int,
    ) -> float | None:
        """Find the closest key level in the same direction beyond entry.

        For short_fade: next level BELOW entry (closer profit cap).
        For long_fade: next level ABOVE entry.
        """
        candidates: list[float] = []
        for i, other in enumerate(all_levels):
            if i == exclude_idx:
                continue
            if other.direction != level.direction:
                continue
            if level.direction == "short_fade" and other.price < level.price:
                candidates.append(other.price)
            elif level.direction == "long_fade" and other.price > level.price:
                candidates.append(other.price)
        if not candidates:
            return None
        if level.direction == "short_fade":
            return max(candidates)
        return min(candidates)
