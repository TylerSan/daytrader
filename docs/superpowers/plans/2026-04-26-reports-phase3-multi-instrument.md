# Reports System — Phase 3: Multi-Instrument Premarket Report

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute. Steps use checkbox `- [ ]` syntax.

**Goal:** Extend the Phase 2 single-instrument (MES) premarket pipeline to cover **MES + MNQ + MGC** in a single report. Per signed Contract.md: MES + MGC are *tradable* (count toward 30-trade lock-in, get full plan formation in C); MNQ is *context-only* (cross-asset risk-on/off reference, no plan). After Phase 3: `daytrader reports run --type premarket` produces one Obsidian markdown file with three instrument analyses, two plans, and one integrated narrative.

**Architecture:** Strictly additive to Phase 2. The orchestrator loops over symbols for bar fetching; PromptBuilder accepts a `bars_by_symbol_and_tf` dict; the AI call remains a single shot returning one merged report. PlanExtractor returns plans per tradable instrument; orchestrator saves N plans per report (one per tradable). InstrumentConfig grows a `tradable` flag.

**Tech Stack:** Same as Phase 2. No new external deps.

**Spec reference:** `docs/superpowers/specs/2026-04-25-reports-system-design.md` §2.4, §3.6, §3.7, §4.5; user fork choice "A. 全交易" (later refined to MES+MGC tradable, MNQ context-only via Contract.md 2026-04-26).

**Prerequisites:**
- Phase 1 (foundation) ✅
- Phase 2 (single-instrument premarket end-to-end) ✅
- Phase 2.5 (Pine generator) ✅ — already multi-instrument-aware
- Contract.md signed with MES+MGC tradable, MNQ context-only ✅

**Out of scope** (later phases):
- F. 期货结构 section (OI/COT/Basis/Term/VolumeProfile) → Phase 4
- Anthropic Web Search for breaking news → Phase 4
- Telegram push, PDF rendering, charts → Phase 6
- Other report types (intraday/EOD/night/weekly) → Phase 5
- launchd auto-trigger → Phase 7

---

## File Structure

| File | Action | Why |
|---|---|---|
| `config/instruments.yaml` | Modify (add `tradable` per symbol) | Distinguish lock-in symbols from context-only |
| `src/daytrader/reports/instruments/definitions.py` | Modify (`InstrumentConfig.tradable`) | New field |
| `tests/reports/test_instruments.py` | Modify (test tradable flag) | Coverage |
| `src/daytrader/reports/templates/premarket.md` | Rewrite (multi-instrument layout) | New section structure |
| `src/daytrader/reports/core/prompt_builder.py` | Modify (per-symbol bars dict) | Multi-instrument input |
| `tests/reports/test_prompt_builder.py` | Modify | Coverage |
| `src/daytrader/reports/types/premarket.py` | Modify (loop over symbols) | Multi-symbol fetch |
| `tests/reports/test_premarket_type.py` | Modify | Coverage |
| `src/daytrader/reports/core/output_validator.py` | Modify (per-instrument required) | New sections to verify |
| `tests/reports/test_output_validator.py` | Modify | Coverage |
| `src/daytrader/reports/core/plan_extractor.py` | Modify (per-instrument plans) | Returns dict[symbol → ExtractedPlan] |
| `tests/reports/test_plan_extractor.py` | Modify | Coverage |
| `src/daytrader/reports/core/orchestrator.py` | Modify (save N plans, pass instrument list) | Multi-instrument coordination |
| `tests/reports/test_orchestrator.py` | Modify | Coverage |
| `src/daytrader/cli/reports.py` | Modify (load instruments from config) | Pass to orchestrator |

---

## Task 1: Add `tradable` flag to instruments.yaml + InstrumentConfig

**Files:**
- Modify: `config/instruments.yaml`
- Modify: `src/daytrader/reports/instruments/definitions.py`
- Modify: `tests/reports/test_instruments.py` and `tests/reports/conftest.py`

- [ ] **Step 1: Update instruments.yaml**

Edit `config/instruments.yaml`. Add `tradable: true` to MES + MGC; `tradable: false` to MNQ.

```yaml
instruments:
  MES:
    full_name: "Micro E-mini S&P 500"
    underlying_index: SPX
    cme_symbol: MES
    typical_atr_pts: 14
    typical_stop_pts: 8
    typical_target_pts: 16
    cot_commodity: "S&P 500 STOCK INDEX"
    tradable: true

  MNQ:
    full_name: "Micro E-mini Nasdaq 100"
    underlying_index: NDX
    cme_symbol: MNQ
    typical_atr_pts: 60
    typical_stop_pts: 30
    typical_target_pts: 60
    cot_commodity: "NASDAQ MINI"
    tradable: false

  MGC:
    full_name: "Micro Gold"
    underlying_index: null
    cme_symbol: MGC
    typical_atr_pts: 8
    typical_stop_pts: 5
    typical_target_pts: 10
    cot_commodity: "GOLD"
    tradable: true
```

- [ ] **Step 2: Update fixture in conftest**

