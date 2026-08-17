"""S2 Intraday Momentum mechanical core (spec §3.3 + §3.4 + §3.7).

Pure functions on pandas DataFrames. No I/O, no cost model. Shared by
S2a and S2b.
"""

from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from daytrader.research.bakeoff.strategies._orb_core import ExitInfo
from daytrader.research.bakeoff.strategies._trade import TradeOutcome


Direction = Literal["long", "short"]


CHECK_TIMES_ET = [
    "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30",
    "14:00", "14:30", "15:00", "15:30",
]


def daily_true_range(daily: pd.DataFrame) -> pd.Series:
    prev_close = daily["close"].shift(1)
    hl = daily["high"] - daily["low"]
    hc = (daily["high"] - prev_close).abs()
    lc = (daily["low"] - prev_close).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr


def atr_14(daily: pd.DataFrame) -> pd.Series:
    tr = daily_true_range(daily)
    sma = tr.rolling(window=14, min_periods=14).mean()
    return sma.shift(1)


def avg_intraday_return_14d(
    bars_1m: pd.DataFrame,
    check_times_et: list[str],
    tz: str,
) -> pd.DataFrame:
    zoneinfo = ZoneInfo(tz)
    local = bars_1m.index.tz_convert(zoneinfo)
    local_date = pd.Series(local.date, index=bars_1m.index, name="_d")
    local_hm = pd.Series(
        [t.strftime("%H:%M") for t in local], index=bars_1m.index, name="_hm"
    )
    tagged = bars_1m.assign(_d=local_date, _hm=local_hm)

    opens = tagged[tagged["_hm"] == "09:30"].groupby("_d")["open"].first()
    missing = set(tagged["_d"].unique()) - set(opens.index)
    if missing:
        raise ValueError(f"missing 09:30 bar for dates: {sorted(missing)}")

    per_day_return = {}
    for ct in check_times_et:
        ct_closes = tagged[tagged["_hm"] == ct].groupby("_d")["close"].first()
        ret = (ct_closes - opens) / opens
        per_day_return[ct] = ret

    per_day_df = pd.DataFrame(per_day_return).sort_index()
    rolled = per_day_df.rolling(window=14, min_periods=14).mean()
    return rolled.shift(1)


def compute_noise_boundary(
    daily_open: float,
    overnight_gap: float,
    avg_intra_return_row: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    abs_ret = avg_intra_return_row.abs()
    raw_upper = daily_open * (1 + abs_ret)
    raw_lower = daily_open * (1 - abs_ret)
    if overnight_gap > 0:
        lower = raw_lower - overnight_gap
        upper = raw_upper
    elif overnight_gap < 0:
        upper = raw_upper + abs(overnight_gap)
        lower = raw_lower
    else:
        upper, lower = raw_upper, raw_lower
    return upper, lower


def walk_forward_with_trailing(
    bars_after_entry: pd.DataFrame,
    direction: Direction,
    entry_price: float,
    initial_stop: float,
    atr_14_d: float,
    eod_cutoff_ts: pd.Timestamp,
    atr_multiplier: float = 2.0,
) -> ExitInfo:
    stop = initial_stop

    for i in range(1, len(bars_after_entry)):
        ts = bars_after_entry.index[i]
        bar = bars_after_entry.iloc[i]
        hi = float(bar["high"])
        lo = float(bar["low"])

        if direction == "long":
            if lo <= stop:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop,
                    outcome=TradeOutcome.STOP,
                )
            candidate = hi - atr_multiplier * atr_14_d
            if candidate > stop:
                stop = candidate
        else:
            if hi >= stop:
                return ExitInfo(
                    exit_time=ts.to_pydatetime(),
                    exit_price=stop,
                    outcome=TradeOutcome.STOP,
                )
            candidate = lo + atr_multiplier * atr_14_d
            if candidate < stop:
                stop = candidate

    last_bar = bars_after_entry.iloc[-1]
    return ExitInfo(
        exit_time=eod_cutoff_ts.to_pydatetime(),
        exit_price=float(last_bar["close"]),
        outcome=TradeOutcome.EOD,
    )
