"""TodayTradesQuery — query journal DB for today's trades + run §6 / §9 audit."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


# R unit per Contract.md §1.
_R_UNIT_USD = 50.0


class TodayTradesQuery:
    """Read-only access to journal.db for EOD report."""

    def __init__(self, journal_db_path: Path) -> None:
        self._db_path = Path(journal_db_path)

    def trades_for_date(
        self, date_et: str, mode: str = "real"
    ) -> list[dict[str, Any]]:
        """Return list of trade dicts for the given ET date + mode.

        Returns dicts (not Pydantic models) to keep this query layer
        decoupled from the journal model — EOD only needs read-only views.
        """
        if not self._db_path.exists():
            return []

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM trades WHERE date = ? AND mode = ? ORDER BY entry_time ASC",
                (date_et, mode),
            )
            rows = [dict(r) for r in cur]
            conn.close()
            return rows
        except sqlite3.Error:
            return []

    @staticmethod
    def audit_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate audit summary for the trade list.

        Returns:
          - count: int
          - daily_r: float (sum of pnl_usd / R_UNIT)
          - violations_total: int (sum of len(violations) per trade)
          - screenshots_complete: int (count of trades with 'screenshots: yes' in notes)
          - per_trade_violations: dict[trade_id, list[str]]
        """
        if not trades:
            return {
                "count": 0,
                "daily_r": 0.0,
                "violations_total": 0,
                "screenshots_complete": 0,
                "per_trade_violations": {},
            }

        total_pnl = 0.0
        violations_total = 0
        screenshots_complete = 0
        per_trade_violations: dict[str, list[str]] = {}

        for t in trades:
            pnl = t.get("pnl_usd") or 0.0
            total_pnl += float(pnl)

            raw_violations = t.get("violations") or "[]"
            try:
                violation_list = json.loads(raw_violations)
                if not isinstance(violation_list, list):
                    violation_list = []
            except (json.JSONDecodeError, TypeError):
                violation_list = []
            violations_total += len(violation_list)
            per_trade_violations[t["id"]] = violation_list

            notes = (t.get("notes") or "").lower()
            if "screenshots: yes" in notes:
                screenshots_complete += 1

        return {
            "count": len(trades),
            "daily_r": total_pnl / _R_UNIT_USD,
            "violations_total": violations_total,
            "screenshots_complete": screenshots_complete,
            "per_trade_violations": per_trade_violations,
        }
