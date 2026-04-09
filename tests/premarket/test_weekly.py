# tests/premarket/test_weekly.py
from datetime import datetime, date, timezone
from unittest.mock import AsyncMock

import pytest

from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.weekly import WeeklyPlanGenerator


@pytest.fixture
def mock_results():
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
            data={"ES=F": {"price": 5425.50, "change_pct": 0.35, "prev_close": 5400.0}},
            success=True,
        ),
        "sectors": CollectorResult(
            collector_name="sectors",
            timestamp=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
            data={"XLK": {"name": "Technology", "change_pct": 1.2}},
            success=True,
        ),
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "weekly_high": 543.0,
                    "weekly_low": 536.0,
                    "prior_day_close": 540.0,
                },
            },
            success=True,
        ),
    }


@pytest.mark.asyncio
async def test_weekly_plan_generates_report(tmp_dir, mock_results):
    mock_mdc = AsyncMock(spec=MarketDataCollector)
    mock_mdc.collect_all.return_value = mock_results

    generator = WeeklyPlanGenerator(collector=mock_mdc, output_dir=str(tmp_dir))
    report = await generator.generate(week_start=date(2026, 4, 6))
    assert "# Weekly Trading Plan" in report
    assert "2026-04-06" in report
    assert "ES=F" in report


@pytest.mark.asyncio
async def test_weekly_plan_saves_file(tmp_dir, mock_results):
    mock_mdc = AsyncMock(spec=MarketDataCollector)
    mock_mdc.collect_all.return_value = mock_results

    generator = WeeklyPlanGenerator(collector=mock_mdc, output_dir=str(tmp_dir))
    path = await generator.generate_and_save(week_start=date(2026, 4, 6))
    assert path.exists()
    assert "weekly" in path.name
