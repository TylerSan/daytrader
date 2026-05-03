"""Parse the AI's sentiment markdown response into SentimentResult."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from daytrader.reports.sentiment.dataclasses import (
    MacroSentiment,
    SentimentResult,
    SentimentScore,
    SymbolSentiment,
)


class ParseError(ValueError):
    """Raised when the AI response doesn't match the expected markdown contract."""


# --- Helpers ----------------------------------------------------------------

_INT_RE = re.compile(r"[-+]?\d+")


def _clamp(n: int, low: int = -5, high: int = 5) -> int:
    return max(low, min(high, n))


def _parse_score_token(token: str, *, where: str) -> int:
    """Parse a single integer score from a markdown table cell.

    Strips whitespace + leading '+'. Clamps to [-5, +5]. Raises on garbage."""
    s = token.strip().lstrip("+")
    if not s:
        raise ParseError(f"empty score at {where}")
    try:
        return _clamp(int(s))
    except ValueError as e:
        raise ParseError(f"invalid score {token!r} at {where}: {e}") from e


# --- Section extractors -----------------------------------------------------

def _extract_macro_block(raw: str) -> str:
    """Slice out the Macro Sentiment block (between '### 🌐 Macro Sentiment'
    and the next '###' or end-of-string)."""
    m = re.search(
        r"###\s*🌐?\s*Macro Sentiment(.*?)(?=\n###|\Z)",
        raw,
        re.DOTALL,
    )
    if not m:
        raise ParseError("macro section header not found")
    return m.group(1)


def _extract_per_symbol_block(raw: str) -> str:
    """Slice out the Per-Symbol block (between '### 📊 Per-Symbol' and
    the next '###' / blockquote / end)."""
    m = re.search(
        r"###\s*📊?\s*Per-Symbol(.*?)(?=\n###|\n>|\Z)",
        raw,
        re.DOTALL,
    )
    if not m:
        raise ParseError("per-symbol section header not found")
    return m.group(1)


def _extract_sources(raw: str) -> list[str]:
    """Extract URLs from anywhere after a '> Sources:' line, or any http(s)
    URLs in the response if 'Sources' marker missing."""
    # Prefer Sources: line
    m = re.search(r">\s*Sources?:\s*(.+?)(?=\n[^>\s]|\Z)", raw, re.DOTALL)
    body = m.group(1) if m else raw
    urls = re.findall(r"https?://[^\s,)\]\"]+", body)
    # De-dup preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        # Trim trailing punctuation
        u = u.rstrip(".,;)")
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


# --- Macro parser -----------------------------------------------------------

def _parse_macro(macro_block: str) -> MacroSentiment:
    """Parse the macro block into a MacroSentiment.

    Expected lines (order tolerant):
      **总体 [偏多/中性/偏空] [+N/0/-N] / 10**（news +N, social +N）
      - 主流叙事：...
      - 风险点：...
      - 关键事件...：item1, item2, item3
    """
    # Combined score line
    m = re.search(
        r"\*\*总体\s+\S+\s+([-+]?\d+)\s*/\s*10\*\*\s*（\s*news\s+([-+]?\d+)\s*,\s*social\s+([-+]?\d+)\s*）",
        macro_block,
    )
    if not m:
        raise ParseError("macro score line not found or malformed")
    combined = _clamp(int(m.group(1)))
    news = _clamp(int(m.group(2)))
    social = _clamp(int(m.group(3)))

    def _bullet(label: str) -> str:
        bm = re.search(rf"-\s*{label}\s*[:：]\s*(.+)", macro_block)
        return bm.group(1).strip() if bm else ""

    main_theme = _bullet("主流叙事")
    risk = _bullet("风险点")
    events_line = _bullet("关键事件.*?")  # tolerate suffix like "（24h 内）"

    events: list[str] = []
    if events_line:
        events = [e.strip() for e in re.split(r"[,，、]", events_line) if e.strip()]

    return MacroSentiment(
        score=SentimentScore(news=news, social=social, combined=combined,
                             narrative=main_theme),
        main_themes=[main_theme] if main_theme else [],
        risks=[risk] if risk else [],
        upcoming_events=events,
    )


# --- Per-symbol parser ------------------------------------------------------

_SYMBOL_ROW_RE = re.compile(
    r"^\|\s*([A-Z]{2,5})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$",
    re.MULTILINE,
)


def _parse_per_symbol(per_block: str, expected_symbols: list[str]) -> list[SymbolSentiment]:
    out: list[SymbolSentiment] = []
    for match in _SYMBOL_ROW_RE.finditer(per_block):
        sym, news_t, social_t, combined_t, narrative = match.groups()
        if sym not in expected_symbols:
            continue  # e.g. header row "Symbol | News | ..." — skip
        news = _parse_score_token(news_t, where=f"{sym}.news")
        social = _parse_score_token(social_t, where=f"{sym}.social")
        combined = _parse_score_token(combined_t, where=f"{sym}.combined")
        out.append(
            SymbolSentiment(
                symbol=sym,
                score=SentimentScore(news=news, social=social, combined=combined,
                                     narrative=narrative.strip()),
            )
        )
    return out


# --- Public entry -----------------------------------------------------------

def parse_sentiment_response(raw: str, expected_symbols: list[str]) -> SentimentResult:
    """Parse a raw claude -p sentiment response into SentimentResult.

    Raises:
        ParseError: if structural sections are missing or scores unparseable.
            Caller (collector) handles by returning unavailable=True.
    """
    if not raw or not raw.strip():
        raise ParseError("empty response")

    macro_block = _extract_macro_block(raw)
    per_block = _extract_per_symbol_block(raw)

    macro = _parse_macro(macro_block)
    per_symbol = _parse_per_symbol(per_block, expected_symbols)
    sources = _extract_sources(raw)

    return SentimentResult(
        timestamp=datetime.now(timezone.utc),
        unavailable=False,
        unavailable_reason="",
        macro=macro,
        per_symbol=per_symbol,
        sources=sources,
    )
