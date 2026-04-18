"""Daily loss circuit service.

Tracks realized R per day, consecutive stops, and cool-off windows.
Makes go/no-go decisions for pre-trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta
from decimal import Decimal
from typing import Optional

from daytrader.journal.models import CircuitState
from daytrader.journal.repository import JournalRepository

# TODO: move to Contract model when consecutive_stops_day_end field is added.
CONSECUTIVE_STOPS_DAY_END = 2


@dataclass
class CircuitDecision:
    allowed: bool
    reason: Optional[str] = None
    detail: Optional[str] = None


class CircuitService:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def _contract_or_none(self):
        try:
            return self.repo.get_active_contract()
        except Exception:
            return None

    def check_can_trade(self, on: date_type, now: datetime) -> CircuitDecision:
        try:
            contract = self.repo.get_active_contract()
        except Exception:
            return CircuitDecision(
                allowed=False,
                reason="circuit_state_unavailable",
            )

        if contract is None:
            # Fail-safe: no active contract → no trade
            return CircuitDecision(
                allowed=False,
                reason="no_active_contract",
            )

        try:
            state = self.repo.get_circuit_state(on)
        except Exception:
            # Fail-safe: circuit state inaccessible → no trade
            return CircuitDecision(
                allowed=False,
                reason="circuit_state_unavailable",
            )

        if state.no_trade_flag:
            return CircuitDecision(
                allowed=False,
                reason=state.lock_reason or "circuit_locked",
            )

        if state.trade_count >= contract.max_trades_per_day:
            return CircuitDecision(
                allowed=False,
                reason="max_trades_per_day_reached",
            )

        if state.last_stop_time is not None:
            cooloff = timedelta(minutes=contract.stop_cooloff_minutes)
            if now - state.last_stop_time < cooloff:
                return CircuitDecision(
                    allowed=False,
                    reason="within_cooloff",
                    detail=f"cooloff ends at {state.last_stop_time + cooloff}",
                )

        return CircuitDecision(allowed=True)

    def register_trade_outcome(
        self,
        on: date_type,
        r_multiple: Decimal,
        pnl_usd: Decimal,
        was_stop: bool,
        now: datetime,
    ) -> CircuitState:
        contract = self._contract_or_none()
        if contract is None:
            raise RuntimeError("cannot register outcome without active contract")

        state = self.repo.get_circuit_state(on)
        new_r = state.realized_r + r_multiple
        new_usd = state.realized_usd + pnl_usd
        new_count = state.trade_count + 1

        last_stop = now if was_stop else state.last_stop_time

        no_trade = state.no_trade_flag
        lock_reason = state.lock_reason

        # Rule: daily loss limit hit
        if new_r <= -Decimal(contract.daily_loss_limit_r):
            no_trade = True
            lock_reason = "daily_loss_limit_hit"

        # Rule: consecutive stops — heuristic via list_trades_on_date.
        # If this trade is a stop AND the prior trade on the same date was also
        # a losing trade, we have CONSECUTIVE_STOPS_DAY_END consecutive stops
        # and should end the day.
        if (
            was_stop
            and state.last_stop_time is not None
            and state.trade_count >= 1
            and not no_trade  # don't override a stricter lock already applied
        ):
            recent = self.repo.list_trades_on_date(on)
            if len(recent) >= 1:
                last_trade = recent[-1]
                if (
                    last_trade.pnl_usd is not None
                    and last_trade.pnl_usd < 0
                ):
                    no_trade = True
                    lock_reason = "consecutive_stops"

        new_state = CircuitState(
            date=on,
            realized_r=new_r,
            realized_usd=new_usd,
            trade_count=new_count,
            no_trade_flag=no_trade,
            lock_reason=lock_reason,
            last_stop_time=last_stop,
        )
        self.repo.upsert_circuit_state(new_state)
        return new_state
