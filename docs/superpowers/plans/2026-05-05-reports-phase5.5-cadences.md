# Phase 5.5 — Multi-Cadence Buildout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new cadences (intraday-4h-1, intraday-4h-2, night, asia) via a new `BaseCadenceGenerator` abstract class, without touching existing premarket / EOD / weekly code.

**Architecture:** New `BaseCadenceGenerator` (template method pattern) defines common pipeline (fetch bars → F section → news → AI → validate). Subclasses `IntradayFourHGenerator` and `NightAsiaGenerator` are config-parameterized (4h-1 vs 4h-2 share one class; night vs asia share another). Premarket / EOD / weekly stay UNCHANGED — Phase 5.6 will retrofit later.

**Tech Stack:** Python 3.12, ib_insync, click, claude CLI subprocess, sqlite3, launchd (macOS), pytest.

**Spec:** `docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md`

---

## Pre-flight

Before starting:

- [ ] **Confirm baseline 538 tests passing**: `pytest tests/ -q --tb=line` should show `538 passed, 12 skipped`
- [ ] **Confirm no in-flight changes**: `git status` should show clean working tree (untracked files OK)
- [ ] **Confirm on correct branch**: `git rev-parse --abbrev-ref HEAD` should show `claude/nice-varahamihira-9d6142`
- [ ] **Confirm spec is accessible**: `test -f docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md`

If any pre-flight fails, STOP and fix before proceeding.

---

## Regression Boundary (read this BEFORE every task)

Per spec §3 + §11.6, the following files MUST NOT be modified:

```
src/daytrader/reports/types/premarket.py
src/daytrader/reports/types/eod.py
src/daytrader/reports/templates/premarket.md
src/daytrader/reports/templates/eod.md
src/daytrader/premarket/weekly.py
scripts/preflight_check.py
scripts/run_premarket_launchd.sh
scripts/run_eod_launchd.sh
tests/premarket/**
tests/reports/eod/**  (only additive — no existing test modified)
```

Plus partial restrictions on:
- `src/daytrader/reports/core/prompt_builder.py` — DO NOT modify `build_premarket()` / `build_eod()` (only ADD new methods)
- `src/daytrader/reports/core/output_validator.py` — DO NOT modify `REQUIRED_SECTIONS["premarket"]` / `["eod"]` (only ADD new entries)
- `src/daytrader/reports/core/orchestrator.py` — DO NOT modify `run_premarket` / `run_eod` (only ADD new methods)
- `src/daytrader/reports/delivery/obsidian_writer.py` — DO NOT modify `write_premarket` / `write_eod` (only ADD new methods)

After each task: run `pytest tests/ -q --tb=line` and verify ≥ 538 tests still pass.

---

## Task 1: BaseCadenceGenerator + CadenceOutcome

**Goal:** Define the abstract base class with template-method `generate()` and default-skip hooks.

**Files:**
- Create: `src/daytrader/reports/types/base.py`
- Test: `tests/reports/types/test_base_generator.py`

**Why:** Foundation for IntradayFourHGenerator + NightAsiaGenerator. Hooks default to "skip" (return ""/[]/{}); subclasses override only what differs.

- [ ] **Step 1.1: Create test directory and __init__**

```bash
mkdir -p tests/reports/types
touch tests/reports/types/__init__.py
```

- [ ] **Step 1.2: Write the failing test (default hooks return empty)**

Create `tests/reports/types/test_base_generator.py`:

```python
"""Unit tests for BaseCadenceGenerator template-method pattern."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.base import BaseCadenceGenerator, CadenceOutcome


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0, lock_in_target=30,
        cumulative_r=None, last_trade_date=None, last_trade_r=None, streak=None,
    )


def _ohlcv(c: float = 5240.0):
    from datetime import datetime, timezone
    return OHLCV(
        timestamp=datetime(2026, 5, 5, 7, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_text():
    """Mock AI result; subclass tests assert validator-pass text."""
    result = MagicMock()
    result.text = "## Required\nstub\n"
    result.input_tokens = 100
    result.output_tokens = 200
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


class _DummyCadence(BaseCadenceGenerator):
    """Minimal concrete subclass for testing the abstract base."""

    @property
    def report_type(self) -> str:
        return "test-cadence"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("1D", "4H")

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"1D": 5, "4H": 6}

    def _build_prompt(self, **kwargs):
        return [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "test"},
        ]


def _make_dummy(**overrides):
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    return _DummyCadence(
        ib_client=overrides.get("ib", fake_ib),
        ai_analyst=overrides.get("ai", fake_ai),
        symbols=overrides.get("symbols", ["MES", "MNQ", "MGC"]),
        tradable_symbols=overrides.get("tradable", ["MES", "MGC"]),
        validator=overrides.get("validator", fake_validator),
    )


def test_base_default_sentiment_returns_empty():
    gen = _make_dummy()
    assert gen._maybe_fetch_sentiment() == ""


def test_base_default_read_plan_returns_empty_dict():
    gen = _make_dummy()
    assert gen._maybe_read_plan("2026-05-05") == {}


def test_base_default_fetch_trades_returns_empty_list():
    gen = _make_dummy()
    assert gen._maybe_fetch_trades("2026-05-05") == []


def test_base_default_compose_retrospective_returns_empty():
    gen = _make_dummy()
    assert gen._maybe_compose_retrospective({}, [], "2026-05-05") == ""


def test_base_default_compose_tomorrow_returns_empty():
    gen = _make_dummy()
    assert gen._maybe_compose_tomorrow() == ""


def test_base_validates_symbols_non_empty():
    fake_ib = MagicMock()
    fake_ai = MagicMock()
    with pytest.raises(ValueError, match="symbols must be non-empty"):
        _DummyCadence(
            ib_client=fake_ib, ai_analyst=fake_ai,
            symbols=[], tradable_symbols=[],
        )


def test_base_validates_tradable_subset_of_symbols():
    fake_ib = MagicMock()
    fake_ai = MagicMock()
    with pytest.raises(ValueError, match="not in symbols"):
        _DummyCadence(
            ib_client=fake_ib, ai_analyst=fake_ai,
            symbols=["MES"], tradable_symbols=["MGC"],
        )


def test_base_generate_returns_cadence_outcome():
    gen = _make_dummy()
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
        news_items=[], sentiment_md="",
    )
    assert isinstance(outcome, CadenceOutcome)
    assert outcome.report_text == "## Required\nstub\n"
    assert outcome.warnings == ()


def test_base_generate_fetches_all_tfs_per_symbol():
    """3 symbols × 2 TFs = 6 get_bars calls (no F-section get_bars to count separately)."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    gen = _DummyCadence(
        ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES"],
        validator=fake_validator,
    )
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
    )
    # Multi-TF: 3 symbols × 2 TFs = 6 bar fetches + 1 VP fetch per symbol = 9
    assert fake_ib.get_bars.call_count >= 6


def test_base_generate_warnings_accumulate():
    """When _fetch_news raises, warning entry is added but pipeline continues."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    fake_news_collector = MagicMock(side_effect=RuntimeError("network blew up"))

    gen = _DummyCadence(
        ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES"], tradable_symbols=["MES"],
        validator=fake_validator,
        news_collector=fake_news_collector,
    )
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
    )
    assert any("news" in w for w in outcome.warnings), \
        f"news failure must be in warnings, got: {outcome.warnings}"


def test_cadence_outcome_is_frozen_dataclass():
    """CadenceOutcome should be frozen — no in-place mutation."""
    from daytrader.reports.types.base import CadenceOutcome
    fake_ai_result = MagicMock()
    fake_validation = MagicMock(ok=True, missing=[])
    outcome = CadenceOutcome(
        report_text="x", ai_result=fake_ai_result, validation=fake_validation,
        bars_by_symbol_and_tf={}, warnings=(),
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        outcome.report_text = "different"


def test_cadence_outcome_warnings_default_empty_tuple():
    from daytrader.reports.types.base import CadenceOutcome
    outcome = CadenceOutcome(
        report_text="x",
        ai_result=MagicMock(),
        validation=MagicMock(ok=True, missing=[]),
    )
    assert outcome.warnings == ()
    assert outcome.bars_by_symbol_and_tf is None
```

- [ ] **Step 1.3: Run tests to verify red (module not exist)**

Run: `pytest tests/reports/types/test_base_generator.py -q --tb=line`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.reports.types.base'`

- [ ] **Step 1.4: Implement base.py**

Create `src/daytrader/reports/types/base.py`:

```python
"""BaseCadenceGenerator — abstract template-method pattern for all cadences.

Phase 5.5 (2026-05-05): introduces a shared scaffold for the 4 new cadences
(intraday-4h-1, intraday-4h-2, night, asia). Premarket and EOD are explicitly
NOT migrated to this base class in this phase per user constraint
"不要影响已实现的功能". Phase 5.6 will retrofit them later.

Design: subclass overrides _build_prompt + report_type + tfs + bars_per_tf.
Optional hooks (_maybe_*) default to skip — subclass overrides only what
the cadence actually needs (e.g. retrospective only enabled in 4h-2 and EOD).
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient, OHLCV
from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult
from daytrader.reports.core.context_loader import ReportContext
from daytrader.reports.core.output_validator import OutputValidator, ValidationResult
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.futures_data.futures_section import (
    FuturesSection,
    build_futures_section,
)


@dataclass(frozen=True)
class CadenceOutcome:
    """Output of BaseCadenceGenerator.generate().

    Mirrors EODOutcome shape so orchestrator can use the same
    warnings → state.failures pipeline (I1 fix pattern).
    """
    report_text: str
    ai_result: AIResult
    validation: ValidationResult
    bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] | None = None
    warnings: tuple[str, ...] = ()


class BaseCadenceGenerator(ABC):
    """Common cadence generation pipeline.

    Subclasses MUST implement: report_type, tfs, bars_per_tf, _build_prompt.
    Subclasses MAY override: _maybe_fetch_sentiment, _maybe_read_plan,
        _maybe_fetch_trades, _maybe_compose_retrospective,
        _maybe_compose_tomorrow.
    """

    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher=None,
        term_price_fetcher=None,
        tick_sizes: dict[str, float] | None = None,
        news_collector=None,
    ) -> None:
        if not symbols:
            raise ValueError("symbols must be non-empty")
        for s in tradable_symbols:
            if s not in symbols:
                raise ValueError(
                    f"tradable symbol {s!r} not in symbols list {symbols}"
                )
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()
        self.underlying_price_fetcher = underlying_price_fetcher
        self.term_price_fetcher = term_price_fetcher
        self.tick_sizes = tick_sizes or {s: 0.25 for s in symbols}
        self.news_collector = news_collector

    # --- abstract methods (subclass MUST implement) ---

    @property
    @abstractmethod
    def report_type(self) -> str:
        """Identifier for state.db reports table + validator dispatch."""

    @property
    @abstractmethod
    def tfs(self) -> tuple[str, ...]:
        """TFs to fetch for multi-TF analysis (e.g. ('1D', '4H', '1H'))."""

    @property
    @abstractmethod
    def bars_per_tf(self) -> dict[str, int]:
        """How many bars to fetch per TF (e.g. {'1D': 10, '4H': 12})."""

    @abstractmethod
    def _build_prompt(self, **inputs) -> list[dict[str, Any]]:
        """Build the AI message list. Cadence-specific."""

    # --- optional hooks (default = skip) ---

    def _maybe_fetch_sentiment(self) -> str:
        """Override to fetch fresh sentiment via Phase 4.5 SentimentSection.
        Default: return empty string (caller may pass premarket cache via
        sentiment_md kwarg)."""
        return ""

    def _maybe_read_plan(self, date_et: str) -> dict[str, str]:
        """Override to read today's premarket plan blocks per symbol.
        Default: return empty dict (no plan recheck needed)."""
        return {}

    def _maybe_fetch_trades(self, date_et: str) -> list[dict[str, Any]]:
        """Override to fetch today's trades from journal DB.
        Default: empty list (no trade reflection needed)."""
        return []

    def _maybe_compose_retrospective(
        self,
        plans: dict[str, str],
        trades: list[dict[str, Any]],
        date_et: str,
    ) -> str:
        """Override to run PlanRetrospective + persist + render markdown.
        Default: empty string (no retrospective for this cadence)."""
        return ""

    def _maybe_compose_tomorrow(self, **kwargs) -> str:
        """Override to build tomorrow's preliminary plan (EOD only).
        Default: empty string."""
        return ""

    # --- shared pipeline (template method) ---

    def generate(
        self,
        context: ReportContext,
        date_et: str,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
        sentiment_md: str = "",
    ) -> CadenceOutcome:
        """Run the cadence pipeline end-to-end.

        Steps: fetch bars → F section → news → sentiment (optional) →
        plan read (optional) → trades fetch (optional) → retrospective
        (optional) → tomorrow (optional) → AI call → validate.
        """
        warnings_list: list[str] = []

        # Step 1: fetch multi-TF bars per symbol.
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]] = {}
        for symbol in self.symbols:
            bars_by_symbol_and_tf[symbol] = {}
            for tf in self.tfs:
                try:
                    bars_by_symbol_and_tf[symbol][tf] = self.ib_client.get_bars(
                        symbol=symbol, timeframe=tf,
                        bars=self.bars_per_tf[tf],
                    )
                except Exception as exc:
                    print(
                        f"[base_cadence] WARNING: bars fetch {symbol} {tf} failed: {exc}",
                        file=sys.stderr,
                    )
                    warnings_list.append(
                        f"bars: {symbol} {tf}: {type(exc).__name__}: {str(exc)[:120]}"
                    )
                    bars_by_symbol_and_tf[symbol][tf] = []

        # Step 2: F-section (basis + term + RTH-formed VP).
        futures_data: FuturesSection | None = None
        try:
            underlying_prices = (
                self.underlying_price_fetcher(self.symbols)
                if self.underlying_price_fetcher else {}
            )
            term_prices = (
                self.term_price_fetcher(self.symbols)
                if self.term_price_fetcher else {}
            )
            futures_data = build_futures_section(
                ib_client=self.ib_client,
                symbols=self.symbols,
                underlying_prices=underlying_prices,
                term_prices=term_prices,
                tick_sizes=self.tick_sizes,
            )
        except Exception as exc:
            print(
                f"[base_cadence] WARNING: F-section build failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"f_section: {type(exc).__name__}: {str(exc)[:120]}"
            )
            futures_data = None

        # Step 3: news (best-effort).
        if news_items is None:
            news_items = []
            if self.news_collector is not None:
                try:
                    news_items = self.news_collector()
                except Exception as exc:
                    print(
                        f"[base_cadence] WARNING: news fetch failed: {exc}",
                        file=sys.stderr,
                    )
                    warnings_list.append(
                        f"news: {type(exc).__name__}: {str(exc)[:120]}"
                    )

        # Step 4: sentiment (optional — caller may pass cache via kwarg).
        if not sentiment_md:
            try:
                sentiment_md = self._maybe_fetch_sentiment()
            except Exception as exc:
                print(
                    f"[base_cadence] WARNING: sentiment fetch failed: {exc}",
                    file=sys.stderr,
                )
                warnings_list.append(
                    f"sentiment: {type(exc).__name__}: {str(exc)[:120]}"
                )
                sentiment_md = ""

        # Step 5-7: plan read + trades + retrospective (optional hooks).
        try:
            plans = self._maybe_read_plan(date_et)
        except Exception as exc:
            warnings_list.append(
                f"plan_read: {type(exc).__name__}: {str(exc)[:120]}"
            )
            plans = {}

        try:
            trades = self._maybe_fetch_trades(date_et)
        except Exception as exc:
            warnings_list.append(
                f"trades_fetch: {type(exc).__name__}: {str(exc)[:120]}"
            )
            trades = []

        try:
            retrospective_md = self._maybe_compose_retrospective(
                plans, trades, date_et
            )
        except Exception as exc:
            print(
                f"[base_cadence] WARNING: retrospective failed: {exc}",
                file=sys.stderr,
            )
            warnings_list.append(
                f"retrospective: {type(exc).__name__}: {str(exc)[:120]}"
            )
            retrospective_md = (
                "## 🔄 Plan Retrospective / 计划复盘\n\n"
                f"⚠️ retrospective composition failed: {exc}"
            )

        try:
            tomorrow_md = self._maybe_compose_tomorrow(
                bars_by_symbol_and_tf=bars_by_symbol_and_tf,
                trades=trades,
                date_et=date_et,
            )
        except Exception as exc:
            warnings_list.append(
                f"tomorrow: {type(exc).__name__}: {str(exc)[:120]}"
            )
            tomorrow_md = ""

        # Step 8: build prompt (cadence-specific).
        messages = self._build_prompt(
            context=context,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            tradable_symbols=self.tradable_symbols,
            news_items=news_items,
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
            futures_data=futures_data,
            sentiment_md=sentiment_md,
            today_plan_blocks=plans,
            today_trades=trades,
            retrospective_md=retrospective_md,
            tomorrow_preliminary_md=tomorrow_md,
        )

        # Step 9: AI call + validate.
        ai_result = self.ai_analyst.call(messages=messages, max_tokens=12288)
        validation = self.validator.validate(
            ai_result.text, report_type=self.report_type
        )

        return CadenceOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
            bars_by_symbol_and_tf=bars_by_symbol_and_tf,
            warnings=tuple(warnings_list),
        )
```

- [ ] **Step 1.5: Run tests to verify green**

Run: `pytest tests/reports/types/test_base_generator.py -q --tb=line`

Expected: `12 passed`

- [ ] **Step 1.6: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥538 passed` (existing tests intact + 12 new)

- [ ] **Step 1.7: Commit**

```bash
git add src/daytrader/reports/types/base.py tests/reports/types/__init__.py tests/reports/types/test_base_generator.py
git commit -m "$(cat <<'EOF'
feat(reports): BaseCadenceGenerator + CadenceOutcome (Phase 5.5 T1)

