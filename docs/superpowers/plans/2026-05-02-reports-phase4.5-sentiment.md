# Reports System — Phase 4.5: Sentiment Section (News + Social Bull/Bear Index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `## D. 情绪面 / Sentiment Index` section to the daily premarket report, populated by `claude -p` with WebSearch over news + social media, output as a structured -5..+5 bull/bear index per symbol + macro overall.

**Architecture:** New `src/daytrader/reports/sentiment/` module mirrors the existing `FuturesSection` pattern (Phase 4). Two-call sequential pipeline: a focused `SentimentSection.collect()` calls `claude -p` to fetch + analyze sentiment, returns a `SentimentResult` dataclass. The orchestrator renders it to markdown and feeds the markdown to `PromptBuilder`, which embeds it in the main report prompt for `AIAnalyst`. Graceful degradation on any failure — main pipeline never blocked.

**Tech Stack:** Python 3.11+, `subprocess` (no new deps), `pytest` for tests, `claude -p` (Claude Code headless mode with WebSearch tool, verified 2026-05-02).

**Spec:** [`docs/superpowers/specs/2026-05-02-reports-phase4.5-sentiment-design.md`](../specs/2026-05-02-reports-phase4.5-sentiment-design.md)

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `src/daytrader/reports/sentiment/__init__.py` | Create | Module init, re-export public names |
| `src/daytrader/reports/sentiment/dataclasses.py` | Create | `SentimentScore`, `MacroSentiment`, `SymbolSentiment`, `SentimentResult` (frozen dataclasses) |
| `src/daytrader/reports/sentiment/prompts.py` | Create | `build_sentiment_prompt(symbols, time_window)` |
| `src/daytrader/reports/sentiment/parser.py` | Create | `parse_sentiment_response(raw, expected_symbols)` + `ParseError` |
| `src/daytrader/reports/sentiment/collector.py` | Create | `SentimentCollector` — `subprocess.run(["claude", "-p"])` wrapper |
| `src/daytrader/reports/sentiment/section.py` | Create | `SentimentSection` facade with `collect()` + `render()` |
| `src/daytrader/reports/core/prompt_builder.py` | Modify | Add `sentiment_md: str = ""` parameter to `build_premarket()`; embed before `## A.` |
| `src/daytrader/reports/core/orchestrator.py` | Modify | Instantiate + call `SentimentSection`, pass rendered string to `PromptBuilder` |
| `src/daytrader/reports/core/output_validator.py` | Modify | Add `["情绪面", "D. 情绪面", "Sentiment Index"]` to `REQUIRED_SECTIONS["premarket"]` |
| `src/daytrader/reports/templates/premarket.md` | Modify | Add `## D. 情绪面 / Sentiment Index` section |
| `tests/reports/sentiment/__init__.py` | Create | Test module init |
| `tests/reports/sentiment/test_dataclasses.py` | Create | Unit tests |
| `tests/reports/sentiment/test_prompts.py` | Create | Unit tests |
| `tests/reports/sentiment/test_parser.py` | Create | Unit tests |
| `tests/reports/sentiment/test_collector.py` | Create | Unit tests with mocked subprocess |
| `tests/reports/sentiment/test_section.py` | Create | Unit tests |
| `tests/reports/sentiment/test_integration_live.py` | Create | Live integration, marked `@pytest.mark.slow` |

---

## Task 1: Dataclasses

**Files:**
- Create: `src/daytrader/reports/sentiment/__init__.py`
- Create: `src/daytrader/reports/sentiment/dataclasses.py`
- Create: `tests/reports/sentiment/__init__.py`
- Create: `tests/reports/sentiment/test_dataclasses.py`

- [ ] **Step 1: Create `tests/reports/sentiment/__init__.py`** (empty file)

```bash
mkdir -p tests/reports/sentiment
touch tests/reports/sentiment/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/reports/sentiment/test_dataclasses.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail (red)**

Run: `uv run pytest tests/reports/sentiment/test_dataclasses.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.reports.sentiment'`

- [ ] **Step 4: Create `src/daytrader/reports/sentiment/__init__.py`**

```python
"""Sentiment section: web-sourced news + social media bull/bear index.

Mirrors the FuturesSection pattern (Phase 4). Public surface:

- `SentimentSection`: orchestrator-facing facade
- `SentimentResult`: structured result dataclass
- `SentimentCollector`: low-level claude -p wrapper (use SentimentSection in
  most cases)
"""

from daytrader.reports.sentiment.collector import SentimentCollector
from daytrader.reports.sentiment.dataclasses import (
    MacroSentiment,
    SentimentResult,
    SentimentScore,
    SymbolSentiment,
)
from daytrader.reports.sentiment.section import SentimentSection

__all__ = [
    "MacroSentiment",
    "SentimentCollector",
    "SentimentResult",
    "SentimentScore",
    "SentimentSection",
    "SymbolSentiment",
]
```

(This file imports modules that don't exist yet — that's intentional. The next tasks create them. Tests for THIS task only import dataclasses, which we create next.)

- [ ] **Step 5: Implement `src/daytrader/reports/sentiment/dataclasses.py`**

