"""Unit tests for the sentiment markdown parser."""

from __future__ import annotations

import pytest

from daytrader.reports.sentiment.parser import (
    ParseError,
    parse_sentiment_response,
)


# Reusable: a well-formed AI response matching the prompt contract
SAMPLE_HAPPY = """### 🌐 Macro Sentiment
**总体 偏多 +3 / 10**（news +4, social +2）
- 主流叙事：earnings beat + Fed cuts priced in
- 风险点：Iran/Israel escalation
- 关键事件（past 24h 内）：FOMC Wed, CPI Thu, NFP Fri

### 📊 Per-Symbol
| Symbol | News | Social | Combined | 1-句叙事 |
|---|---|---|---|---|
| MES | +3 | +1 | +2 | strong trend tired but bought |
| MGC | -2 | -3 | -3 | DXY strong + risk-on |
| MNQ | +4 | +5 | +5 | AI theme persists |

> 评分：-5 (极空) → 0 (中性) → +5 (极多)
> 综合权重：news 60% / social 40%
> Sources: https://www.cnbc.com/x, https://www.bloomberg.com/y, https://www.reuters.com/z, https://www.wsj.com/a, https://www.ft.com/b
"""


def test_parse_happy_path():
    res = parse_sentiment_response(SAMPLE_HAPPY, expected_symbols=["MES", "MGC", "MNQ"])
    assert res.unavailable is False
    assert res.macro is not None
    assert res.macro.score.combined == 3
    assert res.macro.score.news == 4
    assert res.macro.score.social == 2
    assert "earnings beat" in res.macro.main_themes[0]
    assert "Iran" in res.macro.risks[0]
    assert "FOMC" in " ".join(res.macro.upcoming_events)
    assert len(res.per_symbol) == 3
    by_sym = {s.symbol: s for s in res.per_symbol}
    assert by_sym["MES"].score.combined == 2
    assert by_sym["MGC"].score.combined == -3
    assert by_sym["MNQ"].score.combined == 5
    assert len(res.sources) == 5


def test_parse_partial_symbols():
    """Only MES + MGC in response when MNQ also expected → partial result."""
    partial = SAMPLE_HAPPY.replace(
        "| MNQ | +4 | +5 | +5 | AI theme persists |\n", ""
    )
    res = parse_sentiment_response(partial, expected_symbols=["MES", "MGC", "MNQ"])
    assert res.unavailable is False  # partial ≠ unavailable
    assert len(res.per_symbol) == 2
    syms = {s.symbol for s in res.per_symbol}
    assert syms == {"MES", "MGC"}


def test_parse_missing_macro_section_raises():
    no_macro = SAMPLE_HAPPY.split("### 📊 Per-Symbol")[1]
    no_macro = "### 📊 Per-Symbol" + no_macro
    with pytest.raises(ParseError, match=r"(?i)macro"):
        parse_sentiment_response(no_macro, expected_symbols=["MES", "MGC", "MNQ"])


def test_parse_missing_per_symbol_section_raises():
    no_per = SAMPLE_HAPPY.split("### 📊 Per-Symbol")[0]
    with pytest.raises(ParseError, match=r"(?i)per-symbol"):
        parse_sentiment_response(no_per, expected_symbols=["MES", "MGC", "MNQ"])


def test_parse_score_out_of_range_clamps():
    """AI sometimes returns +7 — clamp to +5 silently (don't raise)."""
    over = SAMPLE_HAPPY.replace("| +4 | +5 | +5 |", "| +7 | +9 | +8 |")
    res = parse_sentiment_response(over, expected_symbols=["MES", "MGC", "MNQ"])
    by_sym = {s.symbol: s for s in res.per_symbol}
    assert by_sym["MNQ"].score.news == 5
    assert by_sym["MNQ"].score.social == 5
    assert by_sym["MNQ"].score.combined == 5


def test_parse_invalid_score_text_raises():
    """AI returns 'high' instead of an integer → ParseError for that row."""
    bad = SAMPLE_HAPPY.replace("| +4 | +5 | +5 |", "| high | +5 | +5 |")
    with pytest.raises(ParseError, match=r"(?i)score"):
        parse_sentiment_response(bad, expected_symbols=["MES", "MGC", "MNQ"])


def test_parse_extra_text_after_table_tolerated():
    extra = SAMPLE_HAPPY + "\n\nThis is some stray AI commentary at the end.\n"
    res = parse_sentiment_response(extra, expected_symbols=["MES", "MGC", "MNQ"])
    assert len(res.per_symbol) == 3


def test_parse_garbage_input_raises():
    with pytest.raises(ParseError):
        parse_sentiment_response("hello world this is not the format", expected_symbols=["MES"])


def test_parse_sources_extracted():
    res = parse_sentiment_response(SAMPLE_HAPPY, expected_symbols=["MES", "MGC", "MNQ"])
    assert all(s.startswith("http") for s in res.sources)


def test_parse_negative_macro_score():
    """Negative macro overall."""
    neg = SAMPLE_HAPPY.replace("**总体 偏多 +3 / 10**（news +4, social +2）",
                                "**总体 偏空 -3 / 10**（news -4, social -2）")
    res = parse_sentiment_response(neg, expected_symbols=["MES", "MGC", "MNQ"])
    assert res.macro is not None
    assert res.macro.score.combined == -3
    assert res.macro.score.news == -4


def test_parse_macro_with_full_width_punctuation():
    """Real claude output may use full-width Chinese comma + ascii or full-width parens."""
    fw = SAMPLE_HAPPY.replace(
        "**总体 偏多 +3 / 10**（news +4, social +2）",
        "**总体 偏多 +3 / 10**（news +4，social +2）",  # full-width comma
    )
    res = parse_sentiment_response(fw, expected_symbols=["MES", "MGC", "MNQ"])
    assert res.macro is not None
    assert res.macro.score.combined == 3
    assert res.macro.score.news == 4
    assert res.macro.score.social == 2


def test_parse_macro_with_half_width_parens():
    """Test claude using half-width parens instead of Chinese full-width."""
    hw = SAMPLE_HAPPY.replace(
        "**总体 偏多 +3 / 10**（news +4, social +2）",
        "**总体 偏多 +3 / 10**(news +4, social +2)",  # half-width parens
    )
    res = parse_sentiment_response(hw, expected_symbols=["MES", "MGC", "MNQ"])
    assert res.macro is not None
    assert res.macro.score.combined == 3