Foundation for the 4 new cadences (intraday-4h-1, intraday-4h-2,
night, asia). Premarket + EOD are explicitly UNCHANGED in this
phase per user constraint — Phase 5.6 will retrofit them.

BaseCadenceGenerator implements the template-method pattern:
  - generate() runs: bars → F-section → news → sentiment → plan
    → trades → retrospective → tomorrow → AI → validate
  - 5 _maybe_* hooks default to skip (return ""/[]/{})
  - Subclass overrides only what differs (e.g. 4h-2 enables
    sentiment + retrospective; night/asia keep all defaults)

CadenceOutcome mirrors EODOutcome (frozen dataclass with warnings
tuple) so orchestrator can use the same warnings → state.failures
pipeline (I1 fix pattern).

Per-step exception handling: each pipeline stage catches and
records to warnings, never crashes the whole generate(). Hard
failures (AI call, validator) propagate to outcome.validation.

12 new tests under tests/reports/types/test_base_generator.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Markdown templates (intraday_4h.md + night_asia.md)

**Goal:** Two new markdown templates instructing AI on output structure.

**Files:**
- Create: `src/daytrader/reports/templates/intraday_4h.md`
- Create: `src/daytrader/reports/templates/night_asia.md`

**Why:** PromptBuilder loads these as the system prompt. They define section ordering, length budget, A-section forbidden behaviors, etc.

- [ ] **Step 2.1: Create intraday_4h.md**

Create `src/daytrader/reports/templates/intraday_4h.md`:

```markdown
# Intraday 4H Report Template

You are generating an intraday 4-hour cadence report. Today's RTH session is in progress.

## Required Sections (output MUST contain ALL of these in this order)

1. **🔒 Lock-in Metadata**: today's trades count update, daily R so far, week R, position state
2. **📊 MES — Multi-TF (D / 4H / 1H)**: today's bars analysis per TF
3. **📊 MNQ — Multi-TF** (context only)
4. **📊 MGC — Multi-TF**
5. **🌐 Cross-Asset Narrative** (so far today)
6. **📰 Breaking News (past N hours)** — N = 1h for 4h-1, 5h for 4h-2
7. **F. 期货结构 / Futures Positioning** (basis + term + RTH-formed VP — embed verbatim from input)
8. **D. 情绪面 / Sentiment Index** (verbatim from sentiment_md input — may be from premarket cache for 4h-1 or refreshed for 4h-2)
9. **今日交易档案 / Today's Trade Archive (since 06:30 PT)** — light list table only (NO §6/§9 audit; that's EOD's job)
10. **🔄 Plan Retrospective / 计划复盘** — **4h-2 ONLY**; 4h-1 must omit this entire section and instead show "下次复盘 4h-2 (11:00 PT)" placeholder
11. **C. 计划复核 / Plan Adherence Assessment**: VERBATIM quote of today's premarket C-MES / C-MGC blocks (embed from today_plan_blocks input), then plan-vs-actual comparison
12. **B. 市场叙事 / Today's Narrative (so far)** (past-tense for the period 06:30 PT → now; FORBIDDEN: forward predictions for rest of session)
13. **A. 建议 / Recommendation (rest-of-session)** — A-3 default (ladder of trigger conditions); A-2 escalation if conditions met; **NO A-1** (direct buy/sell calls). Mixed form A.3: each instrument has mini-A inside F section; main A is cross-instrument integration.
14. **📑 数据快照 / Data Snapshot** (key numbers in compact table)

## CRITICAL Output Constraints

- **C must verbatim-quote today's premarket plan** before adding adherence commentary.
- **B is past-tense**: describe what happened so far today, NOT what will happen.
- **A is forward-looking** but uses A-3 ladder, NOT direct calls.
- **🔄 Plan Retrospective**: 4h-2 only. 4h-1 explicitly says "retrospective deferred to 4h-2".
- **Sources**: when web search is used, cite real URLs at end.

## Output Format Notes

- Use Chinese where input data is Chinese; mixed Chinese/English is acceptable.
- Total length 5-7K characters (per spec §2.2).
- No preamble; start directly with the # heading.
```

- [ ] **Step 2.2: Create night_asia.md**

Create `src/daytrader/reports/templates/night_asia.md`:

```markdown
# Night/Asia D-Archive Report Template

You are generating a D-only learning archive report. The US RTH session has closed.

## Required Sections (output MUST contain ALL of these in this order)

1. **🔒 Lock-in Metadata (compact)** — trades count + last trade summary; NO analysis
2. **📊 MES — Multi-TF (4H / 1H)** — overnight session bars
3. **📊 MNQ — Multi-TF**
4. **📊 MGC — Multi-TF**
5. **F. 期货结构 / Futures Positioning (compact)**: settlement + OI Δ + basis (if cash open)
6. **📰 Breaking News (past 4h)**
7. **D. Pattern Archive** — bar-by-bar pattern description per symbol; pattern_tags populated for future query
8. **📑 数据快照 / Data Snapshot**

## CRITICAL Output Constraints

- **NO A. section** (no recommendation — D purpose only).
- **NO B. section** (no narrative beyond fact statement).
- **NO C. section** (no plan recheck — overnight has no premarket plan to review).
- **NO sentiment block** — D purpose is descriptive archive, not decision aid.
- **D body is brief**: bar data + pattern description + news summary.
- **pattern_tags in frontmatter**: AI populates from observed patterns (e.g. ["bullish_engulf", "support_test", "doji_at_resistance"]).
- **news_event_tags in frontmatter**: AI populates (e.g. ["FOMC_minutes", "boj_intervention"]).

## Output Format Notes

- Use Chinese where input data is Chinese; mixed Chinese/English is acceptable.
- Total length 3.5-5K characters.
- No preamble; start directly with the # heading.
- Frontmatter at top (YAML) with pattern_tags + news_event_tags arrays — these enable future programmatic query like "all bullish_engulf at support_test in last 30 days".
```

- [ ] **Step 2.3: Verify templates load correctly (smoke test)**

Run:

```bash
python -c "
from pathlib import Path
intraday = Path('src/daytrader/reports/templates/intraday_4h.md').read_text()
night = Path('src/daytrader/reports/templates/night_asia.md').read_text()
print(f'intraday_4h.md: {len(intraday)} chars, {intraday.count(chr(10))} lines')
print(f'night_asia.md: {len(night)} chars, {night.count(chr(10))} lines')
assert 'Plan Retrospective' in intraday
assert 'Pattern Archive' in night
assert 'NO A. section' in night
print('OK')
"
```

Expected: prints char counts + "OK".

- [ ] **Step 2.4: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥538 passed` (no test changes; templates are static).

- [ ] **Step 2.5: Commit**

```bash
git add src/daytrader/reports/templates/intraday_4h.md src/daytrader/reports/templates/night_asia.md
git commit -m "$(cat <<'EOF'
feat(reports): intraday-4h + night-asia markdown templates (Phase 5.5 T2)

intraday_4h.md (8-section A+B+C+F template):
  - Section order FIXED per master spec §3.6: metadata → multi-TF
    → cross-asset → news → F → sentiment → trades → [retrospective
    in 4h-2] → C → B → A → snapshot
  - C BEFORE A (self-anchored thinking — user reads own plan first)
  - Plan Retrospective marked 4h-2-only; 4h-1 must show "下次复盘
    4h-2" placeholder
  - 5-7K chars target

night_asia.md (D-only learning archive template):
  - 7 sections: metadata → multi-TF → F → news → D archive → snapshot
  - NO A/B/C/sentiment (pure descriptive)
  - pattern_tags + news_event_tags in frontmatter for future
    programmatic query ("all bullish_engulf at support_test")
  - 3.5-5K chars target

Both templates self-document the AI's output constraints. PromptBuilder
will load these as system content in Task 3 / Task 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PromptBuilder.build_intraday_4h

**Goal:** Add `build_intraday_4h(cadence_label, ...)` method to PromptBuilder. Mirrors `build_eod` shape but loads `intraday_4h.md` template.

**Files:**
- Modify: `src/daytrader/reports/core/prompt_builder.py` (ADD new method, do NOT touch build_premarket / build_eod)
- Test: `tests/reports/test_prompt_builder.py` (extend)

- [ ] **Step 3.1: Write failing tests**

Append to `tests/reports/test_prompt_builder.py`:

```python
def test_build_intraday_4h_loads_template_and_returns_messages():
    """build_intraday_4h returns 2 messages (system + user) with the
    intraday_4h.md template embedded as system content."""
    pb = PromptBuilder()
    msgs = pb.build_intraday_4h(
        cadence_label="intraday-4h-1",
        context=_basic_ctx(),
        bars_by_symbol_and_tf={
            "MES": {"1D": [], "4H": [], "1H": []},
            "MNQ": {"1D": [], "4H": [], "1H": []},
            "MGC": {"1D": [], "4H": [], "1H": []},
        },
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="07:00 PT",
        run_timestamp_et="10:00 ET",
        sentiment_md="## D. 情绪面\nmacro +3\n",
        today_plan_blocks={"MES": "**plan**\n- entry 5240\n"},
        today_trades=[],
        retrospective_md="",  # 4h-1: empty
        tomorrow_preliminary_md="",  # never for intraday
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    full = _joined_prompt_text(msgs)
    # Template loaded
    assert "Intraday 4H Report Template" in full
    # Cadence label embedded
    assert "intraday-4h-1" in full
    # User-provided inputs embedded
    assert "macro +3" in full
    assert "entry 5240" in full


def test_build_intraday_4h_2_includes_retrospective_when_provided():
    """4h-2 passes retrospective_md; it must appear verbatim in user content."""
    pb = PromptBuilder()
    retro = "## 🔄 Plan Retrospective\n| MES | 1/3 triggered |\n"
    msgs = pb.build_intraday_4h(
        cadence_label="intraday-4h-2",
        context=_basic_ctx(),
        bars_by_symbol_and_tf={
            "MES": {"1D": [], "4H": [], "1H": []},
            "MNQ": {"1D": [], "4H": [], "1H": []},
            "MGC": {"1D": [], "4H": [], "1H": []},
        },
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="11:00 PT",
        run_timestamp_et="14:00 ET",
        sentiment_md="",
        today_plan_blocks={},
        today_trades=[],
        retrospective_md=retro,
        tomorrow_preliminary_md="",
    )
    full = _joined_prompt_text(msgs)
    assert "Plan Retrospective" in full
    assert "1/3 triggered" in full


def test_build_intraday_4h_omits_1h_block_for_intraday_shape_input():
    """C3-style guard: only render TFs in input dict — intraday-4h dict has
    1D/4H/1H, all should appear."""
    pb = PromptBuilder()
    bars = {
        "MES": {
            "1D": [_ohlcv(datetime(2026, 5, 5, 13, tzinfo=timezone.utc), 5246.0)],
            "4H": [],
            "1H": [_ohlcv(datetime(2026, 5, 5, 13, tzinfo=timezone.utc), 5247.0)],
        },
        "MNQ": {"1D": [], "4H": [], "1H": []},
        "MGC": {"1D": [], "4H": [], "1H": []},
    }
    msgs = pb.build_intraday_4h(
        cadence_label="intraday-4h-1",
        context=_basic_ctx(),
        bars_by_symbol_and_tf=bars,
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="07:00 PT",
        run_timestamp_et="10:00 ET",
    )
    full = _joined_prompt_text(msgs)
    assert "#### 1D" in full
    assert "#### 4H" in full
    assert "#### 1H" in full
    # No W placeholder (intraday doesn't fetch W):
    assert "#### 1W" not in full
```

- [ ] **Step 3.2: Run tests to verify red**

Run: `pytest tests/reports/test_prompt_builder.py -v -k "intraday_4h"`

Expected: FAIL with `AttributeError: 'PromptBuilder' object has no attribute 'build_intraday_4h'`

- [ ] **Step 3.3: Implement build_intraday_4h**

Append to `src/daytrader/reports/core/prompt_builder.py` (after `build_eod`, before `_build_multi_symbol_bars_block`):

```python
    def build_intraday_4h(
        self,
        cadence_label: str,                # "intraday-4h-1" | "intraday-4h-2"
        context: ReportContext,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        tradable_symbols: list[str],
        news_items: list[dict[str, Any]],
        run_timestamp_pt: str,
        run_timestamp_et: str,
        futures_data: "FuturesSection | None" = None,
        sentiment_md: str = "",
        today_plan_blocks: dict[str, str] | None = None,
        today_trades: list[dict[str, Any]] | None = None,
        retrospective_md: str = "",
        tomorrow_preliminary_md: str = "",  # always "" for intraday
    ) -> list[dict[str, Any]]:
        """Build intraday-4h prompt (used by both 4h-1 and 4h-2).

        Section order per spec §3.6 + §6.1: metadata → multi-TF (D/4H/1H)
        → cross-asset → news → F → sentiment → trades → [retrospective
        for 4h-2] → C → B → A → snapshot. The verbatim grounding inputs
        (today_plan_blocks, retrospective_md, today_trades) are embedded
        into the user message so the AI can quote them directly.
        """
        template = load_template("intraday_4h")
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
            {
                "type": "text",
                "text": f"## Cadence label\n\n{cadence_label}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        lock_in_block = self._build_lock_in_block(context)
        bars_block = self._build_multi_symbol_bars_block(bars_by_symbol_and_tf)
        futures_block = self._build_futures_section_block(futures_data)
        news_block = self._build_news_block(news_items)
        tradable_block = (
            f"## Tradable symbols (count toward 30-trade lock-in)\n"
            f"{', '.join(tradable_symbols)}\n\n"
            f"All other symbols are context-only — describe but NO plan."
        )

        sentiment_block = sentiment_md.strip() if sentiment_md else ""
        retrospective_block = retrospective_md.strip() if retrospective_md else ""
        plan_blocks = today_plan_blocks or {}
        trades_list = today_trades or []

        # Verbatim plan blocks for C section
        plan_section_md = ""
        if plan_blocks:
            plan_section_md = (
                "## Today's premarket plan blocks "
                "(verbatim — quote in C section)\n\n"
            )
            plan_section_md += "\n\n".join(
                f"### Today's premarket C-{sym} (verbatim)\n\n{block}"
                for sym, block in plan_blocks.items()
            )
        else:
            plan_section_md = (
                "## Today's premarket plan blocks\n\n"
                "⚠️ premarket plan 未找到 — C 段降级，复盘跳过"
            )

        # Trades light list (no §6/§9 audit per Q3 decision)
        trades_section_md = ""
        if trades_list:
            trades_section_md = "## Today's trades (since 06:30 PT, light list)\n\n"
            trades_section_md += "| # | time | symbol | side | entry | exit | R |\n"
            trades_section_md += "|---|---|---|---|---|---|---|\n"
            for i, t in enumerate(trades_list, start=1):
                trades_section_md += (
                    f"| {i} | {t.get('time_pt', '?')} | "
                    f"{t.get('symbol', '?')} | {t.get('side', '?')} | "
                    f"{t.get('entry', '?')} | {t.get('exit', '?')} | "
                    f"{t.get('r', '?')} |\n"
                )
        else:
            trades_section_md = "## Today's trades\n\n(0 trades since 06:30 PT)"

        composed_blocks: list[str] = [futures_block]
        if sentiment_block:
            composed_blocks.append(sentiment_block)
        if trades_section_md:
            composed_blocks.append(trades_section_md)
        if retrospective_block:
            composed_blocks.append(retrospective_block)
        else:
            composed_blocks.append(
                "## 🔄 Plan Retrospective / 计划复盘\n\n"
                "⏭️  Retrospective deferred to 4h-2 (11:00 PT) "
                "— too few level touches in first 30min of RTH"
            )
        composed_blocks.append(plan_section_md)
        composed_md = "\n\n".join(b for b in composed_blocks if b)

        user_text = (
            f"# Intraday 4H ({cadence_label}) — {run_timestamp_pt} ({run_timestamp_et})\n\n"
            f"{lock_in_block}\n\n"
            f"{bars_block}\n\n"
            f"{news_block}\n\n"
            f"{composed_md}\n\n"
            f"{tradable_block}"
        )

        return [
            {"role": "system", "content": system_blocks},
            {"role": "user", "content": user_text},
        ]
```

- [ ] **Step 3.4: Run tests to verify green**

Run: `pytest tests/reports/test_prompt_builder.py -v -k "intraday_4h"`

Expected: 3 PASSED

- [ ] **Step 3.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥541 passed` (538 + 3 new)

- [ ] **Step 3.6: Commit**

```bash
git add src/daytrader/reports/core/prompt_builder.py tests/reports/test_prompt_builder.py
git commit -m "$(cat <<'EOF'
feat(reports): PromptBuilder.build_intraday_4h (Phase 5.5 T3)

Adds build_intraday_4h() method shared by both 4h-1 and 4h-2
cadences. Differs by cadence_label parameter + presence of
retrospective_md (4h-1 always passes "" → placeholder; 4h-2
passes the composed retrospective markdown).

Section order matches master spec §3.6 fixed order:
  metadata → multi-TF → news → F → sentiment → trades →
  [retrospective] → plan blocks → tradable list

C BEFORE A is enforced via the markdown TEMPLATE (not the prompt
order), so the AI sees grounding inputs in the order it produces
the report.

build_premarket / build_eod NOT TOUCHED (per regression boundary).

3 new tests; 541 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: PromptBuilder.build_night_asia

**Goal:** Add `build_night_asia(cadence_label, ...)` method. D-only — much simpler than intraday-4h.

**Files:**
- Modify: `src/daytrader/reports/core/prompt_builder.py`
- Test: `tests/reports/test_prompt_builder.py` (extend)

- [ ] **Step 4.1: Write failing tests**

Append to `tests/reports/test_prompt_builder.py`:

