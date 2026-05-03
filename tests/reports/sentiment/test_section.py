"""Unit tests for SentimentSection facade + markdown renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from daytrader.reports.sentiment.dataclasses import (
    MacroSentiment,
    SentimentResult,
    SentimentScore,
    SymbolSentiment,
)
from daytrader.reports.sentiment.section import SentimentSection


def _happy_result() -> SentimentResult:
    macro = MacroSentiment(
        score=SentimentScore(news=4, social=2, combined=3,
                             narrative="earnings beat + Fed cuts priced"),
        main_themes=["earnings beat + Fed cuts priced"],
        risks=["Iran/Israel escalation"],
        upcoming_events=["FOMC Wed", "CPI Thu", "NFP Fri"],
    )
    per_symbol = [
        SymbolSentiment("MES", SentimentScore(3, 1, 2, "trend tired")),
        SymbolSentiment("MGC", SentimentScore(-2, -3, -3, "DXY strong")),
        SymbolSentiment("MNQ", SentimentScore(4, 5, 5, "AI theme")),
    ]
    return SentimentResult(
        timestamp=datetime.now(timezone.utc),
        unavailable=False,
        unavailable_reason="",
        macro=macro,
        per_symbol=per_symbol,
        sources=["https://a.com", "https://b.com", "https://c.com",
                 "https://d.com", "https://e.com"],
    )


def test_section_collect_delegates_to_collector():
    fake_result = _happy_result()
    fake_collector = MagicMock()
    fake_collector.collect.return_value = fake_result

    section = SentimentSection(symbols=["MES", "MGC", "MNQ"], collector=fake_collector)
    res = section.collect()

    assert res is fake_result
    fake_collector.collect.assert_called_once()


def test_render_happy_path_includes_d_section_header():
    section = SentimentSection(symbols=["MES", "MGC", "MNQ"])
    md = section.render(_happy_result())
    assert "## D. 情绪面" in md or "Sentiment Index" in md


def test_render_happy_path_includes_macro_block():
    section = SentimentSection(symbols=["MES", "MGC", "MNQ"])
    md = section.render(_happy_result())
    assert "Macro" in md
    assert "+3" in md  # macro combined
    assert "FOMC" in md  # event passed through


def test_render_happy_path_includes_per_symbol_table():
    section = SentimentSection(symbols=["MES", "MGC", "MNQ"])
    md = section.render(_happy_result())
    assert "| MES |" in md
    assert "| MGC |" in md
    assert "| MNQ |" in md
    assert "+2" in md  # MES combined
    assert "-3" in md  # MGC combined
    assert "+5" in md  # MNQ combined


def test_render_happy_path_includes_sources():
    section = SentimentSection(symbols=["MES", "MGC", "MNQ"])
    md = section.render(_happy_result())
    assert "https://a.com" in md
    assert "https://e.com" in md


def test_render_unavailable_block():
    section = SentimentSection(symbols=["MES"])
    res = SentimentResult.unavailable_due_to("claude timeout 180s")
    md = section.render(res)
    assert "## D. 情绪面" in md or "Sentiment Index" in md
    assert "不可用" in md or "unavailable" in md.lower()
    assert "timeout" in md


def test_render_partial_per_symbol():
    """If per_symbol has only MES + MGC but expected included MNQ, renderer
    should still produce a table with the available rows + an 'unavailable'
    note for MNQ."""
    macro = MacroSentiment(
        score=SentimentScore(0, 0, 0, ""),
        main_themes=[], risks=[], upcoming_events=[],
    )
    res = SentimentResult(
        timestamp=datetime.now(timezone.utc),
        unavailable=False,
        unavailable_reason="",
        macro=macro,
        per_symbol=[
            SymbolSentiment("MES", SentimentScore(1, 1, 1, "n")),
            SymbolSentiment("MGC", SentimentScore(0, 0, 0, "n")),
        ],
        sources=[],
    )
    section = SentimentSection(symbols=["MES", "MGC", "MNQ"])
    md = section.render(res)
    assert "| MES |" in md
    assert "| MGC |" in md
    # MNQ row missing — note must mention it
    assert "MNQ" in md  # at least mentioned in unavailable note


def test_section_collect_uses_default_collector_when_none_supplied(monkeypatch):
    """If no collector passed, SentimentSection constructs a SentimentCollector."""
    constructed: dict = {}

    class _FakeCollector:
        def __init__(self, symbols, **kw):
            constructed["symbols"] = symbols
            constructed["kw"] = kw

        def collect(self):
            return SentimentResult.unavailable_due_to("test")

    monkeypatch.setattr(
        "daytrader.reports.sentiment.section.SentimentCollector",
        _FakeCollector,
    )
    section = SentimentSection(symbols=["MES"])
    section.collect()
    assert constructed["symbols"] == ["MES"]
