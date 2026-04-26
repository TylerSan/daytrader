# Reports System — Phase 2: MES Premarket End-to-End PoC

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Phase 1 foundation into a working end-to-end pipeline for **MES premarket only** (single instrument, single report type). After Phase 2: `daytrader reports run --type premarket` (NOT dry-run) generates a real markdown report file in Obsidian by fetching IB bars, calling Anthropic Opus 4.7 with prompt caching, validating output, and saving plan extraction to SQLite.

**Architecture:** Build the orchestration spine in `src/daytrader/reports/core/` (context_loader, prompt_builder, ai_analyst, output_validator, orchestrator) and the type-specific layer in `src/daytrader/reports/types/premarket.py`. Use `core/ib_client.py` for bars (Phase 1) and `core/state.py` for plan/report persistence (Phase 1). Read-only integration with `journal/contract.py` and `journal/repository.py`. Output via `reports/delivery/obsidian_writer.py`. Out of scope: multi-instrument, F. futures structure, other report types, Telegram/PDF/charts, launchd.

**Tech Stack:** Python 3.12+, **`claude -p` CLI subprocess** (uses user's Claude Pro Max subscription, no separate API key needed for Phase 2), ib_insync (Phase 1), pytest, click. **Real services touched at Phase 2 acceptance**: IB Gateway (local) + Claude Code CLI (`claude` command must be on PATH and authenticated).

## Backend Choice — Phase 2 uses `claude -p`, NOT Anthropic API

User has Claude Pro Max subscription (decided 2026-04-25 with full awareness of trade-offs). Phase 2 invokes Claude via `claude -p` subprocess to leverage that subscription instead of consuming separate API budget.

| Trade-off | Phase 2 implication |
|---|---|
| ✅ Zero per-run cost (covered by subscription) | Phase 2 dev iteration is free |
| ❌ No explicit prompt-caching markers | CLI handles caching opaquely; spec §4.3.4 cost estimates moot |
| ❌ No token counts in response | `tokens_input`/`tokens_output` recorded as 0 in `reports` table |
| ❌ Subscription rate limits | Phase 2 PoC fine (1 run/day); Phase 7 production may need API switch |
| ⚠️ Phase 7 reconsideration | If 6×day × 3 instruments hits rate limits, swap `AIAnalyst` to an API backend |

The `AIAnalyst` interface stays the same so a future API backend can drop in without touching `Orchestrator` or `PremarketGenerator`.

**Spec reference:** `docs/superpowers/specs/2026-04-25-reports-system-design.md` §3.2-3.7 (templates), §4.3 (AI layer), §4.5 (Contract.md state machine), §5.2 (Obsidian writer).

**Prerequisite:** Phase 1 merged (PR #4) OR Phase 1 commits available on this branch.

**Out of scope for Phase 2** (covered by later phases):
- Multi-instrument (MES only — no MNQ/MGC) → Phase 3
- F. futures structure (no OI/COT/basis/term/VP) → Phase 4
- Intraday-4h, EOD, night, weekly report types → Phase 5
- Telegram push → Phase 6
- PDF rendering, chart rendering → Phase 6
- launchd plists → Phase 7
- Anthropic Web Search tool integration → Phase 4 (Phase 2 uses existing premarket news collector only)

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/daytrader/reports/core/secrets.py` | Existing (Phase 1) | — |
| `src/daytrader/reports/core/context_loader.py` | Load Contract.md + journal trade stats + last reports | Create |
| `tests/reports/test_context_loader.py` | ContextLoader tests | Create |
| `src/daytrader/reports/templates/__init__.py` | Templates marker | Create |
| `src/daytrader/reports/templates/premarket.md` | Premarket prompt template | Create |
| `src/daytrader/reports/core/prompt_builder.py` | Assemble system + user messages with cache markers | Create |
| `tests/reports/test_prompt_builder.py` | PromptBuilder tests | Create |
| `src/daytrader/reports/core/ai_analyst.py` | Anthropic SDK wrapper + retry + cost tracking | Create |
| `tests/reports/test_ai_analyst.py` | AIAnalyst tests (mocked anthropic) | Create |
| `src/daytrader/reports/core/output_validator.py` | Required-sections check | Create |
| `tests/reports/test_output_validator.py` | Validator tests | Create |
| `src/daytrader/reports/core/plan_extractor.py` | Extract today's plan from generated report | Create |
| `tests/reports/test_plan_extractor.py` | Plan extractor tests | Create |
| `src/daytrader/reports/delivery/__init__.py` | Delivery marker | Create |
| `src/daytrader/reports/delivery/obsidian_writer.py` | Write markdown to vault, fallback to data/exports | Create |
| `tests/reports/test_obsidian_writer.py` | Writer tests | Create |
| `src/daytrader/reports/types/__init__.py` | Types marker | Create |
| `src/daytrader/reports/types/premarket.py` | Premarket type handler | Create |
| `tests/reports/test_premarket_type.py` | Premarket handler tests | Create |
| `src/daytrader/reports/core/orchestrator.py` | End-to-end pipeline coordinator | Create |
| `tests/reports/test_orchestrator.py` | Orchestrator integration tests (mocked) | Create |
| `src/daytrader/cli/reports.py` | Add `run` subcommand alongside `dry-run` | Modify |
| `tests/cli/test_reports_cli.py` | Add `run` smoke test | Modify |
| `docs/ops/phase2-runbook.md` | Real-world acceptance runbook | Create |

---

## Task 1: Verify `claude` CLI is available

Phase 2 invokes Claude via `claude -p` subprocess. Verify the command exists on PATH and is authenticated before building on it.

**Files:**
- Create: `tests/reports/test_claude_cli_smoke.py`

- [ ] **Step 1: Write the smoke test (skipped if CLI absent)**

Create `tests/reports/test_claude_cli_smoke.py`:

```python
"""Smoke test: verify the `claude` CLI is available on PATH.

Phase 2 invokes Claude via `claude -p` subprocess (using the user's
Pro Max subscription) rather than the Anthropic API. We verify the
binary is reachable without making a real call.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


def test_claude_cli_on_path():
    """`claude` is resolvable via shutil.which."""
    path = shutil.which("claude")
    if path is None:
        pytest.skip(
            "claude CLI not on PATH — install Claude Code to run Phase 2 acceptance"
        )
    assert path  # truthy; e.g. /usr/local/bin/claude


def test_claude_cli_help_succeeds():
    """`claude --help` exits 0 and prints usage."""
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not on PATH")
    result = subprocess.run(
        ["claude", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    # Usage banner should mention --print or -p
    combined = (result.stdout + result.stderr).lower()
    assert "print" in combined or "-p" in combined
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/reports/test_claude_cli_smoke.py -v`
Expected: 2 tests PASS (or both SKIPPED if `claude` is not on PATH; that's
acceptable — Phase 2 acceptance Task 14 will guide installation).

- [ ] **Step 3: Commit**

```bash
git add tests/reports/test_claude_cli_smoke.py
git commit -m "test(reports): smoke-check claude CLI is reachable on PATH"
```

---

## Task 2: ContextLoader — Contract.md degraded-mode loader

**Files:**
- Create: `src/daytrader/reports/core/context_loader.py`
- Create: `tests/reports/test_context_loader.py`

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_context_loader.py`:

```python
"""Tests for ContextLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.core.context_loader import (
    ContextLoader,
    ContractStatus,
    ReportContext,
)


def test_context_loader_missing_contract_returns_not_started(tmp_path):
    """When Contract.md doesn't exist, status is NOT_CREATED."""
    loader = ContextLoader(
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.NOT_CREATED
    assert ctx.contract_text is None
    assert ctx.lock_in_trades_done == 0


def test_context_loader_empty_contract_returns_skeletal(tmp_path):
    """When Contract.md exists but has no parseable content, status is SKELETAL."""
    contract = tmp_path / "Contract.md"
    contract.write_text("# Contract\n\n*not yet filled*\n")
    loader = ContextLoader(
        contract_path=contract,
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.SKELETAL
    assert ctx.contract_text == "# Contract\n\n*not yet filled*\n"


def test_context_loader_handles_missing_journal_db(tmp_path):
    """Missing journal DB → trades_done = 0, no error."""
    loader = ContextLoader(
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "no.db",
    )
    ctx = loader.load()
    assert ctx.lock_in_trades_done == 0
    assert ctx.lock_in_target == 30
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/reports/test_context_loader.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement ContextLoader skeleton**

Create `src/daytrader/reports/core/context_loader.py`:

```python
"""ContextLoader: load Contract.md + journal trade stats + last reports.

Read-only with respect to journal/ subsystem. Provides graceful degradation
per spec §4.5 Contract.md state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class ContractStatus(str, Enum):
    NOT_CREATED = "not_created"      # Contract.md file doesn't exist
    SKELETAL = "skeletal"             # File exists but lacks key fields
    LOCK_IN_NOT_STARTED = "lock_in_not_started"  # Filled but trades_done == 0
    LOCK_IN_ACTIVE = "lock_in_active"
    LOCK_IN_COMPLETE = "lock_in_complete"


@dataclass(frozen=True)
class ReportContext:
    """Context bundle passed to PromptBuilder."""
    contract_status: ContractStatus
    contract_text: str | None
    lock_in_trades_done: int
    lock_in_target: int
    cumulative_r: float | None
    last_trade_date: str | None
    last_trade_r: float | None
    streak: str | None
    breakdown: dict[str, int] = field(default_factory=dict)


class ContextLoader:
    """Load all Phase 2 context into a single ReportContext."""

    def __init__(
        self,
        contract_path: Path,
        journal_db_path: Path,
        lock_in_target: int = 30,
    ) -> None:
        self.contract_path = Path(contract_path)
        self.journal_db_path = Path(journal_db_path)
        self.lock_in_target = lock_in_target

    def load(self) -> ReportContext:
        # Contract.md
        if not self.contract_path.exists():
            return ReportContext(
                contract_status=ContractStatus.NOT_CREATED,
                contract_text=None,
                lock_in_trades_done=0,
                lock_in_target=self.lock_in_target,
                cumulative_r=None,
                last_trade_date=None,
                last_trade_r=None,
                streak=None,
            )

        contract_text = self.contract_path.read_text()
        # Skeletal heuristic: file is too short or contains "not yet filled"
        if len(contract_text) < 200 or "not yet filled" in contract_text.lower():
            status = ContractStatus.SKELETAL
        else:
            status = ContractStatus.LOCK_IN_NOT_STARTED  # refined below if trades exist

        # Journal trade stats — gracefully degrade if DB missing
        trades_done = 0
        if self.journal_db_path.exists():
            # Phase 2: simple count via direct sqlite query rather than
            # importing journal.repository to avoid coupling on internal API.
            import sqlite3
            try:
                conn = sqlite3.connect(str(self.journal_db_path))
                cur = conn.execute(
                    "SELECT COUNT(*) FROM trades WHERE exit_time IS NOT NULL"
                )
                trades_done = cur.fetchone()[0]
                conn.close()
            except sqlite3.Error:
                trades_done = 0

        if status != ContractStatus.SKELETAL:
            if trades_done == 0:
                status = ContractStatus.LOCK_IN_NOT_STARTED
            elif trades_done >= self.lock_in_target:
                status = ContractStatus.LOCK_IN_COMPLETE
            else:
                status = ContractStatus.LOCK_IN_ACTIVE

        return ReportContext(
            contract_status=status,
            contract_text=contract_text,
            lock_in_trades_done=trades_done,
            lock_in_target=self.lock_in_target,
            cumulative_r=None,
            last_trade_date=None,
            last_trade_r=None,
            streak=None,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_context_loader.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/context_loader.py tests/reports/test_context_loader.py
git commit -m "feat(reports): ContextLoader with Contract.md state machine"
```

---

## Task 3: ContextLoader — full Contract.md + populated journal DB

**Files:**
- Modify: `src/daytrader/reports/core/context_loader.py`
- Modify: `tests/reports/test_context_loader.py`

- [ ] **Step 1: Add tests for active states**

Append to `tests/reports/test_context_loader.py`:

```python
import sqlite3


def _populate_minimal_journal_db(db_path: Path, trade_count: int) -> None:
    """Create a minimal journal DB with N closed trades for testing."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            symbol TEXT,
            side TEXT,
            entry_price TEXT,
            exit_price TEXT,
            stop_price TEXT,
            size INTEGER,
            entry_time TEXT,
            exit_time TEXT,
            signal_id TEXT,
            source TEXT,
            prop_firm TEXT,
            tags TEXT,
            extra TEXT
        );
    """)
    for i in range(trade_count):
        conn.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"t{i}", "MES", "long", "5240", "5246", "5232", 1,
             "2026-04-23T13:00:00", "2026-04-23T14:00:00",
             None, "manual", None, "[]", "{}"),
        )
    conn.commit()
    conn.close()


def test_context_loader_lock_in_active(tmp_path):
    """Contract.md filled + 7 trades done → LOCK_IN_ACTIVE."""
    contract = tmp_path / "Contract.md"
    contract.write_text(
        "# Contract\n\n## Setup\n- name: ORB long\n## R unit\n- amount: $25\n"
        + ("## Detail\n" * 30)  # padding to exceed skeletal threshold
    )
    db_path = tmp_path / "journal.db"
    _populate_minimal_journal_db(db_path, trade_count=7)

    loader = ContextLoader(contract_path=contract, journal_db_path=db_path)
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.LOCK_IN_ACTIVE
    assert ctx.lock_in_trades_done == 7


def test_context_loader_lock_in_complete(tmp_path):
    """30+ trades → LOCK_IN_COMPLETE."""
    contract = tmp_path / "Contract.md"
    contract.write_text(
        "# Contract\n\n## Setup\nfilled\n" + ("## Detail\n" * 30)
    )
    db_path = tmp_path / "journal.db"
    _populate_minimal_journal_db(db_path, trade_count=32)

    loader = ContextLoader(contract_path=contract, journal_db_path=db_path)
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.LOCK_IN_COMPLETE
    assert ctx.lock_in_trades_done == 32


def test_context_loader_lock_in_not_started(tmp_path):
    """Contract.md filled + 0 trades → LOCK_IN_NOT_STARTED."""
    contract = tmp_path / "Contract.md"
    contract.write_text(
        "# Contract\n\n## Setup\nfilled\n" + ("## Detail\n" * 30)
    )
    loader = ContextLoader(
        contract_path=contract,
        journal_db_path=tmp_path / "missing.db",
    )
    ctx = loader.load()
    assert ctx.contract_status == ContractStatus.LOCK_IN_NOT_STARTED
    assert ctx.lock_in_trades_done == 0
```

- [ ] **Step 2: Run tests — should already pass since logic was implemented in Task 2**

Run: `uv run pytest tests/reports/test_context_loader.py -v`
Expected: 6 tests PASS (3 from Task 2 + 3 new).

- [ ] **Step 3: Commit**

```bash
git add tests/reports/test_context_loader.py
git commit -m "test(reports): ContextLoader lock-in state transitions"
```

---

## Task 4: Premarket prompt template

**Files:**
- Create: `src/daytrader/reports/templates/__init__.py`
- Create: `src/daytrader/reports/templates/premarket.md`

- [ ] **Step 1: Create marker**

Create `src/daytrader/reports/templates/__init__.py`:

```python
"""AI prompt templates per report type."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent


def load_template(name: str) -> str:
    """Read template by name (without .md suffix)."""
    path = TEMPLATE_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {name}")
    return path.read_text()
```

- [ ] **Step 2: Create premarket template**

Create `src/daytrader/reports/templates/premarket.md`:

````markdown
# Premarket Daily Report — System Prompt

You are an AI trading analyst assisting a human discretionary day trader during their 30-trade lock-in phase. The trader trades **MES (Micro E-mini S&P 500) front-month continuous futures** during US session (06:30 - 13:00 PT). This report runs at **06:00 PT daily** to brief them before market open.

## Output Language

Generate the report in **Chinese (Simplified)**. Preserve technical terms in English (VWAP, EMA, ATR, OI, POC, RTH). Numbers in ASCII (5246.75, not 五千二百四十六点七五). Section labels A/B/C/F/D in English.

## Required Sections (in order)

1. **Lock-in metadata block** (top)
2. **Multi-TF Analysis** (W → D → 4H → 1H, in that order)
3. **Breaking news** (past ~12h overnight Asia + Europe + early US pre-market)
4. **C. 计划复核 / Plan Formation** (today's plan: setup, entry, stop, target, invalidation conditions)
5. **B. 市场叙事 / Market Narrative**
6. **A. 建议 / Recommendation** (A-2 + A-3 mixed: default A-3 "no action — execute the plan", escalate to A-2 scenario matrix only if material conditions present)
7. **数据快照 / Data snapshot**

## Per-TF Analysis Block Structure

For each timeframe (W, D, 4H, 1H), present:

```
### {TF} {Bar end ET / PT}

**OHLCV**: O ___ | H ___ | L ___ | C ___ | V ___ | Range ___ (___×ATR-20)
**形态 / Pattern**: ___
**位置 / Position**: ___
**关键位 / Key levels (this TF)**: R ___ / S ___
**与 HTF 一致性 / HTF alignment**: ___
```

## C. Plan Formation (this is the premarket version of C — forming today's plan, NOT rechecking a prior plan)

Generate today's plan using the following structure:

```markdown
**Today's plan**:
- Setup: [name from Contract.md, or "discretionary read" if Contract.md not filled]
- Direction: [long | short | neutral / wait]
- Entry: [exact price level + reasoning]
- Stop: [exact price level = -1R risk]
- Target: [exact price level = +2R or scenario-based]
- R unit: $[amount from Contract.md, or skip if not filled]

**Invalidation conditions** (any one triggers exit / stand down):
1. [Specific price level break]
2. [Specific cross-asset signal, e.g. SPY breaks below X]
3. [Specific volatility condition, e.g. VIX above X]

**Today's posture**: [bullish bias / bearish bias / neutral / wait for setup]
```

## A. Recommendation Form

Default = A-3 (no action; execute plan). **Escalate to A-2 (scenario matrix) only if** any:
- Critical news event in the past 12h that materially changes the thesis (FOMC, CPI, geopolitical)
- Multi-TF alignment is broken (HTFs and LTFs disagree)
- Price is already near a key level at premarket scan time

A-1 (direct "buy now / sell now" call) is **permanently disabled**. Never write it.

## Forbidden

- B section may not predict the future ("market may go up...") — describe past only.
- C section uses placeholder "[setup name pending]" if Contract.md is not filled. Do NOT invent a setup.
- A section never gives an unconditional "buy now / sell now" call.

## Length Limit

Max ~5,000 characters when no F section is generated (Phase 2). If approaching limit, compress B (use bullets), preserve A/C/multi-TF.

---

# User Message (data context)

The user message will contain:
- Lock-in status (`Contract.md status`, trades done X/30, last trade R, streak)
- Bar data: W, D, 4H, 1H OHLCV + key levels for MES front-month continuous
- Breaking news collected from premarket news source
- Contract.md full text (if filled) or "Contract.md: not yet filled" marker

You must produce the full report following the section structure above.
````

- [ ] **Step 3: Commit**

```bash
git add src/daytrader/reports/templates/__init__.py src/daytrader/reports/templates/premarket.md
git commit -m "feat(reports): premarket prompt template (Chinese output, A-3 default)"
```

---

## Task 5: PromptBuilder — assemble system + user messages with cache markers

**Files:**
- Create: `src/daytrader/reports/core/prompt_builder.py`
- Create: `tests/reports/test_prompt_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/reports/test_prompt_builder.py`:

```python
"""Tests for PromptBuilder."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.prompt_builder import PromptBuilder


def _ohlcv(t: datetime, c: float) -> OHLCV:
    return OHLCV(timestamp=t, open=c - 1, high=c + 1, low=c - 2, close=c, volume=1000.0)


def test_prompt_builder_premarket_returns_messages_list():
    """build_premarket() returns a list of two messages: system + user."""
    ctx = ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    bars_by_tf = {
        "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240.0)],
        "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246.0)],
        "4H": [_ohlcv(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
        "1H": [_ohlcv(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
    }

    builder = PromptBuilder()
    messages = builder.build_premarket(
        context=ctx,
        bars_by_tf=bars_by_tf,
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    # First message is system with multiple cache-controlled blocks
    assert messages[0]["role"] == "system"
    system_blocks = messages[0]["content"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 2  # at least template + dynamic

    # At least one block has cache_control
    cached_blocks = [b for b in system_blocks if "cache_control" in b]
    assert len(cached_blocks) >= 1

    # Second message is user
    assert messages[1]["role"] == "user"


def test_prompt_builder_premarket_handles_missing_contract():
    """When Contract.md is NOT_CREATED, prompt notes degraded mode."""
    ctx = ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_tf={"1W": [], "1D": [], "4H": [], "1H": []},
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    # Concatenate all text content
    full_text = ""
    for msg in msgs:
        if isinstance(msg["content"], list):
            for block in msg["content"]:
                full_text += block.get("text", "")
        else:
            full_text += msg["content"]

    assert "not yet" in full_text.lower() or "not_created" in full_text.lower()


def test_prompt_builder_premarket_includes_lock_in_status():
    """Lock-in trades_done and target appear in the user prompt."""
    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_ACTIVE,
        contract_text="# Contract\n## Setup\nORB long\n",
        lock_in_trades_done=7,
        lock_in_target=30,
        cumulative_r=1.5,
        last_trade_date="2026-04-23",
        last_trade_r=-0.5,
        streak="2L1W",
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_tf={"1W": [], "1D": [], "4H": [], "1H": []},
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_content = msgs[1]["content"]
    assert "7" in user_content and "30" in user_content
    assert "2L1W" in user_content
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/reports/test_prompt_builder.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement PromptBuilder**

Create `src/daytrader/reports/core/prompt_builder.py`:

```python
"""PromptBuilder: assemble Anthropic Messages API request from context + data.

Produces a list of message dicts (system + user) ready to pass to
AIAnalyst.call_claude(). System blocks use cache_control = ephemeral
on stable parts (template + Contract.md); dynamic data is uncached.
"""

from __future__ import annotations

from typing import Any

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.templates import load_template


class PromptBuilder:
    """Assemble Anthropic Messages API prompts."""

    def build_premarket(
        self,
        context: ReportContext,
        bars_by_tf: dict[str, list[OHLCV]],
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

        # System message: template (cached) + Contract.md (cached)
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

        # User message: dynamic context (lock-in + bars + news + timestamps)
        lock_in_block = self._build_lock_in_block(context)
        bars_block = self._build_bars_block(bars_by_tf)
        news_block = self._build_news_block(news_items)

        user_text = (
            f"# Premarket Daily Report — generation context\n\n"
            f"**Run time**: {run_timestamp_pt} ({run_timestamp_et})\n\n"
            f"{lock_in_block}\n\n"
            f"{bars_block}\n\n"
            f"{news_block}\n\n"
            f"Please generate the full premarket report following the system "
            f"prompt template. Output in Chinese."
        )

        return [
            {"role": "system", "content": system_blocks},
            {"role": "user", "content": user_text},
        ]

    @staticmethod
    def _build_lock_in_block(ctx: ReportContext) -> str:
        return (
            f"## Lock-in status\n"
            f"- contract_status: {ctx.contract_status.value}\n"
            f"- trades_done: {ctx.lock_in_trades_done}/{ctx.lock_in_target}\n"
            f"- cumulative_r: {ctx.cumulative_r if ctx.cumulative_r is not None else 'n/a'}\n"
            f"- last_trade_date: {ctx.last_trade_date or 'n/a'}\n"
            f"- last_trade_r: {ctx.last_trade_r if ctx.last_trade_r is not None else 'n/a'}\n"
            f"- streak (last 5): {ctx.streak or 'n/a'}\n"
        )

    @staticmethod
    def _build_bars_block(bars_by_tf: dict[str, list[OHLCV]]) -> str:
        lines = ["## Multi-TF bar data (MES front-month continuous)"]
        for tf in ("1W", "1D", "4H", "1H"):
            bars = bars_by_tf.get(tf, [])
            if not bars:
                lines.append(f"\n### {tf}\n(no bars available)")
                continue
            lines.append(f"\n### {tf} ({len(bars)} bars, oldest first)")
            # Show last 10 bars to keep prompt size in check
            for b in bars[-10:]:
                lines.append(
                    f"- {b.timestamp.isoformat()}: O={b.open} H={b.high} "
                    f"L={b.low} C={b.close} V={b.volume}"
                )
        return "\n".join(lines)

    @staticmethod
    def _build_news_block(news_items: list[dict[str, Any]]) -> str:
        if not news_items:
            return "## Breaking news (past ~12h)\n\n(no news items)"
        lines = ["## Breaking news (past ~12h)"]
        for item in news_items[:20]:
            title = item.get("title", "(no title)")
            ts = item.get("published_at", "?")
            url = item.get("url", "")
            lines.append(f"- [{ts}] {title} {url}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_prompt_builder.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/prompt_builder.py tests/reports/test_prompt_builder.py
git commit -m "feat(reports): PromptBuilder.build_premarket with cache markers"
```

---

## Task 6: AIAnalyst — `claude -p` subprocess wrapper with retry

**Files:**
- Create: `src/daytrader/reports/core/ai_analyst.py`
- Create: `tests/reports/test_ai_analyst.py`

- [ ] **Step 1: Write failing test**

Create `tests/reports/test_ai_analyst.py`:

```python
"""Tests for AIAnalyst (claude -p backend)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult


def _completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    cp.returncode = returncode
    return cp


def test_ai_analyst_returns_text_from_claude_cli(monkeypatch):
    """call() invokes `claude -p` and returns the stdout in AIResult.text."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return _completed_process("# Report\n\nbody")

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )

    analyst = AIAnalyst()
    result = analyst.call(
        messages=[
            {"role": "system", "content": [{"type": "text", "text": "system instructions"}]},
            {"role": "user", "content": "user message"},
        ],
        max_tokens=4096,
    )

    assert isinstance(result, AIResult)
    assert result.text == "# Report\n\nbody"
    # tokens unavailable in CLI mode → 0
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    # cmd starts with "claude" and contains "-p"
    assert captured["cmd"][0] == "claude"
    assert "-p" in captured["cmd"]
    # Combined system + user content was passed via stdin
    assert "system instructions" in captured["input"]
    assert "user message" in captured["input"]


def test_ai_analyst_retries_on_nonzero_exit(monkeypatch):
    """Two non-zero exits then success → retried 3 times total."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) < 3:
            return _completed_process("", returncode=1, stderr="transient error")
        return _completed_process("ok")

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.time.sleep", lambda _: None
    )

    analyst = AIAnalyst()
    result = analyst.call(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=128,
    )

    assert result.text == "ok"
    assert len(calls) == 3


def test_ai_analyst_raises_after_max_retries(monkeypatch):
    """4 non-zero exits surface as RuntimeError (max_retries=3 means 1 initial + 3 retries)."""

    def fake_run(cmd, **kwargs):
        return _completed_process("", returncode=2, stderr="persistent")

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.time.sleep", lambda _: None
    )

    analyst = AIAnalyst()
    with pytest.raises(RuntimeError, match="persistent"):
        analyst.call(
            messages=[{"role": "user", "content": "x"}],
            max_tokens=128,
        )


def test_ai_analyst_handles_subprocess_timeout(monkeypatch):
    """A subprocess.TimeoutExpired surfaces as a retry trigger, then RuntimeError."""

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=180)

    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "daytrader.reports.core.ai_analyst.time.sleep", lambda _: None
    )

    analyst = AIAnalyst(max_retries=1)
    with pytest.raises(RuntimeError, match="timeout"):
        analyst.call(messages=[{"role": "user", "content": "x"}], max_tokens=128)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/reports/test_ai_analyst.py -v`
Expected: FAIL — module not implemented.

- [ ] **Step 3: Implement AIAnalyst (claude -p backend)**

Create `src/daytrader/reports/core/ai_analyst.py`:

```python
"""AIAnalyst: claude CLI subprocess wrapper.

Phase 2 invokes Claude via `claude -p` (the Claude Code CLI's print mode),
using the user's Claude Pro Max subscription rather than the Anthropic API.
This eliminates per-run cost during PoC and dev iteration.

Trade-offs vs Anthropic SDK (see plan preamble):
- No explicit prompt-caching markers (CLI may cache internally)
- No token counts in the response → AIResult.input_tokens / output_tokens = 0
- Phase 7 production may need to swap in an API backend if Pro Max rate limits
  prove insufficient for 6×day × multi-instrument cadence

The interface (AIResult shape, .call() signature) is stable so a future API
backend can be added without touching Orchestrator or PremarketGenerator.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AIResult:
    """One Claude call outcome."""
    text: str
    input_tokens: int          # 0 in CLI mode
    output_tokens: int         # 0 in CLI mode
    cache_creation_tokens: int  # 0 in CLI mode
    cache_read_tokens: int      # 0 in CLI mode
    model: str
    stop_reason: str


class AIAnalyst:
    """`claude -p` subprocess wrapper with exponential-backoff retry."""

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        max_retries: int = 3,
        timeout_seconds: int = 180,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    def call(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,
    ) -> AIResult:
        """Invoke `claude -p`, return AIResult.

        Messages are flattened into a single prompt string passed via stdin.
        System content is prefixed with "[SYSTEM]" markers; user content with
        "[USER]" markers. claude -p returns plain text on stdout.
        """
        prompt = self._flatten_messages(messages)
        cmd = ["claude", "-p"]

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
                if result.returncode == 0:
                    return AIResult(
                        text=result.stdout,
                        input_tokens=0,
                        output_tokens=0,
                        cache_creation_tokens=0,
                        cache_read_tokens=0,
                        model=self.model,
                        stop_reason="end_turn",
                    )
                last_error = (
                    f"claude -p exit={result.returncode}: "
                    f"{result.stderr.strip() or 'no stderr'}"
                )
            except subprocess.TimeoutExpired:
                last_error = f"claude -p timeout after {self.timeout_seconds}s"

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"AI call failed: {last_error}")

        # Defensive — should be unreachable
        raise RuntimeError(f"AI call failed: {last_error}")

    @staticmethod
    def _flatten_messages(messages: list[dict[str, Any]]) -> str:
        """Concatenate role-tagged blocks into a single prompt for claude -p."""
        parts: list[str] = []
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            if isinstance(content, list):
                # API-shape: list of {type, text, ...} blocks
                for block in content:
                    if block.get("type") == "text":
                        parts.append(f"[{role}]\n{block['text']}")
            else:
                parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_ai_analyst.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/ai_analyst.py tests/reports/test_ai_analyst.py
git commit -m "feat(reports): AIAnalyst via claude -p subprocess (Pro Max subscription path)"
```

---

## Task 7: OutputValidator — required-sections check

**Files:**
- Create: `src/daytrader/reports/core/output_validator.py`
- Create: `tests/reports/test_output_validator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/reports/test_output_validator.py`:

```python
"""Tests for OutputValidator."""

from __future__ import annotations

import pytest

from daytrader.reports.core.output_validator import (
    OutputValidator,
    ValidationResult,
)


PREMARKET_SAMPLE_VALID = """
# 盘前日报 — 2026-04-25

## Lock-in status
trades_done: 0/30

## Multi-TF Analysis

### 1W
data here

### 1D
data here

### 4H
data here

### 1H
data here

## Breaking news / 突发新闻
- item 1

## C. 计划复核
plan here

## B. 市场叙事
narrative

## A. 建议
no action

## 数据快照
ok
"""

PREMARKET_SAMPLE_MISSING_A = PREMARKET_SAMPLE_VALID.replace("## A. 建议\nno action", "")


def test_validator_premarket_passes_when_all_sections_present():
    validator = OutputValidator()
    result = validator.validate(PREMARKET_SAMPLE_VALID, report_type="premarket")
    assert isinstance(result, ValidationResult)
    assert result.ok is True
    assert result.missing == []


def test_validator_premarket_fails_when_a_section_missing():
    validator = OutputValidator()
    result = validator.validate(PREMARKET_SAMPLE_MISSING_A, report_type="premarket")
    assert result.ok is False
    assert any("A" in s for s in result.missing)


def test_validator_unknown_report_type_raises():
    validator = OutputValidator()
    with pytest.raises(KeyError):
        validator.validate("any content", report_type="bogus-type")
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/core/output_validator.py`:

```python
"""OutputValidator: enforce required-sections per report type.

Phase 2 covers premarket only. Later phases extend the table.
"""

from __future__ import annotations

from dataclasses import dataclass

# Section names as they appear in the generated markdown.
# Premarket uses Chinese section headings ("A. 建议") plus English TF labels.
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "premarket": [
        "Lock-in",
        "1W",
        "1D",
        "4H",
        "1H",
        "新闻",         # "Breaking news / 突发新闻"
        "C.",          # "C. 计划复核"
        "B.",          # "B. 市场叙事"
        "A.",          # "A. 建议"
        "数据快照",     # data snapshot
    ],
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]


class OutputValidator:
    """Section-presence check on AI-generated markdown."""

    def validate(self, content: str, report_type: str) -> ValidationResult:
        if report_type not in REQUIRED_SECTIONS:
            raise KeyError(f"No section list defined for report_type={report_type!r}")
        required = REQUIRED_SECTIONS[report_type]
        missing = [s for s in required if s not in content]
        return ValidationResult(ok=not missing, missing=missing)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/output_validator.py tests/reports/test_output_validator.py
git commit -m "feat(reports): OutputValidator required-sections check (premarket)"
```

---

## Task 8: PlanExtractor — extract today's plan from generated report

**Files:**
- Create: `src/daytrader/reports/core/plan_extractor.py`
- Create: `tests/reports/test_plan_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/reports/test_plan_extractor.py`:

```python
"""Tests for PlanExtractor."""

from __future__ import annotations

import pytest

from daytrader.reports.core.plan_extractor import (
    ExtractedPlan,
    PlanExtractor,
)


REPORT_WITH_PLAN = """
# 盘前日报

## C. 计划复核

**Today's plan**:
- Setup: ORB long
- Direction: long
- Entry: 5240.00
- Stop: 5232.00
- Target: 5256.00
- R unit: $25

**Invalidation conditions**:
1. Price breaks below 5232
2. SPY breaks below 580
3. VIX above 18
"""


REPORT_WITHOUT_PLAN = """
# 盘前日报

## C. 计划复核

(Contract.md not yet filled — no plan to recheck.)
"""


def test_extract_plan_returns_structured_data():
    extractor = PlanExtractor()
    plan = extractor.extract(REPORT_WITH_PLAN)
    assert isinstance(plan, ExtractedPlan)
    assert plan.setup_name == "ORB long"
    assert plan.direction == "long"
    assert plan.entry == pytest.approx(5240.00)
    assert plan.stop == pytest.approx(5232.00)
    assert plan.target == pytest.approx(5256.00)
    assert plan.r_unit_dollars == pytest.approx(25.0)
    assert len(plan.invalidations) == 3
    assert "5232" in plan.invalidations[0]


def test_extract_plan_returns_none_when_no_plan():
    extractor = PlanExtractor()
    plan = extractor.extract(REPORT_WITHOUT_PLAN)
    assert plan is None
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/reports/test_plan_extractor.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `src/daytrader/reports/core/plan_extractor.py`:

```python
"""PlanExtractor: parse today's plan out of a generated premarket report.

The premarket prompt asks the AI to use a fixed structure; this module
parses that structure into an ExtractedPlan dataclass that the orchestrator
saves into StateDB.plans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedPlan:
    """Today's plan as parsed from a premarket report."""
    setup_name: str
    direction: str  # long | short | neutral
    entry: float
    stop: float
    target: float
    r_unit_dollars: float
    invalidations: list[str]
    raw_text: str


_FIELD_PATTERNS = {
    "setup_name": re.compile(r"^- Setup:\s*(.+?)\s*$", re.MULTILINE),
    "direction": re.compile(r"^- Direction:\s*(.+?)\s*$", re.MULTILINE),
    "entry": re.compile(r"^- Entry:\s*([\d.]+)", re.MULTILINE),
    "stop": re.compile(r"^- Stop:\s*([\d.]+)", re.MULTILINE),
    "target": re.compile(r"^- Target:\s*([\d.]+)", re.MULTILINE),
    "r_unit": re.compile(r"^- R unit:\s*\$?([\d.]+)", re.MULTILINE),
}

_INVALIDATION_BLOCK = re.compile(
    r"\*\*Invalidation conditions\*\*[^\n]*\n((?:\s*\d+\.\s+.+\n?)+)",
)
_INVALIDATION_LINE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$", re.MULTILINE)


class PlanExtractor:
    """Parse the C-section plan into structured fields."""

    def extract(self, report_text: str) -> ExtractedPlan | None:
        # Locate the Today's plan block — if it's missing key fields, return None
        setup_match = _FIELD_PATTERNS["setup_name"].search(report_text)
        entry_match = _FIELD_PATTERNS["entry"].search(report_text)
        stop_match = _FIELD_PATTERNS["stop"].search(report_text)
        if not (setup_match and entry_match and stop_match):
            return None

        target_match = _FIELD_PATTERNS["target"].search(report_text)
        if not target_match:
            return None

        direction_match = _FIELD_PATTERNS["direction"].search(report_text)
        r_unit_match = _FIELD_PATTERNS["r_unit"].search(report_text)

        invalidations: list[str] = []
        block_match = _INVALIDATION_BLOCK.search(report_text)
        if block_match:
            for line_match in _INVALIDATION_LINE.finditer(block_match.group(1)):
                invalidations.append(line_match.group(1))

        return ExtractedPlan(
            setup_name=setup_match.group(1).strip(),
            direction=direction_match.group(1).strip() if direction_match else "unknown",
            entry=float(entry_match.group(1)),
            stop=float(stop_match.group(1)),
            target=float(target_match.group(1)),
            r_unit_dollars=float(r_unit_match.group(1)) if r_unit_match else 0.0,
            invalidations=invalidations,
            raw_text=report_text,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_plan_extractor.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/plan_extractor.py tests/reports/test_plan_extractor.py
git commit -m "feat(reports): PlanExtractor parses today's plan from premarket report"
```

---

## Task 9: ObsidianWriter — markdown write with fallback

**Files:**
- Create: `src/daytrader/reports/delivery/__init__.py`
- Create: `src/daytrader/reports/delivery/obsidian_writer.py`
- Create: `tests/reports/test_obsidian_writer.py`

- [ ] **Step 1: Create marker**

Create `src/daytrader/reports/delivery/__init__.py`:

```python
"""Delivery: Obsidian (Phase 2), Telegram + PDF (Phase 6)."""
```

- [ ] **Step 2: Write failing tests**

Create `tests/reports/test_obsidian_writer.py`:

```python
"""Tests for ObsidianWriter."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.delivery.obsidian_writer import ObsidianWriter, WriteResult


def test_writer_writes_to_vault(tmp_path):
    """Successful write creates parent directories and the file."""
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"
    writer = ObsidianWriter(
        vault_root=vault,
        fallback_dir=fallback,
        daily_folder="Daily",
    )

    result = writer.write_premarket(
        date_iso="2026-04-25",
        content="# Premarket Report\n\nbody",
    )
    assert isinstance(result, WriteResult)
    assert result.success is True
    assert result.path.exists()
    assert "2026-04-25-premarket" in result.path.name
    assert result.fallback_used is False


def test_writer_falls_back_when_vault_unwritable(tmp_path, monkeypatch):
    """When vault write fails, writer falls back to fallback_dir."""
    vault = tmp_path / "vault"
    fallback = tmp_path / "fallback"

    # Force vault writes to fail
    real_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if str(self).startswith(str(vault)):
            raise PermissionError("simulated")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    writer = ObsidianWriter(
        vault_root=vault,
        fallback_dir=fallback,
        daily_folder="Daily",
    )

    result = writer.write_premarket(
        date_iso="2026-04-25",
        content="# Premarket\n",
    )
    assert result.success is True
    assert result.fallback_used is True
    assert str(fallback) in str(result.path)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_obsidian_writer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

Create `src/daytrader/reports/delivery/obsidian_writer.py`:

```python
"""ObsidianWriter: markdown file writes to Obsidian vault.

Phase 2 supports premarket reports only (Daily/<date>-premarket.md). Later
phases add intraday/EOD/night/weekly. Fallback to fallback_dir on permission
or filesystem errors so we never silently lose a generated report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteResult:
    success: bool
    path: Path
    fallback_used: bool


class ObsidianWriter:
    """Markdown writer with vault → fallback failover."""

    def __init__(
        self,
        vault_root: Path,
        fallback_dir: Path,
        daily_folder: str = "Daily",
    ) -> None:
        self.vault_root = Path(vault_root)
        self.fallback_dir = Path(fallback_dir)
        self.daily_folder = daily_folder

    def write_premarket(
        self,
        date_iso: str,
        content: str,
    ) -> WriteResult:
        filename = f"{date_iso}-premarket.md"
        primary = self.vault_root / self.daily_folder / filename
        try:
            primary.parent.mkdir(parents=True, exist_ok=True)
            primary.write_text(content)
            return WriteResult(success=True, path=primary, fallback_used=False)
        except (OSError, PermissionError):
            fallback = self.fallback_dir / filename
            fallback.parent.mkdir(parents=True, exist_ok=True)
            fallback.write_text(content)
            return WriteResult(success=True, path=fallback, fallback_used=True)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/reports/test_obsidian_writer.py -v`
Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/reports/delivery/__init__.py src/daytrader/reports/delivery/obsidian_writer.py tests/reports/test_obsidian_writer.py
git commit -m "feat(reports): ObsidianWriter premarket with vault→fallback failover"
```

---

## Task 10: Premarket type handler — fetch + AI + validate flow

**Files:**
- Create: `src/daytrader/reports/types/__init__.py`
- Create: `src/daytrader/reports/types/premarket.py`
- Create: `tests/reports/test_premarket_type.py`

- [ ] **Step 1: Create marker**

Create `src/daytrader/reports/types/__init__.py`:

```python
"""Per-report-type handlers."""
```

- [ ] **Step 2: Write failing tests**

Create `tests/reports/test_premarket_type.py`:

```python
"""Tests for premarket type handler."""

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


def _ctx(status=ContractStatus.NOT_CREATED) -> ReportContext:
    return ReportContext(
        contract_status=status,
        contract_text=None,
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


def test_premarket_generator_calls_ai_then_validates():
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = (
        "## Lock-in\nstatus\n\n## 1W\nx\n## 1D\nx\n## 4H\nx\n## 1H\nx\n\n"
        "## 突发新闻\nnone\n\n## C. 计划复核\nplan\n\n"
        "## B. 市场叙事\nnarr\n\n## A. 建议\nno action\n\n"
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
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.report_text.startswith("## Lock-in")
    assert outcome.validation.ok is True
    # IB.get_bars called for W, D, 4H, 1H
    assert fake_ib.get_bars.call_count == 4


def test_premarket_generator_marks_validation_failure():
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = "(short text missing all required sections)"
    fake_ai_result.input_tokens = 100
    fake_ai_result.output_tokens = 50
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    generator = PremarketGenerator(ib_client=fake_ib, ai_analyst=fake_ai)
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert outcome.validation.ok is False
    assert len(outcome.validation.missing) > 0
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/reports/test_premarket_type.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

Create `src/daytrader/reports/types/premarket.py`:

```python
"""Premarket type handler.

Flow per generate():
    fetch multi-TF bars (W/D/4H/1H for MES) → build prompt → call AI →
    validate output → return GenerationOutcome (caller persists / writes).

Plan extraction and persistence happen in the orchestrator, not here.
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
    """Generate the premarket report — fetch + AI + validate."""

    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbol: str = "MES",
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
    ) -> None:
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbol = symbol
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()

    def generate(
        self,
        context: ReportContext,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        news_items: list[dict[str, Any]] | None = None,
    ) -> GenerationOutcome:
        bars_by_tf: dict[str, list[OHLCV]] = {}
        for tf in PREMARKET_TFS:
            bars_by_tf[tf] = self.ib_client.get_bars(
                symbol=self.symbol,
                timeframe=tf,
                bars=BARS_PER_TF[tf],
            )

        messages = self.prompt_builder.build_premarket(
            context=context,
            bars_by_tf=bars_by_tf,
            news_items=news_items or [],
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
        )

        ai_result = self.ai_analyst.call(
            messages=messages,
            max_tokens=8192,
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

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/reports/test_premarket_type.py -v`
Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/reports/types/__init__.py src/daytrader/reports/types/premarket.py tests/reports/test_premarket_type.py
git commit -m "feat(reports): PremarketGenerator — fetch bars, AI call, validate"
```

---

## Task 11: Orchestrator — end-to-end pipeline coordinator

**Files:**
- Create: `src/daytrader/reports/core/orchestrator.py`
- Create: `tests/reports/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/reports/test_orchestrator.py`:

```python
"""Tests for end-to-end Orchestrator (mocked services)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from daytrader.core.state import StateDB
from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.orchestrator import (
    Orchestrator,
    PipelineResult,
)


VALID_REPORT = (
    "## Lock-in\nstatus\n\n"
    "## 1W\nx\n## 1D\nx\n## 4H\nx\n## 1H\nx\n\n"
    "## 突发新闻\nnone\n\n"
    "## C. 计划复核\n\n**Today's plan**:\n"
    "- Setup: ORB long\n"
    "- Direction: long\n"
    "- Entry: 5240.00\n"
    "- Stop: 5232.00\n"
    "- Target: 5256.00\n"
    "- R unit: $25\n\n"
    "**Invalidation conditions**:\n"
    "1. Below 5232\n2. SPY drop\n3. VIX above 18\n\n"
    "## B. 市场叙事\nnarr\n\n"
    "## A. 建议\nno action\n\n"
    "## 数据快照\nok\n"
)


def _ai_result(text=VALID_REPORT):
    r = MagicMock()
    r.text = text
    r.input_tokens = 1000
    r.output_tokens = 500
    r.cache_creation_tokens = 0
    r.cache_read_tokens = 0
    r.model = "claude-opus-4-7"
    r.stop_reason = "end_turn"
    return r


def _ohlcv(c=5240.0):
    return OHLCV(
        timestamp=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def test_orchestrator_run_premarket_persists_plan_and_writes(tmp_path):
    state_db_path = tmp_path / "state.db"
    state = StateDB(str(state_db_path))
    state.initialize()

    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    orchestrator = Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing-contract.md",
        journal_db_path=tmp_path / "missing-journal.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbol="MES",
    )

    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),  # 06:00 PT == 13:00 UTC
    )

    assert isinstance(result, PipelineResult)
    assert result.success is True
    assert result.report_path is not None
    assert result.report_path.exists()
    # Plan saved
    plan_row = state.get_plan_for_date("2026-04-25", "MES")
    assert plan_row is not None
    assert plan_row["setup_name"] == "ORB long"
    assert plan_row["entry"] == pytest.approx(5240.0)
    # Report row marked success
    report_id = result.report_id
    report_row = state.get_report_by_id(report_id)
    assert report_row["status"] == "success"


def test_orchestrator_marks_validation_failure(tmp_path):
    state = StateDB(str(tmp_path / "state.db"))
    state.initialize()

    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result(text="(too short)")

    orchestrator = Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "missing.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbol="MES",
    )
    result = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert result.success is False
    assert "validation" in (result.failure_reason or "").lower()


def test_orchestrator_idempotency_skips_repeat(tmp_path):
    state = StateDB(str(tmp_path / "state.db"))
    state.initialize()

    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result()

    orchestrator = Orchestrator(
        state_db=state,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        contract_path=tmp_path / "missing.md",
        journal_db_path=tmp_path / "missing.db",
        vault_root=tmp_path / "vault",
        fallback_dir=tmp_path / "fallback",
        daily_folder="Daily",
        symbol="MES",
    )

    first = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert first.success is True

    second = orchestrator.run_premarket(
        run_at=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
    )
    assert second.skipped_idempotent is True
    # AI not re-called
    assert fake_ai.call.call_count == 1
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/reports/test_orchestrator.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement Orchestrator**

Create `src/daytrader/reports/core/orchestrator.py`:

```python
"""Orchestrator: end-to-end pipeline for one report run.

Phase 2 supports premarket only. Phase 5 will add other report types via
a per-type dispatch table.
"""

from __future__ import annotations

import time
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.core.state import StateDB
from daytrader.reports.core.ai_analyst import AIAnalyst
from daytrader.reports.core.context_loader import ContextLoader
from daytrader.reports.core.plan_extractor import PlanExtractor
from daytrader.reports.delivery.obsidian_writer import ObsidianWriter
from daytrader.reports.types.premarket import PremarketGenerator


PT = zoneinfo.ZoneInfo("America/Los_Angeles")
ET = zoneinfo.ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PipelineResult:
    success: bool
    report_id: int | None
    report_path: Path | None
    failure_reason: str | None = None
    skipped_idempotent: bool = False


class Orchestrator:
    """Coordinate one end-to-end report run for premarket."""

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
        symbol: str = "MES",
    ) -> None:
        self.state_db = state_db
        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.contract_path = Path(contract_path)
        self.journal_db_path = Path(journal_db_path)
        self.vault_root = Path(vault_root)
        self.fallback_dir = Path(fallback_dir)
        self.daily_folder = daily_folder
        self.symbol = symbol

    def run_premarket(self, run_at: datetime) -> PipelineResult:
        """Execute one premarket pipeline run."""
        run_at_utc = run_at.astimezone(timezone.utc)
        date_et = run_at_utc.astimezone(ET).date().isoformat()
        time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
        time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

        # Idempotency check
        if self.state_db.already_generated_today("premarket", date_et):
            return PipelineResult(
                success=True,
                report_id=None,
                report_path=None,
                skipped_idempotent=True,
            )

        # Insert pending report row
        report_id = self.state_db.insert_report(
            report_type="premarket",
            date_et=date_et,
            time_pt=time_pt_str,
            time_et=time_et_str,
            status="pending",
            created_at=run_at_utc,
        )

        start = time.perf_counter()

        # Load context
        loader = ContextLoader(
            contract_path=self.contract_path,
            journal_db_path=self.journal_db_path,
        )
        context = loader.load()

        # Generate
        generator = PremarketGenerator(
            ib_client=self.ib_client,
            ai_analyst=self.ai_analyst,
            symbol=self.symbol,
        )
        outcome = generator.generate(
            context=context,
            run_timestamp_pt=f"{time_pt_str} PT",
            run_timestamp_et=f"{time_et_str} ET",
        )

        if not outcome.validation.ok:
            self.state_db.update_report_status(
                report_id,
                status="failed",
                failure_reason=f"validation missing: {outcome.validation.missing}",
                tokens_input=outcome.ai_result.input_tokens,
                tokens_output=outcome.ai_result.output_tokens,
                duration_seconds=time.perf_counter() - start,
            )
            return PipelineResult(
                success=False,
                report_id=report_id,
                report_path=None,
                failure_reason=(
                    f"validation: missing sections {outcome.validation.missing}"
                ),
            )

        # Persist plan if extractable
        plan = PlanExtractor().extract(outcome.report_text)
        if plan is not None:
            self.state_db.save_plan(
                date_et=date_et,
                instrument=self.symbol,
                setup_name=plan.setup_name,
                direction=plan.direction,
                entry=plan.entry,
                stop=plan.stop,
                target=plan.target,
                r_unit_dollars=plan.r_unit_dollars,
                invalidations=plan.invalidations,
                raw_plan_text=plan.raw_text,
                source_report_path="",  # filled below
                created_at=run_at_utc,
            )

        # Write to Obsidian
        writer = ObsidianWriter(
            vault_root=self.vault_root,
            fallback_dir=self.fallback_dir,
            daily_folder=self.daily_folder,
        )
        write_result = writer.write_premarket(
            date_iso=date_et,
            content=outcome.report_text,
        )

        duration = time.perf_counter() - start
        self.state_db.update_report_status(
            report_id,
            status="success",
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
            success=True,
            report_id=report_id,
            report_path=write_result.path,
        )

    @staticmethod
    def _estimate_cost(ai_result: Any) -> float:
        """Rough Opus 4.7 cost estimate, USD."""
        # $15/M input (uncached); $1.50/M cache read; $18.75/M cache write; $75/M output
        in_uncached = (
            ai_result.input_tokens
            - ai_result.cache_read_tokens
            - ai_result.cache_creation_tokens
        )
        return (
            in_uncached / 1_000_000 * 15.0
            + ai_result.cache_creation_tokens / 1_000_000 * 18.75
            + ai_result.cache_read_tokens / 1_000_000 * 1.50
            + ai_result.output_tokens / 1_000_000 * 75.0
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/reports/test_orchestrator.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/core/orchestrator.py tests/reports/test_orchestrator.py
git commit -m "feat(reports): Orchestrator end-to-end premarket pipeline (idempotent)"
```

---

## Task 12: CLI — `daytrader reports run --type premarket`

**Files:**
- Modify: `src/daytrader/cli/reports.py`
- Modify: `tests/cli/test_reports_cli.py`

- [ ] **Step 1: Add failing test**

Append to `tests/cli/test_reports_cli.py`:

```python
def test_reports_run_command_registered():
    """`daytrader reports run --help` lists --type."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "run", "--help"])
    assert result.exit_code == 0
    assert "--type" in result.output


def test_reports_run_unknown_type_fails():
    """Unknown --type → non-zero exit."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "run", "--type", "bogus"])
    assert result.exit_code != 0


def test_reports_run_premarket_no_claude_cli_clearly_errors(monkeypatch, tmp_path):
    """Without claude CLI on PATH, run --type premarket exits non-zero with a clear message."""
    runner = CliRunner()
    # Strip PATH so `claude` cannot be found
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["reports", "run", "--type", "premarket"])
    assert result.exit_code != 0
    combined = (result.output or "").lower()
    assert "claude" in combined or "not found" in combined or "path" in combined
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/cli/test_reports_cli.py -v`
Expected: FAIL — `run` command not registered.

- [ ] **Step 3: Add `run` command to cli/reports.py**

Append to `src/daytrader/cli/reports.py` (below the existing `dry_run` command):

```python


@reports.command("run")
@click.option(
    "--type",
    "report_type",
    required=True,
    type=click.Choice(VALID_TYPES, case_sensitive=False),
    help="Report type to generate (Phase 2: only 'premarket' is implemented).",
)
@click.pass_context
def run_cmd(ctx: click.Context, report_type: str) -> None:
    """Run a real report end-to-end (touches IB Gateway and Anthropic API).

    Phase 2 implements `--type premarket` only. Other types raise NotImplementedError.
    """
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    from daytrader.core.config import load_config
    from daytrader.core.ib_client import IBClient
    from daytrader.core.state import StateDB
    from daytrader.reports.core.ai_analyst import AIAnalyst
    from daytrader.reports.core.orchestrator import Orchestrator

    if report_type != "premarket":
        click.echo(
            f"Phase 2 implements premarket only. {report_type!r} is in a later phase.",
            err=True,
        )
        ctx.exit(2)

    if shutil.which("claude") is None:
        click.echo(
            "claude CLI not found on PATH. Phase 2 uses `claude -p` "
            "(Pro Max subscription) — install Claude Code first.",
            err=True,
        )
        ctx.exit(3)

    project_root = Path(ctx.obj["project_root"]) if ctx.obj else Path.cwd()
    cfg = load_config(
        default_config=project_root / "config" / "default.yaml",
        user_config=project_root / "config" / "user.yaml",
    )

    state = StateDB(str(project_root / cfg.reports.state_db_path))
    state.initialize()

    ib = IBClient(
        host=cfg.reports.ib.host,
        port=cfg.reports.ib.port,
        client_id=cfg.reports.ib.client_id,
    )
    ib.connect()
    try:
        ai = AIAnalyst()  # claude -p backend; no API key needed

        vault_root = Path(cfg.obsidian.vault_path).expanduser()
        fallback_dir = project_root / "data" / "exports"

        orchestrator = Orchestrator(
            state_db=state,
            ib_client=ib,
            ai_analyst=ai,
            contract_path=project_root / cfg.journal.contract_path,
            journal_db_path=project_root / cfg.journal.db_path,
            vault_root=vault_root,
            fallback_dir=fallback_dir,
            daily_folder=cfg.obsidian.daily_folder,
            symbol="MES",
        )
        result = orchestrator.run_premarket(run_at=datetime.now(timezone.utc))

        if result.skipped_idempotent:
            click.echo("Report already generated today (skipped).")
            return
        if result.success:
            click.echo(f"Report generated: {result.report_path}")
        else:
            click.echo(f"Report FAILED: {result.failure_reason}", err=True)
            ctx.exit(1)
    finally:
        ib.disconnect()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/cli/test_reports_cli.py -v`
Expected: 7 tests PASS (4 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/cli/reports.py tests/cli/test_reports_cli.py
git commit -m "feat(reports): CLI run subcommand (premarket end-to-end, real services)"
```

---

## Task 13: Wire `run_report.py` to call orchestrator (real path)

**Files:**
- Modify: `scripts/run_report.py`
- Modify: `tests/scripts/test_run_report.py`

- [ ] **Step 1: Add failing test**

Append to `tests/scripts/test_run_report.py`:

```python
def test_run_report_premarket_no_secrets_exits_clearly(tmp_path):
    """Without secrets.yaml, --type premarket (no --dry) exits non-zero with msg."""
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "scripts" / "run_report.py"

    # Run from a temp cwd so config/secrets.yaml is absent
    result = subprocess.run(
        [sys.executable, str(script), "--type", "premarket"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "secrets" in combined or "not found" in combined or "phase" in combined
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/scripts/test_run_report.py -v`
Expected: this new test may PASS or FAIL depending on current script behavior. If it fails, proceed to Step 3.

- [ ] **Step 3: Update `scripts/run_report.py` non-dry path to call CLI**

Modify `scripts/run_report.py`. Replace the body of `main()` non-dry branch. The full updated `main()`:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description="Run a scheduled report.")
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_TYPES,
        help="Report type to generate.",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Phase 1 dry-run: skip IB / AI / delivery, print stub progress.",
    )
    args = parser.parse_args()

    lock_fd = _acquire_lock(args.type)
    try:
        if args.dry:
            print(f"[run_report] report_type={args.type}")
            print("[run_report] (Phase 1 stub) all stages skipped")
            print("[run_report] complete")
            return 0

        # Phase 2: delegate to CLI run subcommand for premarket; other types
        # surface a NotImplementedError-style exit until later phases.
        if args.type != "premarket":
            print(
                f"[run_report] {args.type!r} not yet implemented (Phase 2 supports premarket only)",
                file=sys.stderr,
            )
            return 4

        # Use the CLI runner so the path matches `daytrader reports run`
        import subprocess
        cmd = [
            sys.executable, "-m", "daytrader.cli.main",
            "reports", "run", "--type", "premarket",
        ]
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        return completed.returncode
    finally:
        os.close(lock_fd)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/scripts/test_run_report.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_report.py tests/scripts/test_run_report.py
git commit -m "feat(reports): scripts/run_report.py wires premarket non-dry to CLI"
```

---

## Task 14: Phase 2 acceptance — full unit + integration test pass + docs

**Files:**
- Create: `docs/ops/phase2-runbook.md`

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: All Phase 1 + Phase 2 tests pass; should be 220+ tests.

- [ ] **Step 2: Verify dry-run still works (no regression)**

Run: `uv run daytrader reports dry-run --type premarket`
Expected: 6 stub lines + "dry-run complete".

- [ ] **Step 3: Create Phase 2 runbook for real-world acceptance**

Create `docs/ops/phase2-runbook.md`:

```markdown
# Phase 2 Real-World Acceptance Runbook

After Phase 2 is merged, this runbook walks through the manual end-to-end test
that proves the foundation works against real IB Gateway and real Anthropic API.

## Prerequisites

1. **IB Gateway running locally** — see `docs/ops/ib-gateway-setup.md` (Phase 1).
2. **Claude Code CLI installed and authenticated** — Phase 2 invokes Claude via
   `claude -p` (Pro Max subscription path), NOT the Anthropic API. Verify:

   ```bash
   which claude        # should print a path
   claude --help       # should show usage
   echo "say hi" | claude -p   # quick auth check; should print a response
   ```

   If `claude` is not on PATH, install Claude Code from <https://claude.com/claude-code>
   and sign in with your Pro/Max account before continuing.

3. **Obsidian vault path** — set in `config/user.yaml`:

   ```yaml
   obsidian:
     enabled: true
     vault_path: ~/Path/To/Your/Vault
     daily_folder: Daily
   ```

4. **(Optional) Contract.md** — Phase 2 runs even with empty Contract; it will
   degrade per spec §4.5 state machine. To get the full premarket flow with C
   plan formation tied to your real setup, fill `docs/trading/Contract.md` first.

## Step 1: Smoke test in dry-run mode

```bash
uv run daytrader reports dry-run --type premarket
```

Expected: 6 stub lines, exit 0.

## Step 2: Real end-to-end run

```bash
uv run daytrader reports run --type premarket
```

What it does:
1. Verifies `claude` CLI is on PATH (fails fast if missing)
2. Loads config (no API key needed in Phase 2)
3. Connects to IB Gateway on `127.0.0.1:4002`
4. Fetches MES bars: 52 weekly + 200 daily + 50 4H + 24 1H
5. Loads Contract.md (degrades gracefully if missing)
6. Builds prompt as a flattened `[SYSTEM] / [USER]` text block
7. Invokes `claude -p` subprocess (~5-30 seconds, depends on subscription queue)
8. Validates required sections in the returned markdown
9. Extracts today's plan, saves to SQLite `plans` table
10. Writes markdown to `<vault>/Daily/2026-MM-DD-premarket.md`
11. Records report metadata in SQLite `reports` table (token counts will be 0)
12. Disconnects from IB Gateway

Expected stdout: `Report generated: /path/to/2026-MM-DD-premarket.md`

Expected cost (per run): **$0** — covered by your Claude Pro Max subscription. Subscription
usage counts toward your monthly quota; for Phase 2 dev/testing this is not a concern,
but Phase 7 production cadence (~6 runs/day × 3 instruments) may need re-evaluation.

## Step 3: Inspect the output

1. Open the generated markdown in Obsidian. Check:
   - Lock-in metadata block at top
   - Multi-TF analysis (W / D / 4H / 1H), each with OHLCV + pattern
   - Breaking news section (may say "no news items" if news collector not wired in Phase 2)
   - C section with plan structure
   - B section narrative
   - A section ("no action — execute plan" by default)

2. Check the SQLite plan was extracted:

   ```bash
   uv run python -c "
   from daytrader.core.state import StateDB
   db = StateDB('data/state.db')
   row = db.get_plan_for_date('2026-MM-DD', 'MES')
   print(dict(row) if row else 'no plan')
   "
   ```

3. Check the report record:

   ```bash
   uv run python -c "
   import sqlite3
   conn = sqlite3.connect('data/state.db')
   conn.row_factory = sqlite3.Row
   row = conn.execute('SELECT * FROM reports ORDER BY id DESC LIMIT 1').fetchone()
   print(dict(row))
   "
   ```

## Step 4: Idempotency check

Run again on the same day:

```bash
uv run daytrader reports run --type premarket
```

Expected: `Report already generated today (skipped).` Exit 0. AI not called again.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "claude CLI not found on PATH" | Claude Code not installed or not in shell PATH | Install Claude Code; ensure shell rc sources its bin path |
| "claude -p exit=1: not authenticated" | Claude Code CLI not signed in | Run `claude` interactively once to complete sign-in |
| "claude -p timeout after 180s" | Slow subscription queue or hung CLI | Retry; if persistent, check `claude doctor` for issues |
| "IBClient is not connected" | IB Gateway not running | Start IBC; verify port 4002 |
| Validation fails: missing C / B / A | Generated structure differs from template expectation | Inspect the report content; adjust `reports/templates/premarket.md` if needed |
| Bars empty for some TF | IB Gateway not receiving market data | Check CME data subscription in IBKR account |
| Subscription rate-limited | Hit Pro Max quota | Wait or temporarily switch to API backend (future Phase 7 work) |

## What this run does NOT yet do (Phase 3+)

- Multi-instrument (only MES) → Phase 3
- F. futures structure (no OI/COT/basis/term/VP) → Phase 4
- Other report types (intraday/EOD/weekly/night) → Phase 5
- Telegram push (only Obsidian today) → Phase 6
- PDF / chart rendering → Phase 6
- Automatic launchd schedule → Phase 7

## Acceptance criteria

Phase 2 is "done" when:
1. ☐ `daytrader reports run --type premarket` succeeds without error
2. ☐ A markdown file is created in your Obsidian Daily folder
3. ☐ The file passes a manual sanity read — sections look correct, numbers are real
4. ☐ The plan extraction populates `state.db.plans` with valid setup/entry/stop/target
5. ☐ Idempotent re-run within the same ET day prints "skipped" and does not call AI
6. ☐ Estimated cost in the `reports` row is under $1.00 for a typical run
```

- [ ] **Step 4: Commit**

```bash
git add docs/ops/phase2-runbook.md
git commit -m "docs(reports): Phase 2 real-world acceptance runbook"
```

---

## Task 15: Phase 2 completion verification

**Files:**
- None (verification only)

- [ ] **Step 1: Final test pass**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: all tests pass; total count significantly > 193 (Phase 1).

- [ ] **Step 2: Inspect git log**

Run: `git log --oneline | head -20`
Expected: ~14 new commits since Phase 1 (`bb007a3` was last Phase 1 commit), all `feat(reports):` / `test(reports):` / `docs(reports):` prefixed.

- [ ] **Step 3: Confirm Phase 2 file structure**

Run:

```bash
find src/daytrader/reports -type f | sort
```

Expected output (Phase 1 + Phase 2):

```
src/daytrader/reports/__init__.py
src/daytrader/reports/core/__init__.py
src/daytrader/reports/core/ai_analyst.py
src/daytrader/reports/core/context_loader.py
src/daytrader/reports/core/orchestrator.py
src/daytrader/reports/core/output_validator.py
src/daytrader/reports/core/plan_extractor.py
src/daytrader/reports/core/prompt_builder.py
src/daytrader/reports/core/secrets.py
src/daytrader/reports/delivery/__init__.py
src/daytrader/reports/delivery/obsidian_writer.py
src/daytrader/reports/instruments/__init__.py
src/daytrader/reports/instruments/definitions.py
src/daytrader/reports/templates/__init__.py
src/daytrader/reports/templates/premarket.md
src/daytrader/reports/types/__init__.py
src/daytrader/reports/types/premarket.py
```

- [ ] **Step 4: Verify nothing in `premarket/` or `journal/` was modified**

Run: `git diff bb007a3..HEAD -- src/daytrader/premarket src/daytrader/journal`
Expected: no diff output.

- [ ] **Step 5: No commit needed — Phase 2 acceptance is verification only**

If any check fails, return to the offending task and fix.

---

## Summary

After all 15 tasks Phase 2 produces:

1. **Context loading**: `ContextLoader` + `ReportContext` + `ContractStatus` state machine.
2. **Prompt assembly**: `PromptBuilder.build_premarket()` with Anthropic cache markers.
3. **AI integration**: `AIAnalyst` calling Claude Opus 4.7 with retry + cost tracking.
4. **Validation**: `OutputValidator` enforces required sections.
5. **Plan extraction**: `PlanExtractor` parses today's plan and saves to `StateDB.plans`.
6. **Delivery**: `ObsidianWriter` writes to vault with fallback to `data/exports/`.
7. **Type handler**: `PremarketGenerator` orchestrates fetch → AI → validate.
8. **Pipeline**: `Orchestrator.run_premarket()` end-to-end; idempotent within an ET day.
9. **CLI**: `daytrader reports run --type premarket` real run command.
10. **Script entry**: `scripts/run_report.py` non-dry path delegates to CLI.
11. **Runbook**: `docs/ops/phase2-runbook.md` for manual acceptance test.

**~25 new tests** across `tests/reports/` and updated `tests/cli/`, `tests/scripts/`.

**Existing modules** (`premarket/`, `journal/`, `core/db.py`, Phase 1 modules) — **unchanged**.

**Next**: Phase 3 plan — multi-TF + multi-instrument (MES + MNQ + MGC) — to be written as a separate plan file after Phase 2 lands.
