from datetime import datetime, timezone
from pathlib import Path

import pytest

from daytrader.premarket.collectors.base import CollectorResult
from daytrader.premarket.renderers.markdown import MarkdownRenderer


@pytest.fixture
def sample_results() -> dict[str, CollectorResult]:
    return {
        "futures": CollectorResult(
            collector_name="futures",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "ES=F": {"price": 5425.50, "change_pct": 0.35, "prev_close": 5400.0},
                "NQ=F": {"price": 19250.0, "change_pct": 0.45, "prev_close": 19150.0},
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
        "levels": CollectorResult(
            collector_name="levels",
            timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
            data={
                "SPY": {
                    "prior_day_high": 542.0,
                    "prior_day_low": 538.0,
                    "prior_day_close": 540.0,
                    "weekly_high": 543.0,
                    "weekly_low": 536.0,
                },
            },
            success=True,
        ),
    }


def test_markdown_renderer_produces_report(sample_results):
    renderer = MarkdownRenderer()
    report = renderer.render(sample_results, date=datetime(2026, 4, 9).date())
    assert "盘前分析报告" in report
    assert "2026-04-09" in report
    assert "type: premarket" in report  # YAML frontmatter
    assert "ES=F" in report
    assert "5425.5" in report
    assert "VIX" in report or "^VIX" in report
    assert "Technology" in report
    assert "SPY" in report


def test_markdown_renderer_saves_to_file(sample_results, tmp_dir):
    renderer = MarkdownRenderer(output_dir=str(tmp_dir))
    path = renderer.render_and_save(sample_results, date=datetime(2026, 4, 9).date())
    assert path.exists()
    content = path.read_text()
    assert "盘前分析报告" in content


def test_render_with_card_images_shows_snapshot_section(sample_results):
    renderer = MarkdownRenderer()
    card_images = [
        Path("data/exports/images/premarket-2026-04-09-overview.webp"),
        Path("data/exports/images/premarket-2026-04-09-sectors.webp"),
    ]
    report = renderer.render(
        sample_results,
        date=datetime(2026, 4, 9).date(),
        card_images=card_images,
    )
    assert "数据速览" in report
    assert "premarket-2026-04-09-overview.webp" in report
    assert "premarket-2026-04-09-sectors.webp" in report


def test_render_with_card_images_folds_tables(sample_results):
    renderer = MarkdownRenderer()
    card_images = [Path("data/exports/images/premarket-2026-04-09-overview.webp")]
    report = renderer.render(
        sample_results,
        date=datetime(2026, 4, 9).date(),
        card_images=card_images,
    )
    assert "> [!info]- 详细数据" in report


def test_render_without_card_images_no_folding(sample_results):
    renderer = MarkdownRenderer()
    report = renderer.render(sample_results, date=datetime(2026, 4, 9).date())
    assert "> [!info]-" not in report
    assert "数据速览" not in report


def test_render_news_without_summary(sample_results):
    sample_results["news"] = CollectorResult(
        collector_name="news",
        timestamp=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
        data={
            "headlines": [
                {"title": "S&P 500 Surges", "publisher": "Reuters", "summary": "The index rose..."},
            ]
        },
        success=True,
    )
    renderer = MarkdownRenderer()
    report = renderer.render(sample_results, date=datetime(2026, 4, 9).date())
    assert "> The index rose" not in report
    assert "S&P 500 Surges" in report
    assert "Reuters" in report
