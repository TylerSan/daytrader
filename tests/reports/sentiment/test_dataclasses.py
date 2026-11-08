"""Unit tests for sentiment dataclasses."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.reports.sentiment.dataclasses import (
    MacroSentiment,
    SentimentResult,
    SentimentScore,
    SymbolSentiment,
)


def test_sentiment_score_construction():
    s = SentimentScore(news=3, social=1, combined=2, narrative="strong but tired")
    assert s.news == 3
    assert s.social == 1
    assert s.combined == 2
    assert "strong" in s.narrative


def test_sentiment_score_is_frozen():
    s = SentimentScore(news=0, social=0, combined=0, narrative="")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        s.news = 5  # type: ignore[misc]


def test_macro_sentiment_construction():
    score = SentimentScore(news=2, social=1, combined=2, narrative="bullish")
    macro = MacroSentiment(
        score=score,
        main_themes=["earnings beat"],
        risks=["geopolitics"],
        upcoming_events=["FOMC Wed", "CPI Thu"],
    )
    assert macro.score.combined == 2
    assert macro.main_themes == ["earnings beat"]
    assert len(macro.upcoming_events) == 2


def test_symbol_sentiment_construction():
    score = SentimentScore(news=-2, social=-3, combined=-3, narrative="DXY strong")
    sym = SymbolSentiment(symbol="MGC", score=score)
    assert sym.symbol == "MGC"
    assert sym.score.combined == -3


def test_sentiment_result_happy_path():
    macro = MacroSentiment(
        score=SentimentScore(news=2, social=1, combined=2, narrative="ok"),
        main_themes=["x"],
        risks=["y"],
        upcoming_events=["z"],
    )
    per_symbol = [
        SymbolSentiment("MES", SentimentScore(3, 1, 2, "n1")),
        SymbolSentiment("MGC", SentimentScore(-2, -3, -3, "n2")),
    ]
    res = SentimentResult(
        timestamp=datetime.now(timezone.utc),
        unavailable=False,
        unavailable_reason="",
        macro=macro,
        per_symbol=per_symbol,
        sources=["https://example.com/a", "https://example.com/b"],
    )
    assert res.unavailable is False
    assert res.macro is not None
    assert len(res.per_symbol) == 2
    assert len(res.sources) == 2


def test_sentiment_result_unavailable_factory():
    res = SentimentResult.unavailable_due_to("claude timeout 180s")
    assert res.unavailable is True
    assert "timeout" in res.unavailable_reason
    assert res.macro is None
    assert res.per_symbol == []
    assert res.sources == []


def test_sentiment_result_unavailable_factory_uses_utc_timestamp():
    res = SentimentResult.unavailable_due_to("anything")
    # Timestamp should be timezone-aware UTC
    assert res.timestamp.tzinfo is not None
