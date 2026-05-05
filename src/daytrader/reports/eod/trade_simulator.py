"""TradeSimulator — per (PlanLevel, intraday_bars) → SimOutcome.

Algorithm:
  1. Detect first-touch bar (level price within bar's high/low range)
  2. Compute sim entry / stop / target from the level using literal setup yaml
     geometry (entry at level for POINT, near-edge for ZONE)
  3. Walk forward from touch bar; determine whether stop or target is hit first
  4. If neither, mark "open" and compute partial sim_r from last-bar close
  5. Track MFE / MAE in R units for diagnostics
"""

from __future__ import annotations

from typing import Any

from daytrader.reports.eod.plan_dataclasses import PlanLevel, SimOutcome


def simulate_level(
    level: PlanLevel,
    intraday_bars: list[Any],          # OHLCV-like; needs .high / .low / .close / .timestamp
    next_key_level: float | None,
    tick_size: float = 0.25,
    stop_offset_ticks: int = 2,
    target_r_multiple: float = 2.0,
) -> SimOutcome:
    """Simulate one level against today's intraday bars.

    `next_key_level` if provided caps the target — for short_fade target = max
    (more conservative) of (2R target, next_key_level); for long_fade target =
    min of the two.
    """
    if not intraday_bars:
        return SimOutcome.untriggered()

    # Step 1: detect first-touch bar
    touch_idx = _find_first_touch(level, intraday_bars)
    if touch_idx is None:
        return SimOutcome.untriggered()
    touch_bar = intraday_bars[touch_idx]

    # Step 2: compute entry / stop / target
    sim_entry = _entry_for_direction(level)
    sim_stop = _stop_for_level(level, sim_entry, tick_size, stop_offset_ticks)
    r_distance = abs(sim_stop - sim_entry)
    sim_target = _target_for_direction(
        level, sim_entry, r_distance, target_r_multiple, next_key_level
    )

    # Step 3: walk forward to determine outcome (stop / target / open).
    # Start from the bar AFTER the touch — the touch bar fills the entry;
    # stop/target are evaluated from the next bar onward.
    # Seed MFE/MAE from the touch bar itself (excursion during the entry bar counts).
    mfe_r = 0.0  # max favorable excursion in R units
    mae_r = 0.0  # max adverse excursion (negative)
    if r_distance:
        if level.direction == "short_fade":
            _touch_favorable = (sim_entry - touch_bar.low) / r_distance
            _touch_adverse = (touch_bar.high - sim_entry) / r_distance
        else:
            _touch_favorable = (touch_bar.high - sim_entry) / r_distance
            _touch_adverse = (sim_entry - touch_bar.low) / r_distance
        mfe_r = max(mfe_r, _touch_favorable)
        mae_r = min(mae_r, -_touch_adverse)

    for bar in intraday_bars[touch_idx + 1:]:
        if level.direction == "short_fade":
            # Adverse = price up; favorable = price down
            adverse = (bar.high - sim_entry) / r_distance if r_distance else 0.0
            favorable = (sim_entry - bar.low) / r_distance if r_distance else 0.0
            mfe_r = max(mfe_r, favorable)
            mae_r = min(mae_r, -adverse)
            if bar.high >= sim_stop:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "stop", -1.0, mfe_r, mae_r)
            if bar.low <= sim_target:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "target", target_r_multiple, mfe_r, mae_r)
        else:  # long_fade
            adverse = (sim_entry - bar.low) / r_distance if r_distance else 0.0
            favorable = (bar.high - sim_entry) / r_distance if r_distance else 0.0
            mfe_r = max(mfe_r, favorable)
            mae_r = min(mae_r, -adverse)
            if bar.low <= sim_stop:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "stop", -1.0, mfe_r, mae_r)
            if bar.high >= sim_target:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "target", target_r_multiple, mfe_r, mae_r)

    # Step 4: open at session end — partial sim_r based on last close
    last_close = intraday_bars[-1].close
    if level.direction == "short_fade":
        partial_r = (sim_entry - last_close) / r_distance if r_distance else 0.0
    else:
        partial_r = (last_close - sim_entry) / r_distance if r_distance else 0.0
    return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "open", partial_r, mfe_r, mae_r)


