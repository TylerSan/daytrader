"""MES 1-minute data loader — Databento-backed with local parquet cache.

Handles:
- Continuous contract front-month via Databento `c-1` symbology
- Rollover day detection via `instrument_id` transitions
- RTH session filter (09:30-16:00 ET)
- Data quality report (missing bar rate per day)

See spec §1.2, §2.3, R1, R3.
"""

from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

import pandas as pd


ET = ZoneInfo("America/New_York")


def detect_rollover_skip_dates(df: pd.DataFrame) -> list[date]:
    """Return sorted list of local-ET dates to skip due to rollover.

    A rollover is a row where `instrument_id` differs from the previous row.
    Both the rollover day and the preceding trading day are skipped to avoid
    false breakouts from mid-day front-month transitions.

    Args:
        df: DataFrame indexed by UTC timestamps, must contain `instrument_id`.

    Returns:
        Sorted unique list of dates (local ET) to exclude from backtests.

    Raises:
        ValueError if `instrument_id` column missing.
    """
    if "instrument_id" not in df.columns:
        raise ValueError("DataFrame must have 'instrument_id' column")
    if df.empty:
        return []

    local_dates = df.index.tz_convert(ET).date
    iids = df["instrument_id"].to_numpy()
    skip: set[date] = set()
    for i in range(1, len(iids)):
        if iids[i] != iids[i - 1]:
            # rollover day (i) + preceding day (i-1)
            skip.add(local_dates[i])
            skip.add(local_dates[i - 1])
    return sorted(skip)


RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only bars whose timestamp falls in [09:30, 16:00) ET.

    Input must be UTC-indexed. DST-aware via zoneinfo. Returns a new DataFrame;
    does not mutate input.
    """
    if df.empty:
        return df.copy()
    local_times = df.index.tz_convert(ET).time
    mask = (local_times >= RTH_OPEN) & (local_times < RTH_CLOSE)
    return df[mask].copy()