Modify `tests/reports/conftest.py` — add `tradable: true/false` to all three fixture instruments to match.

```python
# In fixture_instruments_yaml, append `tradable: true` (or false for MNQ) to each block
```

The existing fixture has all 3 instruments. Just add the `tradable` line per block (true for MES/MGC, false for MNQ).

- [ ] **Step 3: Add failing tests**

Append to `tests/reports/test_instruments.py`:

```python
def test_load_instruments_tradable_flag(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    assert cfg["MES"].tradable is True
    assert cfg["MGC"].tradable is True
    assert cfg["MNQ"].tradable is False


def test_tradable_subset_helper(fixture_instruments_yaml):
    """tradable_symbols() returns only tradable=true symbols, sorted."""
    from daytrader.reports.instruments.definitions import tradable_symbols
    cfg = load_instruments(str(fixture_instruments_yaml))
    assert tradable_symbols(cfg) == ["MES", "MGC"] or tradable_symbols(cfg) == ["MGC", "MES"]
```

- [ ] **Step 4: Run tests (red)**

Run: `uv run pytest tests/reports/test_instruments.py -v`
Expected: 2 new tests fail (tradable attribute / tradable_symbols missing).

- [ ] **Step 5: Implement**

Modify `src/daytrader/reports/instruments/definitions.py`:

```python
class InstrumentConfig(BaseModel):
    """Per-instrument futures parameters."""
    full_name: str
    underlying_index: str | None
    cme_symbol: str
    typical_atr_pts: float
    typical_stop_pts: float
    typical_target_pts: float
    cot_commodity: str
    tradable: bool = False  # default False for safety; YAML must explicitly set True


def tradable_symbols(instruments: dict[str, InstrumentConfig]) -> list[str]:
    """Return symbols where tradable=True. Order is stable (insertion order)."""
    return [sym for sym, cfg in instruments.items() if cfg.tradable]
```

- [ ] **Step 6: Run tests (green)**

Run: `uv run pytest tests/reports/test_instruments.py -v`
Expected: all 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add config/instruments.yaml src/daytrader/reports/instruments/definitions.py tests/reports/test_instruments.py tests/reports/conftest.py
git commit -m "feat(reports): InstrumentConfig.tradable flag (MES+MGC=true, MNQ=false)"
```

---

## Task 2: Premarket template v2 (multi-instrument layout)

**Files:**
- Modify: `src/daytrader/reports/templates/premarket.md`

- [ ] **Step 1: Rewrite premarket.md**

Replace the entire content of `src/daytrader/reports/templates/premarket.md` with:

````markdown
# Premarket Daily Report — System Prompt (Multi-Instrument)

You are an AI trading analyst assisting a human discretionary day trader during their 30-trade lock-in phase. The trader trades **MES (Micro E-mini S&P 500) and MGC (Micro Gold)** during US session; **MNQ (Micro E-mini Nasdaq 100)** is monitored as a cross-asset risk-on/off reference but NOT traded during this lock-in. This report runs at **06:00 PT daily** to brief them before market open.

## Output Language

Generate the report in **Chinese (Simplified)**. Preserve technical terms in English (VWAP, EMA, ATR, OI, POC, RTH). Numbers in ASCII (5246.75, not 五千二百四十六点七五). Section labels A/B/C/F/D in English.

## Required Sections (in order)

1. **Lock-in metadata block** (top)
2. **Per-instrument Multi-TF Analysis**
   - **MES** section: W → D → 4H → 1H
   - **MNQ** section: W → D → 4H → 1H (context analysis only — no plan)
   - **MGC** section: W → D → 4H → 1H
3. **Cross-asset narrative** — short paragraph relating MES + MNQ + MGC posture (risk-on/off, sector rotation, dollar/gold inverse)
4. **Breaking news** (past ~12h overnight Asia + Europe + early US pre-market) — single combined section, since news affects all three
5. **C. 计划复核 / Plan Formation** — **two** plan blocks:
   - C-MES (MES tradable plan)
   - C-MGC (MGC tradable plan)
   - NOTE: NO C-MNQ block (MNQ is context-only)
6. **B. 市场叙事 / Market Narrative** (combined, describing past activity across all three)
7. **A. 建议 / Recommendation** (A-2 + A-3 mixed; integrated overview, not per-symbol)
8. **数据快照 / Data snapshot** (table covering all three symbols)

## Per-Instrument Section Template

For each of MES, MNQ, MGC, present:

```
### 📊 {SYMBOL} ({Full Name})

#### W (Bar end {ET / PT})
**OHLCV**: O ___ | H ___ | L ___ | C ___ | V ___ | Range ___ (___×ATR-20)
**形态 / Pattern**: ___
**位置 / Position**: ___
**关键位 / Key levels (this TF)**: R ___ / S ___

#### D ({Bar end ET / PT})
[same structure]

#### 4H ({Bar end ET / PT})
[same structure]

#### 1H ({Bar end ET / PT})
[same structure]

**多 TF 一致性 (HTF↔LTF alignment)**: ___
```

## C. Plan Formation — TRADABLE INSTRUMENTS ONLY

For **MES** and **MGC** (NOT MNQ), use this structure under "## C. 计划复核":

```markdown
### C-{SYMBOL}

