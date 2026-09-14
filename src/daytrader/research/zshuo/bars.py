"""1m parquet -> 5m bars with session tags and rollover marks."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "instrument_id": "first"}


def load_1m(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    cols = ["open", "high", "low", "close", "volume", "instrument_id"]
    df = df[cols].sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def resample_5m(df1m: pd.DataFrame) -> pd.DataFrame:
    if df1m.empty:
        raise ValueError("empty 1m frame")
    df = df1m.resample("5min", label="left", closed="left").agg(_AGG).dropna(
        subset=["open"])
    df["instrument_id"] = df["instrument_id"].astype(int)
    df["rollover"] = df["instrument_id"].ne(df["instrument_id"].shift())
    df.iloc[0, df.columns.get_loc("rollover")] = False  # first bar is never a roll
    return df


def tag_sessions(df5m: pd.DataFrame) -> pd.DataFrame:
    et = df5m.index.tz_convert("America/New_York")
    df = df5m.copy()
    df["rth"] = (et.time >= pd.Timestamp("09:30").time()) & (
        et.time < pd.Timestamp("16:00").time())
    # CME trading day, not ET calendar day: the session opens 18:00 ET and is
    # dated to the NEXT day, so shifting +6h puts the 18:00 boundary at
    # midnight and .date then yields the trading day. Used for expiry counting.
    df["session_date"] = (et + pd.Timedelta(hours=6)).date
    return df
