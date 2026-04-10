from datetime import date, datetime, timezone

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.cards import CardGenerator


@pytest.fixture
def sample_results() -> dict[str, CollectorResult]:
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "ES=F": {
                    "price": 5425.50,
                    "change_pct": 0.35,
                    "prev_close": 5400.0,
                    "day_high": 5440.0,
                    "day_low": 5390.0,
                    "overnight_high": 5435.0,
                    "overnight_low": 5395.0,
                    "overnight_range": 40.0,
                    "asia_high": 5420.0,
                    "asia_low": 5400.0,
                    "europe_high": 5435.0,
                    "europe_low": 5395.0,
                },
                "NQ=F": {
                    "price": 19250.0,
                    "change_pct": 0.45,
                    "prev_close": 19150.0,
                    "day_high": 19300.0,
                    "day_low": 19100.0,
                },
                "^VIX": {"price": 18.5, "change_pct": -2.1, "prev_close": 18.9},
            },
            success=True,
        ),
        "sectors": CollectorResult(
            collector_name="sectors",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "XLK": {"name": "Technology", "change_pct": 1.2},
                "XLF": {"name": "Financials", "change_pct": -0.3},
            },
            success=True,
        ),
        "movers": CollectorResult(
            collector_name="movers",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "movers": [
                    {"symbol": "PLTR", "name": "Palantir", "price": 129.55, "gap_pct": -7.96, "vol_ratio": 2.14},
                    {"symbol": "AMZN", "name": "Amazon", "price": 233.09, "gap_pct": 5.35, "vol_ratio": 1.23},
                ]
            },
            success=True,
        ),
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 681.15,
                    "prior_day_low": 673.77,
                    "prior_day_close": 676.01,
                    "approx_vwap_5d": 666.54,
                    "weekly_high": 681.15,
                    "weekly_low": 645.11,
                },
            },
            success=True,
        ),
    }


def test_build_overview_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_overview_prompt(sample_results, date(2026, 4, 9))
    assert "ES=F" in prompt
    assert "5425.5" in prompt
    assert "VIX" in prompt
    assert "18.5" in prompt


def test_build_sectors_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_sectors_prompt(sample_results)
    assert "Technology" in prompt
    assert "+1.20%" in prompt
    assert "Financials" in prompt


def test_build_movers_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_movers_prompt(sample_results)
    assert "PLTR" in prompt
    assert "-7.96%" in prompt
    assert "AMZN" in prompt


def test_build_levels_prompt(sample_results):
    gen = CardGenerator(output_dir="/tmp/test-cards")
    prompt = gen.build_levels_prompt(sample_results)
    assert "SPY" in prompt
    assert "681.15" in prompt
    assert "VWAP" in prompt or "vwap" in prompt.lower()


def test_build_prompts_returns_empty_on_missing_data():
    gen = CardGenerator(output_dir="/tmp/test-cards")
    empty = {}
    assert gen.build_overview_prompt(empty, date(2026, 4, 9)) == ""
    assert gen.build_sectors_prompt(empty) == ""
    assert gen.build_movers_prompt(empty) == ""
    assert gen.build_levels_prompt(empty) == ""


# --- generate_card / generate_premarket_cards / generate_weekly_cards ---

from unittest.mock import patch, MagicMock
import subprocess


def test_generate_card_calls_claude_cli(sample_results, tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Image generated successfully"

    with patch("daytrader.premarket.renderers.cards.subprocess.run", return_value=mock_result) as mock_run:
        path = gen.generate_card(
            prompt="test prompt",
            output_path=tmp_dir / "test.webp",
        )
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "claude" in call_args[0][0][0] or "claude" in str(call_args)


def test_generate_card_returns_none_on_failure(tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    with patch("daytrader.premarket.renderers.cards.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)):
        path = gen.generate_card(
            prompt="test prompt",
            output_path=tmp_dir / "test.webp",
        )
        assert path is None


def test_generate_all_premarket(sample_results, tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))

    with patch.object(gen, "generate_card", return_value=tmp_dir / "fake.webp") as mock_gen:
        paths = gen.generate_premarket_cards(sample_results, date(2026, 4, 9))
        assert mock_gen.call_count == 4  # overview, sectors, movers, levels


def test_generate_all_premarket_skips_missing_data(tmp_dir):
    gen = CardGenerator(output_dir=str(tmp_dir))
    empty_results = {}

    with patch.object(gen, "generate_card") as mock_gen:
        paths = gen.generate_premarket_cards(empty_results, date(2026, 4, 9))
        assert mock_gen.call_count == 0
        assert paths == []
