"""Live Databento SPY daily integration smoke test. Skipped unless enabled.

Run:
    RUN_LIVE_TESTS=1 DATABENTO_API_KEY=<key> \\
        pytest tests/research/bakeoff/test_integration_spy_daily.py -v

Cost: 1 week of SPY daily ≈ pennies.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from daytrader.research.bakeoff.data_spy_daily import load_spy_daily


LIVE_ENABLED = (
    os.getenv("RUN_LIVE_TESTS") == "1"
    and os.getenv("DATABENTO_API_KEY")
)


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="live Databento disabled (set RUN_LIVE_TESTS=1 + DATABENTO_API_KEY)",
)
def test_live_fetch_one_week_spy_daily(tmp_path):
    df = load_spy_daily(
        start=date(2023, 6, 5),
        end=date(2023, 6, 9),
        api_key=os.environ["DATABENTO_API_KEY"],
        cache_dir=tmp_path,
    )
    assert 4 <= len(df) <= 5
    for c in ["open", "high", "low", "close"]:
        assert c in df.columns, f"missing column: {c}"
    assert 380 <= df["close"].mean() <= 500