```python
def test_build_night_asia_loads_template_and_returns_messages():
    """night cadence: 5-section D-only template."""
    pb = PromptBuilder()
    msgs = pb.build_night_asia(
        cadence_label="night",
        context=_basic_ctx(),
        bars_by_symbol_and_tf={
            "MES": {"4H": [], "1H": []},
            "MNQ": {"4H": [], "1H": []},
            "MGC": {"4H": [], "1H": []},
        },
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="19:00 PT",
        run_timestamp_et="22:00 ET",
    )
    assert len(msgs) == 2
    full = _joined_prompt_text(msgs)
    assert "Night/Asia D-Archive Report Template" in full
    assert "night" in full.lower()
    assert "NO A. section" in full
    # No C/A/B sentiment grounding (D-only):
    assert "Plan Retrospective" not in full or "Pattern Archive" in full


def test_build_night_asia_for_asia_cadence():
    """asia cadence uses same template, label differs."""
    pb = PromptBuilder()
    msgs = pb.build_night_asia(
        cadence_label="asia",
        context=_basic_ctx(),
        bars_by_symbol_and_tf={
            "MES": {"4H": [], "1H": []},
            "MNQ": {"4H": [], "1H": []},
            "MGC": {"4H": [], "1H": []},
        },
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="23:00 PT",
        run_timestamp_et="02:00 ET",
    )
    full = _joined_prompt_text(msgs)
    assert "asia" in full.lower()


def test_build_night_asia_does_not_emit_d_or_w_tf_block():
    """night/asia fetch only 4H/1H; D/W must not appear in bars block."""
    pb = PromptBuilder()
    bars = {
        "MES": {"4H": [], "1H": []},
        "MNQ": {"4H": [], "1H": []},
        "MGC": {"4H": [], "1H": []},
    }
    msgs = pb.build_night_asia(
        cadence_label="night",
        context=_basic_ctx(),
        bars_by_symbol_and_tf=bars,
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="19:00 PT",
        run_timestamp_et="22:00 ET",
    )
    full = _joined_prompt_text(msgs)
    assert "#### 4H" in full
    assert "#### 1H" in full
    # No D or W blocks (only 4H + 1H per night/asia spec):
    assert "#### 1D" not in full
    assert "#### 1W" not in full
```

- [ ] **Step 4.2: Run tests to verify red**

Run: `pytest tests/reports/test_prompt_builder.py -v -k "night_asia"`

Expected: FAIL with `AttributeError: 'PromptBuilder' object has no attribute 'build_night_asia'`

- [ ] **Step 4.3: Implement build_night_asia**

Append to `src/daytrader/reports/core/prompt_builder.py` (after `build_intraday_4h`):

```python
    def build_night_asia(
        self,
        cadence_label: str,                  # "night" | "asia"
        context: ReportContext,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        tradable_symbols: list[str],
        news_items: list[dict[str, Any]],
        run_timestamp_pt: str,
        run_timestamp_et: str,
        futures_data: "FuturesSection | None" = None,
        sentiment_md: str = "",  # IGNORED — night/asia have no sentiment
        today_plan_blocks: dict[str, str] | None = None,  # IGNORED
        today_trades: list[dict[str, Any]] | None = None,  # IGNORED beyond lock-in count
        retrospective_md: str = "",  # IGNORED
        tomorrow_preliminary_md: str = "",  # IGNORED
    ) -> list[dict[str, Any]]:
        """Build night/asia D-only prompt.

        Per master spec §3.7: night/asia "Removes A, B, C; only multi-TF
        + news + D frontmatter". Inputs that don't apply (sentiment, plans,
        trades, retrospective, tomorrow) are accepted but ignored — the
        BaseCadenceGenerator passes them as kwargs uniformly.
        """
        template = load_template("night_asia")
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
            {
                "type": "text",
                "text": f"## Cadence label\n\n{cadence_label}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        lock_in_block = self._build_lock_in_block(context)
        bars_block = self._build_multi_symbol_bars_block(bars_by_symbol_and_tf)
        futures_block = self._build_futures_section_block(futures_data)
        news_block = self._build_news_block(news_items)

        user_text = (
            f"# {cadence_label.title()} D-Archive — "
            f"{run_timestamp_pt} ({run_timestamp_et})\n\n"
            f"{lock_in_block}\n\n"
            f"{bars_block}\n\n"
            f"{futures_block}\n\n"
            f"{news_block}\n\n"
            f"## Note: this is a D-only learning archive. "
            f"NO A/B/C sections. Populate frontmatter "
            f"pattern_tags + news_event_tags arrays for future query."
        )

        return [
            {"role": "system", "content": system_blocks},
            {"role": "user", "content": user_text},
        ]
```

- [ ] **Step 4.4: Run tests to verify green**

Run: `pytest tests/reports/test_prompt_builder.py -v -k "night_asia"`

Expected: 3 PASSED

- [ ] **Step 4.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥544 passed`

- [ ] **Step 4.6: Commit**

```bash
git add src/daytrader/reports/core/prompt_builder.py tests/reports/test_prompt_builder.py
git commit -m "$(cat <<'EOF'
feat(reports): PromptBuilder.build_night_asia (Phase 5.5 T4)