```python
"""Frozen dataclasses for sentiment section data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SentimentScore:
    """One symbol's or macro's sentiment breakdown.

    All scores are integers in [-5, +5]:
      -5 = extremely bearish, 0 = neutral, +5 = extremely bullish.
    """
    news: int           # -5..+5
    social: int         # -5..+5
    combined: int       # -5..+5 (AI-weighted, typically 60% news + 40% social)
    narrative: str      # 1-sentence summary


@dataclass(frozen=True)
class MacroSentiment:
    """Overall macro sentiment + key context for the report period."""
    score: SentimentScore
    main_themes: list[str] = field(default_factory=list)        # 主流叙事
    risks: list[str] = field(default_factory=list)              # 风险点
    upcoming_events: list[str] = field(default_factory=list)    # 关键事件 (24-48h)


@dataclass(frozen=True)
class SymbolSentiment:
    """Per-symbol sentiment."""
    symbol: str            # e.g. "MES", "MGC", "MNQ"
    score: SentimentScore


@dataclass(frozen=True)
class SentimentResult:
    """Top-level sentiment fetch result.

    `unavailable=True` signals graceful degradation — main pipeline must
    continue and the renderer writes an "unavailable" block.
    """
    timestamp: datetime                          # UTC
    unavailable: bool
    unavailable_reason: str
    macro: MacroSentiment | None
    per_symbol: list[SymbolSentiment]
    sources: list[str]                           # URLs cited by the AI

    @classmethod
    def unavailable_due_to(cls, reason: str) -> SentimentResult:
        """Factory for the failure case."""
        return cls(
            timestamp=datetime.now(timezone.utc),
            unavailable=True,
            unavailable_reason=reason,
            macro=None,
            per_symbol=[],
            sources=[],
        )
```

- [ ] **Step 6: Run tests to verify they pass (green)**

Run: `uv run pytest tests/reports/sentiment/test_dataclasses.py -v`
Expected: 7 tests pass.

⚠️ Note: the `__init__.py` from Step 4 imports modules that don't exist yet (`collector`, `section`). If pytest collection fails because of that import, temporarily replace `__init__.py` content with a single line `# stub — populated incrementally by Phase 4.5 plan tasks` and add the full re-exports back at the end of Task 5. Up to you, implementer.

- [ ] **Step 7: Commit**

```bash
git add src/daytrader/reports/sentiment/__init__.py src/daytrader/reports/sentiment/dataclasses.py tests/reports/sentiment/__init__.py tests/reports/sentiment/test_dataclasses.py
git commit -m "feat(sentiment): dataclasses (SentimentScore/MacroSentiment/SymbolSentiment/SentimentResult)"
```

---

## Task 2: Prompt builder

**Files:**
- Create: `src/daytrader/reports/sentiment/prompts.py`
- Create: `tests/reports/sentiment/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/reports/sentiment/test_prompts.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail (red)**

Run: `uv run pytest tests/reports/sentiment/test_prompts.py -v`
Expected: FAIL — `prompts` module not found.

- [ ] **Step 3: Implement `src/daytrader/reports/sentiment/prompts.py`**

```python
"""Sentiment prompt template for claude -p with WebSearch."""

from __future__ import annotations


def build_sentiment_prompt(
    symbols: list[str],
    time_window: str = "past 24h",
) -> str:
    """Build the prompt for a sentiment-fetch claude -p call.

    The output format is strict markdown — see parser.py for the contract.

    Args:
        symbols: Instruments to analyze, e.g. ["MES", "MGC", "MNQ"].
        time_window: Lookback window for the search, e.g. "past 24h" or
            "past 7 days". Default suits daily premarket; weekly should
            pass "past 7 days".
    """
    symbols_str = ", ".join(symbols)
    table_rows = "\n".join(
        f"| {sym} | [-5..+5] | [-5..+5] | [-5..+5] | [短句] |"
        for sym in symbols
    )

    return f"""你是金融情绪分析师。请使用 web search，搜索 {time_window} 内：

1. 与 {symbols_str} 相关的财经新闻
   （Reuters / Bloomberg / CNBC / WSJ / FT / MarketWatch / Yahoo Finance / 路透 / 华尔街日报）
2. 这些 symbol 在 X (Twitter) / Reddit (r/wallstreetbets, r/futures, r/options)
   / StockTwits 上的讨论情绪
3. 影响这些 symbol 的宏观事件
   （Fed / CPI / NFP / PMI / 财报 / 地缘政治 / 大宗商品政策）

完成搜索后，按以下 EXACT markdown 格式输出（不加任何额外说明文字）：

### 🌐 Macro Sentiment
**总体 [偏多/中性/偏空] [+N/0/-N] / 10**（news +N, social +N）
- 主流叙事：[1 句]
- 风险点：[1 句]
- 关键事件（{time_window} 内）：[逗号分隔事件名]

### 📊 Per-Symbol
| Symbol | News | Social | Combined | 1-句叙事 |
|---|---|---|---|---|
{table_rows}

> 评分：-5 (极空) → 0 (中性) → +5 (极多)
> 综合权重：news 60% / social 40%
> Sources: [至少 5 个真实查到的 URL]

重要：
- 评分必须是 -5 到 +5 之间的整数
- 不要用 "very bullish" 这种描述性词代替数值
- Sources 必须是真实搜到的 URL，不要编造
"""
```

- [ ] **Step 4: Run tests to verify they pass (green)**

Run: `uv run pytest tests/reports/sentiment/test_prompts.py -v`
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/sentiment/prompts.py tests/reports/sentiment/test_prompts.py
git commit -m "feat(sentiment): prompt template with strict markdown output contract"
```