**Today's plan**:
- Setup: [name from Contract.md, or "discretionary read" if Contract.md not filled]
- Direction: [long | short | neutral / wait]
- Entry: [exact price level + reasoning]
- Stop: [exact price level = -1R risk]
- Target: [exact price level = +2R or scenario-based]
- R unit: $[amount from Contract.md]

**Invalidation conditions** (any one triggers exit / stand down):
1. [Specific price level break]
2. [Specific cross-asset signal]
3. [Specific volatility condition]

**Today's posture**: [bullish bias / bearish bias / neutral / wait for setup]
```

**MNQ does NOT get a plan block.** Instead, the MNQ section in (2) ends with a short "context interpretation" paragraph (1-2 sentences) on what MNQ posture implies for MES.

## A. Recommendation Form

Default = A-3 (no action; execute plan). Single integrated A across all instruments. Escalate to A-2 (scenario matrix) only if any:
- Critical news event in the past 12h that materially changes thesis (FOMC, CPI, geopolitical)
- Multi-TF alignment broken across the tradable instruments (MES/MGC disagree)
- Either tradable instrument near a key level at premarket scan time

A-1 (direct "buy now / sell now" call) is **permanently disabled**.

## Forbidden

- B section may not predict the future — describe past only.
- C-MES / C-MGC use placeholder "[setup name pending]" if Contract.md is not filled.
- A section never gives an unconditional "buy now / sell now" call.
- Do not generate a C block for MNQ.

## Length Limit

Max ~9,000 characters when no F section is generated (Phase 3). If approaching limit, compress B (use bullets), preserve all multi-TF + C-MES + C-MGC + A.

---

# User Message (data context)

The user message will contain:
- Lock-in status (`Contract.md status`, trades done X/30, last trade R, streak)
- Per-symbol bar data: W, D, 4H, 1H OHLCV + key levels for MES, MNQ, MGC
- Breaking news collected from premarket news source
- Contract.md full text (if filled) or "Contract.md: not yet filled" marker
- List of tradable symbols (e.g. ["MES", "MGC"])

You must produce the full report following the section structure above.
````

- [ ] **Step 2: Verify file readable + the load_template helper still works**

Run: `uv run python -c "from daytrader.reports.templates import load_template; t = load_template('premarket'); print(len(t), 'chars'); assert 'Multi-Instrument' in t"`
Expected: prints char count > 3000 with the assertion passing.

- [ ] **Step 3: Commit**

```bash
git add src/daytrader/reports/templates/premarket.md
git commit -m "feat(reports): premarket template v2 (multi-instrument layout)"
```

---

## Task 3: PromptBuilder — accept per-symbol bars dict

**Files:**
- Modify: `src/daytrader/reports/core/prompt_builder.py`
- Modify: `tests/reports/test_prompt_builder.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/reports/test_prompt_builder.py`:

```python
def test_prompt_builder_premarket_multi_symbol_in_user_block():
    """User message contains explicit per-symbol bar blocks."""
    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n",
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    bars = {
        "MES": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246.0)],
            "4H": [],
            "1H": [],
        },
        "MNQ": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 18420.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 18500.0)],
            "4H": [],
            "1H": [],
        },
        "MGC": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 2340.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 2342.0)],
            "4H": [],
            "1H": [],
        },
    }
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=bars,
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_text = msgs[1]["content"]
    assert "MES" in user_text
    assert "MNQ" in user_text
    assert "MGC" in user_text
    assert "5246" in user_text  # MES daily close
    assert "18500" in user_text  # MNQ daily close
    assert "2342" in user_text  # MGC daily close


def test_prompt_builder_user_block_lists_tradable_symbols():
    """User message explicitly states which symbols are tradable."""
    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_ACTIVE,
        contract_text="# Contract\nfilled\n",
        lock_in_trades_done=3,
        lock_in_target=30,
        cumulative_r=0.5,
        last_trade_date="2026-04-24",
        last_trade_r=1.0,
        streak="2W1L",
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf={"MES": {"1W": [], "1D": [], "4H": [], "1H": []},
                               "MNQ": {"1W": [], "1D": [], "4H": [], "1H": []},
                               "MGC": {"1W": [], "1D": [], "4H": [], "1H": []}},
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_text = msgs[1]["content"]
    assert "tradable" in user_text.lower()
    assert "MES" in user_text and "MGC" in user_text
```

Also REMOVE the old single-symbol tests:
```python
# Remove or update test_prompt_builder_premarket_returns_messages_list
# Remove or update test_prompt_builder_premarket_handles_missing_contract
# Remove or update test_prompt_builder_premarket_includes_lock_in_status
```

Replace those with multi-symbol equivalents that pass the new signature. Keep all the assertion-style coverage but adapt to new signature.

For brevity, simply update each existing test's `build_premarket(bars_by_tf=...)` call to `build_premarket(bars_by_symbol_and_tf={"MES": <existing bars>, "MNQ": {...}, "MGC": {...}}, tradable_symbols=["MES", "MGC"], ...)`.

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/test_prompt_builder.py -v`
Expected: tests fail because old `bars_by_tf` is gone or signature mismatches.

