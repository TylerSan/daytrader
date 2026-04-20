"""S2 Intraday Momentum strategies (Zarattini-Aziz-Barbon 2024).

Two variants sharing identical entry/exit logic; differ only in
max trades per day. Per spec §3.3, §3.5-§3.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from daytrader.research.bakeoff.strategies._s2_core import (
    CHECK_TIMES_ET,
    atr_14,
    avg_intraday_return_14d,
    compute_noise_boundary,
    walk_forward_with_trailing,
)
from daytrader.research.bakeoff.strategies._trade import Trade


SESSION_TZ = "America/New_York"
EOD_CUTOFF_ET = "15:55"


def _group_by_local_date(bars: pd.DataFrame, tz: str) -> dict:
    zoneinfo = ZoneInfo(tz)
    local_dates = bars.index.tz_convert(zoneinfo).date
    df = bars.copy()
    df["_local_date"] = local_dates
    return {d: g.drop(columns=["_local_date"]) for d, g in df.groupby("_local_date")}


def _local_hm(ts: pd.Timestamp, tz: str) -> str:
    return ts.tz_convert(ZoneInfo(tz)).strftime("%H:%M")


def _run_day(
    symbol: str,
    day_bars_1m: pd.DataFrame,
    daily_open: float,
    prev_close: float,
    atr_14_d: float,
    avg_intra_row: pd.Series,
    max_trades: int,
) -> list[Trade]:
    if (
        np.isnan(atr_14_d)
        or avg_intra_row.isna().any()
        or np.isnan(daily_open)
        or np.isnan(prev_close)
    ):
        return []

    overnight_gap = daily_open - prev_close
    upper, lower = compute_noise_boundary(
        daily_open=daily_open,
        overnight_gap=overnight_gap,
        avg_intra_return_row=avg_intra_row,
    )

    local_hm = np.array([_local_hm(ts, SESSION_TZ) for ts in day_bars_1m.index])

    eod_mask = local_hm == EOD_CUTOFF_ET
    if eod_mask.any():
        eod_idx = int(np.argmax(eod_mask))
    else:
        eod_idx = len(day_bars_1m) - 1
    eod_ts = day_bars_1m.index[eod_idx]

    trades: list[Trade] = []
    open_until_idx = -1

    for ct in CHECK_TIMES_ET:
        if len(trades) >= max_trades:
            break

        matches = np.where(local_hm == ct)[0]
        if len(matches) == 0:
            continue
        ct_idx = int(matches[0])

        if ct_idx < open_until_idx:
            continue

        ct_bar = day_bars_1m.iloc[ct_idx]
        price = float(ct_bar["close"])
        ct_upper = float(upper[ct])
        ct_lower = float(lower[ct])

        direction: str | None = None
        if price > ct_upper:
            direction = "long"
        elif price < ct_lower:
            direction = "short"
        if direction is None:
            continue

        entry_price = price
        if direction == "long":
            initial_stop = entry_price - 2.0 * atr_14_d
        else:
            initial_stop = entry_price + 2.0 * atr_14_d

        bars_after = day_bars_1m.iloc[ct_idx : eod_idx + 1]
        if len(bars_after) < 2:
            continue

        exit_info = walk_forward_with_trailing(
            bars_after_entry=bars_after,
            direction=direction,
            entry_price=entry_price,
            initial_stop=initial_stop,
            atr_14_d=atr_14_d,
            eod_cutoff_ts=eod_ts,
        )

        if exit_info.exit_time == eod_ts.to_pydatetime():
            exit_idx_in_day = eod_idx
        else:
            match = np.where(day_bars_1m.index == pd.Timestamp(exit_info.exit_time))[0]
            exit_idx_in_day = int(match[0]) if len(match) > 0 else eod_idx

        open_until_idx = exit_idx_in_day + 1

        risk = abs(entry_price - initial_stop)
        pnl = (exit_info.exit_price - entry_price) if direction == "long" \
            else (entry_price - exit_info.exit_price)
        r_multiple = 0.0 if risk == 0 else pnl / risk

        trades.append(Trade(
            date=str(day_bars_1m.index[0].tz_convert(SESSION_TZ).date()),
            symbol=symbol,
            direction=direction,
            entry_time=day_bars_1m.index[ct_idx].to_pydatetime(),
            entry_price=entry_price,
            stop_price=initial_stop,
            target_price=float("nan"),
            exit_time=exit_info.exit_time,
            exit_price=exit_info.exit_price,
            outcome=exit_info.outcome,
            r_multiple=r_multiple,
        ))

    return trades


def _generate(
    symbol: str,
    bars_1m: pd.DataFrame,
    bars_1d: pd.DataFrame,
    max_trades: int,
) -> list[Trade]:
    atr_series = atr_14(bars_1d)
    avg_intra = avg_intraday_return_14d(
        bars_1m, check_times_et=CHECK_TIMES_ET, tz=SESSION_TZ
    )

    per_day = _group_by_local_date(bars_1m, SESSION_TZ)
    out: list[Trade] = []

    prev_close_series = bars_1d["close"].shift(1)

    for d, day_bars in per_day.items():
        # bars_1d has a pd.Timestamp DatetimeIndex (normalized to midnight);
        # avg_intra has a datetime.date Index (from the groupby key). Build
        # both lookup keys explicitly.
        d_ts = pd.Timestamp(d).normalize()
        if d_ts not in bars_1d.index:
            continue
        daily_open = float(bars_1d.loc[d_ts, "open"])
        prev_close = (
            float(prev_close_series.loc[d_ts])
            if not pd.isna(prev_close_series.loc[d_ts])
            else float("nan")
        )
        atr_d = float(atr_series.loc[d_ts]) if d_ts in atr_series.index else float("nan")

        if d not in avg_intra.index:
            continue
        avg_row = avg_intra.loc[d]

        out.extend(_run_day(
            symbol=symbol,
            day_bars_1m=day_bars,
            daily_open=daily_open,
            prev_close=prev_close,
            atr_14_d=atr_d,
            avg_intra_row=avg_row,
            max_trades=max_trades,
        ))

    return out


@dataclass
class S2a_IntradayMomentum_Max1:
    """S2a: max 1 trade per day (conservative). Per spec §3.3 + §3.6."""
    symbol: str

    def generate_trades(
        self, bars_1m: pd.DataFrame, bars_1d: pd.DataFrame
    ) -> list[Trade]:
        return _generate(self.symbol, bars_1m, bars_1d, max_trades=1)


@dataclass
class S2b_IntradayMomentum_Max5:
    """S2b: max 5 trades per day (Contract ceiling, close to paper intent)."""
    symbol: str

    def generate_trades(
        self, bars_1m: pd.DataFrame, bars_1d: pd.DataFrame
    ) -> list[Trade]:
        return _generate(self.symbol, bars_1m, bars_1d, max_trades=5)