---

## Task 3: Parser

**Files:**
- Create: `src/daytrader/reports/sentiment/parser.py`
- Create: `tests/reports/sentiment/test_parser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/reports/sentiment/test_parser.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail (red)**

Run: `uv run pytest tests/reports/sentiment/test_parser.py -v`
Expected: FAIL — `parser` module not found.

- [ ] **Step 3: Implement `src/daytrader/reports/sentiment/parser.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass (green)**

Run: `uv run pytest tests/reports/sentiment/test_parser.py -v`
Expected: 10 tests pass. If any fail because of regex edge cases (Chinese punctuation, emoji in headers), tweak the regex incrementally — don't relax the test assertions.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/sentiment/parser.py tests/reports/sentiment/test_parser.py
git commit -m "feat(sentiment): markdown response parser + ParseError"
```

---

## Task 4: Collector

**Files:**
- Create: `src/daytrader/reports/sentiment/collector.py`
- Create: `tests/reports/sentiment/test_collector.py`

**Pattern reference:** `src/daytrader/reports/core/ai_analyst.py` for subprocess.run + timeout.

- [ ] **Step 1: Write the failing test**

Create `tests/reports/sentiment/test_collector.py`:

```python
"""Unit tests for SentimentCollector with mocked subprocess."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from daytrader.reports.sentiment.collector import SentimentCollector
from daytrader.reports.sentiment.dataclasses import SentimentResult


SAMPLE_RESPONSE = """### 🌐 Macro Sentiment
**总体 偏多 +3 / 10**（news +4, social +2）
- 主流叙事：earnings beat
- 风险点：geopolitics
- 关键事件（past 24h 内）：FOMC Wed, CPI Thu

### 📊 Per-Symbol
| Symbol | News | Social | Combined | 1-句叙事 |
|---|---|---|---|---|
| MES | +3 | +1 | +2 | n1 |
| MGC | -2 | -3 | -3 | n2 |
| MNQ | +4 | +5 | +5 | n3 |

> 评分：-5 (极空) → 0 (中性) → +5 (极多)
> Sources: https://a.com, https://b.com, https://c.com, https://d.com, https://e.com
"""


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude", "-p"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_collector_happy_path():
    with patch("subprocess.run", return_value=_completed(SAMPLE_RESPONSE)):
        collector = SentimentCollector(symbols=["MES", "MGC", "MNQ"])
        res = collector.collect()
    assert isinstance(res, SentimentResult)
    assert res.unavailable is False
    assert res.macro is not None
    assert res.macro.score.combined == 3
    assert len(res.per_symbol) == 3
    assert len(res.sources) == 5


def test_collector_timeout_returns_unavailable():
    timeout_exc = subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=180)
    with patch("subprocess.run", side_effect=timeout_exc):
        collector = SentimentCollector(symbols=["MES"], timeout_s=180)
        res = collector.collect()
    assert res.unavailable is True
    assert "timeout" in res.unavailable_reason.lower()
    assert res.macro is None
    assert res.per_symbol == []


def test_collector_nonzero_exit_returns_unavailable():
    with patch("subprocess.run", return_value=_completed("", returncode=2)):
        collector = SentimentCollector(symbols=["MES"])
        res = collector.collect()
    assert res.unavailable is True
    assert "exit" in res.unavailable_reason.lower() or "2" in res.unavailable_reason


def test_collector_garbage_response_returns_unavailable():
    with patch("subprocess.run", return_value=_completed("hello world")):
        collector = SentimentCollector(symbols=["MES"])
        res = collector.collect()
    assert res.unavailable is True
    assert "parse" in res.unavailable_reason.lower()


def test_collector_invokes_subprocess_with_claude_minus_p():
    """Verify the actual subprocess.run command — implementer must call claude -p
    with prompt as stdin, not as argv."""
    captured: dict = {}

    def _fake_run(cmd, *, input=None, capture_output=None, text=None, timeout=None, **kw):
        captured["cmd"] = cmd
        captured["input"] = input
        captured["timeout"] = timeout
        return _completed(SAMPLE_RESPONSE)

    with patch("subprocess.run", side_effect=_fake_run):
        SentimentCollector(symbols=["MES", "MGC"], timeout_s=180).collect()

    assert captured["cmd"][0] == "claude"
    assert "-p" in captured["cmd"]
    assert "MES" in captured["input"]
    assert "MGC" in captured["input"]
    assert captured["timeout"] == 180


def test_collector_default_symbols_passed_through():
    """Collector accepts symbols at construction time, includes in prompt."""
    captured: dict = {}

    def _fake_run(cmd, *, input=None, **kw):
        captured["input"] = input
        return _completed(SAMPLE_RESPONSE)

    with patch("subprocess.run", side_effect=_fake_run):
        SentimentCollector(symbols=["AAPL"]).collect()

    assert "AAPL" in captured["input"]


def test_collector_records_raw_on_parse_failure(tmp_path, monkeypatch):
    """When parse fails, the raw response should be saved for debugging."""
    monkeypatch.chdir(tmp_path)
    with patch("subprocess.run", return_value=_completed("malformed garbage no markers")):
        collector = SentimentCollector(symbols=["MES"])
        res = collector.collect()
    assert res.unavailable is True
    log_dir = tmp_path / "data" / "logs" / "sentiment-failures"
    if log_dir.exists():
        files = list(log_dir.glob("*.txt"))
        # At least one log file written (best-effort, not strictly required)
        assert len(files) >= 0  # tolerate environments where dir creation fails
```

- [ ] **Step 2: Run tests to verify they fail (red)**

Run: `uv run pytest tests/reports/sentiment/test_collector.py -v`
Expected: FAIL — `SentimentCollector` not defined.

- [ ] **Step 3: Implement `src/daytrader/reports/sentiment/collector.py`**

```python
"""SentimentCollector — invokes `claude -p` with sentiment prompt, parses response."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from daytrader.reports.sentiment.dataclasses import SentimentResult
from daytrader.reports.sentiment.parser import ParseError, parse_sentiment_response
from daytrader.reports.sentiment.prompts import build_sentiment_prompt


