"""Core domain models for the DayTrader platform."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- Enums ---

class SignalDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class LevelSource(str, Enum):
    PRIOR_DAY_HIGH = "prior_day_high"
    PRIOR_DAY_LOW = "prior_day_low"
    PRIOR_DAY_CLOSE = "prior_day_close"
    PREMARKET_HIGH = "premarket_high"
    PREMARKET_LOW = "premarket_low"
    VOLUME_PROFILE_POC = "vp_poc"
    VOLUME_PROFILE_VAH = "vp_vah"
    VOLUME_PROFILE_VAL = "vp_val"
    WEEKLY_HIGH = "weekly_high"
    WEEKLY_LOW = "weekly_low"
    CUSTOM = "custom"


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGE_BOUND = "range_bound"
    VOLATILE = "volatile"
    LOW_VOLATILITY = "low_volatility"


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- Models ---

class Signal(BaseModel):
    id: str = Field(default_factory=_new_id)
    symbol: str
    direction: SignalDirection
    strength: int  # number of stacked imbalance layers
    price: Decimal
    timestamp: datetime
    imbalance_layers: int
    delta_ratio: Decimal
    context_regime: MarketRegime | None = None
    confidence: Confidence = Confidence.MEDIUM


class Trade(BaseModel):
    id: str = Field(default_factory=_new_id)
    symbol: str
    side: TradeSide
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    size: int
    entry_time: datetime
    exit_time: datetime
    signal_id: str | None = None
    source: str = ""  # "motivewave", "broker", etc.
    prop_firm: str | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def risk(self) -> Decimal:
        return abs(self.entry_price - self.stop_price)

    @property
    def pnl(self) -> Decimal:
        if self.side == TradeSide.LONG:
            return self.exit_price - self.entry_price
        return self.entry_price - self.exit_price

    @property
    def r_multiple(self) -> Decimal:
        if self.risk == 0:
            return Decimal("0")
        return self.pnl / self.risk


class Level(BaseModel):
    id: str = Field(default_factory=_new_id)
    symbol: str
    price: Decimal
    source: LevelSource
    label: str = ""
    date: datetime | None = None


class MarketContext(BaseModel):
    timestamp: datetime
    regime: MarketRegime
    vix: Decimal | None = None
    es_change_pct: Decimal | None = None
    nq_change_pct: Decimal | None = None
    sector_leaders: list[str] = Field(default_factory=list)
    sector_laggards: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str = Field(default_factory=_new_id)
    title: str
    description: str
    status: HypothesisStatus = HypothesisStatus.PENDING
    confidence: Confidence = Confidence.LOW
    evidence: str = ""
    recommendation: str = ""
    created_at: datetime | None = None
    validated_at: datetime | None = None
