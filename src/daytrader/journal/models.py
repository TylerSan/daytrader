"""Journal domain models — Pydantic v2."""

from __future__ import annotations

from datetime import date as date_type, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


ALLOWED_SYMBOLS = {"MES", "MNQ", "MGC"}


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradeMode(str, Enum):
    REAL = "real"
    DRY_RUN = "dry_run"


class DryRunOutcome(str, Enum):
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    RULE_EXIT = "rule_exit"
    NO_TRIGGER = "no_trigger"


class ChecklistItems(BaseModel):
    item_stop_at_broker: bool
    item_within_r_limit: bool
    item_matches_locked_setup: bool
    item_within_daily_r: bool
    item_past_cooloff: bool

    def all_passed(self) -> bool:
        return all(
            [
                self.item_stop_at_broker,
                self.item_within_r_limit,
                self.item_matches_locked_setup,
                self.item_within_daily_r,
                self.item_past_cooloff,
            ]
        )

    def failed_items(self) -> list[str]:
        return [k for k, v in self.model_dump().items() if v is False]


class Checklist(BaseModel):
    id: str
    timestamp: datetime
    mode: TradeMode
    contract_version: int
    items: ChecklistItems
    passed: bool
    failure_reason: Optional[str] = None


class JournalTrade(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str
    checklist_id: str
    date: date_type
    symbol: str
    direction: TradeSide
    setup_type: str
    entry_time: datetime
    entry_price: Decimal
    stop_price: Decimal              # REQUIRED by design
    target_price: Decimal            # REQUIRED by design
    size: int
    exit_time: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    pnl_usd: Optional[Decimal] = None
    notes: Optional[str] = None
    violations: list[str] = Field(default_factory=list)

    def risk(self) -> Decimal:
        return abs(self.entry_price - self.stop_price)

    def pnl(self) -> Optional[Decimal]:
        if self.exit_price is None:
            return None
        if self.direction == TradeSide.LONG:
            return self.exit_price - self.entry_price
        return self.entry_price - self.exit_price

    def r_multiple(self) -> Optional[Decimal]:
        p = self.pnl()
        if p is None:
            return None
        r = self.risk()
        if r == 0:
            return Decimal("0")
        return p / r

    def model_post_init(self, _ctx) -> None:
        if self.symbol not in ALLOWED_SYMBOLS:
            raise ValueError(
                f"symbol {self.symbol!r} not in {sorted(ALLOWED_SYMBOLS)}"
            )


class DryRun(BaseModel):
    id: str
    checklist_id: str
    date: date_type
    symbol: str
    direction: TradeSide
    setup_type: str
    identified_time: datetime
    hypothetical_entry: Decimal
    hypothetical_stop: Decimal
    hypothetical_target: Decimal
    hypothetical_size: int
    outcome: Optional[DryRunOutcome] = None
    outcome_time: Optional[datetime] = None
    outcome_price: Optional[Decimal] = None
    hypothetical_r_multiple: Optional[Decimal] = None
    notes: Optional[str] = None

    def model_post_init(self, _ctx) -> None:
        if self.symbol not in ALLOWED_SYMBOLS:
            raise ValueError(
                f"symbol {self.symbol!r} not in {sorted(ALLOWED_SYMBOLS)}"
            )


class CircuitState(BaseModel):
    date: date_type
    realized_r: Decimal = Decimal("0")
    realized_usd: Decimal = Decimal("0")
    trade_count: int = 0
    no_trade_flag: bool = False
    lock_reason: Optional[str] = None
    last_stop_time: Optional[datetime] = None


class Contract(BaseModel):
    version: int
    signed_date: date_type
    active: bool
    r_unit_usd: Decimal
    daily_loss_limit_r: int
    daily_loss_warning_r: int
    max_trades_per_day: int
    stop_cooloff_minutes: int
    locked_setup_name: Optional[str] = None
    locked_setup_file: Optional[str] = None
    lock_in_min_trades: int = 30
    backup_setup_name: Optional[str] = None
    backup_setup_file: Optional[str] = None
    backup_setup_status: str = "benched"  # 'benched' | 'active'


class SetupVerdict(BaseModel):
    setup_name: str
    setup_version: str
    run_date: date_type
    symbol: str
    data_window_days: int
    n_samples: int
    win_rate: float
    avg_r: float
    passed: bool
