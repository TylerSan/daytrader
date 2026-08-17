"""Historical OHLCV loader with local parquet cache.

- 1-minute data from yfinance has a ~7-day rolling window limit.
- We cache whatever we fetch to parquet for re-runnability.
- On cache miss, fetch from yfinance and write to cache.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


# yfinance tickers for CME futures continuous contracts
SYMBOL_TO_YFINANCE = {
    "MES": "MES=F",
    "MNQ": "MNQ=F",
    "MGC": "MGC=F",
    # fallbacks at full-size E-mini if micros fail:
    "ES": "ES=F",
    "NQ": "NQ=F",
    "GC": "GC=F",
}


class DataLoadError(RuntimeError):
    pass


class HistoricalDataLoader:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(
        self, symbol: str, interval: str, start: date, end: date
    ) -> Path:
        fname = f"{symbol}_{interval}_{start.isoformat()}_{end.isoformat()}.parquet"
        return self.cache_dir / fname

    def load(
        self,
        symbol: str,
        interval: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame indexed by UTC timestamp.

        Raises DataLoadError if fetch fails and no cache exists.
        """
        p = self._cache_path(symbol, interval, start, end)
        if p.exists():
            return pd.read_parquet(p)

        yf_symbol = SYMBOL_TO_YFINANCE.get(symbol)
        if yf_symbol is None:
            raise DataLoadError(f"unknown symbol: {symbol}")

        try:
            import yfinance as yf
        except ImportError as e:
            raise DataLoadError("yfinance not installed") from e

        df = yf.download(
            yf_symbol,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval=interval,
            auto_adjust=False,
            progress=False,
        )
        if df is None or df.empty:
            raise DataLoadError(
                f"no data returned for {symbol} ({yf_symbol}) "
                f"{interval} {start}→{end}"
            )
        # Flatten MultiIndex columns (yfinance v0.2+ returns them)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        # Ensure UTC index
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        df.to_parquet(p)
        return df
