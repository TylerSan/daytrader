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

RTH_BARS_PER_DAY = 390       # 6.5h * 60min
LOW_COVERAGE_THRESHOLD = 99.0  # pct; below this → flag


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


def data_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-day bar counts and coverage flags.

    Expects RTH-filtered input (use filter_rth first). Returns a DataFrame
    indexed by local ET date with columns: n_bars, coverage_pct,
    flag_low_coverage (bool).

    Empty input returns an empty DataFrame with the correct schema.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["n_bars", "coverage_pct", "flag_low_coverage"],
            index=pd.Index([], name="date"),
        )
    local_dates = df.index.tz_convert(ET).date
    by_day = pd.Series(local_dates).value_counts().sort_index()
    coverage = by_day / RTH_BARS_PER_DAY * 100.0
    rep = pd.DataFrame({
        "n_bars": by_day,
        "coverage_pct": coverage,
        "flag_low_coverage": coverage < LOW_COVERAGE_THRESHOLD,
    })
    rep.index.name = "date"
    return rep


from dataclasses import dataclass
from pathlib import Path
from datetime import date as _date


@dataclass
class MesDataset:
    """Cleaned MES bars + diagnostic artifacts.

    - bars: UTC-indexed DataFrame, RTH only, has OHLCV + instrument_id.
      WARNING: bars is NOT filtered by rollover_skip_dates or
      quality_report.flag_low_coverage. Callers (strategies in Plan 2+)
      MUST intersect bars' ET dates against these filter artifacts before
      running backtests. See spec §5.2 R1 (rollover) and R3 (low coverage).
    - rollover_skip_dates: list of local-ET dates on which trades must
      not be opened (rollover day + preceding day).
    - quality_report: per-day coverage DataFrame. The `flag_low_coverage`
      column marks days that callers should exclude from pure-OOS counts.
    """
    bars: pd.DataFrame
    rollover_skip_dates: list[_date]
    quality_report: pd.DataFrame


@dataclass
class MesDatabentoLoader:
    """Fetch MES 1-minute OHLCV from Databento, cached to parquet.

    Uses Databento's `continuous` symbology with `c-1` (front-month by open
    interest). Raw fetch (including `instrument_id` column for rollover
    detection) is cached to `<cache_dir>/MES_1m_<start>_<end>_raw.parquet`.
    """
    api_key: str
    cache_dir: Path

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("api_key is required")
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, start: _date, end: _date) -> Path:
        return self.cache_dir / (
            f"MES_1m_{start.isoformat()}_{end.isoformat()}_raw.parquet"
        )

    def load(self, start: _date, end: _date) -> pd.DataFrame:
        """Return UTC-indexed DataFrame with OHLCV + instrument_id.

        Inclusive on both ends. Cache-first.
        """
        p = self._cache_path(start, end)
        if p.exists():
            return pd.read_parquet(p)

        import databento
        client = databento.Historical(self.api_key)
        req = client.timeseries.get_range(
            dataset="GLBX.MDP3",
            schema="ohlcv-1m",
            symbols=["MES.c.0"],  # continuous front-month by OI
            stype_in="continuous",
            start=start.isoformat(),
            end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
        )
        df = req.to_df()
        # Normalize timezone to UTC.
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.to_parquet(p)
        return df


def load_mes_1m(
    start: _date,
    end: _date,
    api_key: str,
    cache_dir: Path,
) -> MesDataset:
    """End-to-end loader: fetch → RTH filter → diagnostics.

    Rollover detection runs on the raw (pre-RTH-filter) data so that mid-day
    instrument_id transitions are not lost.
    """
    loader = MesDatabentoLoader(api_key=api_key, cache_dir=cache_dir)
    raw = loader.load(start, end)
    skip_dates = detect_rollover_skip_dates(raw)
    rth = filter_rth(raw)
    qa = data_quality_report(rth)
    return MesDataset(bars=rth, rollover_skip_dates=skip_dates, quality_report=qa)
