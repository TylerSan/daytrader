"""Frozen dataclasses for the EOD plan retrospective subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class PlanLevel:
    """A single key level extracted from today's premarket C block.

    POINT levels are single prices (e.g. "7272.75 (4H POC)"). The
    `entry_proximity` rule is `max_ticks=4` (per setup yaml).

    ZONE levels are price ranges (e.g. "7185-7195 W demand zone"). The
    entry rule is "price within zone edges". `zone_low` / `zone_high`
    capture the edges; `price` is set to the midpoint or the level the
    AI emphasized as primary.
    """
    price: float
    level_type: Literal["POINT", "ZONE"]
    source: str  # e.g. "4H POC", "W high", "htf_demand_zone fresh"
    direction: Literal["short_fade", "long_fade"]
    zone_low: float | None = None
    zone_high: float | None = None


@dataclass(frozen=True)
class Plan:
    """Today's structured plan for one symbol, parsed from premarket C block."""
    symbol: str
    levels: list[PlanLevel]
    stop_offset_ticks: int = 2          # per setup yaml
    target_r_multiple: float = 2.0      # per setup yaml
    raw_block_md: str = ""              # for verbatim quote in C section
    parse_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SimOutcome:
    """Result of simulating one PlanLevel against today's intraday bars."""
    triggered: bool
    touch_time_pt: str | None       # e.g. "06:53" or None if untriggered
    touch_bar_high: float | None
    touch_bar_low: float | None
    sim_entry: float | None
    sim_stop: float | None
    sim_target: float | None
    outcome: Literal["target", "stop", "open", "untriggered"]
    sim_r: float                    # 0 if untriggered, +N if target, -1 if stop, partial if open
    mfe_r: float | None             # max favorable excursion in R units
    mae_r: float | None             # max adverse excursion in R units

    @classmethod
    def untriggered(cls) -> "SimOutcome":
        """Factory for the level-not-touched case."""
        return cls(
            triggered=False,
            touch_time_pt=None,
            touch_bar_high=None,
            touch_bar_low=None,
            sim_entry=None,
            sim_stop=None,
            sim_target=None,
            outcome="untriggered",
            sim_r=0.0,
            mfe_r=None,
            mae_r=None,
        )


@dataclass(frozen=True)
class RetrospectiveRow:
    """Per-symbol per-day retrospective summary. One row → one row in
    `plan_retrospective_daily` SQLite table."""
    symbol: str
    date_et: str                    # YYYY-MM-DD
    total_levels: int
    triggered_count: int
    sim_total_r: float              # sum of all levels' sim_r
    actual_total_r: float           # from journal DB
    gap_r: float                    # sim - actual
    per_level_outcomes: list[tuple[PlanLevel, SimOutcome]]
