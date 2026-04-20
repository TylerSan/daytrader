"""Live Databento integration smoke test. Skipped unless explicitly enabled.

Run with:
    DATABENTO_API_KEY=<key> RUN_LIVE_TESTS=1 \\
        pytest tests/research/bakeoff/test_integration_data.py -v

Cost: downloads 1 trading day of MES 1m OHLCV (~390 rows). Expected Databento
bill: << $1 (OHLCV-1m is Databento's cheapest schema).
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from daytrader.research.bakeoff.data import load_mes_1m


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
)


@pytest.mark.skipif(not LIVE_ENABLED, reason="live Databento disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY)")
def test_live_fetch_one_day_mes(tmp_path):
    ds = load_mes_1m(
        start=date(2024, 6, 10),
        end=date(2024, 6, 10),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=tmp_path,
    )
    # RTH = 390 bars for a normal session; allow small missing-bar tolerance.
    assert 380 <= len(ds.bars) <= 390
    # Required columns.
    for c in ["open", "high", "low", "close", "volume", "instrument_id"]:
        assert c in ds.bars.columns, f"missing column: {c}"
    # UTC index.
    assert str(ds.bars.index.tz) == "UTC"
    # No rollover expected on an isolated mid-June day.
    assert ds.rollover_skip_dates == []
    # Quality report has that one date.
    assert date(2024, 6, 10) in ds.quality_report.index
