"""Trade dataclass — the atomic unit of a bake-off strategy's output.

Every strategy class in `research.bakeoff.strategies` produces a list of
`Trade` from a bar DataFrame. This is the wire format between strategy
code and the metrics / walk-forward harness (Plan 3).

Kept deliberately separate from `daytrader.journal.models.SimulatedTrade`
— the journal version is frozen per spec §4.3, and mixing the two would
create accidental coupling between the research pipeline and the
discipline pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TradeOutcome(str, Enum):
    TARGET = "target"
    STOP = "stop"
    EOD = "eod"


_VALID_DIRECTIONS = {"long", "short"}


@dataclass(frozen=True)
class Trade:
    date: str
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    stop_price: float
    target_price: float
    exit_time: datetime
    exit_price: float
    outcome: TradeOutcome
    r_multiple: float

    def __post_init__(self):
        if self.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of {sorted(_VALID_DIRECTIONS)}, "
                f"got {self.direction!r}"
            )
