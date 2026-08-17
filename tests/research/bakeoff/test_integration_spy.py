"""Live Databento SPY integration smoke test. Skipped unless enabled.

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> \\
        pytest tests/research/bakeoff/test_integration_spy.py -v

Cost: 1 trading day of SPY 1m ≈ pennies.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from daytrader.research.bakeoff.data_spy import load_spy_1m


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
)


@pytest.mark.skipif(not LIVE_ENABLED, reason="live Databento disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY)")
def test_live_fetch_one_day_spy(tmp_path):
    ds = load_spy_1m(
        start=date(2024, 6, 10),
        end=date(2024, 6, 10),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=tmp_path,
    )
    assert 370 <= len(ds.bars) <= 390
    for c in ["open", "high", "low", "close", "volume"]:
        assert c in ds.bars.columns, f"missing column: {c}"
    assert str(ds.bars.index.tz) == "UTC"
    assert date(2024, 6, 10) in ds.quality_report.index
