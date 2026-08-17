"""Post-trade orchestration: close trade + update circuit state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from daytrader.journal.checklist import INSTRUMENT_TICK_VALUE
from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import TradeSide
from daytrader.journal.repository import JournalRepository


@dataclass
class PostTradeInput:
    trade_id: str
    exit_time: datetime
    exit_price: Decimal
    was_stop: bool
    notes: Optional[str] = None
    violations: Optional[list[str]] = None


class PostTradeService:
    def __init__(
        self, repo: JournalRepository, circuit: CircuitService
    ) -> None:
        self.repo = repo
        self.circuit = circuit

    def close(self, inp: PostTradeInput) -> None:
        trade = self.repo.get_trade(inp.trade_id)
        if trade is None:
            raise ValueError(f"trade not found: {inp.trade_id}")
        if trade.exit_price is not None:
            raise ValueError(f"trade already closed: {inp.trade_id}")

        mult = INSTRUMENT_TICK_VALUE.get(trade.symbol, Decimal("1"))
        if trade.direction == TradeSide.LONG:
            pnl = (inp.exit_price - trade.entry_price) * mult * Decimal(trade.size)
        else:
            pnl = (trade.entry_price - inp.exit_price) * mult * Decimal(trade.size)

        risk_usd = (
            abs(trade.entry_price - trade.stop_price)
            * mult * Decimal(trade.size)
        )
        r_mult = Decimal("0") if risk_usd == 0 else pnl / risk_usd

        self.repo.close_trade(
            trade_id=inp.trade_id,
            exit_time=inp.exit_time,
            exit_price=inp.exit_price,
            pnl_usd=pnl,
            notes=inp.notes,
            violations=inp.violations,
        )

        self.circuit.register_trade_outcome(
            on=trade.date,
            r_multiple=r_mult,
            pnl_usd=pnl,
            was_stop=inp.was_stop,
            now=inp.exit_time,
        )