- [ ] **Step 3: Implement multi-symbol PromptBuilder**

Replace `src/daytrader/reports/core/prompt_builder.py` `build_premarket` method body with:

```python
    def build_premarket(
        self,
        context: ReportContext,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        tradable_symbols: list[str],
        news_items: list[dict[str, Any]],
        run_timestamp_pt: str,
        run_timestamp_et: str,
    ) -> list[dict[str, Any]]:
        template = load_template("premarket")
        contract_section = (
            context.contract_text
            if context.contract_text is not None
            else "Contract.md: not yet filled by user"
        )

        system_blocks = [
            {
                "type": "text",
                "text": template,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"## Contract.md content\n\n{contract_section}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        lock_in_block = self._build_lock_in_block(context)
        bars_block = self._build_multi_symbol_bars_block(bars_by_symbol_and_tf)
        news_block = self._build_news_block(news_items)
        tradable_block = (
            f"## Tradable symbols (count toward 30-trade lock-in)\n"
            f"{', '.join(tradable_symbols)}\n\n"
            f"All other symbols are context-only — generate analysis but NO plan."
        )

        user_text = (
            f"# Premarket Daily Report — generation context\n\n"
            f"**Run time**: {run_timestamp_pt} ({run_timestamp_et})\n\n"
            f"{lock_in_block}\n\n"
            f"{tradable_block}\n\n"
            f"{bars_block}\n\n"
            f"{news_block}\n\n"
            f"Please generate the full multi-instrument premarket report following "
            f"the system prompt template. Output in Chinese."
        )

        return [
            {"role": "system", "content": system_blocks},
            {"role": "user", "content": user_text},
        ]

    @staticmethod
    def _build_multi_symbol_bars_block(
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
    ) -> str:
        """Format per-symbol multi-TF bar data."""
        lines = ["## Multi-TF bar data (per instrument)"]
        for symbol in bars_by_symbol_and_tf:
            lines.append(f"\n### Symbol: {symbol}")
            tfs = bars_by_symbol_and_tf[symbol]
            for tf in ("1W", "1D", "4H", "1H"):
                bars = tfs.get(tf, [])
                if not bars:
                    lines.append(f"\n#### {tf}\n(no bars available)")
                    continue
                lines.append(f"\n#### {tf} ({len(bars)} bars, oldest first)")
                for b in bars[-10:]:
                    lines.append(
                        f"- {b.timestamp.isoformat()}: O={b.open} H={b.high} "
                        f"L={b.low} C={b.close} V={b.volume}"
                    )
        return "\n".join(lines)
```

You may KEEP the old `_build_bars_block` static method to avoid breaking other callers in case something else uses it; the new method `_build_multi_symbol_bars_block` is added alongside.

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/test_prompt_builder.py -v`
Expected: all tests pass (existing single-symbol ones will need to have been updated in Step 1).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/prompt_builder.py tests/reports/test_prompt_builder.py
git commit -m "feat(reports): PromptBuilder multi-symbol bars + tradable list (Phase 3)"
```

---

## Task 4: PremarketGenerator — fetch bars for all symbols

**Files:**
- Modify: `src/daytrader/reports/types/premarket.py`
- Modify: `tests/reports/test_premarket_type.py`

- [ ] **Step 1: Update tests**

Replace `tests/reports/test_premarket_type.py` content with:

```python
"""Tests for premarket type handler (multi-instrument)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.premarket import (
    PremarketGenerator,
    GenerationOutcome,
)


def _ctx(status=ContractStatus.LOCK_IN_NOT_STARTED) -> ReportContext:
    return ReportContext(
        contract_status=status,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )


def _ohlcv(c: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def test_premarket_generator_fetches_bars_for_each_symbol():
    """get_bars called 4 TFs × 3 symbols = 12 times."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = (
        "## Lock-in\nstatus\n\n"
        "## Multi-TF Analysis\n"
        "### MES\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "### MNQ\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "### MGC\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n\n"
        "## 突发新闻\nnone\n\n"
        "## C. 计划复核\n### C-MES\nplan\n### C-MGC\nplan\n\n"
        "## B. 市场叙事\nnarr\n\n"
        "## A. 建议\nno action\n\n"
        "## 数据快照\nok\n"
    )
    fake_ai_result.input_tokens = 1000
    fake_ai_result.output_tokens = 500
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    generator = PremarketGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert isinstance(outcome, GenerationOutcome)
    # 4 TFs × 3 symbols = 12 calls
    assert fake_ib.get_bars.call_count == 12
    # AI called once with combined context
    assert fake_ai.call.call_count == 1
    assert outcome.validation.ok is True


def test_premarket_generator_marks_validation_failure_on_short_text():
    """If AI returns truncated text missing instrument blocks, validation fails."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = "(too short)"
    fake_ai_result.input_tokens = 100
    fake_ai_result.output_tokens = 50
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    generator = PremarketGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert outcome.validation.ok is False
    assert len(outcome.validation.missing) > 0
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/test_premarket_type.py -v`
Expected: tests fail (signature mismatch — `symbols=` and `tradable_symbols=` not accepted).