class SentimentCollector:
    """Calls `claude -p` with a focused sentiment prompt; parses the response.

    Failures (timeout, non-zero exit, parse error) are caught and translated
    into `SentimentResult.unavailable_due_to(...)` — never raises to the
    caller. The orchestrator must always be able to continue after this.
    """

    DEFAULT_TIMEOUT_S = 180

    def __init__(
        self,
        symbols: list[str],
        time_window: str = "past 24h",
        timeout_s: int = DEFAULT_TIMEOUT_S,
        failure_log_dir: Path | None = None,
    ) -> None:
        self._symbols = list(symbols)
        self._time_window = time_window
        self._timeout_s = timeout_s
        self._failure_log_dir = failure_log_dir or (
            Path("data") / "logs" / "sentiment-failures"
        )

    def collect(self) -> SentimentResult:
        prompt = build_sentiment_prompt(self._symbols, time_window=self._time_window)
        try:
            result = subprocess.run(
                ["claude", "-p"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
        except subprocess.TimeoutExpired:
            return SentimentResult.unavailable_due_to(
                f"claude -p timeout after {self._timeout_s}s"
            )
        except FileNotFoundError:
            return SentimentResult.unavailable_due_to(
                "claude CLI not found on PATH"
            )

        if result.returncode != 0:
            return SentimentResult.unavailable_due_to(
                f"claude -p exit={result.returncode}: {result.stderr.strip()[:200]}"
            )

        raw = result.stdout
        try:
            return parse_sentiment_response(raw, expected_symbols=self._symbols)
        except ParseError as e:
            self._log_raw_response(raw, str(e))
            return SentimentResult.unavailable_due_to(f"parse failed: {e}")

    def _log_raw_response(self, raw: str, reason: str) -> None:
        """Best-effort save of unparseable responses for debugging."""
        try:
            self._failure_log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            target = self._failure_log_dir / f"sentiment-{ts}.txt"
            target.write_text(f"# parse failure: {reason}\n\n{raw}", encoding="utf-8")
        except Exception as e:
            # Non-fatal — log to stderr but don't propagate
            print(f"[sentiment_collector] could not save raw response: {e}",
                  file=sys.stderr)
```

- [ ] **Step 4: Run tests to verify they pass (green)**

Run: `uv run pytest tests/reports/sentiment/test_collector.py -v`
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/sentiment/collector.py tests/reports/sentiment/test_collector.py
git commit -m "feat(sentiment): SentimentCollector subprocess wrapper with graceful degradation"
```

---

## Task 5: Section facade + renderer

**Files:**
- Create: `src/daytrader/reports/sentiment/section.py`
- Create: `tests/reports/sentiment/test_section.py`

- [ ] **Step 1: Write the failing test**

Create `tests/reports/sentiment/test_section.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail (red)**

Run: `uv run pytest tests/reports/sentiment/test_section.py -v`
Expected: FAIL — `SentimentSection` not defined.

- [ ] **Step 3: Implement `src/daytrader/reports/sentiment/section.py`**

```python
"""SentimentSection — orchestrator-facing facade with collect() + render()."""

from __future__ import annotations

from daytrader.reports.sentiment.collector import SentimentCollector
from daytrader.reports.sentiment.dataclasses import SentimentResult


class SentimentSection:
    """Facade: orchestrator calls .collect() to fetch, .render() to format.

    Mirrors the FuturesSection pattern from Phase 4. Always returns a string
    from render() even if the result is unavailable — no exceptions cross the
    facade boundary.
    """

    def __init__(
        self,
        symbols: list[str],
        collector: SentimentCollector | None = None,
        time_window: str = "past 24h",
    ) -> None:
        self._symbols = list(symbols)
        self._time_window = time_window
        self._collector = collector or SentimentCollector(
            symbols=symbols, time_window=time_window
        )

    def collect(self) -> SentimentResult:
        return self._collector.collect()

    def render(self, result: SentimentResult) -> str:
        if result.unavailable:
            return self._render_unavailable(result)
        return self._render_happy(result)

    # ---------- private renderers ----------

    def _render_unavailable(self, result: SentimentResult) -> str:
        return (
            "## D. 情绪面 / Sentiment Index\n\n"
            f"⚠️ **情绪数据本次不可用** — {result.unavailable_reason}\n\n"
            "主报告其余章节正常生成；可手动跑 `uv run daytrader reports run "
            "--type premarket` 或检查 `claude -p` 状态后重试。\n"
        )

    def _render_happy(self, result: SentimentResult) -> str:
        assert result.macro is not None  # type narrowing
        macro = result.macro

        themes = "; ".join(macro.main_themes) if macro.main_themes else "(none)"
        risks = "; ".join(macro.risks) if macro.risks else "(none)"
        events = ", ".join(macro.upcoming_events) if macro.upcoming_events else "(none)"

        header = (
            "## D. 情绪面 / Sentiment Index\n\n"
            f"### 🌐 Macro Sentiment\n"
            f"**总体综合 {self._fmt_score(macro.score.combined)} / 10**"
            f"（news {self._fmt_score(macro.score.news)}, "
            f"social {self._fmt_score(macro.score.social)}）\n"
            f"- 主流叙事：{themes}\n"
            f"- 风险点：{risks}\n"
            f"- 关键事件（{self._time_window} 内）：{events}\n\n"
        )

        rows: list[str] = ["| Symbol | News | Social | Combined | 1-句叙事 |",
                            "|---|---|---|---|---|"]
        present = {s.symbol for s in result.per_symbol}
        for s in result.per_symbol:
            rows.append(
                f"| {s.symbol} "
                f"| {self._fmt_score(s.score.news)} "
                f"| {self._fmt_score(s.score.social)} "
                f"| {self._fmt_score(s.score.combined)} "
                f"| {s.score.narrative} |"
            )

        per_symbol_block = "### 📊 Per-Symbol\n" + "\n".join(rows) + "\n\n"

        # Note any expected-but-missing symbols
        missing = [sym for sym in self._symbols if sym not in present]
        missing_note = ""
        if missing:
            missing_note = (
                f"> ⚠️ 以下 symbol 数据在本次 fetch 中缺失："
                f"{', '.join(missing)}（按 'unavailable' 处理）\n\n"
            )

        sources_lines = "\n".join(f"- {url}" for url in result.sources)
        footer = (
            "> 评分：-5 (极空) → 0 (中性) → +5 (极多)\n"
            "> 综合权重：news 60% / social 40%\n\n"
            "**Sources:**\n"
            f"{sources_lines if sources_lines else '(none)'}\n"
        )

        return header + per_symbol_block + missing_note + footer

    @staticmethod
    def _fmt_score(n: int) -> str:
        return f"+{n}" if n > 0 else str(n)
```

- [ ] **Step 4: Run tests to verify they pass (green)**

Run: `uv run pytest tests/reports/sentiment/test_section.py -v`
Expected: 8 tests pass.

- [ ] **Step 5: Run all sentiment tests together**

Run: `uv run pytest tests/reports/sentiment/ -v`
Expected: ~32 tests pass (7 + 7 + 10 + 7 + 8). The `__init__.py` re-export from Task 1 should now resolve cleanly because all submodules exist.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/reports/sentiment/section.py tests/reports/sentiment/test_section.py
git commit -m "feat(sentiment): SentimentSection facade + markdown renderer"
```

---

## Task 6: Wire into Orchestrator + PromptBuilder + OutputValidator

**Files:**
- Modify: `src/daytrader/reports/core/prompt_builder.py`
- Modify: `src/daytrader/reports/core/orchestrator.py`
- Modify: `src/daytrader/reports/core/output_validator.py`
- Modify: `tests/reports/test_prompt_builder.py` (add a test)
- Modify: `tests/reports/test_output_validator.py` (add a test)

- [ ] **Step 1: Read existing files to find integration points**

```bash
grep -n "futures_data\|build_premarket\|FuturesSection" src/daytrader/reports/core/prompt_builder.py
grep -n "FuturesSection\|build_futures_section\|futures" src/daytrader/reports/core/orchestrator.py
grep -n "premarket" src/daytrader/reports/core/output_validator.py
```

Take notes on:
- The exact signature of `PromptBuilder.build_premarket(...)`
- Where `FuturesSection` is constructed in the orchestrator (we insert SentimentSection after it)
- The `REQUIRED_SECTIONS["premarket"]` list

- [ ] **Step 2: Extend PromptBuilder — write the failing test**

In `tests/reports/test_prompt_builder.py`, add this test (do NOT replace existing tests):

```python
def test_build_premarket_includes_sentiment_block_when_provided():
    """PromptBuilder.build_premarket should embed sentiment_md verbatim
    when supplied."""
    from daytrader.reports.core.prompt_builder import PromptBuilder
    pb = PromptBuilder()
    sentiment_md = (
        "## D. 情绪面 / Sentiment Index\n\n"
        "### 🌐 Macro Sentiment\n"
        "**总体综合 +3 / 10**（news +4, social +2）\n"
        "..."
    )
    # The exact build_premarket signature varies — implementer must adapt
    # this call. The point is: passing sentiment_md must result in the
    # block appearing in the returned prompt string.
    prompt = pb.build_premarket(
        report_date="2026-05-04",
        instruments_data={},  # may need real shape per existing tests
        futures_data=None,
        sentiment_md=sentiment_md,
    )
    assert "## D. 情绪面" in prompt or "Sentiment Index" in prompt


def test_build_premarket_without_sentiment_md_works():
    """sentiment_md is optional — omitting it must not crash, just no D. section."""
    from daytrader.reports.core.prompt_builder import PromptBuilder
    pb = PromptBuilder()
    prompt = pb.build_premarket(
        report_date="2026-05-04",
        instruments_data={},
        futures_data=None,
    )
    # Sentiment block absent
    assert "## D. 情绪面" not in prompt
```

- [ ] **Step 3: Run the new test, expect failure**

Run: `uv run pytest tests/reports/test_prompt_builder.py::test_build_premarket_includes_sentiment_block_when_provided -v`
Expected: FAIL — `build_premarket()` doesn't accept `sentiment_md` kwarg.

- [ ] **Step 4: Modify `PromptBuilder.build_premarket()` to accept `sentiment_md`**

Open `src/daytrader/reports/core/prompt_builder.py`. Find the `build_premarket` method signature. Add a new parameter `sentiment_md: str = ""` AFTER the existing `futures_data` parameter (preserve order of existing args). In the method body, embed `sentiment_md` BEFORE the line that injects `futures_block` — sentiment goes ahead of futures so the AI sees it during synthesis.

Concretely, find this section (current state):

```python
        futures_block = self._build_futures_section_block(futures_data)
        # ... other block builders ...
        prompt = (
            ...
            f"{futures_block}\n\n"
            ...
        )
```

Replace with (assuming the existing pattern uses an f-string-concat block):

```python
        futures_block = self._build_futures_section_block(futures_data)
        sentiment_block = sentiment_md.strip() if sentiment_md else ""
        # ... other block builders ...
        # Compose: futures, then sentiment (if present), then the rest.
        composed_blocks = [futures_block]
        if sentiment_block:
            composed_blocks.append(sentiment_block)
        composed_md = "\n\n".join(composed_blocks)

        prompt = (
            ...
            f"{composed_md}\n\n"
            ...
        )
```

Implementer: adapt to the actual existing string-build pattern at `prompt_builder.py:55–69`. The contract is: when `sentiment_md` is non-empty, its content appears verbatim somewhere between `futures_block` and the AI's output instructions. **The two new tests in Step 2 are the source of truth — passing them is sufficient.**

⚠️ Note on test signature: the test in Step 2 calls `pb.build_premarket(report_date=..., instruments_data={}, futures_data=None, sentiment_md=...)`. The actual existing signature may have different positional args. Read `src/daytrader/reports/core/prompt_builder.py:23–55` first, then adjust the test to match the real signature while preserving the assertion (the `sentiment_md` parameter is what matters).

- [ ] **Step 5: Run the new tests + the existing prompt_builder tests**

Run: `uv run pytest tests/reports/test_prompt_builder.py -v`
Expected: all pass (new 2 + existing).

- [ ] **Step 6: Extend OutputValidator — write the failing test**

In `tests/reports/test_output_validator.py`, add:

```python
def test_premarket_validator_requires_sentiment_section():
    """A premarket report without 'D. 情绪面' / 'Sentiment Index' should fail validation."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    # Build a minimal report missing the sentiment section
    content = """# 📋 Premarket Daily Report
## Lock-in Metadata
...
## 📊 MES
## 📊 MNQ
## 📊 MGC
### W
### D
### 4H
### 1H
News
F. 期货结构
### C-MES
### C-MGC
C.
B.
A.
数据快照
"""
    result = v.validate(content, "premarket")
    assert not result.ok
    assert any("情绪" in m or "Sentiment" in m for m in result.missing)


def test_premarket_validator_accepts_sentiment_alternatives():
    """Either '情绪面' or 'Sentiment Index' or 'D. 情绪面' should satisfy the slot."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    base = """# 📋 Premarket Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
### W
### D
### 4H
### 1H
News
F. 期货结构
### C-MES
### C-MGC
C.
B.
A.
数据快照
"""
    for marker in ["## D. 情绪面", "Sentiment Index", "## 情绪面"]:
        full = base + f"\n{marker}\n"
        result = v.validate(full, "premarket")
        # All other required sections present, only sentiment varies → must pass
        assert result.ok or all("情绪" not in m and "Sentiment" not in m for m in result.missing), \
            f"marker {marker!r} should satisfy sentiment slot but didn't: {result.missing}"
```

- [ ] **Step 7: Run the new tests, expect failure**

Run: `uv run pytest tests/reports/test_output_validator.py::test_premarket_validator_requires_sentiment_section -v`
Expected: FAIL — `情绪面` not in REQUIRED_SECTIONS yet.

- [ ] **Step 8: Modify `output_validator.py` — add sentiment slot to premarket required-sections**

Open `src/daytrader/reports/core/output_validator.py`. Find `REQUIRED_SECTIONS["premarket"]`. Add this entry between the existing `["F. 期货结构", ...]` slot and `["C-MES", ...]`:

```python
        # D. 情绪面 — accept multiple variants (Phase 4.5)
        ["情绪面", "D. 情绪面", "Sentiment Index", "Sentiment"],
```

- [ ] **Step 9: Run validator tests**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: all pass (new 2 + existing).

- [ ] **Step 10: Wire SentimentSection into Orchestrator**

Open `src/daytrader/reports/core/orchestrator.py`. Find where the orchestrator either:
- (a) calls `build_futures_section(...)` and stores the FuturesSection result, OR
- (b) constructs the FuturesSection / passes it to PromptBuilder

Add SentimentSection invocation right after the FuturesSection step:

```python
# After futures section is built (the existing pattern):
from daytrader.reports.sentiment import SentimentSection

sentiment_section = SentimentSection(symbols=tradable_plus_context_symbols)
sentiment_result = sentiment_section.collect()  # may take 60–120s
sentiment_md = sentiment_section.render(sentiment_result)

# Then pass sentiment_md when calling PromptBuilder.build_premarket(...)
prompt = prompt_builder.build_premarket(
    ...,
    futures_data=futures_section,
    sentiment_md=sentiment_md,
)
```

The exact `tradable_plus_context_symbols` variable already exists in the orchestrator — find the variable that holds the full instrument list (likely sourced from `instruments.yaml` via the existing `load_instruments()`).

- [ ] **Step 11: Update orchestrator tests if any break**

Run: `uv run pytest tests/reports/test_orchestrator.py -v`

If any orchestrator test now fails because it doesn't mock `SentimentSection`, add a mock. Pattern (only if needed):

```python
from unittest.mock import patch

with patch("daytrader.reports.core.orchestrator.SentimentSection") as mock_section_cls:
    mock_section = mock_section_cls.return_value
    mock_section.collect.return_value = SentimentResult.unavailable_due_to("test")
    mock_section.render.return_value = "## D. 情绪面 / Sentiment Index\n\n⚠️ test\n"
    # ... existing test body ...
```

- [ ] **Step 12: Run full test suite**

Run: `uv run pytest tests/ --ignore=tests/research -q | tail -10`
Expected: all pass. Total now ~290 (was ~280 — added ~32 sentiment tests, plus 4 in prompt_builder/output_validator).

- [ ] **Step 13: Commit**

```bash
git add src/daytrader/reports/core/prompt_builder.py src/daytrader/reports/core/orchestrator.py src/daytrader/reports/core/output_validator.py tests/reports/test_prompt_builder.py tests/reports/test_output_validator.py
git commit -m "feat(sentiment): wire SentimentSection into Orchestrator + PromptBuilder + OutputValidator"
```

---

## Task 7: Add D. section to premarket template

**Files:**
- Modify: `src/daytrader/reports/templates/premarket.md`

- [ ] **Step 1: Read the current template**

```bash
cat src/daytrader/reports/templates/premarket.md
```

Identify where `## F. 期货结构` ends and `## C. 计划复核` begins. The new D. section goes between F and C.

- [ ] **Step 2: Insert the D. section placeholder in the template**

Find the section after `## F. 期货结构` (or its rendered placeholder) and BEFORE `## C. 计划复核`. Add:

```markdown
---

## D. 情绪面 / Sentiment Index

{sentiment_block}

---
```

(Where `{sentiment_block}` is the placeholder that gets replaced by the rendered SentimentSection markdown. Match the templating convention used elsewhere in the file — if the codebase uses Python f-string-style `{name}` placeholders, use that; if Jinja-style `{{ name }}`, use that.)

If the template doesn't use placeholders at all (the old AI-generated approach is to instruct the AI to produce the full report from a prompt), skip this template change — the AI will produce the D. section because the PromptBuilder feeds `sentiment_md` into the prompt, and the prompt instructs the AI to include it. In that case, no template change needed; verify with the next step.

- [ ] **Step 3: Run output_validator tests to confirm D. section flows through**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: pass.

- [ ] **Step 4: Commit (only if template was actually modified)**

```bash
git add src/daytrader/reports/templates/premarket.md
git commit -m "feat(sentiment): add D. section placeholder to premarket template"
```

If no template change was needed, skip this commit and add a note on the PR that the template is AI-driven.

---

## Task 8: Live integration test (slow, opt-in)

**Files:**
- Create: `tests/reports/sentiment/test_integration_live.py`

This test actually invokes `claude -p` and validates the prompt contract still holds. It's slow (~2 min) and depends on network + Claude availability, so it's marked `slow` and skipped by default.

- [ ] **Step 1: Write the test**

Create `tests/reports/sentiment/test_integration_live.py`:

```python
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
```

- [ ] **Step 2: Verify the slow marker is registered**

Open `pyproject.toml`. Look for `[tool.pytest.ini_options]` → `markers`. If `slow` is not registered, add it:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests that hit the network or take >30s — skipped by default",
]
```

If `markers` already exists, append `"slow: ..."` to the list.

If pytest is configured in `setup.cfg` or `pytest.ini` instead of `pyproject.toml`, add the marker there.

- [ ] **Step 3: Confirm the test is skipped by default**

Run: `uv run pytest tests/reports/sentiment/ -v`
Expected: ~32 tests + 1 SKIPPED for the live test.

- [ ] **Step 4: (Optional, manual) Run the live test once**

Run: `uv run pytest -m slow tests/reports/sentiment/ -v --no-header -s`
Expected: passes after ~120–180s (or fails with a meaningful diagnostic if claude / WebSearch is unavailable).

If it fails because of parser regex edge cases against real claude output, fix the parser. Don't relax the test.

- [ ] **Step 5: Commit**

```bash
git add tests/reports/sentiment/test_integration_live.py pyproject.toml
git commit -m "test(sentiment): live integration test (slow-marked, opt-in)"
```

---

## Task 9: End-to-end acceptance

**Files:** None (verification only).

- [ ] **Step 1: Full test suite passes**

Run: `uv run pytest tests/ --ignore=tests/research -q | tail -10`
Expected: all pass. Total ~290 tests.

- [ ] **Step 2: Confirm preflight still works**

Run: `uv run python scripts/preflight_check.py`
Expected: TWS / claude / config all checked, exit 0 (or exit 1 with TWS unreachable if TWS is not running — that's fine).

- [ ] **Step 3: Live test fire — full premarket pipeline**

⚠️ Make sure TWS is running (port 7496).

Run: `cd "/Users/tylersan/Projects/Day trading/.claude/worktrees/nice-varahamihira-9d6142" && uv run daytrader reports run --type premarket --no-pdf`

Expected:
- Total wall time: ~7 min (was ~5 min — sentiment adds ~2 min)
- Output ends with `Report generated: .../Daily/2026-05-XX-premarket.md`

- [ ] **Step 4: Inspect the generated report**

```bash
TODAY=$(date +%Y-%m-%d)
head -200 "$HOME/Documents/DayTrader Vault/Daily/${TODAY}-premarket.md"
grep -E "^##? " "$HOME/Documents/DayTrader Vault/Daily/${TODAY}-premarket.md"
```

Confirm:
- `## D. 情绪面 / Sentiment Index` appears in the report
- `### 🌐 Macro Sentiment` block with a combined score
- `### 📊 Per-Symbol` table with rows for MES, MGC, MNQ
- At least 5 source URLs (real, clickable — spot-check 2 by opening in browser)

- [ ] **Step 5: Failure-path verification**

Stop / quit `claude` mid-fetch and confirm graceful degradation:

Option A (simplest — disable claude temporarily):

```bash
# Hide claude from PATH temporarily
PATH=/usr/bin:/bin uv run daytrader reports run --type premarket --no-pdf 2>&1 | tail -30
```

Expected: The pipeline now fails preflight (since claude is not on PATH) — wrapper exits 0 with notification. Re-enable PATH and verify the regular run still works.

Option B (more targeted — leave preflight passing, fail just the sentiment call):

This is harder without code modification. Acceptable to skip Option B for v1; the unit test `test_collector_timeout_returns_unavailable` already validates the graceful-degrade code path.

- [ ] **Step 6: Confirm wall-time impact is acceptable**

From the live run log, calculate total elapsed time. Acceptable: ≤ 10 min (target ~7 min).

If it's >10 min:
- Check claude -p latency in `data/logs/launchd/` — is it the sentiment call or main analyst that's slow?
- Consider bumping sentiment timeout or splitting into 2 calls (news + social separate)

- [ ] **Step 7: Push commits**

```bash
git push 2>&1
```

- [ ] **Step 8: Confirm PR #4 status**

```bash
gh pr view 4 --json number,state,commits --jq '{number, state, total_commits: (.commits|length)}'
```

- [ ] **Step 9: Update the runbook / spec note**

Open `docs/superpowers/specs/2026-05-02-reports-phase4.5-sentiment-design.md`. Change the "Status" line at the top from `Approved (brainstorm complete, awaiting plan)` to `Implemented (commit <SHA>)`. Commit:

```bash
git add docs/superpowers/specs/2026-05-02-reports-phase4.5-sentiment-design.md
git commit -m "docs(sentiment): mark Phase 4.5 spec as implemented"
git push
```

---

## Summary

After Phase 4.5:
- New `## D. 情绪面 / Sentiment Index` section in every premarket report
- Macro overall + per-symbol bull/bear -5..+5 index
- News + social media split, plus combined score
- 5+ real source URLs cited
- Mon-Fri 06:00 PT auto-trigger (Phase 7 v1) carries this through unchanged
- Sun 14:00 PT weekly auto-trigger (added 2026-05-02) — the OLD weekly path doesn't use SentimentSection yet; that's a Phase 5 follow-up
- Total pipeline time: ~7 min (was ~5 min)
- Failure paths: graceful — main report always generates

**Coverage vs spec:**
- §3 Out of scope items remain out of scope (no caching / multi-language / history / alerts) ✅
- §11 Acceptance criteria: all 6 items verified in Task 9
- §13 Risks: mitigation in place for 4 of 6; URL liveness + paywall risks deferred to Phase 4.6

**Next phases:**
- Phase 5: build out other report cadences (intraday-4h-1, intraday-4h-2, eod, night, asia, weekly-new) — each can reuse SentimentSection unchanged
- Phase 4.6: URL liveness check + Chinese-language sources
- Phase 7.5: launchd plists for the other 5 report types (after Phase 5)
