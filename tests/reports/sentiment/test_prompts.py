"""Unit tests for sentiment prompt builder."""

from __future__ import annotations

from daytrader.reports.sentiment.prompts import build_sentiment_prompt


def test_build_sentiment_prompt_contains_all_symbols():
    prompt = build_sentiment_prompt(["MES", "MGC", "MNQ"])
    for sym in ["MES", "MGC", "MNQ"]:
        assert sym in prompt


def test_build_sentiment_prompt_includes_web_search_instruction():
    prompt = build_sentiment_prompt(["MES"])
    assert "web search" in prompt.lower() or "websearch" in prompt.lower()


def test_build_sentiment_prompt_includes_required_markdown_markers():
    prompt = build_sentiment_prompt(["MES", "MGC"])
    # The strict output contract — these markers MUST appear so the parser knows what to look for
    assert "Macro Sentiment" in prompt
    assert "Per-Symbol" in prompt
    assert "-5" in prompt and "+5" in prompt
    assert "Sources" in prompt


def test_build_sentiment_prompt_default_time_window():
    prompt = build_sentiment_prompt(["MES"])
    assert "24" in prompt or "past 24" in prompt or "过去 24" in prompt


def test_build_sentiment_prompt_custom_time_window():
    prompt = build_sentiment_prompt(["MES"], time_window="past 7 days")
    assert "7 days" in prompt


def test_build_sentiment_prompt_includes_news_sources():
    prompt = build_sentiment_prompt(["MES"])
    # At least 3 of these sources should be mentioned
    sources = ["Reuters", "Bloomberg", "CNBC", "WSJ", "FT", "MarketWatch", "Yahoo"]
    found = sum(1 for s in sources if s in prompt)
    assert found >= 3, f"only found {found} news sources, expected >=3"


def test_build_sentiment_prompt_includes_social_sources():
    prompt = build_sentiment_prompt(["MES"])
    # At least 2 of these social sources should be mentioned
    sources = ["X (Twitter)", "Twitter", "Reddit", "StockTwits", "wallstreetbets"]
    found = sum(1 for s in sources if s in prompt)
    assert found >= 2