- [ ] **Step 3: Implement multi-symbol generator**

Replace the body of `src/daytrader/reports/types/premarket.py` with:

```python
"""Premarket type handler (multi-instrument).

Flow per generate():
    For each symbol: fetch multi-TF bars (W/D/4H/1H).
    Build single integrated prompt with per-symbol bars + tradable list.
    AI call → validate → return GenerationOutcome.

Plan extraction (per tradable instrument) and persistence happen in the
orchestrator, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient, OHLCV
from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult
from daytrader.reports.core.context_loader import ReportContext
from daytrader.reports.core.output_validator import (
    OutputValidator,
    ValidationResult,
)
from daytrader.reports.core.prompt_builder import PromptBuilder


@dataclass(frozen=True)
class GenerationOutcome:
    report_text: str
    ai_result: AIResult
    validation: ValidationResult


PREMARKET_TFS = ("1W", "1D", "4H", "1H")
BARS_PER_TF: dict[str, int] = {"1W": 52, "1D": 200, "4H": 50, "1H": 24}


class PremarketGenerator:
    """Generate the premarket report — multi-symbol fetch + AI + validate."""

    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
    ) -> None:
        if not symbols:
            raise ValueError("symbols must be non-empty")
        for s in tradable_symbols:
            if s not in symbols:
                raise ValueError(f"tradable symbol {s!r} not in symbols list {symbols}")
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()

    def generate(
        self,
        context: ReportContext,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
    ) -> GenerationOutcome:
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] = {}
        for symbol in self.symbols:
            bars_by_symbol_and_tf[symbol] = {}
            for tf in PREMARKET_TFS:
                bars_by_symbol_and_tf[symbol][tf] = self.ib_client.get_bars(
                    symbol=symbol,
                    timeframe=tf,
                    bars=BARS_PER_TF[tf],
                )

        messages = self.prompt_builder.build_premarket(
            context=context,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            tradable_symbols=self.tradable_symbols,
            news_items=news_items or [],
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
        )

        ai_result = self.ai_analyst.call(
            messages=messages,
            max_tokens=12288,  # increased for multi-instrument
        )
        validation = self.validator.validate(
            ai_result.text, report_type="premarket"
        )
        return GenerationOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
        )
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/test_premarket_type.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/types/premarket.py tests/reports/test_premarket_type.py
git commit -m "feat(reports): PremarketGenerator multi-symbol fetch + dispatch"
```

---

## Task 5: OutputValidator — multi-instrument required sections

**Files:**
- Modify: `src/daytrader/reports/core/output_validator.py`
- Modify: `tests/reports/test_output_validator.py`

- [ ] **Step 1: Update REQUIRED_SECTIONS**

Replace the `REQUIRED_SECTIONS` dict in `src/daytrader/reports/core/output_validator.py`:

```python
REQUIRED_SECTIONS: dict[str, list[SectionSpec]] = {
    "premarket": [
        "Lock-in",
        # Per-symbol Multi-TF — each symbol must appear in headers
        ["MES", "📊 MES"],
        ["MNQ", "📊 MNQ"],
        ["MGC", "📊 MGC"],
        # Per symbol per TF — at least the labels must be present somewhere
        # (we only require ONE TF per symbol to avoid over-strictness during
        # AI variance; multi-TF coverage is enforced by the template)
        ["1W", "## W", "### W ", "Weekly", "周线"],
        ["1D", "## D", "### D ", "Daily", "日线"],
        ["4H", "4 H", "4小时"],
        ["1H", "1 H", "1小时", "Hourly"],
        ["新闻", "News", "Breaking"],
        # Plan blocks for tradable instruments
        ["C-MES", "### C-MES", "C. MES", "MES Plan"],
        ["C-MGC", "### C-MGC", "C. MGC", "MGC Plan"],
        "C.",
        "B.",
        "A.",
        ["数据快照", "Data snapshot", "Snapshot"],
    ],
}
```

Note: we EXPLICITLY do NOT require a `C-MNQ` block (MNQ is context-only).

- [ ] **Step 2: Update test fixture**

Replace the `PREMARKET_SAMPLE_VALID` constant in `tests/reports/test_output_validator.py`:

```python
PREMARKET_SAMPLE_VALID = """
# 盘前日报 — 2026-04-25

## Lock-in status
trades_done: 0/30

## Multi-TF Analysis

### 📊 MES
#### W
data
#### D
data
#### 4H
data
#### 1H
data

### 📊 MNQ
#### W
data
#### D
data
#### 4H
data
#### 1H
data

### 📊 MGC
#### W
data
#### D
data
#### 4H
data
#### 1H
data

## Breaking news / 突发新闻
- item

## C. 计划复核
### C-MES
plan
### C-MGC
plan

## B. 市场叙事
narrative

## A. 建议
no action

## 数据快照
ok
"""
```

Add new test:

```python
def test_validator_premarket_fails_when_mes_section_missing():
    no_mes = PREMARKET_SAMPLE_VALID.replace("📊 MES", "x").replace("MES", "x")
    validator = OutputValidator()
    result = validator.validate(no_mes, report_type="premarket")
    assert result.ok is False
    # Should mention MES somewhere in missing label
    missing_str = " ".join(result.missing)
    assert "MES" in missing_str


def test_validator_premarket_fails_when_c_mes_missing():
    no_c_mes = PREMARKET_SAMPLE_VALID.replace("### C-MES\nplan", "")
    validator = OutputValidator()
    result = validator.validate(no_c_mes, report_type="premarket")
    assert result.ok is False
```

Update existing tests' string content if their valid samples don't have MES/MNQ/MGC sections.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/reports/core/output_validator.py tests/reports/test_output_validator.py
git commit -m "feat(reports): OutputValidator multi-instrument required sections"
```

---

## Task 6: PlanExtractor — return per-instrument plans

**Files:**
- Modify: `src/daytrader/reports/core/plan_extractor.py`
- Modify: `tests/reports/test_plan_extractor.py`

- [ ] **Step 1: Update tests**

Replace `tests/reports/test_plan_extractor.py` content with:

```python
"""Tests for PlanExtractor (multi-instrument)."""

from __future__ import annotations

import pytest

from daytrader.reports.core.plan_extractor import (
    ExtractedPlan,
    PlanExtractor,
)


REPORT_WITH_BOTH_PLANS = """
# 盘前日报

## C. 计划复核

### C-MES

**Today's plan**:
- Setup: ORB long
- Direction: long
- Entry: 5240.00
- Stop: 5232.00
- Target: 5256.00
- R unit: $50

**Invalidation conditions**:
1. Price breaks below 5232
2. SPY breaks below 580
3. VIX above 18

### C-MGC

**Today's plan**:
- Setup: VWAP fade
- Direction: short
- Entry: 2350.00
- Stop: 2355.00
- Target: 2340.00
- R unit: $50

**Invalidation conditions**:
1. Price breaks above 2355
2. DXY drops below 103
3. Fed announces rate cut
"""


REPORT_WITHOUT_PLANS = """
# 盘前日报

## C. 计划复核

(Contract.md not yet filled — no plans formed.)
"""


def test_extract_plans_returns_dict_keyed_by_symbol():
    extractor = PlanExtractor()
    plans = extractor.extract_per_instrument(
        REPORT_WITH_BOTH_PLANS, instruments=["MES", "MGC"]
    )
    assert isinstance(plans, dict)
    assert set(plans.keys()) == {"MES", "MGC"}

    mes = plans["MES"]
    assert isinstance(mes, ExtractedPlan)
    assert mes.setup_name == "ORB long"
    assert mes.entry == pytest.approx(5240.00)

    mgc = plans["MGC"]
    assert mgc.setup_name == "VWAP fade"
    assert mgc.entry == pytest.approx(2350.00)
    assert mgc.direction == "short"


def test_extract_plans_returns_empty_dict_when_no_plans():
    extractor = PlanExtractor()
    plans = extractor.extract_per_instrument(
        REPORT_WITHOUT_PLANS, instruments=["MES", "MGC"]
    )
    assert plans == {}


def test_extract_plans_skips_missing_instruments():
    """If only MES has a plan, only MES is in the result."""
    only_mes = REPORT_WITH_BOTH_PLANS.split("### C-MGC")[0]
    extractor = PlanExtractor()
    plans = extractor.extract_per_instrument(only_mes, instruments=["MES", "MGC"])
    assert "MES" in plans
    assert "MGC" not in plans