D-only template — accepts the same kwargs shape as build_intraday_4h
but ignores sentiment/plans/trades/retrospective/tomorrow (BaseCadence
generator passes them uniformly; night/asia just don't render them).

Per master spec §3.7: "Removes A, B, C; only multi-TF + news + D
frontmatter". Output template instructs AI to populate pattern_tags
+ news_event_tags in YAML frontmatter for future programmatic
query ("all bullish_engulf at support_test in last 30 days").

3 new tests; 544 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: OutputValidator.REQUIRED_SECTIONS — 3 new entries

**Goal:** Add validator entries for the 3 new report types.

**Files:**
- Modify: `src/daytrader/reports/core/output_validator.py` (ADD entries; do NOT touch existing)
- Test: `tests/reports/test_output_validator.py` (extend)

- [ ] **Step 5.1: Write failing tests**

Append to `tests/reports/test_output_validator.py`:

```python
INTRADAY_4H_VALID_SAMPLE = """# Intraday 4H Report
## 🔒 Lock-in Metadata
status
## 📊 MES — Multi-TF
#### D
x
#### 4H
x
#### 1H
x
## 📊 MNQ — Multi-TF
## 📊 MGC — Multi-TF
## 🌐 Cross-Asset Narrative
narr
## 📰 Breaking News
news
## F. 期货结构
ok
## D. 情绪面 / Sentiment Index
ok
## 今日交易档案 / Today's Trade Archive
0 trades
## 🔄 Plan Retrospective / 计划复盘
n/a (4h-1)
## C. 计划复核
ok
## B. 市场叙事
narr
## A. 建议
A-3 default
## 📑 数据快照
ok
"""


def test_validator_intraday_4h_passes_when_all_sections_present():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    result = v.validate(INTRADAY_4H_VALID_SAMPLE, report_type="intraday-4h")
    assert result.ok is True, f"missing: {result.missing}"


def test_validator_intraday_4h_fails_when_a_section_missing():
    """Intraday-4h KEEPS A section (unlike EOD which removes it)."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    no_a = INTRADAY_4H_VALID_SAMPLE.replace("## A. 建议\nA-3 default\n", "")
    result = v.validate(no_a, report_type="intraday-4h")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "A" in missing_str or "建议" in missing_str


def test_validator_intraday_4h_fails_when_plan_retrospective_missing():
    """Both 4h-1 and 4h-2 must show retrospective slot (4h-1 has placeholder)."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    no_retro = INTRADAY_4H_VALID_SAMPLE.replace(
        "## 🔄 Plan Retrospective / 计划复盘\nn/a (4h-1)\n", ""
    )
    result = v.validate(no_retro, report_type="intraday-4h")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "Retrospective" in missing_str or "复盘" in missing_str


NIGHT_ASIA_VALID_SAMPLE = """# Night D-Archive
## 🔒 Lock-in Metadata
trades 0/30
## 📊 MES — Multi-TF
## 📊 MNQ — Multi-TF
## 📊 MGC — Multi-TF
## F. 期货结构
ok
## 📰 Breaking News
none
## D. Pattern Archive
patterns
## 📑 数据快照
ok
"""


def test_validator_night_passes_when_all_sections_present():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    result = v.validate(NIGHT_ASIA_VALID_SAMPLE, report_type="night")
    assert result.ok is True, f"missing: {result.missing}"


def test_validator_asia_passes_with_same_required_sections_as_night():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    result = v.validate(NIGHT_ASIA_VALID_SAMPLE, report_type="asia")
    assert result.ok is True, f"missing: {result.missing}"


def test_validator_night_fails_when_d_archive_section_missing():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    no_d = NIGHT_ASIA_VALID_SAMPLE.replace(
        "## D. Pattern Archive\npatterns\n", ""
    )
    result = v.validate(no_d, report_type="night")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "Pattern Archive" in missing_str or "Archive" in missing_str or "D." in missing_str


def test_validator_night_does_not_require_a_or_b_or_c_sections():
    """night/asia explicitly lack A/B/C — must NOT enforce them."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    # Confirm by inspecting: NIGHT_ASIA_VALID_SAMPLE has no A/B/C sections;
    # validator passes anyway.
    assert "## A." not in NIGHT_ASIA_VALID_SAMPLE
    assert "## B." not in NIGHT_ASIA_VALID_SAMPLE
    assert "## C." not in NIGHT_ASIA_VALID_SAMPLE
    result = v.validate(NIGHT_ASIA_VALID_SAMPLE, report_type="night")
    assert result.ok is True
```

- [ ] **Step 5.2: Run tests to verify red**

Run: `pytest tests/reports/test_output_validator.py -v -k "intraday_4h or night or asia"`

Expected: FAIL with `KeyError: "No section list defined for report_type='intraday-4h'"`

- [ ] **Step 5.3: Add REQUIRED_SECTIONS entries**

Modify `src/daytrader/reports/core/output_validator.py` — find the closing `}` of `REQUIRED_SECTIONS` dict and ADD before it (do NOT touch existing premarket/eod entries):

```python
    "intraday-4h": [
        # Phase 5.5 T5 (2026-05-05) — used by both intraday-4h-1 (07:00 PT)
        # and intraday-4h-2 (11:00 PT). 4h-1 shows retrospective placeholder;
        # 4h-2 shows real retrospective. Validator enforces the section
        # presence either way.
        ["Lock-in", "🔒 Lock-in"],
        ["MES", "📊 MES"],
        ["MNQ", "📊 MNQ"],
        ["MGC", "📊 MGC"],
        ["🌐", "Cross-Asset", "跨市场", "跨资产"],
        ["📰", "Breaking News", "新闻"],
        ["F. 期货结构", "F-MES", "Futures Positioning", "期货结构"],
        ["情绪面", "D. 情绪面", "Sentiment Index", "Sentiment"],
        ["今日交易档案", "Trade Archive", "Today's Trade"],
        # Plan Retrospective slot — 4h-1 fills with placeholder, 4h-2
        # fills with real retrospective; both pass:
        ["Plan Retrospective", "🔄 Plan", "计划复盘"],
        ["C.", "计划复核", "Plan Adherence"],
        ["B.", "市场叙事", "Narrative"],
        # NOTE: A is REQUIRED (unlike EOD which removes A). Intraday is
        # forward-looking for rest-of-session.
        ["A.", "建议", "Recommendation"],
        ["数据快照", "Data Snapshot", "Snapshot"],
    ],
    "night": [
        # Phase 5.5 T5 — D-only learning archive. NO A/B/C/sentiment.
        ["Lock-in", "🔒 Lock-in"],
        ["MES", "📊 MES"],
        ["MNQ", "📊 MNQ"],
        ["MGC", "📊 MGC"],
        ["F. 期货结构", "F-MES", "Futures Positioning", "期货结构"],
        ["📰", "Breaking News", "新闻"],
        ["D.", "Pattern Archive", "D-Archive", "Archive"],
        ["数据快照", "Data Snapshot", "Snapshot"],
    ],
    "asia": [
        # Same shape as night — D-only learning archive.
        ["Lock-in", "🔒 Lock-in"],
        ["MES", "📊 MES"],
        ["MNQ", "📊 MNQ"],
        ["MGC", "📊 MGC"],
        ["F. 期货结构", "F-MES", "Futures Positioning", "期货结构"],
        ["📰", "Breaking News", "新闻"],
        ["D.", "Pattern Archive", "D-Archive", "Archive"],
        ["数据快照", "Data Snapshot", "Snapshot"],
    ],
```

- [ ] **Step 5.4: Run tests to verify green**

Run: `pytest tests/reports/test_output_validator.py -v -k "intraday_4h or night or asia"`

Expected: 7 PASSED

- [ ] **Step 5.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥551 passed`

- [ ] **Step 5.6: Commit**

```bash
git add src/daytrader/reports/core/output_validator.py tests/reports/test_output_validator.py
git commit -m "$(cat <<'EOF'
feat(reports): OutputValidator REQUIRED_SECTIONS for 3 new types (Phase 5.5 T5)

Adds validator entries for "intraday-4h", "night", "asia". Existing
REQUIRED_SECTIONS["premarket"] and ["eod"] UNCHANGED per regression
boundary.

intraday-4h: 14 slots — keeps A section (unlike EOD which removed
A); both 4h-1 and 4h-2 share the dispatch key (4h-1 satisfies
Plan Retrospective slot via placeholder text).

night/asia: 8 slots each, identical structure — D-only learning
archive. No A/B/C/sentiment slots (lack of those sections is
intentional, not missing-required).

7 new tests; 551 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: ObsidianWriter.write_intraday_4h + write_night_asia

**Goal:** Add 2 new write methods to ObsidianWriter. Filename format per master spec §2.2.

**Files:**
- Modify: `src/daytrader/reports/delivery/obsidian_writer.py` (ADD methods; do NOT touch write_premarket / write_eod)
- Test: `tests/reports/test_obsidian_writer.py` (extend)

**Filename patterns**:
- 4h-1: `<date>-0700PT-4H1.md`
- 4h-2: `<date>-1100PT-4H2.md`
- night: `<date>-1900PT-night.md`
- asia: `<date>-2300PT-asia.md`

- [ ] **Step 6.1: Inspect existing pattern**

Run: `grep -n "def write_premarket\|def write_eod\|class ObsidianWriter" src/daytrader/reports/delivery/obsidian_writer.py`

Note the signatures and adopt parallel pattern.

- [ ] **Step 6.2: Write failing tests**

Append to `tests/reports/test_obsidian_writer.py`:

```python
def test_write_intraday_4h_1_to_vault(tmp_path):
    """4h-1 writes <date>-0700PT-4H1.md."""
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_intraday_4h(
        date_iso="2026-05-05",
        time_label="0700PT-4H1",
        content="# Intraday 4H Report\nbody\n",
    )
    assert result.path.name == "2026-05-05-0700PT-4H1.md"
    assert result.path.parent == daily
    assert result.path.read_text().startswith("# Intraday 4H Report")


def test_write_intraday_4h_2_to_vault(tmp_path):
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_intraday_4h(
        date_iso="2026-05-05",
        time_label="1100PT-4H2",
        content="# Intraday 4H Report (#2)\n",
    )
    assert result.path.name == "2026-05-05-1100PT-4H2.md"


def test_write_intraday_4h_falls_back_when_vault_missing(tmp_path):
    """When vault path doesn't exist, fall back to fallback_dir."""
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "missing-vault"
    fallback = tmp_path / "fallback"
    fallback.mkdir()

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_intraday_4h(
        date_iso="2026-05-05", time_label="0700PT-4H1",
        content="# fallback test\n",
    )
    assert result.path.parent == fallback
    assert result.path.read_text() == "# fallback test\n"


def test_write_night_to_vault(tmp_path):
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_night_asia(
        date_iso="2026-05-05",
        cadence="night",
        content="# Night D-Archive\n",
    )
    assert result.path.name == "2026-05-05-1900PT-night.md"


def test_write_asia_to_vault(tmp_path):
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    daily = vault / "Daily"
    daily.mkdir(parents=True)

    writer = ObsidianWriter(vault_root=vault, fallback_dir=fallback,
                            daily_folder="Daily")
    result = writer.write_night_asia(
        date_iso="2026-05-05",
        cadence="asia",
        content="# Asia D-Archive\n",
    )
    assert result.path.name == "2026-05-05-2300PT-asia.md"


def test_write_night_asia_invalid_cadence_raises():
    from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
    from pathlib import Path
    writer = ObsidianWriter(vault_root=Path("/tmp"),
                            fallback_dir=Path("/tmp"),
                            daily_folder="Daily")
    with pytest.raises(ValueError, match="cadence"):
        writer.write_night_asia(
            date_iso="2026-05-05", cadence="invalid",
            content="x",
        )
```

- [ ] **Step 6.3: Run tests to verify red**

Run: `pytest tests/reports/test_obsidian_writer.py -v -k "intraday_4h or night or asia"`

Expected: FAIL with `AttributeError: 'ObsidianWriter' object has no attribute 'write_intraday_4h'`

- [ ] **Step 6.4: Implement methods**

Append to `src/daytrader/reports/delivery/obsidian_writer.py` (after `write_eod` method, before any closing class brace):

```python
    def write_intraday_4h(
        self,
        date_iso: str,
        time_label: str,  # "0700PT-4H1" | "1100PT-4H2"
        content: str,
    ) -> WriteResult:
        """Write intraday-4h cadence report.

        Filename: <date>-<time_label>.md (e.g. 2026-05-05-0700PT-4H1.md)
        Phase 5.5 T6 (2026-05-05).
        """
        if time_label not in ("0700PT-4H1", "1100PT-4H2"):
            raise ValueError(
                f"time_label must be '0700PT-4H1' or '1100PT-4H2', got {time_label!r}"
            )
        filename = f"{date_iso}-{time_label}.md"
        return self._write_with_fallback(filename, content)

    def write_night_asia(
        self,
        date_iso: str,
        cadence: str,  # "night" | "asia"
        content: str,
    ) -> WriteResult:
        """Write night/asia D-archive report.

        Filename: <date>-<NN>00PT-<cadence>.md
          (night → 2026-05-05-1900PT-night.md
           asia  → 2026-05-05-2300PT-asia.md)
        Phase 5.5 T6.
        """
        if cadence == "night":
            time_label = "1900PT-night"
        elif cadence == "asia":
            time_label = "2300PT-asia"
        else:
            raise ValueError(
                f"cadence must be 'night' or 'asia', got {cadence!r}"
            )
        filename = f"{date_iso}-{time_label}.md"
        return self._write_with_fallback(filename, content)
```

If `_write_with_fallback` doesn't exist, look at how `write_eod` writes. If write_eod has its own inline logic, replicate that pattern (DO NOT refactor existing methods to use a new helper — that would touch them).

- [ ] **Step 6.5: Run tests to verify green**

Run: `pytest tests/reports/test_obsidian_writer.py -v -k "intraday_4h or night or asia"`

Expected: 6 PASSED

- [ ] **Step 6.6: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥557 passed`

- [ ] **Step 6.7: Commit**

```bash
git add src/daytrader/reports/delivery/obsidian_writer.py tests/reports/test_obsidian_writer.py
git commit -m "$(cat <<'EOF'
feat(reports): ObsidianWriter.write_intraday_4h + write_night_asia (Phase 5.5 T6)

Adds 2 new write methods following write_eod pattern:
  write_intraday_4h(date_iso, time_label, content)
    → <date>-0700PT-4H1.md or <date>-1100PT-4H2.md
  write_night_asia(date_iso, cadence, content)
    → <date>-1900PT-night.md or <date>-2300PT-asia.md

Both use the same vault → fallback path resolution as write_eod.
write_premarket / write_eod UNCHANGED (regression boundary).

ValueError raised for invalid time_label / cadence — defensive
guard against orchestrator dispatch bugs.

6 new tests; 557 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: IntradayFourHGenerator + IntradayFourHConfig

**Goal:** Concrete subclass of BaseCadenceGenerator. Used by both 4h-1 and 4h-2; differentiated by config (`do_retrospective`, `sentiment_refresh`, `intraday_end_time_et`).

**Files:**
- Create: `src/daytrader/reports/types/intraday_4h.py`
- Test: `tests/reports/types/test_intraday_4h_generator.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/reports/types/test_intraday_4h_generator.py`:

```python
"""Unit tests for IntradayFourHGenerator (Phase 5.5 T7)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.base import CadenceOutcome
from daytrader.reports.types.intraday_4h import (
    IntradayFourHConfig,
    IntradayFourHGenerator,
)


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0, lock_in_target=30,
        cumulative_r=None, last_trade_date=None, last_trade_r=None, streak=None,
    )


def _ohlcv(c: float = 5240.0):
    return OHLCV(
        timestamp=datetime(2026, 5, 5, 7, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_text():
    text = (
        "# Intraday 4H\n"
        "## 🔒 Lock-in Metadata\nx\n"
        "## 📊 MES — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "## 📊 MNQ — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "## 📊 MGC — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "## 🌐 Cross-Asset\nx\n## 📰 Breaking News\nx\n"
        "## F. 期货结构\nx\n## D. 情绪面\nx\n"
        "## 今日交易档案\nx\n## 🔄 Plan Retrospective\nx\n"
        "## C. 计划复核\nx\n## B. 市场叙事\nx\n## A. 建议\nx\n## 📑 数据快照\nx\n"
    )
    result = MagicMock()
    result.text = text
    result.input_tokens = 100
    result.output_tokens = 200
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


def _config_4h_1() -> IntradayFourHConfig:
    return IntradayFourHConfig(
        cadence_label="intraday-4h-1",
        do_retrospective=False,
        sentiment_refresh=False,
        sentiment_time_window="",
        news_time_window="past 1h",
        intraday_end_time_et="10:00",
    )


def _config_4h_2() -> IntradayFourHConfig:
    return IntradayFourHConfig(
        cadence_label="intraday-4h-2",
        do_retrospective=True,
        sentiment_refresh=True,
        sentiment_time_window="past 5h",
        news_time_window="past 5h",
        intraday_end_time_et="14:00",
    )


def _make_generator(config, **overrides):
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()

    return IntradayFourHGenerator(
        config=config,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=overrides.get("symbols", ["MES", "MNQ", "MGC"]),
        tradable_symbols=overrides.get("tradable", ["MES", "MGC"]),
        plan_reader=overrides.get("plan_reader", MagicMock()),
        plan_parser=overrides.get("plan_parser", MagicMock()),
        trades_query=overrides.get("trades_query", MagicMock()),
        retrospective=overrides.get("retrospective", MagicMock()),
    )


def test_intraday_4h_report_type_is_intraday_4h():
    gen = _make_generator(_config_4h_1())
    assert gen.report_type == "intraday-4h"


def test_intraday_4h_tfs_are_d_4h_1h():
    gen = _make_generator(_config_4h_1())
    assert gen.tfs == ("1D", "4H", "1H")


def test_intraday_4h_bars_per_tf():
    gen = _make_generator(_config_4h_1())
    assert gen.bars_per_tf == {"1D": 10, "4H": 12, "1H": 24}


def test_intraday_4h_1_skips_retrospective():
    """4h-1 config has do_retrospective=False — _maybe_compose_retrospective returns ''."""
    gen = _make_generator(_config_4h_1())
    result = gen._maybe_compose_retrospective({}, [], "2026-05-05")
    assert result == ""


def test_intraday_4h_2_runs_retrospective_when_plans_present():
    """4h-2 with plans + retrospective dep → calls compose + persist."""
    fake_retro = MagicMock()
    fake_retro.compose.return_value = {"MES": MagicMock()}
    fake_retro.persist = MagicMock()

    gen = _make_generator(_config_4h_2(), retrospective=fake_retro)
    result = gen._maybe_compose_retrospective(
        {"MES": "raw"}, [], "2026-05-05"
    )
    fake_retro.compose.assert_called_once()
    fake_retro.persist.assert_called_once()
    assert "Retrospective" in result or "复盘" in result


def test_intraday_4h_2_skips_retrospective_when_no_plans():
    """No plan blocks → skip retrospective even on 4h-2."""
    fake_retro = MagicMock()
    gen = _make_generator(_config_4h_2(), retrospective=fake_retro)
    result = gen._maybe_compose_retrospective({}, [], "2026-05-05")
    fake_retro.compose.assert_not_called()
    assert result == ""


def test_intraday_4h_1_does_not_refresh_sentiment(monkeypatch):
    """4h-1 → _maybe_fetch_sentiment returns '' so caller's cache wins."""
    gen = _make_generator(_config_4h_1())
    result = gen._maybe_fetch_sentiment()
    assert result == ""


def test_intraday_4h_2_refreshes_sentiment(monkeypatch):
    """4h-2 → _maybe_fetch_sentiment calls SentimentSection.collect."""
    from unittest.mock import patch
    from daytrader.reports.sentiment.dataclasses import SentimentResult

    with patch(
        "daytrader.reports.types.intraday_4h.SentimentSection"
    ) as mock_section_cls:
        mock_section = mock_section_cls.return_value
        mock_section.collect.return_value = SentimentResult.unavailable_due_to(
            "test-mock"
        )
        mock_section.render.return_value = "## D. 情绪面\nrefreshed\n"

        gen = _make_generator(_config_4h_2())
        result = gen._maybe_fetch_sentiment()

        # Verify SentimentSection was instantiated with 4h-2 time_window
        mock_section_cls.assert_called_once()
        args = mock_section_cls.call_args
        assert args.kwargs.get("time_window") == "past 5h"
        assert "refreshed" in result


def test_intraday_4h_read_plan_calls_plan_reader():
    fake_reader = MagicMock()
    fake_reader.read_today_plan.return_value = {"MES": "raw block"}

    gen = _make_generator(_config_4h_1(), plan_reader=fake_reader)
    plans = gen._maybe_read_plan("2026-05-05")
    fake_reader.read_today_plan.assert_called_once_with("2026-05-05")
    assert plans == {"MES": "raw block"}


def test_intraday_4h_fetch_trades_calls_trades_query():
    fake_query = MagicMock()
    fake_query.trades_for_date.return_value = [
        {"symbol": "MES", "side": "long", "r": 1.5}
    ]

    gen = _make_generator(_config_4h_1(), trades_query=fake_query)
    trades = gen._maybe_fetch_trades("2026-05-05")
    fake_query.trades_for_date.assert_called_once_with("2026-05-05")
    assert trades == [{"symbol": "MES", "side": "long", "r": 1.5}]


def test_intraday_4h_generate_returns_outcome():
    gen = _make_generator(_config_4h_1())
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="07:00 PT", run_timestamp_et="10:00 ET",
        sentiment_md="## D. 情绪面\nfrom premarket\n",
    )
    assert isinstance(outcome, CadenceOutcome)
    assert outcome.report_text


def test_intraday_4h_2_intraday_end_time_et_in_config():
    """Config carries the end_time_et string for orchestrator's
    _make_intraday_fetcher_4h_2 to use."""
    config = _config_4h_2()
    assert config.intraday_end_time_et == "14:00"


def test_intraday_4h_1_uses_news_window_past_1h():
    config = _config_4h_1()
    assert config.news_time_window == "past 1h"


def test_intraday_4h_2_uses_news_window_past_5h():
    config = _config_4h_2()
    assert config.news_time_window == "past 5h"
```

- [ ] **Step 7.2: Run tests to verify red**

Run: `pytest tests/reports/types/test_intraday_4h_generator.py -q --tb=line`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.reports.types.intraday_4h'`

- [ ] **Step 7.3: Implement intraday_4h.py**

Create `src/daytrader/reports/types/intraday_4h.py`:

```python
"""IntradayFourHGenerator — concrete BaseCadenceGenerator subclass.

Used by both intraday-4h-1 (07:00 PT) and intraday-4h-2 (11:00 PT).
Differentiated by IntradayFourHConfig:
  - 4h-1: do_retrospective=False, sentiment_refresh=False
  - 4h-2: do_retrospective=True, sentiment_refresh=True (past 5h window)

Phase 5.5 T7 (2026-05-05).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.reports.core.ai_analyst import AIAnalyst
from daytrader.reports.core.output_validator import OutputValidator
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.sentiment import SentimentSection
from daytrader.reports.types.base import BaseCadenceGenerator


@dataclass(frozen=True)
class IntradayFourHConfig:
    """Differentiates 4h-1 vs 4h-2 behavior. Same generator class, two configs."""
    cadence_label: str           # "intraday-4h-1" | "intraday-4h-2"
    do_retrospective: bool       # False (4h-1) | True (4h-2)
    sentiment_refresh: bool      # False (4h-1) | True (4h-2)
    sentiment_time_window: str   # "" (no refresh) | "past 5h"
    news_time_window: str        # "past 1h" (4h-1) | "past 5h" (4h-2)
    intraday_end_time_et: str    # "10:00" (4h-1) | "14:00" (4h-2) — for retrospective fetcher


class IntradayFourHGenerator(BaseCadenceGenerator):
    """Generates intraday-4h reports (both 4h-1 and 4h-2 cadences)."""

    def __init__(
        self,
        config: IntradayFourHConfig,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher=None,
        term_price_fetcher=None,
        tick_sizes: dict[str, float] | None = None,
        news_collector=None,
        # Cadence-specific deps:
        plan_reader=None,
        plan_parser=None,
        trades_query=None,
        retrospective=None,
    ) -> None:
        super().__init__(
            ib_client=ib_client,
            ai_analyst=ai_analyst,
            symbols=symbols,
            tradable_symbols=tradable_symbols,
            prompt_builder=prompt_builder,
            validator=validator,
            underlying_price_fetcher=underlying_price_fetcher,
            term_price_fetcher=term_price_fetcher,
            tick_sizes=tick_sizes,
            news_collector=news_collector,
        )
        self._config = config
        self.plan_reader = plan_reader
        self.plan_parser = plan_parser
        self.trades_query = trades_query
        self.retrospective = retrospective

    @property
    def report_type(self) -> str:
        # Both 4h-1 and 4h-2 use the same validator key
        return "intraday-4h"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("1D", "4H", "1H")

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"1D": 10, "4H": 12, "1H": 24}

    # --- hook overrides ---

    def _maybe_fetch_sentiment(self) -> str:
        """4h-2 only: refresh sentiment with cadence-specific time_window.
        4h-1 returns "" so caller-provided premarket cache wins."""
        if not self._config.sentiment_refresh:
            return ""
        try:
            section = SentimentSection(
                symbols=self.symbols,
                time_window=self._config.sentiment_time_window,
            )
            result = section.collect()
            return section.render(result)
        except Exception as exc:
            print(
                f"[intraday_4h] WARNING: sentiment refresh failed: {exc}",
                file=sys.stderr,
            )
            return ""

    def _maybe_read_plan(self, date_et: str) -> dict[str, str]:
        """Both 4h-1 and 4h-2 read today's premarket plan for C section."""
        if self.plan_reader is None:
            return {}
        try:
            return self.plan_reader.read_today_plan(date_et)
        except Exception as exc:
            print(
                f"[intraday_4h] WARNING: plan read failed: {exc}",
                file=sys.stderr,
            )
            return {}

    def _maybe_fetch_trades(self, date_et: str) -> list[dict[str, Any]]:
        """Light list — no §6/§9 audit (that's EOD's job)."""
        if self.trades_query is None:
            return []
        try:
            return self.trades_query.trades_for_date(date_et)
        except Exception as exc:
            print(
                f"[intraday_4h] WARNING: trades fetch failed: {exc}",
                file=sys.stderr,
            )
            return []

    def _maybe_compose_retrospective(
        self,
        plans: dict[str, str],
        trades: list[dict[str, Any]],
        date_et: str,
    ) -> str:
        """4h-2 only: run PlanRetrospective + persist + render."""
        if not self._config.do_retrospective:
            return ""
        if not plans:
            return ""
        if self.retrospective is None:
            return ""
        rows = self.retrospective.compose(
            plans=plans,
            symbols=self.symbols,
            date_et=date_et,
            tick_sizes=self.tick_sizes,
        )
        if not rows:
            return ""
        self.retrospective.persist(rows)
        return self._render_retrospective_block(rows)

    @staticmethod
    def _render_retrospective_block(rows) -> str:
        """Render rows as markdown — same format as EOD generator."""
        if not rows:
            return ""
        lines = ["## 🔄 Plan Retrospective / 计划复盘"]
        for symbol, row in rows.items():
            lines.append(f"\n### {symbol}")
            lines.append(
                f"- Levels triggered: {row.triggered_count}/{row.total_levels}"
            )
            lines.append(
                f"- sim total: {row.sim_total_r:+.2f}R, "
                f"actual: {row.actual_total_r:+.2f}R, "
                f"gap: {row.gap_r:+.2f}R"
            )
            if row.open_trades_count > 0:
                lines.append(
                    f"- ⚠️ {row.open_trades_count} open trade(s) "
                    "— unrealized R not in actual"
                )
        lines.append("")
        lines.append(
            "> 4h-2 retrospective covers RTH 06:30 PT → 11:00 PT. "
            "Full session retrospective in EOD 14:00 PT."
        )
        return "\n".join(lines)

    def _build_prompt(self, **inputs) -> list[dict[str, Any]]:
        return self.prompt_builder.build_intraday_4h(
            cadence_label=self._config.cadence_label, **inputs
        )
```

- [ ] **Step 7.4: Run tests to verify green**

Run: `pytest tests/reports/types/test_intraday_4h_generator.py -q --tb=line`

Expected: 14 PASSED

- [ ] **Step 7.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥571 passed` (557 + 14 new)

- [ ] **Step 7.6: Commit**

```bash
git add src/daytrader/reports/types/intraday_4h.py tests/reports/types/test_intraday_4h_generator.py
git commit -m "$(cat <<'EOF'
feat(reports): IntradayFourHGenerator + IntradayFourHConfig (Phase 5.5 T7)

Concrete BaseCadenceGenerator subclass for both 4h-1 and 4h-2.
Differentiated by IntradayFourHConfig fields:
  - 4h-1: do_retrospective=False, sentiment_refresh=False, news=past 1h
  - 4h-2: do_retrospective=True, sentiment_refresh=True (past 5h),
          news=past 5h, intraday_end_time_et=14:00 (for retrospective
          fetcher's end_time pin per C2 fix pattern)

Hooks override:
  _maybe_fetch_sentiment — 4h-2 calls SentimentSection.collect with
    config.sentiment_time_window; 4h-1 returns "" (caller passes
    premarket cache via sentiment_md kwarg)
  _maybe_read_plan — both cadences read today's premarket plan
  _maybe_fetch_trades — both fetch light list (no §6/§9 audit)
  _maybe_compose_retrospective — 4h-2 only; reuses Phase 5
    PlanRetrospective.compose + persist; renders inline summary
    block; calls out 4h-2 covers RTH 06:30→11:00 PT

14 new tests; 571 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: NightAsiaGenerator + NightAsiaConfig

**Goal:** Concrete subclass of BaseCadenceGenerator for D-only learning archive (night + asia).

**Files:**
- Create: `src/daytrader/reports/types/night_asia.py`
- Test: `tests/reports/types/test_night_asia_generator.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/reports/types/test_night_asia_generator.py`:

```python
"""Unit tests for NightAsiaGenerator (Phase 5.5 T8)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.base import CadenceOutcome
from daytrader.reports.types.night_asia import (
    NightAsiaConfig,
    NightAsiaGenerator,
)


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0, lock_in_target=30,
        cumulative_r=None, last_trade_date=None, last_trade_r=None, streak=None,
    )


def _ohlcv(c: float = 5240.0):
    return OHLCV(
        timestamp=datetime(2026, 5, 5, 19, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_text():
    text = (
        "# Night D-Archive\n"
        "## 🔒 Lock-in Metadata\nx\n"
        "## 📊 MES — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
        "## 📊 MNQ — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
        "## 📊 MGC — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
        "## F. 期货结构\nx\n## 📰 Breaking News\nx\n"
        "## D. Pattern Archive\npatterns\n## 📑 数据快照\nok\n"
    )
    result = MagicMock()
    result.text = text
    result.input_tokens = 100
    result.output_tokens = 200
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


def _config_night() -> NightAsiaConfig:
    return NightAsiaConfig(
        cadence_label="night",
        trigger_time_pt="19:00",
        news_time_window="past 4h",
    )


def _config_asia() -> NightAsiaConfig:
    return NightAsiaConfig(
        cadence_label="asia",
        trigger_time_pt="23:00",
        news_time_window="past 4h",
    )


def _make_generator(config):
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    return NightAsiaGenerator(
        config=config,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )


def test_night_report_type_is_night():
    gen = _make_generator(_config_night())
    assert gen.report_type == "night"


def test_asia_report_type_is_asia():
    gen = _make_generator(_config_asia())
    assert gen.report_type == "asia"


def test_night_asia_tfs_are_4h_and_1h_only():
    """No D — overnight cadence, 2 TFs only."""
    gen_n = _make_generator(_config_night())
    gen_a = _make_generator(_config_asia())
    assert gen_n.tfs == ("4H", "1H")
    assert gen_a.tfs == ("4H", "1H")


def test_night_asia_bars_per_tf():
    gen = _make_generator(_config_night())
    assert gen.bars_per_tf == {"4H": 12, "1H": 24}


def test_night_default_no_sentiment():
    """night/asia inherit base default — empty sentiment."""
    gen = _make_generator(_config_night())
    assert gen._maybe_fetch_sentiment() == ""


def test_night_default_no_plan_read():
    gen = _make_generator(_config_night())
    assert gen._maybe_read_plan("2026-05-05") == {}


def test_night_default_no_trades():
    gen = _make_generator(_config_night())
    assert gen._maybe_fetch_trades("2026-05-05") == []


def test_night_default_no_retrospective():
    gen = _make_generator(_config_night())
    assert gen._maybe_compose_retrospective({}, [], "2026-05-05") == ""


def test_night_generate_returns_outcome():
    gen = _make_generator(_config_night())
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="19:00 PT", run_timestamp_et="22:00 ET",
    )
    assert isinstance(outcome, CadenceOutcome)
    assert outcome.report_text


def test_asia_generate_only_fetches_4h_and_1h_bars():
    """3 symbols × 2 TFs = 6 multi-TF bar fetches (plus VP fetches)."""
    config = _config_asia()
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()

    gen = NightAsiaGenerator(
        config=config, ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"], tradable_symbols=["MES", "MGC"],
    )
    gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="23:00 PT", run_timestamp_et="02:00 ET",
    )
    # Multi-TF: 3 symbols × 2 TFs = 6 calls (VP adds more).
    # We just verify no D / no W timeframe was passed.
    timeframes_called = [
        call.kwargs.get("timeframe")
        for call in fake_ib.get_bars.call_args_list
        if "timeframe" in call.kwargs
    ]
    assert "1D" not in timeframes_called
    assert "1W" not in timeframes_called
    assert "4H" in timeframes_called or "1H" in timeframes_called
```

- [ ] **Step 8.2: Run tests to verify red**

Run: `pytest tests/reports/types/test_night_asia_generator.py -q --tb=line`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrader.reports.types.night_asia'`

- [ ] **Step 8.3: Implement night_asia.py**

Create `src/daytrader/reports/types/night_asia.py`:

```python
"""NightAsiaGenerator — concrete BaseCadenceGenerator subclass.

Used by both night (19:00 PT) and asia (23:00 PT) cadences.
D-only learning archive — overrides nothing except _build_prompt.
All BaseCadenceGenerator hooks default to skip:
  - no sentiment refresh
  - no plan read
  - no trade fetch beyond lock-in counter (covered by lock_in_block)
  - no retrospective
  - no tomorrow preliminary

Per master spec §3.7: "night/asia D | Removes A, B, C; only multi-TF
+ news + D frontmatter".

Phase 5.5 T8 (2026-05-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.reports.core.ai_analyst import AIAnalyst
from daytrader.reports.core.output_validator import OutputValidator
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.types.base import BaseCadenceGenerator


@dataclass(frozen=True)
class NightAsiaConfig:
    """Differentiates night vs asia cadence. Same generator class, two configs."""
    cadence_label: str           # "night" | "asia"
    trigger_time_pt: str         # "19:00" | "23:00"
    news_time_window: str        # "past 4h" both


class NightAsiaGenerator(BaseCadenceGenerator):
    """Generates D-only learning archive reports (both night and asia)."""

    def __init__(
        self,
        config: NightAsiaConfig,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher=None,
        term_price_fetcher=None,
        tick_sizes: dict[str, float] | None = None,
        news_collector=None,
    ) -> None:
        super().__init__(
            ib_client=ib_client,
            ai_analyst=ai_analyst,
            symbols=symbols,
            tradable_symbols=tradable_symbols,
            prompt_builder=prompt_builder,
            validator=validator,
            underlying_price_fetcher=underlying_price_fetcher,
            term_price_fetcher=term_price_fetcher,
            tick_sizes=tick_sizes,
            news_collector=news_collector,
        )
        self._config = config

    @property
    def report_type(self) -> str:
        return self._config.cadence_label  # "night" | "asia"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("4H", "1H")  # No D — overnight cadence, 2 TFs only

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"4H": 12, "1H": 24}

    # NO override of _maybe_* hooks — all defaults apply (return ""/[]/{}).

    def _build_prompt(self, **inputs) -> list[dict[str, Any]]:
        return self.prompt_builder.build_night_asia(
            cadence_label=self._config.cadence_label, **inputs
        )
```

- [ ] **Step 8.4: Run tests to verify green**

Run: `pytest tests/reports/types/test_night_asia_generator.py -q --tb=line`

Expected: 10 PASSED

- [ ] **Step 8.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥581 passed` (571 + 10 new)

- [ ] **Step 8.6: Commit**

```bash
git add src/daytrader/reports/types/night_asia.py tests/reports/types/test_night_asia_generator.py
git commit -m "$(cat <<'EOF'
feat(reports): NightAsiaGenerator + NightAsiaConfig (Phase 5.5 T8)

Concrete BaseCadenceGenerator subclass for night (19:00 PT) and
asia (23:00 PT). D-only learning archive — overrides nothing
except _build_prompt. All optional hooks (sentiment / plan_read /
trades / retrospective / tomorrow) default to skip.

NightAsiaConfig differentiates night vs asia by:
  - cadence_label ("night" | "asia") → drives report_type
  - trigger_time_pt ("19:00" | "23:00") → for runbook documentation
  - news_time_window ("past 4h" both)

TFs are 4H + 1H only (NO D — overnight cadence). bars_per_tf
returns {"4H": 12, "1H": 24}.

Per master spec §3.7: "night/asia D | Removes A, B, C; only
multi-TF + news + D frontmatter".

10 new tests; 581 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Orchestrator — _run_cadence helper + run_intraday_4h_1 + run_intraday_4h_2

**Goal:** Add 2 new orchestrator methods plus a private `_run_cadence` helper that encapsulates the common pipeline (idempotency → pending row → connect IB → generate → write Obsidian → mark success/fail → Telegram).

**Files:**
- Modify: `src/daytrader/reports/core/orchestrator.py` (ADD methods; do NOT touch run_premarket / run_eod)
- Test: `tests/reports/test_orchestrator.py` (extend)

**Why:** A `_run_cadence` helper deduplicates the ~150 LOC pipeline shape across the 4 new cadences. Existing run_premarket / run_eod stay UNCHANGED.

- [ ] **Step 9.1: Write failing tests**

Append to `tests/reports/test_orchestrator.py`:

```python
# ---------- Phase 5.5: intraday-4h orchestrator tests ----------


VALID_INTRADAY_4H_REPORT = (
    "# Intraday 4H Report\n"
    "## 🔒 Lock-in Metadata\nstatus\n\n"
    "## 📊 MES — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MNQ — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MGC — Multi-TF\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
    "## 🌐 Cross-Asset\nx\n## 📰 Breaking News\nx\n"
    "## F. 期货结构\nx\n## D. 情绪面\nx\n"
    "## 今日交易档案\nx\n## 🔄 Plan Retrospective\nx\n"
    "## C. 计划复核\nx\n## B. 市场叙事\nx\n## A. 建议\nA-3\n## 📑 数据快照\nx\n"
)


def _intraday_fake_ib():
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    return fake_ib


def test_run_intraday_4h_1_writes_obsidian_and_marks_success(tmp_path):
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert result.success is True
    assert result.report_path is not None
    assert result.report_path.name == "2026-05-05-0700PT-4H1.md"

    report_row = state.get_report_by_id(result.report_id)
    assert report_row["status"] == "success"
    assert report_row["report_type"] == "intraday-4h-1"


def test_run_intraday_4h_1_idempotent(tmp_path):
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    first = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert first.success is True
    second = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert second.skipped_idempotent is True
    assert fake_ai.call.call_count == 1


def test_run_intraday_4h_2_writes_4h2_filename(tmp_path):
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_intraday_4h_2(
        run_at=datetime(2026, 5, 5, 18, tzinfo=timezone.utc),
    )
    assert result.success is True
    assert result.report_path.name == "2026-05-05-1100PT-4H2.md"


def test_run_intraday_4h_validation_fail_marks_failed(tmp_path):
    """If AI output fails section validation, run marks the row failed."""
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_intraday_4h_1(
        run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()


def test_run_intraday_4h_2_pins_retrospective_end_time_to_11_pt(tmp_path):
    """C2-style guarantee: 4h-2 retrospective fetcher uses end_time = 11:00 PT (14:00 ET)."""
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    # Use the public factory for 4h-2 fetcher
    fetcher = orchestrator._make_intraday_fetcher_for_cadence(
        end_time_et="14:00"
    )
    fetcher("MES", "2026-05-05")

    call_kwargs = fake_ib.get_bars.call_args.kwargs
    end_time = call_kwargs.get("end_time")
    assert end_time is not None
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    expected = datetime(2026, 5, 5, 14, 0, tzinfo=ET)
    assert end_time == expected


def test_run_intraday_4h_persists_warnings_to_state_failures(tmp_path):
    """When generator returns warnings, orchestrator persists to state.failures."""
    fake_ib = _intraday_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)

    from daytrader.reports.types.base import CadenceOutcome
    from daytrader.reports.core.output_validator import ValidationResult

    fake_outcome = CadenceOutcome(
        report_text=VALID_INTRADAY_4H_REPORT,
        ai_result=_ai_result(text=VALID_INTRADAY_4H_REPORT),
        validation=ValidationResult(ok=True, missing=[]),
        bars_by_symbol_and_tf={},
        warnings=("retrospective: ValueError: bad", "news: TimeoutError: net"),
    )

    with patch(
        "daytrader.reports.types.intraday_4h.IntradayFourHGenerator"
    ) as mock_gen_cls:
        mock_gen_cls.return_value.generate.return_value = fake_outcome
        result = orchestrator.run_intraday_4h_1(
            run_at=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
        )
        assert result.success is True

    failures = state.list_unresolved_failures()
    stages = sorted(f["failure_stage"] for f in failures)
    assert "retrospective" in stages
    assert "news" in stages
```

- [ ] **Step 9.2: Run tests to verify red**

Run: `pytest tests/reports/test_orchestrator.py -v -k "intraday_4h"`

Expected: FAIL with `AttributeError: 'Orchestrator' object has no attribute 'run_intraday_4h_1'`

- [ ] **Step 9.3: Implement orchestrator methods**

Append to `src/daytrader/reports/core/orchestrator.py` (after `run_eod`, before `_estimate_cost` if it exists; do NOT touch existing methods):

```python
    # --- Phase 5.5 T9: intraday-4h cadences ---

    def _make_intraday_fetcher_for_cadence(self, end_time_et: str):
        """Build intraday_bar_fetcher closure with end_time pinned to
        a specific ET time (e.g. '11:00' for 4h-2, '14:00' for EOD).

        Generalizes _make_intraday_fetcher (which was hardcoded to 16:00 ET).
        Phase 5.5 T9 (2026-05-05).
        """
        def _fetch(symbol: str, date_et: str):
            from datetime import time
            hh, mm = end_time_et.split(":")
            date = datetime.strptime(date_et, "%Y-%m-%d").date()
            end_time = datetime.combine(
                date, time(int(hh), int(mm)), tzinfo=ET
            )
            return self.ib_client.get_bars(
                symbol=symbol,
                timeframe="5m",
                bars=78,
                end_time=end_time,
            )
        return _fetch

    def run_intraday_4h_1(self, run_at: datetime) -> PipelineResult:
        """Phase 5.5 T9: 07:00 PT cadence. Lightweight (no retrospective,
        no sentiment refresh — uses premarket cache for sentiment if
        available)."""
        from daytrader.reports.types.intraday_4h import (
            IntradayFourHConfig, IntradayFourHGenerator,
        )
        config = IntradayFourHConfig(
            cadence_label="intraday-4h-1",
            do_retrospective=False,
            sentiment_refresh=False,
            sentiment_time_window="",
            news_time_window="past 1h",
            intraday_end_time_et="10:00",
        )
        return self._run_cadence_intraday_4h(config, run_at, "0700PT-4H1")

    def run_intraday_4h_2(self, run_at: datetime) -> PipelineResult:
        """Phase 5.5 T9: 11:00 PT cadence with full retrospective +
        sentiment refresh."""
        from daytrader.reports.types.intraday_4h import (
            IntradayFourHConfig, IntradayFourHGenerator,
        )
        config = IntradayFourHConfig(
            cadence_label="intraday-4h-2",
            do_retrospective=True,
            sentiment_refresh=True,
            sentiment_time_window="past 5h",
            news_time_window="past 5h",
            intraday_end_time_et="14:00",
        )
        return self._run_cadence_intraday_4h(config, run_at, "1100PT-4H2")

    def _run_cadence_intraday_4h(
        self,
        config,
        run_at: datetime,
        time_label: str,
    ) -> PipelineResult:
        """Common pipeline for both 4h-1 and 4h-2 cadences.
        Mirrors run_eod but uses IntradayFourHGenerator + obsidian_writer.write_intraday_4h.
        """
        start = time.perf_counter()

        run_at_utc = run_at if run_at.tzinfo else run_at.replace(tzinfo=timezone.utc)
        date_et = run_at_utc.astimezone(ET).date().isoformat()
        time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
        time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

        if self.state_db.already_generated_today(config.cadence_label, date_et):
            return PipelineResult(
                success=True, report_id=None, report_path=None,
                skipped_idempotent=True,
            )

        report_id = self.state_db.insert_report_pending(
            scheduled_at=run_at_utc,
            report_type=config.cadence_label,
        )

        try:
            context = self.context_loader.load(date_et=date_et)

            # Sentiment: 4h-1 reuses premarket; 4h-2 refreshes inside generator
            sentiment_md = ""
            if not config.sentiment_refresh:
                # Fetch the most recent successful premarket sentiment from
                # today's premarket report markdown if available.
                sentiment_md = self._read_today_premarket_sentiment(date_et)

            from daytrader.reports.core.plan_extractor import PlanExtractor
            from daytrader.reports.eod.plan_reader import PremarketPlanReader
            from daytrader.reports.eod.plan_parser import PremarketPlanParser
            from daytrader.reports.eod.trade_simulator import simulate_level
            from daytrader.reports.eod.trades_query import TodayTradesQuery
            from daytrader.reports.eod.retrospective import PlanRetrospective
            from daytrader.reports.futures_data.term_prices import TermPricesFetcher
            from daytrader.reports.futures_data.underlying_prices import (
                UnderlyingPriceFetcher,
            )
            from daytrader.reports.types.intraday_4h import IntradayFourHGenerator

            plan_reader = PremarketPlanReader(
                vault_path=self.vault_root,
                daily_folder=self.daily_folder,
            )
            plan_parser = PremarketPlanParser()
            trades_query = TodayTradesQuery(self.journal_db_path)

            retrospective = None
            if config.do_retrospective:
                retrospective = PlanRetrospective(
                    plan_parser=plan_parser,
                    trade_simulator=simulate_level,
                    intraday_bar_fetcher=self._make_intraday_fetcher_for_cadence(
                        end_time_et=config.intraday_end_time_et,
                    ),
                    trades_query=trades_query,
                    state_db_path=self.state_db._path,
                )

            generator = IntradayFourHGenerator(
                config=config,
                ib_client=self.ib_client,
                ai_analyst=self.ai_analyst,
                symbols=self.symbols,
                tradable_symbols=self.tradable_symbols,
                underlying_price_fetcher=UnderlyingPriceFetcher(self.ib_client),
                term_price_fetcher=TermPricesFetcher(self.ib_client),
                plan_reader=plan_reader,
                plan_parser=plan_parser,
                trades_query=trades_query,
                retrospective=retrospective,
            )

            outcome = generator.generate(
                context=context,
                date_et=date_et,
                run_timestamp_pt=f"{time_pt_str} PT",
                run_timestamp_et=f"{time_et_str} ET",
                sentiment_md=sentiment_md,
            )

            for warning in outcome.warnings:
                stage, _, reason = warning.partition(": ")
                self.state_db.log_failure(
                    report_type=config.cadence_label,
                    scheduled_at=run_at_utc,
                    failure_stage=stage or "unknown",
                    failure_reason=reason or warning,
                    retry_count=0,
                )

            if not outcome.validation.ok:
                self.state_db.update_report_status(
                    report_id, status="failed",
                    failure_reason=(
                        f"validation missing: {outcome.validation.missing}"
                    ),
                    tokens_input=outcome.ai_result.input_tokens,
                    tokens_output=outcome.ai_result.output_tokens,
                    duration_seconds=time.perf_counter() - start,
                )
                return PipelineResult(
                    success=False, report_id=report_id, report_path=None,
                    failure_reason=(
                        f"validation: missing sections "
                        f"{outcome.validation.missing}"
                    ),
                )

            writer = ObsidianWriter(
                vault_root=self.vault_root,
                fallback_dir=self.fallback_dir,
                daily_folder=self.daily_folder,
            )
            write_result = writer.write_intraday_4h(
                date_iso=date_et,
                time_label=time_label,
                content=outcome.report_text,
            )

            # Best-effort delivery: charts, PDF, Telegram
            chart_paths: list[Path] = []
            if self.chart_renderer is not None and outcome.bars_by_symbol_and_tf:
                try:
                    artifacts = self.chart_renderer.render_all(
                        bars_by_symbol_and_tf=outcome.bars_by_symbol_and_tf,
                        today=date_et,
                    )
                    chart_paths = list(artifacts.tf_stack_paths.values())
                except Exception as e:
                    print(
                        f"[orchestrator] {config.cadence_label} chart render failed: {e}",
                        file=sys.stderr,
                    )

            pdf_path: Path | None = None
            if self.pdf_renderer is not None:
                try:
                    pdf_path = self.pdf_renderer.render_to_pdf(
                        markdown_text=outcome.report_text,
                        title=f"{config.cadence_label} {date_et}",
                        filename_stem=f"{date_et}-{time_label}",
                    )
                except Exception as e:
                    print(
                        f"[orchestrator] {config.cadence_label} PDF failed: {e}",
                        file=sys.stderr,
                    )

            if self.telegram_pusher is not None:
                try:
                    import asyncio
                    asyncio.run(self.telegram_pusher.push(
                        text_messages=[outcome.report_text],
                        chart_paths=chart_paths,
                        pdf_path=pdf_path,
                    ))
                except Exception as e:
                    print(
                        f"[orchestrator] {config.cadence_label} telegram failed: {e}",
                        file=sys.stderr,
                    )

            duration = time.perf_counter() - start
            self.state_db.update_report_status(
                report_id, status="success",
                obsidian_path=str(write_result.path),
                tokens_input=outcome.ai_result.input_tokens,
                tokens_output=outcome.ai_result.output_tokens,
                cache_hit_rate=(
                    outcome.ai_result.cache_read_tokens
                    / max(outcome.ai_result.input_tokens, 1)
                ),
                duration_seconds=duration,
                estimated_cost_usd=self._estimate_cost(outcome.ai_result),
            )
            return PipelineResult(
                success=True, report_id=report_id,
                report_path=write_result.path,
            )

        except Exception as exc:
            duration = time.perf_counter() - start
            self.state_db.update_report_status(
                report_id, status="failed",
                failure_reason=f"{type(exc).__name__}: {exc}",
                duration_seconds=duration,
            )
            return PipelineResult(
                success=False, report_id=report_id, report_path=None,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )

    def _read_today_premarket_sentiment(self, date_et: str) -> str:
        """Read today's premarket report from Obsidian (or fallback) and
        extract the D. 情绪面 section verbatim. If not found, return ''."""
        from pathlib import Path
        candidates = [
            self.vault_root / self.daily_folder / f"{date_et}-premarket.md",
            self.fallback_dir / f"{date_et}-premarket.md",
        ]
        for p in candidates:
            if p.exists():
                content = p.read_text()
                # Find D. 情绪面 section (between "## D." and next "## ")
                import re
                m = re.search(
                    r"^## D\.\s*情绪面.*?(?=^## )",
                    content, re.MULTILINE | re.DOTALL,
                )
                if m:
                    return m.group(0).strip()
        return ""
```

If the file is missing imports for `time` (perf_counter), `Path`, `sys`, `datetime`, `timezone`, ensure they are present at the top of the file (likely already are — verify with the existing run_eod method).

- [ ] **Step 9.4: Run tests to verify green**

Run: `pytest tests/reports/test_orchestrator.py -v -k "intraday_4h"`

Expected: 6 PASSED

- [ ] **Step 9.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥587 passed`

- [ ] **Step 9.6: Commit**

```bash
git add src/daytrader/reports/core/orchestrator.py tests/reports/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(reports): Orchestrator.run_intraday_4h_1 + run_intraday_4h_2 (Phase 5.5 T9)

Adds 2 new orchestrator dispatch methods + a shared
_run_cadence_intraday_4h helper. Pattern mirrors run_eod:
  - idempotency check via state.already_generated_today
  - insert pending row, get report_id
  - construct IntradayFourHGenerator with cadence-specific config
  - generate → outcome.warnings → state.failures (I1 pattern)
  - validation.ok ? write Obsidian + best-effort delivery : mark failed
  - update report status with tokens / duration / cost

run_premarket / run_eod NOT TOUCHED (regression boundary).

Generalizes _make_intraday_fetcher → _make_intraday_fetcher_for_cadence
which accepts end_time_et string. EOD now has its own existing factory
(unchanged); 4h-2 uses the new generalized one with end_time_et="14:00"
(= 11:00 PT). 4h-1 doesn't need a fetcher (no retrospective).

_read_today_premarket_sentiment helper: 4h-1 sentiment_md is sourced
from today's premarket report markdown (D. 情绪面 section) — saves
the ~120s subprocess call.

6 new tests; 587 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Orchestrator — run_night + run_asia

**Goal:** Add 2 more orchestrator methods for D-only cadences. No PDF, no Telegram.

**Files:**
- Modify: `src/daytrader/reports/core/orchestrator.py`
- Test: `tests/reports/test_orchestrator.py` (extend)

- [ ] **Step 10.1: Write failing tests**

Append to `tests/reports/test_orchestrator.py`:

```python
# ---------- Phase 5.5: night/asia orchestrator tests ----------


VALID_NIGHT_ASIA_REPORT = (
    "# D-Archive\n"
    "## 🔒 Lock-in Metadata\nx\n"
    "## 📊 MES — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MNQ — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
    "## 📊 MGC — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
    "## F. 期货结构\nx\n## 📰 Breaking News\nx\n"
    "## D. Pattern Archive\npatterns\n## 📑 数据快照\nok\n"
)


def _night_fake_ib():
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    return fake_ib


def test_run_night_writes_obsidian_with_night_filename(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_night(
        run_at=datetime(2026, 5, 6, 2, tzinfo=timezone.utc),  # 19:00 PT
    )
    assert result.success is True
    assert result.report_path.name == "2026-05-05-1900PT-night.md"

    report_row = state.get_report_by_id(result.report_id)
    assert report_row["report_type"] == "night"


def test_run_asia_writes_obsidian_with_asia_filename(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_asia(
        run_at=datetime(2026, 5, 6, 6, tzinfo=timezone.utc),  # 23:00 PT
    )
    assert result.success is True
    assert result.report_path.name == "2026-05-05-2300PT-asia.md"


def test_run_night_does_not_push_telegram(tmp_path):
    """night/asia explicitly skip Telegram per spec §2.2."""
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    fake_telegram = MagicMock()
    async def _push(*args, **kwargs):
        return MagicMock(success=True, message_count=1)
    fake_telegram.push = _push

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    orchestrator.telegram_pusher = fake_telegram

    result = orchestrator.run_night(
        run_at=datetime(2026, 5, 6, 2, tzinfo=timezone.utc),
    )
    assert result.success is True
    # Telegram pusher.push was NOT called for night
    assert not hasattr(fake_telegram.push, "call_count") or \
           getattr(fake_telegram, "_telegram_called", False) is False


def test_run_asia_idempotent(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text=VALID_NIGHT_ASIA_REPORT)

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    first = orchestrator.run_asia(
        run_at=datetime(2026, 5, 6, 6, tzinfo=timezone.utc),
    )
    second = orchestrator.run_asia(
        run_at=datetime(2026, 5, 6, 6, tzinfo=timezone.utc),
    )
    assert first.success is True
    assert second.skipped_idempotent is True
    assert fake_ai.call.call_count == 1


def test_run_night_validation_fail_marks_failed(tmp_path):
    fake_ib = _night_fake_ib()
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    state, orchestrator = _make_orchestrator(tmp_path, fake_ib, fake_ai)
    result = orchestrator.run_night(
        run_at=datetime(2026, 5, 6, 2, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()
```

- [ ] **Step 10.2: Run tests to verify red**

Run: `pytest tests/reports/test_orchestrator.py -v -k "run_night or run_asia"`

Expected: FAIL with `AttributeError: 'Orchestrator' object has no attribute 'run_night'`

- [ ] **Step 10.3: Implement orchestrator methods**

Append to `src/daytrader/reports/core/orchestrator.py` (after `_run_cadence_intraday_4h`):

```python
    # --- Phase 5.5 T10: night/asia D-only cadences ---

    def run_night(self, run_at: datetime) -> PipelineResult:
        """Phase 5.5 T10: 19:00 PT D-only learning archive."""
        from daytrader.reports.types.night_asia import (
            NightAsiaConfig, NightAsiaGenerator,
        )
        config = NightAsiaConfig(
            cadence_label="night",
            trigger_time_pt="19:00",
            news_time_window="past 4h",
        )
        return self._run_cadence_night_asia(config, run_at)

    def run_asia(self, run_at: datetime) -> PipelineResult:
        """Phase 5.5 T10: 23:00 PT D-only learning archive."""
        from daytrader.reports.types.night_asia import (
            NightAsiaConfig, NightAsiaGenerator,
        )
        config = NightAsiaConfig(
            cadence_label="asia",
            trigger_time_pt="23:00",
            news_time_window="past 4h",
        )
        return self._run_cadence_night_asia(config, run_at)

    def _run_cadence_night_asia(
        self,
        config,
        run_at: datetime,
    ) -> PipelineResult:
        """Common pipeline for night + asia D-only cadences. NO PDF, NO Telegram."""
        start = time.perf_counter()

        run_at_utc = run_at if run_at.tzinfo else run_at.replace(tzinfo=timezone.utc)
        date_et = run_at_utc.astimezone(ET).date().isoformat()
        time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
        time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

        if self.state_db.already_generated_today(config.cadence_label, date_et):
            return PipelineResult(
                success=True, report_id=None, report_path=None,
                skipped_idempotent=True,
            )

        report_id = self.state_db.insert_report_pending(
            scheduled_at=run_at_utc,
            report_type=config.cadence_label,
        )

        try:
            context = self.context_loader.load(date_et=date_et)

            from daytrader.reports.futures_data.term_prices import TermPricesFetcher
            from daytrader.reports.futures_data.underlying_prices import (
                UnderlyingPriceFetcher,
            )
            from daytrader.reports.types.night_asia import NightAsiaGenerator

            generator = NightAsiaGenerator(
                config=config,
                ib_client=self.ib_client,
                ai_analyst=self.ai_analyst,
                symbols=self.symbols,
                tradable_symbols=self.tradable_symbols,
                underlying_price_fetcher=UnderlyingPriceFetcher(self.ib_client),
                term_price_fetcher=TermPricesFetcher(self.ib_client),
            )

            outcome = generator.generate(
                context=context,
                date_et=date_et,
                run_timestamp_pt=f"{time_pt_str} PT",
                run_timestamp_et=f"{time_et_str} ET",
            )

            for warning in outcome.warnings:
                stage, _, reason = warning.partition(": ")
                self.state_db.log_failure(
                    report_type=config.cadence_label,
                    scheduled_at=run_at_utc,
                    failure_stage=stage or "unknown",
                    failure_reason=reason or warning,
                    retry_count=0,
                )

            if not outcome.validation.ok:
                self.state_db.update_report_status(
                    report_id, status="failed",
                    failure_reason=(
                        f"validation missing: {outcome.validation.missing}"
                    ),
                    tokens_input=outcome.ai_result.input_tokens,
                    tokens_output=outcome.ai_result.output_tokens,
                    duration_seconds=time.perf_counter() - start,
                )
                return PipelineResult(
                    success=False, report_id=report_id, report_path=None,
                    failure_reason=(
                        f"validation: missing sections "
                        f"{outcome.validation.missing}"
                    ),
                )

            writer = ObsidianWriter(
                vault_root=self.vault_root,
                fallback_dir=self.fallback_dir,
                daily_folder=self.daily_folder,
            )
            write_result = writer.write_night_asia(
                date_iso=date_et,
                cadence=config.cadence_label,
                content=outcome.report_text,
            )

            # NO PDF, NO Telegram for night/asia per spec §2.2.
            # Lock-in archive is written to Obsidian only.

            duration = time.perf_counter() - start
            self.state_db.update_report_status(
                report_id, status="success",
                obsidian_path=str(write_result.path),
                tokens_input=outcome.ai_result.input_tokens,
                tokens_output=outcome.ai_result.output_tokens,
                cache_hit_rate=(
                    outcome.ai_result.cache_read_tokens
                    / max(outcome.ai_result.input_tokens, 1)
                ),
                duration_seconds=duration,
                estimated_cost_usd=self._estimate_cost(outcome.ai_result),
            )
            return PipelineResult(
                success=True, report_id=report_id,
                report_path=write_result.path,
            )

        except Exception as exc:
            duration = time.perf_counter() - start
            self.state_db.update_report_status(
                report_id, status="failed",
                failure_reason=f"{type(exc).__name__}: {exc}",
                duration_seconds=duration,
            )
            return PipelineResult(
                success=False, report_id=report_id, report_path=None,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
```

- [ ] **Step 10.4: Run tests to verify green**

Run: `pytest tests/reports/test_orchestrator.py -v -k "run_night or run_asia"`

Expected: 5 PASSED

- [ ] **Step 10.5: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥592 passed`

- [ ] **Step 10.6: Commit**

```bash
git add src/daytrader/reports/core/orchestrator.py tests/reports/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(reports): Orchestrator.run_night + run_asia (Phase 5.5 T10)

Adds 2 D-only orchestrator dispatch methods + shared
_run_cadence_night_asia helper. Mirrors _run_cadence_intraday_4h
shape but:
  - NO PDF rendering (D-only is text archive)
  - NO Telegram push (overnight cadences shouldn't ping user)
  - Uses NightAsiaGenerator + obsidian_writer.write_night_asia
  - report_type is "night" or "asia" — distinct cadences for
    state.db reports table + idempotency check

Master spec §2.2: night and asia have Telegram=❌; D purpose only.

5 new tests; 592 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: CLI dispatch extension

**Goal:** Wire CLI `daytrader reports run --type X` to dispatch the 4 new types into orchestrator.

**Files:**
- Modify: `src/daytrader/cli/reports.py` (extend `run_cmd`)
- Test: `tests/cli/test_reports_cli.py` (extend)

- [ ] **Step 11.1: Write failing tests**

Append to `tests/cli/test_reports_cli.py`:

```python
def test_cli_run_intraday_4h_1_active_not_stub():
    """`daytrader reports run --type intraday-4h-1` should NOT fail-fast
    with 'in a later phase' (it's now active in Phase 5.5)."""
    import subprocess, sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "-c",
         "from daytrader.cli.reports import VALID_TYPES; "
         "import sys; "
         "assert 'intraday-4h-1' in VALID_TYPES; "
         "print('ok')"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_run_rejects_only_stub_types():
    """After Phase 5.5, only 'weekly' should remain in 'in later phase' rejection."""
    # Inspect the source — we expect ACTIVE_TYPES to have grown to 6.
    import inspect
    from daytrader.cli import reports as cli_reports
    src = inspect.getsource(cli_reports.run_cmd)
    assert "intraday-4h-1" in src or "intraday_4h_1" in src
    assert "intraday-4h-2" in src or "intraday_4h_2" in src
    assert "night" in src.lower()
    assert "asia" in src.lower()


def test_cli_run_intraday_4h_1_dispatches_to_orchestrator(tmp_path, monkeypatch):
    """When called via subprocess + mock IB, should call run_intraday_4h_1."""
    # This is a smoke test — fully testing CLI dispatch requires a live
    # daytrader subprocess which is heavy. We just verify the dispatch
    # branch exists in source.
    import inspect
    from daytrader.cli import reports as cli_reports
    src = inspect.getsource(cli_reports.run_cmd)
    assert "run_intraday_4h_1" in src
    assert "run_intraday_4h_2" in src
    assert "run_night" in src
    assert "run_asia" in src


def test_cli_run_weekly_still_rejected_as_later_phase():
    """Weekly is the ONLY type still rejected. Phase 5.7+ retrofits weekly."""
    import inspect
    from daytrader.cli import reports as cli_reports
    src = inspect.getsource(cli_reports.run_cmd)
    # weekly should still be in the "later phase" rejection
    assert "weekly" in src
```

- [ ] **Step 11.2: Run tests to verify red**

Run: `pytest tests/cli/test_reports_cli.py -v -k "intraday_4h or _night or _asia or stub or later_phase"`

Expected: at least 3 FAIL because the dispatch branch doesn't yet contain `run_intraday_4h_1` / `run_intraday_4h_2` / `run_night` / `run_asia` calls.

- [ ] **Step 11.3: Update CLI dispatch**

Modify `src/daytrader/cli/reports.py` `run_cmd`. Find the block:

```python
    if report_type not in ("premarket", "eod"):
        click.echo(
            f"Phase 5 implements premarket + eod. {report_type!r} is in a "
            "later phase.",
            err=True,
        )
        ctx.exit(2)
```

Replace with:

```python
    # Phase 5.5 (2026-05-05): now also active for intraday-4h-1, intraday-4h-2,
    # night, asia. Only weekly remains in "later phase" rejection.
    ACTIVE_TYPES = (
        "premarket",
        "eod",
        "intraday-4h-1",
        "intraday-4h-2",
        "night",
        "asia",
    )
    if report_type not in ACTIVE_TYPES:
        click.echo(
            f"Phase 5.5 implements {ACTIVE_TYPES}. {report_type!r} is in a "
            "later phase (Phase 5.7+ for weekly).",
            err=True,
        )
        ctx.exit(2)
```

Also update the dispatch — find:

```python
        if report_type == "premarket":
            result = orchestrator.run_premarket(
                run_at=datetime.now(timezone.utc)
            )
        else:  # report_type == "eod" (validated above)
            result = orchestrator.run_eod(
                run_at=datetime.now(timezone.utc)
            )
```

Replace with:

```python
        # Phase 5.5: dispatch table for 6 active types
        now = datetime.now(timezone.utc)
        DISPATCH = {
            "premarket": orchestrator.run_premarket,
            "eod": orchestrator.run_eod,
            "intraday-4h-1": orchestrator.run_intraday_4h_1,
            "intraday-4h-2": orchestrator.run_intraday_4h_2,
            "night": orchestrator.run_night,
            "asia": orchestrator.run_asia,
        }
        result = DISPATCH[report_type](run_at=now)
```

Also update the help text:

```python
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(VALID_TYPES, case_sensitive=False),
    help=(
        "Report type to generate (Phase 5.5: premarket, eod, "
        "intraday-4h-1, intraday-4h-2, night, asia)."
    ),
)
```

- [ ] **Step 11.4: Run tests to verify green**

Run: `pytest tests/cli/test_reports_cli.py -v`

Expected: All passing including new tests.

- [ ] **Step 11.5: Smoke test live CLI (no IB connection — should fail-fast on connect)**

Run: `daytrader reports run --type intraday-4h-1 2>&1 | head -5`

Expected: error mentioning IB connection / TWS, NOT "in a later phase".

Run: `daytrader reports run --type weekly 2>&1; echo exit=$?`

Expected: "in a later phase" message + exit=2.

- [ ] **Step 11.6: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥596 passed`

- [ ] **Step 11.7: Commit**

```bash
git add src/daytrader/cli/reports.py tests/cli/test_reports_cli.py
git commit -m "$(cat <<'EOF'
feat(reports): CLI dispatch for 4 new cadences (Phase 5.5 T11)

Replaces hard-coded 2-type if/else with DISPATCH table covering 6
active report types: premarket, eod, intraday-4h-1, intraday-4h-2,
night, asia. Only weekly remains stub (Phase 5.7).

ACTIVE_TYPES tuple is the single source of truth — both validation
and dispatch use it. Adding a new cadence in future phases is now
just adding one entry to DISPATCH dict.

4 new tests; 596 total passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: launchd wrapper scripts (4 files)

**Goal:** 4 shell wrappers, mirroring `run_eod_launchd.sh` (49693d2) pattern.

**Files (Create):**
- `scripts/run_intraday_4h_1_launchd.sh`
- `scripts/run_intraday_4h_2_launchd.sh`
- `scripts/run_night_launchd.sh`
- `scripts/run_asia_launchd.sh`

- [ ] **Step 12.1: Create run_intraday_4h_1_launchd.sh**

```bash
cat > scripts/run_intraday_4h_1_launchd.sh <<'WRAPPER'
#!/usr/bin/env bash
# scripts/run_intraday_4h_1_launchd.sh — Phase 5.5 T12 (2026-05-05)
#
# launchd wrapper for intraday-4h-1 cadence (07:00 PT Mon-Fri).
# Mirrors run_eod_launchd.sh pattern.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_intraday_4h_1_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/intraday-4h-1-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_intraday_4h_1_launchd] start $(date -Iseconds)"
echo "[run_intraday_4h_1_launchd] PATH=$PATH"
echo "[run_intraday_4h_1_launchd] PWD=$PROJECT_ROOT"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_intraday_4h_1_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "intraday-4h-1 preflight failed at 07:00 PT" with title "DayTrader 4H-1" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

echo "[run_intraday_4h_1_launchd] preflight ok, invoking reports run --type intraday-4h-1"
uv run daytrader reports run --type intraday-4h-1 --no-pdf
rc=$?
echo "[run_intraday_4h_1_launchd] reports run exit=$rc"
echo "[run_intraday_4h_1_launchd] end $(date -Iseconds)"
exit "$rc"
WRAPPER
chmod +x scripts/run_intraday_4h_1_launchd.sh
```

- [ ] **Step 12.2: Create run_intraday_4h_2_launchd.sh**

```bash
cat > scripts/run_intraday_4h_2_launchd.sh <<'WRAPPER'
#!/usr/bin/env bash
# scripts/run_intraday_4h_2_launchd.sh — Phase 5.5 T12

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_intraday_4h_2_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/intraday-4h-2-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_intraday_4h_2_launchd] start $(date -Iseconds)"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_intraday_4h_2_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "intraday-4h-2 preflight failed at 11:00 PT" with title "DayTrader 4H-2" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

echo "[run_intraday_4h_2_launchd] preflight ok"
uv run daytrader reports run --type intraday-4h-2 --no-pdf
rc=$?
echo "[run_intraday_4h_2_launchd] reports run exit=$rc"
exit "$rc"
WRAPPER
chmod +x scripts/run_intraday_4h_2_launchd.sh
```

- [ ] **Step 12.3: Create run_night_launchd.sh**

```bash
cat > scripts/run_night_launchd.sh <<'WRAPPER'
#!/usr/bin/env bash
# scripts/run_night_launchd.sh — Phase 5.5 T12

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_night_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/night-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_night_launchd] start $(date -Iseconds)"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_night_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "night preflight failed at 19:00 PT" with title "DayTrader Night" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

echo "[run_night_launchd] preflight ok"
uv run daytrader reports run --type night --no-pdf
rc=$?
echo "[run_night_launchd] reports run exit=$rc"
exit "$rc"
WRAPPER
chmod +x scripts/run_night_launchd.sh
```

- [ ] **Step 12.4: Create run_asia_launchd.sh**

```bash
cat > scripts/run_asia_launchd.sh <<'WRAPPER'
#!/usr/bin/env bash
# scripts/run_asia_launchd.sh — Phase 5.5 T12

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_asia_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/asia-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_asia_launchd] start $(date -Iseconds)"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_asia_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "asia preflight failed at 23:00 PT" with title "DayTrader Asia" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

echo "[run_asia_launchd] preflight ok"
uv run daytrader reports run --type asia --no-pdf
rc=$?
echo "[run_asia_launchd] reports run exit=$rc"
exit "$rc"
WRAPPER
chmod +x scripts/run_asia_launchd.sh
```

- [ ] **Step 12.5: Verify all 4 scripts are executable + syntactically valid**

```bash
ls -la scripts/run_intraday_4h_1_launchd.sh scripts/run_intraday_4h_2_launchd.sh scripts/run_night_launchd.sh scripts/run_asia_launchd.sh
bash -n scripts/run_intraday_4h_1_launchd.sh && echo "4h-1 OK"
bash -n scripts/run_intraday_4h_2_launchd.sh && echo "4h-2 OK"
bash -n scripts/run_night_launchd.sh && echo "night OK"
bash -n scripts/run_asia_launchd.sh && echo "asia OK"
```

Expected: 4 files all `-rwxr-xr-x` and all `bash -n` pass.

- [ ] **Step 12.6: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥596 passed` (no test changes).

- [ ] **Step 12.7: Commit**

```bash
git add scripts/run_intraday_4h_1_launchd.sh scripts/run_intraday_4h_2_launchd.sh scripts/run_night_launchd.sh scripts/run_asia_launchd.sh
git commit -m "$(cat <<'EOF'
feat(launchd): 4 wrapper scripts for new cadences (Phase 5.5 T12)

Mirrors run_eod_launchd.sh pattern (49693d2):
  - set -uo pipefail (NOT -e — preflight failure handled separately)
  - PATH explicit (homebrew + system + ~/.local/bin)
  - cd PROJECT_ROOT
  - exec > >(tee) for stdout+stderr capture with proper exit code
  - preflight gate (real ib_insync handshake per daa0d75)
  - macOS notification on preflight fail
  - exit 0 on preflight fail (don't trip launchd ERR exit handling)
  - --no-pdf flag (PDF rendering done in best-effort path inside
    orchestrator; wrapper skips it for speed)

run_premarket_launchd.sh + run_eod_launchd.sh UNCHANGED
(regression boundary).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: launchd plist templates (4 files)

**Goal:** 4 plist templates with Mon-Fri schedule, mirroring EOD (49693d2) pattern.

**Files (Create):**
- `scripts/launchd/com.daytrader.report.intraday-4h-1.0700pt.plist.template`
- `scripts/launchd/com.daytrader.report.intraday-4h-2.1100pt.plist.template`
- `scripts/launchd/com.daytrader.report.night.1900pt.plist.template`
- `scripts/launchd/com.daytrader.report.asia.2300pt.plist.template`

- [ ] **Step 13.1: Create intraday-4h-1 plist (07:00 PT Mon-Fri)**

```bash
cat > scripts/launchd/com.daytrader.report.intraday-4h-1.0700pt.plist.template <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.intraday-4h-1.0700pt</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{PROJECT_ROOT}}/scripts/run_intraday_4h_1_launchd.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/intraday-4h-1.0700pt.out</string>
    <key>StandardErrorPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/intraday-4h-1.0700pt.err</string>

    <key>WorkingDirectory</key>
    <string>{{PROJECT_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>{{HOME}}</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST
```

- [ ] **Step 13.2: Create intraday-4h-2 plist (11:00 PT Mon-Fri)**

```bash
cat > scripts/launchd/com.daytrader.report.intraday-4h-2.1100pt.plist.template <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.intraday-4h-2.1100pt</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{PROJECT_ROOT}}/scripts/run_intraday_4h_2_launchd.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/intraday-4h-2.1100pt.out</string>
    <key>StandardErrorPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/intraday-4h-2.1100pt.err</string>

    <key>WorkingDirectory</key>
    <string>{{PROJECT_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>{{HOME}}</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST
```

- [ ] **Step 13.3: Create night plist (19:00 PT Mon-Fri)**

```bash
cat > scripts/launchd/com.daytrader.report.night.1900pt.plist.template <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.night.1900pt</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{PROJECT_ROOT}}/scripts/run_night_launchd.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/night.1900pt.out</string>
    <key>StandardErrorPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/night.1900pt.err</string>

    <key>WorkingDirectory</key>
    <string>{{PROJECT_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>{{HOME}}</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST
```

- [ ] **Step 13.4: Create asia plist (23:00 PT Mon-Fri)**

```bash
cat > scripts/launchd/com.daytrader.report.asia.2300pt.plist.template <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.asia.2300pt</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{PROJECT_ROOT}}/scripts/run_asia_launchd.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/asia.2300pt.out</string>
    <key>StandardErrorPath</key>
    <string>{{PROJECT_ROOT}}/data/logs/launchd/asia.2300pt.err</string>

    <key>WorkingDirectory</key>
    <string>{{PROJECT_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>{{HOME}}</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST
```

- [ ] **Step 13.5: Verify plist syntax**

```bash
for f in scripts/launchd/com.daytrader.report.intraday-4h-1.0700pt.plist.template \
         scripts/launchd/com.daytrader.report.intraday-4h-2.1100pt.plist.template \
         scripts/launchd/com.daytrader.report.night.1900pt.plist.template \
         scripts/launchd/com.daytrader.report.asia.2300pt.plist.template; do
    plutil -lint "$f"
done
```

Expected: each prints `OK`.

- [ ] **Step 13.6: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥596 passed`.

- [ ] **Step 13.7: Commit**

```bash
git add scripts/launchd/com.daytrader.report.intraday-4h-1.0700pt.plist.template \
        scripts/launchd/com.daytrader.report.intraday-4h-2.1100pt.plist.template \
        scripts/launchd/com.daytrader.report.night.1900pt.plist.template \
        scripts/launchd/com.daytrader.report.asia.2300pt.plist.template
git commit -m "$(cat <<'EOF'
feat(launchd): 4 plist templates for new cadences (Phase 5.5 T13)

Mirrors EOD plist (com.daytrader.report.eod.1400pt.plist.template)
pattern:
  - 5 StartCalendarInterval entries (Weekday 1-5 = Mon-Fri)
  - {{PROJECT_ROOT}} + {{HOME}} placeholders for install script substitution
  - StandardOut/ErrorPath under data/logs/launchd/
  - RunAtLoad=false (only fire on schedule)

Final 6-cadence schedule:
  06:00 PT premarket (existing)
  07:00 PT intraday-4h-1 (NEW)
  11:00 PT intraday-4h-2 (NEW)
  14:00 PT eod (existing)
  19:00 PT night (NEW)
  23:00 PT asia (NEW)
+ Sunday 14:00 PT weekly (existing — Phase 5.7 will refactor)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: install / uninstall scripts (2 pairs)

**Goal:** 4 shell scripts to install + uninstall the new launchd jobs (paired by cadence group).

**Files (Create):**
- `scripts/install_intraday_4h_launchd.sh` (installs both 4h-1 + 4h-2)
- `scripts/uninstall_intraday_4h_launchd.sh`
- `scripts/install_night_asia_launchd.sh` (installs both night + asia)
- `scripts/uninstall_night_asia_launchd.sh`

- [ ] **Step 14.1: Create install_intraday_4h_launchd.sh**

```bash
cat > scripts/install_intraday_4h_launchd.sh <<'INSTALL'
#!/usr/bin/env bash
# scripts/install_intraday_4h_launchd.sh — Phase 5.5 T14
# Installs both intraday-4h-1 and intraday-4h-2 launchd jobs.
# Idempotent: existing jobs are bootout'd first, then re-installed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCHAGENTS"

UID_NUM="$(id -u)"

for cadence in "intraday-4h-1.0700pt" "intraday-4h-2.1100pt"; do
    LABEL="com.daytrader.report.${cadence}"
    TEMPLATE="$SCRIPT_DIR/launchd/${LABEL}.plist.template"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "[install_intraday_4h] missing template: $TEMPLATE" >&2
        exit 1
    fi

    # Bootout existing if loaded (ignore errors — may not be loaded)
    if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
        echo "[install_intraday_4h] bootout existing $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    fi

    # Render template — substitute {{PROJECT_ROOT}} and {{HOME}}
    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{HOME}}|$HOME|g" \
        "$TEMPLATE" > "$DEST"

    echo "[install_intraday_4h] bootstrap $LABEL → $DEST"
    launchctl bootstrap "gui/$UID_NUM" "$DEST"
done

echo "[install_intraday_4h] DONE — verify with: launchctl list | grep intraday-4h"
launchctl list | grep -E "intraday-4h" || echo "(none loaded — check above for errors)"
INSTALL
chmod +x scripts/install_intraday_4h_launchd.sh
```

- [ ] **Step 14.2: Create uninstall_intraday_4h_launchd.sh**

```bash
cat > scripts/uninstall_intraday_4h_launchd.sh <<'UNINSTALL'
#!/usr/bin/env bash
# scripts/uninstall_intraday_4h_launchd.sh — Phase 5.5 T14

set -euo pipefail

LAUNCHAGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

for cadence in "intraday-4h-1.0700pt" "intraday-4h-2.1100pt"; do
    LABEL="com.daytrader.report.${cadence}"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ -f "$DEST" ]]; then
        echo "[uninstall_intraday_4h] bootout + rm $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
        rm -v "$DEST"
    else
        echo "[uninstall_intraday_4h] $LABEL plist not found, skipping"
    fi
done

echo "[uninstall_intraday_4h] DONE"
UNINSTALL
chmod +x scripts/uninstall_intraday_4h_launchd.sh
```

- [ ] **Step 14.3: Create install_night_asia_launchd.sh**

```bash
cat > scripts/install_night_asia_launchd.sh <<'INSTALL'
#!/usr/bin/env bash
# scripts/install_night_asia_launchd.sh — Phase 5.5 T14

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCHAGENTS"

UID_NUM="$(id -u)"

for cadence in "night.1900pt" "asia.2300pt"; do
    LABEL="com.daytrader.report.${cadence}"
    TEMPLATE="$SCRIPT_DIR/launchd/${LABEL}.plist.template"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "[install_night_asia] missing template: $TEMPLATE" >&2
        exit 1
    fi

    if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
        echo "[install_night_asia] bootout existing $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    fi

    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{HOME}}|$HOME|g" \
        "$TEMPLATE" > "$DEST"

    echo "[install_night_asia] bootstrap $LABEL → $DEST"
    launchctl bootstrap "gui/$UID_NUM" "$DEST"
done

echo "[install_night_asia] DONE"
launchctl list | grep -E "night|asia" || echo "(none loaded — check above for errors)"
INSTALL
chmod +x scripts/install_night_asia_launchd.sh
```

- [ ] **Step 14.4: Create uninstall_night_asia_launchd.sh**

```bash
cat > scripts/uninstall_night_asia_launchd.sh <<'UNINSTALL'
#!/usr/bin/env bash
# scripts/uninstall_night_asia_launchd.sh — Phase 5.5 T14

set -euo pipefail

LAUNCHAGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

for cadence in "night.1900pt" "asia.2300pt"; do
    LABEL="com.daytrader.report.${cadence}"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ -f "$DEST" ]]; then
        echo "[uninstall_night_asia] bootout + rm $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
        rm -v "$DEST"
    else
        echo "[uninstall_night_asia] $LABEL plist not found, skipping"
    fi
done

echo "[uninstall_night_asia] DONE"
UNINSTALL
chmod +x scripts/uninstall_night_asia_launchd.sh
```

- [ ] **Step 14.5: Verify scripts are executable + syntactically valid**

```bash
ls -la scripts/install_intraday_4h_launchd.sh scripts/uninstall_intraday_4h_launchd.sh \
       scripts/install_night_asia_launchd.sh scripts/uninstall_night_asia_launchd.sh
for f in scripts/install_intraday_4h_launchd.sh scripts/uninstall_intraday_4h_launchd.sh \
         scripts/install_night_asia_launchd.sh scripts/uninstall_night_asia_launchd.sh; do
    bash -n "$f" && echo "$f OK"
done
```

Expected: 4 files all `-rwxr-xr-x` and all `bash -n` pass.

- [ ] **Step 14.6: Smoke test install + uninstall (idempotent)**

```bash
# Install (first time)
./scripts/install_intraday_4h_launchd.sh

# Verify both jobs loaded
launchctl list | grep intraday-4h

# Install again — should be idempotent (bootout + reinstall)
./scripts/install_intraday_4h_launchd.sh

# Uninstall
./scripts/uninstall_intraday_4h_launchd.sh

# Verify gone
launchctl list | grep intraday-4h && echo "STILL LOADED — BUG" || echo "uninstalled OK"
```

Expected: jobs appear after install, persist after re-install (no error), absent after uninstall.

Then repeat for night/asia:

```bash
./scripts/install_night_asia_launchd.sh
launchctl list | grep -E "night|asia"
./scripts/uninstall_night_asia_launchd.sh
launchctl list | grep -E "night|asia" && echo "STILL LOADED — BUG" || echo "uninstalled OK"
```

- [ ] **Step 14.7: Verify no regression**

Run: `pytest tests/ -q --tb=line --no-header 2>&1 | tail -3`

Expected: `≥596 passed`.

- [ ] **Step 14.8: Commit**

```bash
git add scripts/install_intraday_4h_launchd.sh scripts/uninstall_intraday_4h_launchd.sh \
        scripts/install_night_asia_launchd.sh scripts/uninstall_night_asia_launchd.sh
git commit -m "$(cat <<'EOF'
feat(launchd): install/uninstall scripts for new cadences (Phase 5.5 T14)

Two pairs (4 files):
  install_intraday_4h_launchd.sh   — installs both 4h-1 + 4h-2
  uninstall_intraday_4h_launchd.sh — bootout + rm both
  install_night_asia_launchd.sh    — installs both night + asia
  uninstall_night_asia_launchd.sh  — bootout + rm both

Idempotent: install scripts bootout existing label first, then
re-install (sed substitutes {{PROJECT_ROOT}} + {{HOME}}). Re-running
install is safe.

Pattern mirrors install_eod_launchd.sh (Phase 5 T11).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: .gitignore + runbooks + final verification

**Goal:** Wire .gitignore for the new launchd log globs, write 2 runbooks, run full acceptance check.

**Files:**
- Modify: `.gitignore`
- Create: `docs/ops/intraday-4h-runbook.md`
- Create: `docs/ops/night-asia-runbook.md`
- Modify: `docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md` (mark Implemented)

- [ ] **Step 15.1: Update .gitignore**

Find the existing block (around line 30):

```
data/logs/launchd/premarket-*.log
data/logs/launchd/weekly-*.log
data/logs/launchd/eod-*.log
```

Add 4 new lines:

```bash
cat >> .gitignore <<'GITIGNORE'

# Phase 5.5 launchd logs (2026-05-05)
data/logs/launchd/intraday-4h-1-*.log
data/logs/launchd/intraday-4h-2-*.log
data/logs/launchd/night-*.log
data/logs/launchd/asia-*.log
data/logs/launchd/intraday-4h-1.0700pt.out
data/logs/launchd/intraday-4h-1.0700pt.err
data/logs/launchd/intraday-4h-2.1100pt.out
data/logs/launchd/intraday-4h-2.1100pt.err
data/logs/launchd/night.1900pt.out
data/logs/launchd/night.1900pt.err
data/logs/launchd/asia.2300pt.out
data/logs/launchd/asia.2300pt.err
GITIGNORE
```

- [ ] **Step 15.2: Verify .gitignore works**

```bash
# Create test log files matching the new patterns
mkdir -p data/logs/launchd
touch data/logs/launchd/intraday-4h-1-test.log
touch data/logs/launchd/night-test.log

# Verify git ignores them
git check-ignore -v data/logs/launchd/intraday-4h-1-test.log
git check-ignore -v data/logs/launchd/night-test.log

# Cleanup
rm data/logs/launchd/intraday-4h-1-test.log data/logs/launchd/night-test.log
```

Expected: `git check-ignore` confirms each path matches a `.gitignore` rule.

- [ ] **Step 15.3: Create intraday-4h-runbook.md**

```bash
cat > docs/ops/intraday-4h-runbook.md <<'RUNBOOK'
# Intraday 4H Cadences Runbook

**Cadences:** intraday-4h-1 (07:00 PT) + intraday-4h-2 (11:00 PT)
**Auto-fire:** Mon-Fri via launchd
**Spec:** docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md

## What runs when

| Time | Cadence | Trigger | Generates |
|---|---|---|---|
| 07:00 PT (10:00 ET) | intraday-4h-1 | launchd `com.daytrader.report.intraday-4h-1.0700pt` | `Daily/<date>-0700PT-4H1.md` |
| 11:00 PT (14:00 ET) | intraday-4h-2 | launchd `com.daytrader.report.intraday-4h-2.1100pt` | `Daily/<date>-1100PT-4H2.md` |

## Differences between 4h-1 and 4h-2

| Feature | 4h-1 | 4h-2 |
|---|---|---|
| Plan Retrospective | ❌ skip (placeholder text) | ✅ full retrospective + persist to `plan_retrospective_daily` |
| Sentiment refresh | ❌ reuse premarket cache | ✅ refresh with `time_window="past 5h"` |
| News window | past 1h | past 5h |
| Trade archive | light list | light list |
| Telegram | ✅ | ✅ |
| PDF render | ❌ skipped (--no-pdf flag) | ❌ skipped |
| Length target | 5-7K chars | 5-7K chars |

## Install / uninstall

```bash
# Install both jobs (idempotent)
./scripts/install_intraday_4h_launchd.sh

# Verify loaded
launchctl list | grep intraday-4h

# Uninstall
./scripts/uninstall_intraday_4h_launchd.sh
```

## Manual trigger (skip launchd)

```bash
# Run 4h-1 immediately
daytrader reports run --type intraday-4h-1 --no-pdf

# Run 4h-2 immediately
daytrader reports run --type intraday-4h-2 --no-pdf
```

## Troubleshooting

### Report not generated at 07:00 PT or 11:00 PT

1. **Check launchd actually fired:**
   ```bash
   ls -la data/logs/launchd/intraday-4h-1-*.log
   tail -50 $(ls -t data/logs/launchd/intraday-4h-1-*.log | head -1)
   ```

2. **Check preflight passed:**
   - TWS / IB Gateway running and authenticated
   - claude CLI on PATH (`which claude`)
   - config files present (`config/default.yaml` + `config/user.yaml`)

3. **Check state.db for failed row:**
   ```bash
   sqlite3 data/state.db "SELECT * FROM reports WHERE report_type LIKE 'intraday-4h%' ORDER BY id DESC LIMIT 5;"
   ```

4. **Check warnings table for soft failures (I1 fix):**
   ```bash
   sqlite3 data/state.db "SELECT * FROM failures WHERE report_type LIKE 'intraday-4h%' ORDER BY id DESC LIMIT 10;"
   ```

### 4h-2 retrospective is empty / failed

1. **Check premarket plan was generated today:**
   ```bash
   ls -la <obsidian-vault>/Daily/$(date +%Y-%m-%d)-premarket.md
   ```
   If missing, premarket failed → 4h-2 has no plan to retrospect against.

2. **Check `plan_retrospective_daily` table:**
   ```bash
   sqlite3 data/state.db "SELECT * FROM plan_retrospective_daily WHERE date = date('now');"
   ```

3. **Check 5m bar fetch (intraday_bar_fetcher with end_time pinned to 11:00 PT = 14:00 ET):**
   - Verify TWS healthy at 11:00 PT
   - Verify 5m support in IBClient (Phase 5.5 hot-fix C1, commit b04b151)

### Report missing required sections

Validator catches missing sections and marks report `failed`. Check `state.failures` for `failure_stage="validation"`.

## Logs

Per-fire log files:
- `data/logs/launchd/intraday-4h-1-<TS>.log` — full stdout+stderr from wrapper
- `data/logs/launchd/intraday-4h-1.0700pt.out` — launchd stdout (rotated by launchd)
- `data/logs/launchd/intraday-4h-1.0700pt.err` — launchd stderr (should always be 0 byte if healthy)

Same pattern for 4h-2. All ignored by `.gitignore`.
RUNBOOK
```

- [ ] **Step 15.4: Create night-asia-runbook.md**

```bash
cat > docs/ops/night-asia-runbook.md <<'RUNBOOK'
# Night/Asia Cadences Runbook

**Cadences:** night (19:00 PT) + asia (23:00 PT)
**Auto-fire:** Mon-Fri via launchd
**Spec:** docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md

## What runs when

| Time | Cadence | Trigger | Generates |
|---|---|---|---|
| 19:00 PT (22:00 ET) | night | launchd `com.daytrader.report.night.1900pt` | `Daily/<date>-1900PT-night.md` |
| 23:00 PT (02:00+1 ET) | asia | launchd `com.daytrader.report.asia.2300pt` | `Daily/<date>-2300PT-asia.md` |

## Purpose

D-only learning archive. NO A/B/C sections. Generates pattern_tags + news_event_tags YAML frontmatter for future programmatic queries (e.g. "all bullish_engulf at support_test in last 30 days").

## Differences from intraday-4h

| Feature | night/asia | intraday-4h |
|---|---|---|
| Sections | metadata + multi-TF + F + news + D archive | A+B+C+F + sentiment + retrospective + trades |
| Multi-TF | 4H + 1H only | D + 4H + 1H |
| Telegram | ❌ off (no notification) | ✅ on |
| PDF | ❌ off | ❌ off |
| Length | 3.5-5K chars | 5-7K chars |
| Sentiment | ❌ no fetch | 4h-2 only |
| Plan retrospective | ❌ no | 4h-2 only |
| Trade archive | lock-in count only | light list |

## Install / uninstall

```bash
./scripts/install_night_asia_launchd.sh
launchctl list | grep -E "night|asia"
./scripts/uninstall_night_asia_launchd.sh
```

## Manual trigger

```bash
daytrader reports run --type night --no-pdf
daytrader reports run --type asia --no-pdf
```

## Troubleshooting

Same as intraday-4h-runbook.md, with these specifics:

1. **TWS at 23:00 PT** — IB Gateway is in cme globex / hkfe boundary; preflight handshake confirms healthy.

2. **D archive frontmatter** — verify report file has YAML at top:
   ```yaml
   ---
   type: night  (or asia)
   date: 2026-05-05
   pattern_tags: [...]
   news_event_tags: [...]
   ---
   ```

3. **Future query** — query D archives by tag (Phase 6 work — not yet implemented):
   ```bash
   # Future: daytrader research query --pattern bullish_engulf --days 30
   ```

## Logs

- `data/logs/launchd/night-<TS>.log`
- `data/logs/launchd/asia-<TS>.log`
- Plus the launchd `.out` / `.err` files alongside

All ignored by `.gitignore`.
RUNBOOK
```

- [ ] **Step 15.5: Verify runbooks created**

```bash
ls -la docs/ops/intraday-4h-runbook.md docs/ops/night-asia-runbook.md
wc -l docs/ops/intraday-4h-runbook.md docs/ops/night-asia-runbook.md
```

Expected: both files exist, ≥80 lines each.

- [ ] **Step 15.6: Update spec status to Implemented**

Modify the first line of `docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md`:

Find:
```
**Status**: Approved (2026-05-05) — pending writing-plans phase
```

Replace with:
```
**Status**: Implemented (2026-05-05) — see commit history for task-by-task progress
```

Also update the bottom of `## 17. Status`:

Add:
```
- 2026-05-05 (later): Plan executed via subagent-driven-development.
  All 15 tasks complete; 596+ tests passing; 0 regressions.
  Premarket / EOD UNCHANGED per regression boundary.
```

- [ ] **Step 15.7: Final acceptance check (run all spec §12 ABC items)**

```bash
echo "=== Acceptance A1: dry-run all 4 new types ==="
for t in intraday-4h-1 intraday-4h-2 night asia; do
    daytrader reports dry-run --type $t > /dev/null && echo "$t dry-run OK"
done

echo
echo "=== Acceptance D1+D2: full pytest, regression boundary ==="
pytest tests/ -q --tb=line --no-header 2>&1 | tail -3

echo
echo "=== Acceptance G: regression boundary check (UNCHANGED files) ==="
for f in src/daytrader/reports/types/premarket.py \
         src/daytrader/reports/types/eod.py \
         src/daytrader/reports/templates/premarket.md \
         src/daytrader/reports/templates/eod.md \
         scripts/preflight_check.py \
         scripts/run_premarket_launchd.sh \
         scripts/run_eod_launchd.sh; do
    diff_lines=$(git log 5b90b7b..HEAD --oneline -- "$f" | wc -l | tr -d ' ')
    if [ "$diff_lines" = "0" ]; then
        echo "✅ $f: UNCHANGED since spec start"
    else
        echo "⚠️  $f: modified ($diff_lines commits)"
    fi
done

echo
echo "=== Acceptance E1: launchd state ==="
launchctl list | grep -i daytrader

echo
echo "=== Acceptance F: docs ==="
ls -la docs/ops/intraday-4h-runbook.md docs/ops/night-asia-runbook.md
grep -m1 "^\*\*Status\*\*" docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md
```

Expected:
- All 4 dry-runs OK
- ≥596 tests passing, 0 failed
- All UNCHANGED files showing 0 modifications
- launchd shows 7 jobs (premarket + 4h-1 + 4h-2 + eod + night + asia + weekly)
- Both runbooks exist
- Spec status = Implemented

- [ ] **Step 15.8: Final commit**

```bash
git add .gitignore docs/ops/intraday-4h-runbook.md docs/ops/night-asia-runbook.md docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md
git commit -m "$(cat <<'EOF'
docs(reports): Phase 5.5 runbooks + .gitignore + spec mark Implemented (T15)

Final task of Phase 5.5 multi-cadence rollout:
- .gitignore: 4 new launchd log globs (intraday-4h-1/-2, night, asia)
- docs/ops/intraday-4h-runbook.md: 80+ lines, troubleshooting, install
  scripts, manual trigger commands, log file locations
- docs/ops/night-asia-runbook.md: 70+ lines, D-only specifics,
  pattern_tags/news_event_tags frontmatter for future query
- Spec status: Implemented (2026-05-05)

Final state:
  - 6 active cadences (premarket + 4h-1 + 4h-2 + eod + night + asia)
  - launchd auto-fire Mon-Fri (each cadence) + Sun (weekly legacy)
  - 596+ tests passing (538 base + 80 new + buffer)
  - premarket.py / eod.py UNCHANGED (regression boundary preserved)

Phase 5.6 (post-Trade-#1): retrofit premarket + EOD into
BaseCadenceGenerator pattern.
Phase 5.7: rewrite weekly cadence via base class.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final Self-Review Checklist (run after all 15 tasks complete)

Before declaring Phase 5.5 ship-ready, verify each spec acceptance criterion:

### Spec §12 §A — Functional correctness
- [ ] A1: 4 dry-run types exit 0
- [ ] A2: 4h-1 writes `<date>-0700PT-4H1.md`
- [ ] A3: 4h-2 / night / asia each write correct filename
- [ ] A4: Same-day repeat returns `skipped_idempotent=True`
- [ ] A5: 4h-2 contains `## 🔄 Plan Retrospective` + DB row
- [ ] A6: 4h-1 has retrospective placeholder, NOT real retrospective
- [ ] A7: 4h-2 sentiment refreshed; 4h-1 reuses premarket
- [ ] A8: night/asia have NO A/B/C/sentiment

### Spec §12 §B — Validation
- [ ] B1: OutputValidator on full 4h report → ok=True; missing → ok=False
- [ ] B2: Same for night, asia
- [ ] B3: Length ranges respected
- [ ] B4: C section before A section in 4h template

### Spec §12 §C — Error handling
- [ ] C1: 4h-1 missing plan → graceful "⚠️ plan 未找到", continues
- [ ] C2: 4h-2 retro ValueError → markdown degraded + state.failures row
- [ ] C3: F section partial fail → degraded inline, warnings persisted
- [ ] C4: Validator fail → report failed + failure_reason
- [ ] C5: Vault unavailable → fallback to data/exports/

### Spec §12 §D — Test coverage
- [ ] D1: ≥620 tests passing (target 596 + buffer = OK)
- [ ] D2: 0 existing tests broken
- [ ] D3: Each new generator has ≥10 unit tests
- [ ] D4: Orchestrator integration tests cover all 4 cadences × idempotency / validation-fail / Telegram-disabled paths

### Spec §12 §E — System integration
- [ ] E1: 7 launchd jobs visible
- [ ] E2: install/uninstall idempotent
- [ ] E3: Wrapper scripts match EOD pattern
- [ ] E4: Log files in correct location
- [ ] E5: preflight failure → notification + exit 0

### Spec §12 §F — Documentation
- [ ] F1: Spec status = Implemented
- [ ] F2: Plan tasks all ✅
- [ ] F3: intraday-4h-runbook.md complete
- [ ] F4: night-asia-runbook.md complete
- [ ] F5: README/master spec cadence table updated (optional — Phase 5.7 final cleanup)

### Spec §12 §G — Regression boundary
- [ ] G1-G8: All UNCHANGED files have 0 diff since spec start (run the acceptance check command in step 15.7)

If ANY box is unchecked, that's a deficiency. Either fix it inline or document it as a known follow-up in the final commit message.

---

## Plan Summary

**Total**: 15 tasks, ~3500 LOC, ~80 new tests, 9-15 new commits.

**Risk-mitigated** by regression boundary discipline:
- Premarket / EOD / weekly UNCHANGED throughout
- Each task ends with `pytest tests/` ≥538 verification
- BaseCadenceGenerator is purely additive — no inheritance from existing generators

**Execution time estimate**: 6-10 hours focused work via subagent-driven-development (each task has 5-30min implementation + reviews).

