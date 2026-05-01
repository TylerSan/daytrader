"""Volume profile computation (POC, VAH, VAL).

Distributes each bar's volume uniformly across its price range (high to low),
then identifies:
- POC (Point of Control): price level with the most volume
- Value Area: contiguous range around POC containing `value_area_pct` of total volume
- VAH (Value Area High): top of value area
- VAL (Value Area Low): bottom of value area

Standard convention: value_area_pct = 70%.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from daytrader.core.ib_client import OHLCV


@dataclass(frozen=True)
class VolumeProfile:
    poc: float
    vah: float
    val: float
    total_volume: float
    tick_size: float


def compute_volume_profile(
    bars: list[OHLCV],
    tick_size: float = 0.25,
    value_area_pct: float = 0.7,
) -> VolumeProfile:
    """Compute volume profile from a list of intraday bars."""
    if not bars:
        raise ValueError("compute_volume_profile: empty bars list")

    volume_at_price: dict[float, float] = defaultdict(float)
    for bar in bars:
        if bar.high < bar.low:
            continue
        price_levels = []
        p = bar.low
        while p <= bar.high + 1e-9:
            price_levels.append(round(p, 6))
            p += tick_size
        if not price_levels:
            price_levels = [bar.close]
        per_level_volume = bar.volume / len(price_levels)
        for level in price_levels:
            volume_at_price[level] += per_level_volume

    if not volume_at_price:
        raise ValueError("compute_volume_profile: no price levels accumulated")

    poc = max(volume_at_price.keys(), key=lambda p: volume_at_price[p])
    total_volume = sum(volume_at_price.values())
    target_volume = total_volume * value_area_pct

    sorted_levels = sorted(volume_at_price.keys())
    poc_idx = sorted_levels.index(poc)
    val_idx, vah_idx = poc_idx, poc_idx
    accumulated = volume_at_price[poc]

    while accumulated < target_volume:
        below_idx = val_idx - 1
        above_idx = vah_idx + 1
        below_vol = (
            volume_at_price[sorted_levels[below_idx]] if below_idx >= 0 else -1
        )
        above_vol = (
            volume_at_price[sorted_levels[above_idx]]
            if above_idx < len(sorted_levels) else -1
        )
        if below_vol < 0 and above_vol < 0:
            break
        if above_vol >= below_vol:
            vah_idx = above_idx
            accumulated += above_vol
        else:
            val_idx = below_idx
            accumulated += below_vol

    return VolumeProfile(
        poc=poc,
        vah=sorted_levels[vah_idx],
        val=sorted_levels[val_idx],
        total_volume=total_volume,
        tick_size=tick_size,
    )