```

KEEP the existing single-plan tests as a backward-compat sanity check (they still test `extract()` which we'll keep as a helper).

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/test_plan_extractor.py -v`
Expected: new tests fail (`extract_per_instrument` doesn't exist).

- [ ] **Step 3: Implement multi-plan extraction**

Append to `src/daytrader/reports/core/plan_extractor.py` (KEEP the existing class, add a new method):

```python
    def extract_per_instrument(
        self, report_text: str, instruments: list[str]
    ) -> dict[str, ExtractedPlan]:
        """Extract per-instrument plans by splitting on '### C-{INSTRUMENT}' headers.

        Returns a dict from symbol → ExtractedPlan. Symbols without a parseable
        plan block are omitted (not present in the dict).
        """
        result: dict[str, ExtractedPlan] = {}
        for symbol in instruments:
            # Find this instrument's plan block by anchoring on "### C-SYMBOL"
            marker = f"### C-{symbol}"
            idx = report_text.find(marker)
            if idx == -1:
                continue
            # Block extends until next "### C-" or "## " or end
            after = report_text[idx + len(marker):]
            next_block_relative = -1
            for end_marker in ("\n### C-", "\n## "):
                pos = after.find(end_marker)
                if pos != -1 and (next_block_relative == -1 or pos < next_block_relative):
                    next_block_relative = pos
            if next_block_relative == -1:
                block_text = after
            else:
                block_text = after[:next_block_relative]
            # Now parse the block_text using existing single-plan logic
            plan = self.extract(block_text)
            if plan is not None:
                result[symbol] = plan
        return result
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/test_plan_extractor.py -v`
Expected: all tests pass (5 total: 2 single-plan + 3 multi-plan).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/plan_extractor.py tests/reports/test_plan_extractor.py
git commit -m "feat(reports): PlanExtractor.extract_per_instrument (per-symbol plans)"
```

---

## Task 7: Orchestrator — multi-instrument coordination

**Files:**
- Modify: `src/daytrader/reports/core/orchestrator.py`
- Modify: `tests/reports/test_orchestrator.py`

- [ ] **Step 1: Update tests**

Replace `tests/reports/test_orchestrator.py` content. Use this VALID_REPORT constant (multi-instrument):

```python
VALID_REPORT = (
    "## Lock-in\nstatus\n\n"
    "## Multi-TF Analysis\n"
    "### 📊 MES\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "### 📊 MNQ\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "### 📊 MGC\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n\n"
    "## 突发新闻\nnone\n\n"
    "## C. 计划复核\n\n"
    "### C-MES\n\n**Today's plan**:\n"
    "- Setup: ORB long\n- Direction: long\n- Entry: 5240.00\n"
    "- Stop: 5232.00\n- Target: 5256.00\n- R unit: $50\n\n"
    "**Invalidation conditions**:\n1. below 5232\n2. SPY drop\n3. VIX above 18\n\n"
    "### C-MGC\n\n**Today's plan**:\n"
    "- Setup: VWAP fade\n- Direction: short\n- Entry: 2350.00\n"
    "- Stop: 2355.00\n- Target: 2340.00\n- R unit: $50\n\n"
    "**Invalidation conditions**:\n1. above 2355\n2. DXY drop\n3. Rate cut\n\n"
    "## B. 市场叙事\nnarr\n\n"
    "## A. 建议\nno action\n\n"
    "## 数据快照\nok\n"
)
```

Update `Orchestrator.__init__` calls in tests to use new signature:

```python
orchestrator = Orchestrator(
    state_db=state,
    ib_client=fake_ib,
    ai_analyst=fake_ai,
    contract_path=tmp_path / "missing-contract.md",
    journal_db_path=tmp_path / "missing-journal.db",
    vault_root=tmp_path / "vault",
    fallback_dir=tmp_path / "fallback",
    daily_folder="Daily",
    symbols=["MES", "MNQ", "MGC"],
    tradable_symbols=["MES", "MGC"],
)
```

In `test_orchestrator_run_premarket_persists_plan_and_writes`, expect TWO plan rows (MES + MGC):

```python
mes_plan = state.get_plan_for_date("2026-04-25", "MES")
assert mes_plan is not None
assert mes_plan["setup_name"] == "ORB long"
assert mes_plan["entry"] == pytest.approx(5240.0)

mgc_plan = state.get_plan_for_date("2026-04-25", "MGC")
assert mgc_plan is not None
assert mgc_plan["setup_name"] == "VWAP fade"
assert mgc_plan["entry"] == pytest.approx(2350.0)

# MNQ is context-only, no plan saved
mnq_plan = state.get_plan_for_date("2026-04-25", "MNQ")
assert mnq_plan is None
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/test_orchestrator.py -v`
Expected: tests fail (signature mismatch + missing per-instrument plan logic).

- [ ] **Step 3: Update Orchestrator signature + plan-save loop**

In `src/daytrader/reports/core/orchestrator.py`:

Replace `__init__`:

```python
    def __init__(
        self,
        state_db: StateDB,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        contract_path: Path,
        journal_db_path: Path,
        vault_root: Path,
        fallback_dir: Path,
        daily_folder: str = "Daily",
        symbols: list[str] = None,
        tradable_symbols: list[str] = None,
    ) -> None:
        if symbols is None:
            symbols = ["MES"]
        if tradable_symbols is None:
            tradable_symbols = symbols
        self.state_db = state_db
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.contract_path = Path(contract_path)
        self.journal_db_path = Path(journal_db_path)
        self.vault_root = Path(vault_root)
        self.fallback_dir = Path(fallback_dir)
        self.daily_folder = daily_folder
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
```

In `run_premarket`, replace the `PremarketGenerator(...)` instantiation:

```python
        generator = PremarketGenerator(
            ib_client=self.ib_client,
            ai_analyst=self.ai_analyst,
            symbols=self.symbols,
            tradable_symbols=self.tradable_symbols,
        )
```

Replace the plan-extraction-and-save block (after validation passes):

```python
        # Persist per-tradable plans
        plans = PlanExtractor().extract_per_instrument(
            outcome.report_text, instruments=self.tradable_symbols
        )
        # Write to Obsidian first to capture the report path for plan rows
        writer = ObsidianWriter(
            vault_root=self.vault_root,
            fallback_dir=self.fallback_dir,
            daily_folder=self.daily_folder,
        )
        write_result = writer.write_premarket(
            date_iso=date_et,
            content=outcome.report_text,
        )

        for symbol, plan in plans.items():
            self.state_db.save_plan(
                date_et=date_et,
                instrument=symbol,
                setup_name=plan.setup_name,
                direction=plan.direction,
                entry=plan.entry,
                stop=plan.stop,
                target=plan.target,
                r_unit_dollars=plan.r_unit_dollars,
                invalidations=plan.invalidations,
                raw_plan_text=plan.raw_text,
                source_report_path=str(write_result.path),
                created_at=run_at_utc,
            )
```

Remove the old single-plan extract/save block.

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/test_orchestrator.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/orchestrator.py tests/reports/test_orchestrator.py
git commit -m "feat(reports): Orchestrator multi-instrument (per-tradable plan save)"
```

---

## Task 8: CLI — wire up multi-instrument

**Files:**
- Modify: `src/daytrader/cli/reports.py`

- [ ] **Step 1: Update `run_cmd` to load instruments**

In `src/daytrader/cli/reports.py`, in `run_cmd`, REPLACE the `Orchestrator(...)` instantiation with:

```python
        from daytrader.reports.instruments.definitions import (
            load_instruments,
            tradable_symbols as get_tradable,
        )

        instruments = load_instruments(
            str(project_root / cfg.reports.instruments_yaml)
        )
        all_symbols = sorted(instruments.keys())
        tradable = get_tradable(instruments)

        orchestrator = Orchestrator(
            state_db=state,
            ib_client=ib,
            ai_analyst=ai,
            contract_path=project_root / cfg.journal.contract_path,
            journal_db_path=project_root / cfg.journal.db_path,
            vault_root=vault_root,
            fallback_dir=fallback_dir,
            daily_folder=cfg.obsidian.daily_folder,
            symbols=all_symbols,
            tradable_symbols=tradable,
        )
```

Remove the old `symbol="MES"` parameter.

- [ ] **Step 2: Verify CLI test still passes**

Run: `uv run pytest tests/cli/test_reports_cli.py -v`
Expected: all tests pass (the no-claude test, help test, etc. — none of them invoke the full pipeline).

- [ ] **Step 3: Commit**

```bash
git add src/daytrader/cli/reports.py
git commit -m "feat(reports): CLI run loads symbols + tradable list from instruments.yaml"
```

---

## Task 9: Phase 3 acceptance — full project test pass + manual run prep

**Files:** None (verification + docs only)

- [ ] **Step 1: Full test suite passes**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: ~245+ tests pass (was 234 in Phase 2.5; +tests from Phase 3 modifications).

- [ ] **Step 2: Verify dry-run still works**

Run: `uv run daytrader reports dry-run --type premarket`
Expected: 6 stub lines + "dry-run complete".

- [ ] **Step 3: Update Phase 2 runbook for multi-instrument expectation**

Modify `docs/ops/phase2-runbook.md`. Replace the "What this run does NOT yet do" section with:

```markdown
## What this run does NOT yet do (Phase 4+)

- F. 期货结构 (no OI/COT/basis/term/VolumeProfile) → Phase 4
- Anthropic Web Search for breaking news → Phase 4
- Other report types (intraday/EOD/weekly/night) → Phase 5
- Telegram push (only Obsidian today) → Phase 6
- PDF / chart rendering → Phase 6
- Automatic launchd schedule → Phase 7
```

(Phase 3 has eliminated "Multi-instrument (only MES)" from the gap list.)

Also rename the file copy reference in §"Acceptance criteria" — Phase 3 acceptance now means a SINGLE file with three instrument analyses + two plans.

- [ ] **Step 4: Commit + push**

```bash
git add docs/ops/phase2-runbook.md
git commit -m "docs(reports): runbook update for Phase 3 multi-instrument coverage"
git push
```

- [ ] **Step 5: Live acceptance (manual, requires TWS)**

When TWS is running:

```bash
sqlite3 data/state.db "DELETE FROM reports WHERE date='YYYY-MM-DD';"  # if needed
sqlite3 data/state.db "DELETE FROM plans WHERE date='YYYY-MM-DD';"     # clear prior plans
uv run daytrader reports run --type premarket
```

Expected:
- Pipeline runs ~30-45 sec (3× the bar fetches of Phase 2)
- Output: `Report generated: ~/Documents/DayTrader Vault/Daily/YYYY-MM-DD-premarket.md`
- File is now 8000-12000 chars with MES + MNQ + MGC sections
- SQLite plans table: 2 rows (MES + MGC); no MNQ row
- Idempotent re-run still skips correctly

---

## Summary

After Phase 3, the premarket report goes from MES-only (Phase 2) to **MES + MNQ + MGC** in a single integrated document, with per-tradable-instrument plan formation (MES + MGC each get full C-block; MNQ context-only). Plans extracted and persisted per instrument. ~10 new tests; project total passes.

**Coverage vs spec §3.6:** Phase 2's 70% → Phase 3's **~85%**. Remaining gaps: F. 期货结构 + breaking news → Phase 4.

**Next**: Phase 4 plan (F. 期货结构 + Anthropic Web Search news) — to be written as separate file after Phase 3 lands.
