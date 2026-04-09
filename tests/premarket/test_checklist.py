# tests/premarket/test_checklist.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from daytrader.premarket.checklist import PremarketChecklist
from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.renderers.markdown import MarkdownRenderer


@pytest.fixture
def mock_results():
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={"ES=F": {"price": 5425.50, "change_pct": 0.35, "prev_close": 5400.0}},
            success=True,
        ),
    }


@pytest.mark.asyncio
async def test_checklist_run_collects_and_renders(tmp_dir, mock_results):
    mock_mdc = AsyncMock(spec=MarketDataCollector)
    mock_mdc.collect_all.return_value = mock_results

    checklist = PremarketChecklist(
        collector=mock_mdc,
        renderers=[MarkdownRenderer(output_dir=str(tmp_dir))],
    )

    report = await checklist.run()
    assert report is not None
    assert "ES=F" in report
    mock_mdc.collect_all.assert_called_once()
