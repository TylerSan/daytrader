from datetime import datetime, timezone

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.pinescript import PineScriptRenderer


@pytest.fixture
def levels_result() -> dict[str, CollectorResult]:
    return {
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 542.0,
                    "prior_day_low": 538.0,
                    "prior_day_close": 540.0,
                },
            },
            success=True,
        ),
    }


def test_pinescript_generates_valid_code(levels_result):
    renderer = PineScriptRenderer()
    code = renderer.render(levels_result, symbol="SPY")
    assert "//@version=5" in code
    assert "indicator" in code
    assert "542.0" in code
    assert "538.0" in code
    assert "540.0" in code
    assert "hline" in code or "line.new" in code


def test_pinescript_saves_to_file(levels_result, tmp_dir):
    renderer = PineScriptRenderer(output_dir=str(tmp_dir))
    path = renderer.render_and_save(levels_result, symbol="SPY")
    assert path.exists()
    assert path.suffix == ".pine"
