from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.base import (
    Collector,
    CollectorResult,
    MarketDataCollector,
)


class FakeCollector(Collector):
    @property
    def name(self) -> str:
        return "fake"

    async def collect(self) -> CollectorResult:
        return CollectorResult(
            collector_name="fake",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={"key": "value"},
            success=True,
        )


def test_collector_result_creation():
    result = CollectorResult(
        collector_name="test",
        timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
        data={"futures": {"ES": 5400}},
        success=True,
    )
    assert result.success is True
    assert result.data["futures"]["ES"] == 5400


@pytest.mark.asyncio
async def test_fake_collector():
    c = FakeCollector()
    result = await c.collect()
    assert result.success is True
    assert result.collector_name == "fake"


@pytest.mark.asyncio
async def test_market_data_collector_runs_all():
    mdc = MarketDataCollector()
    fake = FakeCollector()
    mdc.register(fake)
    results = await mdc.collect_all()
    assert "fake" in results
    assert results["fake"].success is True
