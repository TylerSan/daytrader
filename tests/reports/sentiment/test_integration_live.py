"""Live integration test for SentimentCollector — calls real claude -p.

Marked `slow`: skipped by default. Run manually with:
    uv run pytest -m slow tests/reports/sentiment/

Requires:
- `claude` CLI on PATH
- Network access
- ~2 minutes wall time
"""

from __future__ import annotations

import pytest

from daytrader.reports.sentiment.collector import SentimentCollector


@pytest.mark.slow
def test_live_collector_returns_parseable_sentiment():
    """End-to-end smoke: real claude -p call with WebSearch should return
    parseable markdown matching our contract."""
    collector = SentimentCollector(
        symbols=["MES", "MGC", "MNQ"],
        timeout_s=240,  # generous for live call
    )
    result = collector.collect()

    if result.unavailable:
        pytest.fail(
            f"Live sentiment call failed: {result.unavailable_reason}\n"
            "If this is a Claude availability issue, retry. If parser failed,\n"
            "check data/logs/sentiment-failures/ for the raw response and\n"
            "tighten the parser regex."
        )

    assert result.macro is not None
    assert -5 <= result.macro.score.combined <= 5
    assert -5 <= result.macro.score.news <= 5
    assert -5 <= result.macro.score.social <= 5

    assert len(result.per_symbol) >= 1, "expected at least 1 symbol parsed"
    for s in result.per_symbol:
        assert s.symbol in {"MES", "MGC", "MNQ"}
        assert -5 <= s.score.combined <= 5

    assert len(result.sources) >= 3, \
        f"expected >=3 sources, got {len(result.sources)}: {result.sources}"
    assert all(u.startswith("http") for u in result.sources)