# --- helpers ---


def _find_first_touch(level: PlanLevel, bars: list[Any]) -> int | None:
    """Return index of first bar that touches the level (within bar's H/L range)."""
    if level.level_type == "POINT":
        target_price = level.price
        for i, bar in enumerate(bars):
            if level.direction == "short_fade":
                # short fade: price rises into level → high reaches level
                if bar.high >= target_price:
                    return i
            else:
                # long fade: price drops into level → low reaches level
                if bar.low <= target_price:
                    return i
        return None
    else:  # ZONE
        if level.direction == "short_fade":
            # short fade entry @ near-edge (lower edge of zone for short)
            target_price = level.zone_low if level.zone_low is not None else level.price
            for i, bar in enumerate(bars):
                if bar.high >= target_price:
                    return i
        else:
            # long fade entry @ near-edge (upper edge of zone for long)
            target_price = level.zone_high if level.zone_high is not None else level.price
            for i, bar in enumerate(bars):
                if bar.low <= target_price:
                    return i
        return None


def _entry_for_direction(level: PlanLevel) -> float:
    """Entry price assumption.

    POINT: at level.price (limit order at level).
    ZONE short_fade: at zone_low (near edge).
    ZONE long_fade: at zone_high (near edge).
    """
    if level.level_type == "POINT":
        return level.price
    if level.direction == "short_fade":
        return level.zone_low if level.zone_low is not None else level.price
    return level.zone_high if level.zone_high is not None else level.price


def _stop_for_level(
    level: PlanLevel,
    sim_entry: float,
    tick_size: float,
    stop_offset_ticks: int,
) -> float:
    """Stop placement per setup yaml.

    POINT: opposite_side_of_level + 2 ticks → for short_fade: level + offset.
    ZONE: opposite_side_of_zone (far edge) + 2 ticks.
    """
    offset = stop_offset_ticks * tick_size
    if level.level_type == "POINT":
        return level.price + offset if level.direction == "short_fade" else level.price - offset
    # ZONE
    if level.direction == "short_fade":
        far_edge = level.zone_high if level.zone_high is not None else level.price
        return far_edge + offset
    far_edge = level.zone_low if level.zone_low is not None else level.price
    return far_edge - offset


def _target_for_direction(
    level: PlanLevel,
    sim_entry: float,
    r_distance: float,
    target_r_multiple: float,
    next_key_level: float | None,
) -> float:
    """Target = entry +/- target_r_multiple * R_distance, capped by next_key_level
    (more conservative side)."""
    if level.direction == "short_fade":
        target_2r = sim_entry - target_r_multiple * r_distance
        if next_key_level is not None:
            return max(target_2r, next_key_level)  # closer to entry = more conservative for short
        return target_2r
    target_2r = sim_entry + target_r_multiple * r_distance
    if next_key_level is not None:
        return min(target_2r, next_key_level)  # closer to entry = more conservative for long
    return target_2r


def _outcome(
    touch_bar: Any,
    sim_entry: float,
    sim_stop: float,
    sim_target: float,
    outcome: str,
    sim_r: float,
    mfe_r: float,
    mae_r: float,
) -> SimOutcome:
    """Build SimOutcome with formatted touch time."""
    touch_time_pt = touch_bar.timestamp.strftime("%H:%M") if hasattr(touch_bar, "timestamp") else None
    return SimOutcome(
        triggered=True,
        touch_time_pt=touch_time_pt,
        touch_bar_high=touch_bar.high,
        touch_bar_low=touch_bar.low,
        sim_entry=sim_entry,
        sim_stop=sim_stop,
        sim_target=sim_target,
        outcome=outcome,  # type: ignore[arg-type]
        sim_r=sim_r,
        mfe_r=mfe_r if mfe_r != 0 else None,
        mae_r=mae_r if mae_r != 0 else None,
    )
