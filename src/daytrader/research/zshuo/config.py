"""Frozen audit parameters. Spec §2/§4. Do not mutate at runtime."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditConfig:
    k: int = 3                      # fractal half-window (spec §2.1)
    x_ticks: int = 8                # race half-width (spec §3)
    tick_size: float = 0.25         # MES tick
    expiry_days: int = 5            # trading days a line stays open (spec §2.5)
    race_timeout_bars: int = 48     # 4h at 5min; unresolved -> "timeout"
    rollover_blackout_bars: int = 12  # 1h each side of instrument_id change
    min_gap_between_events: int = 24  # non-overlap spacing within group+dir (spec §3)
    phantom_offset_ticks: tuple[int, int] = (8, 24)  # VOID — superseded by spec 修订(二) time-displaced placebo; kept for grid config equality only
    seed: int = 42


SENSITIVITY_GRID = [
    AuditConfig(k=k, x_ticks=x, expiry_days=e)
    for k in (2, 3, 5)
    for x in (4, 8, 16)
    for e in (2, 5, 10)
]
