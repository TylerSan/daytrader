# Phase 4.5: Sentiment Section — News + Social Media Bull/Bear Index

**Date:** 2026-05-02
**Status:** Approved (brainstorm complete, awaiting plan)
**Owner:** Tyler San
**Parent spec:** [`2026-04-25-reports-system-design.md`](./2026-04-25-reports-system-design.md)
**Predecessor:** Phase 4 (Futures Structure) [`2026-04-26-reports-phase4-futures-structure.md`](../plans/2026-04-26-reports-phase4-futures-structure.md)

---

## 1. Goal

Extend the daily premarket report (and, transitively, any other report cadence in Phase 5+) with a new **D. 情绪面 / Sentiment Index** section produced by AI-driven web research. The section delivers a **structured bull/bear index** (-5 to +5 scale) at two levels:

- **Macro overall** sentiment (1 score)
- **Per-symbol** sentiment for tradable + context instruments (MES, MGC, MNQ today)

Each level breaks down into **news dimension** and **social media dimension** plus a **combined** score, accompanied by a 1-sentence narrative.

The data source is **Anthropic Web Search via `claude -p`** (verified available 2026-05-02 — the headless mode inherits the WebSearch tool from Claude Code's interactive session).

## 2. Why This, Why Now

The premarket report generated 2026-05-02 (and every prior premarket since Phase 6 landed) ships with `## Breaking News` empty. The section literally renders:

> 无新闻条目。**注意**：本节为空意味着不能预测未明事件；周日晚 / 周一开盘需在执行前再次刷新新闻面...

That "再次刷新新闻面" is exactly the kind of friction Phase 7 v1 was supposed to remove. Today the user must manually open Google News / Twitter / Reddit at 06:30 PT, which:

1. Costs 5–10 minutes per morning (= one of the top excuses for skipping a trade day)
2. Is ad-hoc — different keywords each morning, no consistency
3. Lacks structured "is sentiment net long or short?" output — user reads anecdotes and forms a fuzzy gestalt

This phase replaces that with a deterministic, structured AI-curated sentiment block delivered alongside the existing IB-data sections.

## 3. Non-Goals (Explicitly Out of Scope)

- **Sentiment caching / dedup across runs.** Each report fetches fresh. ~6 fires/week × ~$0 (Pro Max claude -p) = negligible cost.
- **Multi-language news.** English only. Twitter / Reddit / StockTwits + major US/UK financial press. Chinese-language sources (财联社, 雪球) deferred until proven needed.
- **Sentiment time-series / history charts.** No persisted sentiment DB in v1.
- **Push alerts on sentiment shifts** (e.g., "MES sentiment flipped from +3 to -2 since last report"). User reads each report fresh; no diff alerts.
- **Replacement of `B. 市场叙事` section.** B remains AI's narrative summary of past market action. D adds independent web-sourced sentiment data.
- **Replacement of old-system `daytrader weekly` NewsCollector** (yfinance-based). That collector keeps powering the OLD weekly path for now. New sentiment section is ADDITIVE for new-system reports.

## 4. Background

### 4.1 What exists today

- **Old system** (`daytrader weekly`, `daytrader pre`): has a `NewsCollector` in `src/daytrader/premarket/collectors/news.py` using **yfinance** to pull headlines for SPY/QQQ/VIX/GC=F/ES=F. ~5–8 headlines/symbol. Used by old weekly + premarket commands. **Stable, but not wired into the new system.**
- **New system** (`daytrader reports run --type premarket`): does not call any news collector. The `B. 市场叙事` section in the new template is filled purely by `claude -p` from market data; the dedicated `## Breaking News` section is rendered with whatever AI produces (often empty when no IB-derived event signal exists).
- **`FuturesSection`** (`src/daytrader/reports/futures_data/`): the established pattern for an additive data section. Phase 4 introduced it. It collects OI / basis / term structure / volume profile, formats markdown, hands off to PromptBuilder. **This is the shape we mirror for SentimentSection.**

### 4.2 What changed during brainstorm

| Earlier assumption | Resolution |
|---|---|
| Maybe reuse yfinance NewsCollector | Rejected. User wants AI-analyzed sentiment INDEX, not raw headlines. Going with Anthropic Web Search. |
| `claude -p` may not have WebSearch | Verified 2026-05-02: `claude -p` returned 5 real source URLs (CNBC/MotleyFool/Bloomberg/etc) in response to a search prompt. Confirmed available. |
| Use Anthropic API web_search tool | Rejected. User has Pro Max subscription → claude -p is free. API would cost ~$0.01/search. |
| Single mega-prompt approach | Rejected. Mixing search task + analysis task in one prompt risks token budget overflow + harder testing. |
| Index granularity | Approved: macro overall + per-symbol (MES/MGC/MNQ). Each with news/social/combined sub-scores. -5..+5 integer scale. |

## 5. Architecture

### 5.1 Approach: 2-call sequential

```
Orchestrator (existing)
  ├── ContextLoader (existing)              ← bars / snapshots / OI
  ├── FuturesSection (existing, Phase 4)    ← term structure / volume profile
  ├── SentimentSection (NEW)                ← claude -p call #1 (focused)
  │     ├── Calls claude -p with sentiment prompt + WebSearch
  │     ├── Parses returned markdown → SentimentResult dataclass
  │     └── On any failure → SentimentResult(unavailable=True, reason=...)
  ├── PromptBuilder (extended)              ← injects sentiment markdown into main prompt
  ├── AIAnalyst (existing)                  ← claude -p call #2 (main report)
  ├── OutputValidator (extended)            ← + "情绪面" required section
  ├── ObsidianWriter (existing)
  └── delivery (Telegram / PDF, existing)
```

**Total claude -p calls per report:** 2 (was 1).
**Total wall time impact:** +2 min (~5 min → ~7 min). Acceptable for Sun 14:00 PT and Mon 06:00 PT cadences (well within the 06:00 → 06:30 wake window).

### 5.2 Rejected alternatives

**B. Single-call mega prompt** — embed "search the web for X, then output the full report" in one giant prompt to AIAnalyst.
- **Pro:** 1 fewer call (~5–6 min total).
- **Con:** Mixes two cognitive tasks; claude -p may exhaust tool budget on search and produce truncated analysis. Hard to test. Hard to evolve sentiment prompt without affecting main prompt.

**C. Separate launchd job for sentiment caching** — fire a 05:55 PT sentiment-only job, cache to disk, premarket reads cache.
- **Pro:** Decouples timing; main pipeline stays ~5 min.
- **Con:** Adds a 3rd launchd plist + cache invalidation logic + race-condition surface. Over-engineering for v1.

### 5.3 Why mirror FuturesSection

Phase 4's `FuturesSection` is the working precedent for an additive, AI-prompt-injected, error-tolerant data section. By copying its structure (collect → render → inject), the implementer needs to make minimal architectural decisions; reviewers can compare line-for-line against an approved pattern; future maintainers see a consistent shape.

## 6. Components

### 6.1 New module: `src/daytrader/reports/sentiment/`

```
src/daytrader/reports/sentiment/
  ├── __init__.py
  ├── dataclasses.py            # SentimentScore, MacroSentiment, SymbolSentiment, SentimentResult
  ├── prompts.py                # Build the sentiment-specific claude -p prompt
  ├── parser.py                 # parse_sentiment_response(raw: str) -> SentimentResult; ParseError
  ├── collector.py              # SentimentCollector — invokes claude -p, delegates parsing to parser.py
  └── section.py                # SentimentSection — high-level facade with collect() + render()
```

Note on render responsibility: `SentimentSection.render(result)` produces the markdown. The orchestrator captures the rendered string and passes it to `PromptBuilder` (see 6.6). Splitting parser into its own module keeps the markdown-contract logic testable in isolation from subprocess plumbing.

### 6.2 Dataclasses (frozen)

```python
@dataclass(frozen=True)
class SentimentScore:
    """One symbol's or macro's sentiment breakdown."""
    news: int          # -5..+5
    social: int        # -5..+5
    combined: int      # -5..+5 (AI-weighted, typically 60% news + 40% social)
    narrative: str     # 1-sentence summary

@dataclass(frozen=True)
class MacroSentiment:
    """Overall macro sentiment + key context."""
    score: SentimentScore
    main_themes: list[str]       # 1–3 bullet points (主流叙事)
    risks: list[str]             # 1–3 bullet points (风险点)
    upcoming_events: list[str]   # 1–5 events in next ~24–48h (CPI, FOMC, etc.)

@dataclass(frozen=True)
class SymbolSentiment:
    """Per-symbol sentiment."""
    symbol: str                  # "MES", "MGC", "MNQ"
    score: SentimentScore

@dataclass(frozen=True)
class SentimentResult:
    """Top-level result. unavailable=True signals graceful degradation."""
    timestamp: datetime          # UTC
    unavailable: bool            # True if claude -p / WebSearch / parse failed
    unavailable_reason: str      # Human-readable failure reason if unavailable
    macro: MacroSentiment | None
    per_symbol: list[SymbolSentiment]
    sources: list[str]           # URLs cited by the AI
```

### 6.3 Sentiment prompt (key contract)

Located in `src/daytrader/reports/sentiment/prompts.py`. Returns a string. Single function `build_sentiment_prompt(symbols: list[str]) -> str`.

```
你是金融情绪分析师。请使用 web search，搜索过去 24 小时内：

1. 与 {symbols} 相关的财经新闻
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
- 关键事件（24h 内）：[逗号分隔事件名]

### 📊 Per-Symbol
| Symbol | News | Social | Combined | 1-句叙事 |
|---|---|---|---|---|
| MES | [-5..+5] | [-5..+5] | [-5..+5] | [短句] |
| MGC | [-5..+5] | [-5..+5] | [-5..+5] | [短句] |
| MNQ | [-5..+5] | [-5..+5] | [-5..+5] | [短句] |

> 评分：-5 (极空) → 0 (中性) → +5 (极多)
> 综合权重：news 60% / social 40%
> Sources: [至少 5 个真实查到的 URL]
```

The strict markdown contract is what enables deterministic parsing. Deviations → parser falls back to `unavailable=True`.

### 6.4 SentimentCollector

Located in `src/daytrader/reports/sentiment/collector.py`.

```python
class SentimentCollector:
    """Invokes claude -p to fetch sentiment, returns parsed result."""

    DEFAULT_TIMEOUT_S = 180  # claude -p search may take 60–120s

    def __init__(
        self,
        symbols: list[str],
        timeout_s: int = DEFAULT_TIMEOUT_S,
        claude_runner: Callable[[str, int], str] | None = None,
    ) -> None:
        ...

    def collect(self) -> SentimentResult:
        prompt = build_sentiment_prompt(self.symbols)
        try:
            raw = self._run_claude(prompt, self._timeout_s)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            return SentimentResult.unavailable_due_to(str(e))
        try:
            return parse_sentiment_response(raw, expected_symbols=self.symbols)
        except ParseError as e:
            _log_raw_response(raw)
            return SentimentResult.unavailable_due_to(f"parse failed: {e}")
```

### 6.5 SentimentSection

Located in `src/daytrader/reports/sentiment/section.py`. The orchestrator-facing facade.

```python
class SentimentSection:
    def __init__(self, symbols: list[str], collector: SentimentCollector | None = None) -> None: ...

    def collect(self) -> SentimentResult: ...

    def render(self, result: SentimentResult) -> str:
        """Return markdown for the D. section. Always returns a string,
        even if unavailable (writes a clear unavailable message)."""
```

### 6.6 Modifications to existing files

| File | Change |
|---|---|
| `src/daytrader/reports/core/orchestrator.py` | Instantiate `SentimentSection` after `FuturesSection`. Call `result = section.collect()` then `sentiment_md = section.render(result)`. Pass `sentiment_md` to PromptBuilder. |
| `src/daytrader/reports/core/prompt_builder.py` | Accept `sentiment_md: str` parameter; embed it in the main report prompt as input data (not as instruction — main AI uses it to inform A. recommendation). |
| `src/daytrader/reports/templates/premarket.md` (or wherever the section list lives — to be confirmed in plan) | Add `## D. 情绪面 / Sentiment Index` section with placeholder. |
| `src/daytrader/reports/core/output_validator.py` | Add `"情绪面"` (plus alternatives `"D. 情绪面"`, `"Sentiment Index"`) to the required-sections list. |

## 7. Data Flow Detail

```
T+0    Orchestrator.run() invoked
T+5s   ContextLoader: fetch bars/snapshots for all instruments (~5s)
T+10s  FuturesSection.collect(): OI / volume profile / term structure (~5s)
T+15s  SentimentSection.collect(): subprocess.run(["claude", "-p"], ...)
       └── claude -p does WebSearch + analysis (~60–120s)
T+135s SentimentSection returns SentimentResult
T+135s PromptBuilder.build(...): combines all data + sentiment markdown
T+136s AIAnalyst.analyze(prompt): subprocess.run(["claude", "-p"], ...) (~120–150s)
T+286s OutputValidator.validate(report): ensures all required sections present
T+287s ObsidianWriter writes Daily/YYYY-MM-DD-premarket.md
T+290s Delivery (Telegram / charts / PDF)
T+~5min Done
```

Net: ~7 min total (was ~5 min) — the SentimentSection adds ~2 min.

## 8. Error Handling

The principle: **SentimentSection failure must NEVER prevent the rest of the report from generating.**

| Failure mode | Detection | Behavior |
|---|---|---|
| `claude -p` not on PATH | preflight already checks; collector also catches | `unavailable=True, reason="claude CLI not found"` |
| `claude -p` timeout (180s) | `subprocess.TimeoutExpired` | `unavailable=True, reason="timeout after 180s"` |
| `claude -p` returns non-zero exit | `subprocess.CalledProcessError` | `unavailable=True, reason="claude -p exited N: <stderr>"` |
| WebSearch tool denied / not available | claude -p will explain in response → parser sees no markdown table | `unavailable=True, reason="WebSearch unavailable: <excerpt>"` |
| Response missing required markdown sections | `parse_sentiment_response` raises | `unavailable=True, reason="markdown parse failed"`, raw response saved to `data/logs/sentiment-failures/YYYYMMDD-HHMMSS.txt` |
| Per-symbol scores partial (e.g. only MES, no MGC) | parser detects | Partial result accepted; missing symbols rendered as "unavailable" rows |

Renderer behavior on `unavailable=True`:

```markdown
## D. 情绪面 / Sentiment Index

⚠️ **情绪数据本次不可用** — {unavailable_reason}

主报告其余章节正常生成；周一开盘前可手动跑：
`uv run python -c "from daytrader.reports.sentiment.section import SentimentSection; ..."`
```

## 9. Testing Strategy

### 9.1 Unit tests (mocked claude -p)

`tests/reports/sentiment/test_collector.py`:
- `test_collector_happy_path` — mock returns valid markdown → SentimentResult populated
- `test_collector_timeout` — mock raises TimeoutExpired → result.unavailable=True
- `test_collector_nonzero_exit` — mock raises CalledProcessError → unavailable
- `test_collector_unparseable_response` — mock returns garbage → unavailable + raw logged

`tests/reports/sentiment/test_parser.py`:
- `test_parse_full_response` — all symbols + macro present
- `test_parse_partial_symbols` — only 2 of 3 symbols → 2 SymbolSentiment + missing logged
- `test_parse_missing_macro_section` → ParseError
- `test_parse_extra_text_after_table` — tolerated, table extracted
- `test_parse_score_out_of_range` (e.g. AI returns +7) → clamp to +5 with warning
- `test_parse_invalid_score_text` (e.g. "high") → ParseError

`tests/reports/sentiment/test_section.py`:
- `test_render_happy_path` — produces markdown matching template
- `test_render_unavailable` — produces clear unavailable block
- `test_render_partial_per_symbol` — renders rows for present symbols + "unavailable" for missing

### 9.2 Integration test (slow, opt-in)

`tests/reports/sentiment/test_integration_live.py`:
- Marked `@pytest.mark.slow` (skipped by default)
- Actually invokes claude -p
- Validates returned markdown is parseable
- Confirms the prompt contract still holds against current claude behavior
- Run manually: `uv run pytest -m slow tests/reports/sentiment/`

### 9.3 End-to-end test fire

After implementation lands:
1. Run full premarket pipeline manually: `uv run daytrader reports run --type premarket --no-pdf`
2. Confirm new D. section in `Daily/YYYY-MM-DD-premarket.md`
3. Confirm sources are real URLs (spot-check 2–3)
4. Kill claude mid-fetch → confirm graceful degradation (D. section says "unavailable", rest of report intact)

## 10. Files Inventory

| File | Action | Estimated LOC |
|---|---|---|
| `src/daytrader/reports/sentiment/__init__.py` | Create | ~10 |
| `src/daytrader/reports/sentiment/dataclasses.py` | Create | ~60 |
| `src/daytrader/reports/sentiment/prompts.py` | Create | ~60 |
| `src/daytrader/reports/sentiment/collector.py` | Create | ~80 |
| `src/daytrader/reports/sentiment/section.py` | Create | ~80 |
| `src/daytrader/reports/sentiment/parser.py` | Create | ~120 (parsing logic) |
| `src/daytrader/reports/core/orchestrator.py` | Modify | ~15 inserted lines |
| `src/daytrader/reports/core/prompt_builder.py` | Modify | ~10 inserted lines |
| `src/daytrader/reports/core/output_validator.py` | Modify | ~5 inserted lines |
| Premarket template (path TBD in plan) | Modify | ~10 inserted lines |
| `tests/reports/sentiment/__init__.py` | Create | 0 |
| `tests/reports/sentiment/test_dataclasses.py` | Create | ~50 |
| `tests/reports/sentiment/test_parser.py` | Create | ~150 |
| `tests/reports/sentiment/test_collector.py` | Create | ~120 |
| `tests/reports/sentiment/test_section.py` | Create | ~80 |
| `tests/reports/sentiment/test_integration_live.py` | Create | ~40 (slow-marked) |
| **Total estimated** | | **~890 LOC** |

## 11. Acceptance Criteria

A Phase 4.5 implementation is complete when ALL of these hold:

- [ ] `uv run pytest tests/reports/sentiment/ -v` passes (excluding `slow`)
- [ ] `uv run pytest tests/ --ignore=tests/research -q` still passes (no regressions, total now 290+ tests)
- [ ] A live test fire of `daytrader reports run --type premarket --no-pdf` produces a Daily/YYYY-MM-DD-premarket.md that contains:
  - `## D. 情绪面 / Sentiment Index` heading
  - `### 🌐 Macro Sentiment` block with score
  - `### 📊 Per-Symbol` table with rows for MES, MGC, MNQ
  - At least 5 source URLs listed (real, clickable)
- [ ] Failure-path verification: kill `claude` PID mid-fetch; report still generates; D. section renders "情绪数据本次不可用" cleanly
- [ ] Total pipeline wall time ≤ 10 min (target: ~7 min)
- [ ] No new external dependencies in `pyproject.toml`

## 12. Decision Records

**DR-1: Use `claude -p` WebSearch over Anthropic API `web_search` tool**
- Rationale: User has Pro Max claude subscription (claude -p is free). API costs ~$0.01/search × 6/week = trivial but adds API key management overhead.
- Implication: Sentiment quality depends on Claude Code's WebSearch implementation, not directly controllable.

**DR-2: 2 sequential claude -p calls instead of 1 mega-prompt**
- Rationale: Separation of concerns. Sentiment prompt can iterate independently of main report prompt. Easier to test (mock one call). Easier to debug (failure isolated).
- Implication: +2 min wall time. Two failure modes instead of one.

**DR-3: -5..+5 integer scale (5-level coarse grain)**
- Rationale: AI sentiment estimation precision is fundamentally low. A "+47" vs "+52" 0-100 score implies false precision. Coarse 5-level forces honest categorization.
- Implication: Numeric output, but treat as ordinal categories.

**DR-4: Mirror `FuturesSection` (Phase 4) module pattern**
- Rationale: Existing approved pattern. Reviewers compare against known shape. Implementer needs minimal architectural creativity.
- Implication: Same `collect() / render() / dataclass` triad. New module under `src/daytrader/reports/sentiment/`.

**DR-5: No caching in v1**
- Rationale: 6 fires/week × ~$0 cost. Caching adds invalidation logic + a "stale data" failure mode that's worse than just re-fetching.
- Implication: Each report re-queries the web. Acceptable.

**DR-6: English-only sources**
- Rationale: Claude Web Search default coverage is strong on US/UK financial press + English-language Twitter/Reddit/StockTwits. User's lock-in is on US futures (MES/MGC/MNQ); Chinese-language sentiment less directly relevant.
- Implication: 中文 sources (财联社, 雪球) excluded for v1. Can add via prompt extension if proven needed.

**DR-7: New D. section, not replacement of B./B-news**
- Rationale: B. 市场叙事 = AI's narrative summary of past observed market action (still useful). D. 情绪面 = independent web-sourced sentiment data (additive).
- Implication: Two narrative-flavored sections in the report. They should not contradict — when they do, that's a signal worth noting (potential AI miscalibration).

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `claude -p` WebSearch capability disappears (Anthropic changes Claude Code) | Low | High | Pin behavior with the integration test (`test_integration_live`); when broken, switch to Anthropic API web_search tool (~1h migration) |
| AI hallucinates URLs / sources | Med | Med | Spot-check during acceptance; add a parser hook to flag if URLs return 4xx (Phase 4.6 enhancement, deferred) |
| AI ignores -5..+5 scale (returns "very bullish" text) | Med | Low | Strict markdown parser + ParseError → graceful unavailable |
| Sentiment contradicts main AI analysis (e.g. D=+5, B=空头叙事) | Med | Low | Acceptable — both are signals. User notices contradictions. Document in runbook. |
| WebSearch latency exceeds 180s timeout | Low | Med | Bump timeout to 300s if observed in practice; or split into 2 search calls (news + social) |
| Sources are mostly paywalled (WSJ/FT/Bloomberg) → AI can't read full content | Med | Low | Anthropic WebSearch returns extracts/snippets even for paywalled sources, sufficient for sentiment |

## 14. Future Enhancements (Phase 4.6+)

- URL liveness check (filter dead links)
- Sentiment trend persistence (sqlite table → "MES sentiment 7-day chart")
- Push alert on big sentiment shift (e.g. ±3 in 24h)
- Chinese-language source coverage (财联社, 雪球, 新浪财经)
- Replace `B. 市场叙事` if D's web-sourced narrative consistently outperforms B's data-only narrative

## 15. Migration to Other Cadences (Phase 5+)

Once Phase 5 builds out other report types (intraday-4h-1, intraday-4h-2, eod, night, asia, weekly), `SentimentSection` is reused as-is — same `collect() / render()` API. Each cadence's PromptBuilder + template references it. No new infrastructure.

For weekly reports specifically: bump the time window in the prompt from "past 24h" to "past 7 days" via a `time_window: str = "past 24h"` parameter on `build_sentiment_prompt()`.

---

**End of spec. Next step: write implementation plan via `superpowers:writing-plans` skill.**
