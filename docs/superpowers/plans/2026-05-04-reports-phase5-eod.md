# Reports System — Phase 5: EOD Daily Report (Plan Retrospective + Tomorrow Preliminary)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the EOD (End-Of-Day) report cadence — fired daily at 14:00 PT Mon-Fri — including the closed-loop **Plan Retrospective** (today's premarket plan vs actual price action) and **Tomorrow Preliminary Plan** sections that turn every trading day (including 0-trade days) into a data point for plan quality.

**Architecture:** Mirror the existing `PremarketGenerator` pattern with a new `EODGenerator` parallel to it. Reuse Phase 4 (`FuturesSection`), Phase 4.5 (`SentimentSection`) and Phase 7 v1 (preflight + launchd wrapper) infrastructure unchanged. Add 8 new modules under `src/daytrader/reports/eod/` and `src/daytrader/reports/types/eod.py`. Persist daily retrospective rows to a new `plan_retrospective_daily` SQLite table for v2 multi-day stats.

**Tech Stack:** Python 3.11+, stdlib (`sqlite3`, `re`, `dataclasses`, `pathlib`), `pydantic` (existing journal models), `ib_insync` (via existing `IBClient`), `pytest`, `claude -p` (Pro Max subscription).

**Spec:** [`docs/superpowers/specs/2026-05-04-reports-phase5-eod-design.md`](../specs/2026-05-04-reports-phase5-eod-design.md)

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `src/daytrader/reports/eod/__init__.py` | Create | Module init + public re-exports |
| `src/daytrader/reports/eod/plan_dataclasses.py` | Create | `PlanLevel`, `Plan`, `SimOutcome`, `RetrospectiveRow` (frozen dataclasses) |
| `src/daytrader/reports/eod/plan_reader.py` | Create | Read Obsidian premarket .md → extract `### C-MES` / `### C-MGC` raw blocks |
| `src/daytrader/reports/eod/plan_parser.py` | Create | Raw markdown → structured `Plan` (regex-tolerant; handles multi-price bullets + zones) |
| `src/daytrader/reports/eod/trades_query.py` | Create | Journal DB query → today's trades + §6 / §9 audit |
| `src/daytrader/reports/eod/trade_simulator.py` | Create | `(PlanLevel, intraday_bars) → SimOutcome` — algorithmic heart |
| `src/daytrader/reports/eod/retrospective.py` | Create | Compose plans + simulator outcomes + actual trades → per-symbol retrospective + persist daily row |
| `src/daytrader/reports/eod/tomorrow_plan.py` | Create | Build preliminary tomorrow plan input (key levels carryover + sentiment shift + econ events) |
| `src/daytrader/reports/types/eod.py` | Create | `EODGenerator` class (mirrors `PremarketGenerator`) |
| `src/daytrader/reports/templates/eod.md` | Create | AI prompt instruction template |
| `src/daytrader/reports/core/prompt_builder.py` | Modify | Add `build_eod()` method |
| `src/daytrader/reports/core/output_validator.py` | Modify | Add `REQUIRED_SECTIONS["eod"]` |
| `src/daytrader/reports/core/orchestrator.py` | Modify | Add `run_eod()` method |
| `src/daytrader/cli/reports.py` | Modify | Dispatch `--type eod` to `orchestrator.run_eod()` |
| `src/daytrader/core/state.py` | Modify | Add `plan_retrospective_daily` table init |
| `scripts/run_eod_launchd.sh` | Create | launchd wrapper (mirrors `run_premarket_launchd.sh`) |
| `scripts/launchd/com.daytrader.report.eod.1400pt.plist.template` | Create | launchd plist template |
| `scripts/install_eod_launchd.sh` | Create | One-command install |
| `scripts/uninstall_eod_launchd.sh` | Create | One-command uninstall |
| `.gitignore` | Modify | Ignore `data/logs/launchd/eod-*.log` |
| `tests/reports/eod/*` (10 test files) | Create | Unit + integration tests |

---

## Task 1: Plan dataclasses (foundation)

**Files:**
- Create: `tests/reports/eod/__init__.py`
- Create: `tests/reports/eod/test_plan_dataclasses.py`
- Create: `src/daytrader/reports/eod/__init__.py`
- Create: `src/daytrader/reports/eod/plan_dataclasses.py`

- [ ] **Step 1: Create `tests/reports/eod/__init__.py`** (empty file)

```bash
mkdir -p tests/reports/eod
touch tests/reports/eod/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `tests/reports/eod/test_plan_dataclasses.py`:

```python
"""Unit tests for EOD plan dataclasses."""

from __future__ import annotations

import pytest

from daytrader.reports.eod.plan_dataclasses import (
    Plan,
    PlanLevel,
    RetrospectiveRow,
    SimOutcome,
)


def test_plan_level_point_construction():
    pl = PlanLevel(
        price=7272.75,
        level_type="POINT",
        source="4H POC",
        direction="short_fade",
    )
    assert pl.price == 7272.75
    assert pl.level_type == "POINT"
    assert pl.zone_low is None
    assert pl.zone_high is None


def test_plan_level_zone_construction():
    pl = PlanLevel(
        price=7190.0,
        level_type="ZONE",
        source="W demand zone",
        direction="long_fade",
        zone_low=7185.0,
        zone_high=7195.0,
    )
    assert pl.zone_low == 7185.0
    assert pl.zone_high == 7195.0


def test_plan_level_is_frozen():
    pl = PlanLevel(price=1.0, level_type="POINT", source="x", direction="long_fade")
    with pytest.raises(Exception):  # FrozenInstanceError
        pl.price = 2.0  # type: ignore[misc]


def test_plan_construction():
    levels = [
        PlanLevel(price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"),
        PlanLevel(price=7240.75, level_type="POINT", source="D low", direction="long_fade"),
    ]
    p = Plan(symbol="MES", levels=levels)
    assert p.symbol == "MES"
    assert len(p.levels) == 2
    assert p.stop_offset_ticks == 2  # default
    assert p.target_r_multiple == 2.0  # default
    assert p.parse_warnings == []  # default empty


def test_plan_with_warnings():
    p = Plan(
        symbol="MES",
        levels=[],
        parse_warnings=["could not parse 'Stretch short' label"],
    )
    assert "could not parse" in p.parse_warnings[0]


def test_sim_outcome_untriggered_factory():
    s = SimOutcome.untriggered()
    assert s.triggered is False
    assert s.outcome == "untriggered"
    assert s.sim_r == 0.0
    assert s.touch_time_pt is None
    assert s.sim_entry is None


def test_sim_outcome_target_hit():
    s = SimOutcome(
        triggered=True,
        touch_time_pt="06:53",
        touch_bar_high=7273.5,
        touch_bar_low=7271.0,
        sim_entry=7272.75,
        sim_stop=7273.25,
        sim_target=7252.75,
        outcome="target",
        sim_r=2.0,
        mfe_r=2.0,
        mae_r=-0.4,
    )
    assert s.outcome == "target"
    assert s.sim_r == 2.0
    assert s.mfe_r == 2.0


def test_retrospective_row_construction():
    levels = [PlanLevel(price=7272.75, level_type="POINT", source="4H POC", direction="short_fade")]
    outcomes = [(levels[0], SimOutcome.untriggered())]
    row = RetrospectiveRow(
        symbol="MES",
        date_et="2026-05-04",
        total_levels=1,
        triggered_count=0,
        sim_total_r=0.0,
        actual_total_r=0.0,
        gap_r=0.0,
        per_level_outcomes=outcomes,
    )
    assert row.symbol == "MES"
    assert row.total_levels == 1
    assert row.triggered_count == 0
    assert len(row.per_level_outcomes) == 1
```

- [ ] **Step 3: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_plan_dataclasses.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create `src/daytrader/reports/eod/__init__.py`**

```python
"""Phase 5 EOD report: today's recap + plan retrospective + tomorrow preliminary.

Module structure:
- plan_dataclasses: PlanLevel / Plan / SimOutcome / RetrospectiveRow
- plan_reader:      Read Obsidian premarket .md → extract C blocks
- plan_parser:      Raw markdown → structured Plan (regex-tolerant)
- trades_query:     Journal DB → today's trades + §6 / §9 audit
- trade_simulator:  (level, intraday_bars) → SimOutcome
- retrospective:    Compose all above + persist daily row to state.db
- tomorrow_plan:    Build preliminary tomorrow plan input

Public surface (re-exports below) intentionally minimal — orchestrator
imports from submodules directly.
"""

from daytrader.reports.eod.plan_dataclasses import (
    Plan,
    PlanLevel,
    RetrospectiveRow,
    SimOutcome,
)

__all__ = [
    "Plan",
    "PlanLevel",
    "RetrospectiveRow",
    "SimOutcome",
]
```

- [ ] **Step 5: Implement `plan_dataclasses.py`**

```python
"""Frozen dataclasses for the EOD plan retrospective subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class PlanLevel:
    """A single key level extracted from today's premarket C block.

    POINT levels are single prices (e.g. "7272.75 (4H POC)"). The
    `entry_proximity` rule is `max_ticks=4` (per setup yaml).

    ZONE levels are price ranges (e.g. "7185-7195 W demand zone"). The
    entry rule is "price within zone edges". `zone_low` / `zone_high`
    capture the edges; `price` is set to the midpoint or the level the
    AI emphasized as primary.
    """
    price: float
    level_type: Literal["POINT", "ZONE"]
    source: str  # e.g. "4H POC", "W high", "htf_demand_zone fresh"
    direction: Literal["short_fade", "long_fade"]
    zone_low: float | None = None
    zone_high: float | None = None


@dataclass(frozen=True)
class Plan:
    """Today's structured plan for one symbol, parsed from premarket C block."""
    symbol: str
    levels: list[PlanLevel]
    stop_offset_ticks: int = 2          # per setup yaml
    target_r_multiple: float = 2.0      # per setup yaml
    raw_block_md: str = ""              # for verbatim quote in C section
    parse_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SimOutcome:
    """Result of simulating one PlanLevel against today's intraday bars."""
    triggered: bool
    touch_time_pt: str | None       # e.g. "06:53" or None if untriggered
    touch_bar_high: float | None
    touch_bar_low: float | None
    sim_entry: float | None
    sim_stop: float | None
    sim_target: float | None
    outcome: Literal["target", "stop", "open", "untriggered"]
    sim_r: float                    # 0 if untriggered, +N if target, -1 if stop, partial if open
    mfe_r: float | None             # max favorable excursion in R units
    mae_r: float | None             # max adverse excursion in R units

    @classmethod
    def untriggered(cls) -> "SimOutcome":
        """Factory for the level-not-touched case."""
        return cls(
            triggered=False,
            touch_time_pt=None,
            touch_bar_high=None,
            touch_bar_low=None,
            sim_entry=None,
            sim_stop=None,
            sim_target=None,
            outcome="untriggered",
            sim_r=0.0,
            mfe_r=None,
            mae_r=None,
        )


@dataclass(frozen=True)
class RetrospectiveRow:
    """Per-symbol per-day retrospective summary. One row → one row in
    `plan_retrospective_daily` SQLite table."""
    symbol: str
    date_et: str                    # YYYY-MM-DD
    total_levels: int
    triggered_count: int
    sim_total_r: float              # sum of all levels' sim_r
    actual_total_r: float           # from journal DB
    gap_r: float                    # sim - actual
    per_level_outcomes: list[tuple[PlanLevel, SimOutcome]]
```

- [ ] **Step 6: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_plan_dataclasses.py -v`
Expected: 8 tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/daytrader/reports/eod/__init__.py src/daytrader/reports/eod/plan_dataclasses.py tests/reports/eod/__init__.py tests/reports/eod/test_plan_dataclasses.py
git commit -m "feat(eod): plan dataclasses (PlanLevel/Plan/SimOutcome/RetrospectiveRow)"
```

---

## Task 2: PremarketPlanReader

**Files:**
- Create: `src/daytrader/reports/eod/plan_reader.py`
- Create: `tests/reports/eod/test_plan_reader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/reports/eod/test_plan_reader.py`:

```python
"""Unit tests for PremarketPlanReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from daytrader.reports.eod.plan_reader import PremarketPlanReader


SAMPLE_PREMARKET_MD = """---
date: 2026-05-04
type: premarket
---

# Premarket Daily Report

## 📊 MES (Micro E-mini S&P 500)
[multi-TF data...]

## C. 计划复核 / Plan Formation

### C-MES

**Today's plan**:
- **Setup**: stacked_imbalance_reversal_at_level
- **Entry**: 仅在以下其一区域出现 3+ stacked imbalance 时触发
  - **Long bias 区**: 7199.25（D low）+ 7185–7195（W 低区）
  - **Short bias 区**: 7271–7279.5（4H R）
- **Stop**: 入场 ±1R = ± 8 pt
- **Target**: +2R

**Invalidation conditions**:
1. MES 跌破 7185 RTH close → 转空头观察

**Today's posture**: neutral / wait for setup

### C-MGC

**Today's plan**:
- **Setup**: stacked_imbalance_reversal_at_level
- **Entry**: 触发条件
  - **Long bias 区**: 4570（D low）
  - **Short bias 区**: 4673（D high）

## B. 市场叙事
"""


def test_reader_extracts_both_C_blocks(tmp_path):
    vault = tmp_path / "Vault"
    daily = vault / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-05-04-premarket.md").write_text(SAMPLE_PREMARKET_MD, encoding="utf-8")

    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")
    blocks = reader.read_today_plan(date_et="2026-05-04")

    assert "MES" in blocks
    assert "MGC" in blocks
    assert "Long bias 区" in blocks["MES"]
    assert "7199.25" in blocks["MES"]
    assert "4570" in blocks["MGC"]


def test_reader_returns_empty_dict_when_file_missing(tmp_path):
    vault = tmp_path / "Vault"
    (vault / "Daily").mkdir(parents=True)
    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")

    blocks = reader.read_today_plan(date_et="2026-05-04")
    assert blocks == {}


def test_reader_handles_only_one_C_block(tmp_path):
    """If only C-MES is present (no C-MGC), returns just MES."""
    md = """## C. 计划复核

### C-MES

**Today's plan**:
- Setup: ...
- Long bias 区: 7199

## B. 市场叙事
"""
    vault = tmp_path / "Vault"
    daily = vault / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-05-04-premarket.md").write_text(md, encoding="utf-8")

    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")
    blocks = reader.read_today_plan(date_et="2026-05-04")
    assert "MES" in blocks
    assert "MGC" not in blocks


def test_reader_strips_block_at_next_h3_or_h2(tmp_path):
    """Block extraction should stop at next ### or ## header to avoid
    bleeding into B section."""
    vault = tmp_path / "Vault"
    daily = vault / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-05-04-premarket.md").write_text(SAMPLE_PREMARKET_MD, encoding="utf-8")

    reader = PremarketPlanReader(vault_path=vault, daily_folder="Daily")
    blocks = reader.read_today_plan(date_et="2026-05-04")

    # MES block should NOT contain anything from C-MGC or B section
    assert "C-MGC" not in blocks["MES"]
    assert "市场叙事" not in blocks["MES"]
    # MGC block should NOT contain B section
    assert "市场叙事" not in blocks["MGC"]
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_plan_reader.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `plan_reader.py`**

```python
"""PremarketPlanReader — read today's premarket .md from Obsidian, extract C blocks."""

from __future__ import annotations

import re
from pathlib import Path


class PremarketPlanReader:
    """Read the premarket markdown for a given ET date and extract per-symbol
    C-block raw markdown.

    File path convention (per spec §2.2): `{vault_path}/{daily_folder}/{date_et}-premarket.md`
    where date_et is the ET date string YYYY-MM-DD.

    Returns dict[symbol, raw_markdown] for whichever of MES / MGC is found.
    Empty dict on missing file (graceful degradation — EOD still runs but
    C section reflects "plan unavailable").
    """

    # Regex extracts content from `### C-{SYMBOL}` heading down to the next
    # `### ` or `## ` heading (whichever comes first).
    _BLOCK_RE = re.compile(
        r"^###\s*C-([A-Z]{2,4})\s*$\n+(.+?)(?=\n###\s|\n##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    def __init__(self, vault_path: Path, daily_folder: str = "Daily") -> None:
        self._vault_path = Path(vault_path)
        self._daily_folder = daily_folder

    def read_today_plan(self, date_et: str) -> dict[str, str]:
        """Return {symbol: raw_C_block_markdown} or {} if file missing."""
        path = self._vault_path / self._daily_folder / f"{date_et}-premarket.md"
        if not path.exists():
            return {}

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return {}

        out: dict[str, str] = {}
        for match in self._BLOCK_RE.finditer(text):
            symbol = match.group(1)
            block = match.group(2).strip()
            out[symbol] = block
        return out
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_plan_reader.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/eod/plan_reader.py tests/reports/eod/test_plan_reader.py
git commit -m "feat(eod): PremarketPlanReader extracts C-MES/C-MGC blocks from Obsidian"
```

---

## Task 3: PremarketPlanParser

**Files:**
- Create: `src/daytrader/reports/eod/plan_parser.py`
- Create: `tests/reports/eod/test_plan_parser.py`

The parser handles the actual format the AI uses (verified via 2026-05-04 real premarket):

- `**Long bias 区**: 7199.25（D low）+ 7185–7195（W 低区, htf_demand_zone fresh check）`
- `**Short bias 区**: 7271–7279.5（4H R + D high reject 区）`
- `**Stretch short**: 7253（D 4/30 close 阻力）`

Parser must:
1. Find `**Long bias 区**` / `**Short bias 区**` / `**Stretch short/long**` labels (direction)
2. Extract one or more prices per line: `7199.25`, `7185–7195` (zone), `7253`
3. Extract source from parentheses (full-width `（）` or ASCII `()`)
4. Tolerate format variance — emit `parse_warnings` rather than crashing

- [ ] **Step 1: Write failing tests**

Create `tests/reports/eod/test_plan_parser.py`:

```python
"""Unit tests for PremarketPlanParser."""

from __future__ import annotations

from daytrader.reports.eod.plan_parser import PremarketPlanParser


SAMPLE_C_MES = """**Today's plan (5/5 RTH)**:
- **Setup**: stacked_imbalance_reversal_at_level
- **Direction**: wait for setup
- **Entry**: 仅在以下其一区域出现 3+ stacked imbalance 时触发
  - **Long bias 区**: 7199.25（D low / 4H S）+ 7185–7195（5/1 W 低区, htf_demand_zone fresh check）
  - **Short bias 区**: 7271–7279.5（4H R + D high reject 区）
  - **Stretch short**: 7253（D 4/30 close 阻力）
- **Stop**: 入场 ± 1R = ± 8 pt
- **Target**: +2R

**Invalidation conditions** (任一触发即放弃今日 MES 计划):
1. MES 跌破 7185 RTH close → 转空头

**Today's posture**: neutral / wait for setup
"""


def test_parser_extracts_long_bias_levels():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    long_levels = [lv for lv in plan.levels if lv.direction == "long_fade"]
    prices = [lv.price for lv in long_levels]
    # Should include 7199.25 (POINT) and 7185-7195 zone (could be midpoint or first)
    assert any(p == 7199.25 for p in prices), f"7199.25 missing in {prices}"
    # Zone 7185-7195 should be parsed
    zone_levels = [lv for lv in long_levels if lv.level_type == "ZONE"]
    assert len(zone_levels) >= 1
    assert zone_levels[0].zone_low == 7185.0
    assert zone_levels[0].zone_high == 7195.0


def test_parser_extracts_short_bias_levels():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    short_levels = [lv for lv in plan.levels if lv.direction == "short_fade"]
    # Should include 7271-7279.5 zone + 7253 POINT (Stretch short)
    assert len(short_levels) >= 2
    zones = [lv for lv in short_levels if lv.level_type == "ZONE"]
    assert any(z.zone_low == 7271.0 and z.zone_high == 7279.5 for z in zones)
    points = [lv for lv in short_levels if lv.level_type == "POINT"]
    assert any(lv.price == 7253.0 for lv in points)


def test_parser_extracts_source_from_parens():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    long_levels = [lv for lv in plan.levels if lv.direction == "long_fade" and lv.price == 7199.25]
    assert len(long_levels) >= 1
    assert "D low" in long_levels[0].source or "4H S" in long_levels[0].source


def test_parser_attaches_raw_block_for_verbatim_quote():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    assert "Long bias 区" in plan.raw_block_md
    assert plan.symbol == "MES"


def test_parser_returns_default_stop_target_when_not_explicit():
    """Parser should default to setup yaml values (stop=2 ticks, target=2R)
    if the C block doesn't override them."""
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    assert plan.stop_offset_ticks == 2
    assert plan.target_r_multiple == 2.0


def test_parser_empty_block_returns_empty_levels():
    parser = PremarketPlanParser()
    plan = parser.parse("", symbol="MES")
    assert plan.symbol == "MES"
    assert plan.levels == []
    assert "empty" in plan.parse_warnings[0].lower() or "no" in plan.parse_warnings[0].lower()


def test_parser_unrecognized_format_emits_warning():
    """If the block is unparseable garbage, emit warning, don't crash."""
    parser = PremarketPlanParser()
    plan = parser.parse("hello world this is not a plan", symbol="MES")
    assert plan.symbol == "MES"
    assert plan.levels == []
    assert len(plan.parse_warnings) >= 1


def test_parser_handles_full_width_punctuation():
    """Real AI output uses full-width 全角 parens. Parser should tolerate."""
    block = """- **Long bias 区**: 7199.25（D low）"""
    parser = PremarketPlanParser()
    plan = parser.parse(block, symbol="MES")
    assert len(plan.levels) >= 1
    assert plan.levels[0].price == 7199.25
    assert "D low" in plan.levels[0].source


def test_parser_stretch_label_treated_as_directional():
    """**Stretch short**: 7253 should be parsed as short_fade direction."""
    block = """- **Stretch short**: 7253（D 4/30 阻力）"""
    parser = PremarketPlanParser()
    plan = parser.parse(block, symbol="MES")
    short_levels = [lv for lv in plan.levels if lv.direction == "short_fade"]
    assert len(short_levels) == 1
    assert short_levels[0].price == 7253.0


def test_parser_zone_dash_variants():
    """Both ASCII '-' and Unicode '–' (em-dash) zone separators must work."""
    for sep in ["-", "–", "—"]:
        block = f"""- **Long bias 区**: 7185{sep}7195（W 低区）"""
        parser = PremarketPlanParser()
        plan = parser.parse(block, symbol="MES")
        zones = [lv for lv in plan.levels if lv.level_type == "ZONE"]
        assert len(zones) == 1, f"separator {sep!r} produced {len(zones)} zones"
        assert zones[0].zone_low == 7185.0
        assert zones[0].zone_high == 7195.0
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_plan_parser.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `plan_parser.py`**

```python
"""PremarketPlanParser — raw C-block markdown → structured Plan."""

from __future__ import annotations

import re

from daytrader.reports.eod.plan_dataclasses import Plan, PlanLevel


# Direction-bearing labels and their semantics.
_DIRECTION_LABELS: list[tuple[str, str]] = [
    ("Long bias 区", "long_fade"),
    ("Short bias 区", "short_fade"),
    ("Stretch long", "long_fade"),
    ("Stretch short", "short_fade"),
]

# Match a level bullet line. Captures: label, price-list-text, source-paren-content.
# Tolerates:
#   - full-width ** or ASCII **
#   - full-width parens 全角 （） or ASCII ()
#   - leading spaces (nested bullets)
_LINE_RE = re.compile(
    r"-\s*\*\*\s*(?P<label>[^*\n]+?)\s*\*\*\s*[:：]\s*"
    r"(?P<prices>[^（(\n]+?)\s*"
    r"[（(](?P<source>[^）)\n]*)[）)]"
    r".*?$",
    re.MULTILINE,
)

# Within the prices group, find prices: either a zone (7185-7195) or single (7199.25).
# Zone separators: ASCII '-', Unicode em-dash '—' (U+2014), en-dash '–' (U+2013).
_ZONE_RE = re.compile(r"(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)")
_PRICE_RE = re.compile(r"\b(\d+\.?\d+)\b|\b(\d{4,})\b")  # decimal OR 4+ digit integer


class PremarketPlanParser:
    """Parse C-block raw markdown into structured Plan.

    Defensive: when format varies from expectations, emit `parse_warnings`
    rather than raise. Empty block → Plan with empty levels + warning.
    Unrecognized format → empty levels + warning.
    """

    def parse(self, raw_block_md: str, symbol: str) -> Plan:
        if not raw_block_md or not raw_block_md.strip():
            return Plan(
                symbol=symbol,
                levels=[],
                raw_block_md=raw_block_md,
                parse_warnings=["empty C block — premarket may have failed today"],
            )

        levels: list[PlanLevel] = []
        warnings: list[str] = []

        # Iterate every bullet line that has the **label**: prices (source) shape
        any_match = False
        for m in _LINE_RE.finditer(raw_block_md):
            any_match = True
            label = m.group("label").strip()
            prices_text = m.group("prices").strip()
            source = m.group("source").strip()

            direction = self._resolve_direction(label)
            if direction is None:
                # Label like "Setup" or "Stop" or "Target" — not a level line.
                continue

            for plevel in self._parse_prices(prices_text, source, direction):
                levels.append(plevel)

        if not any_match:
            warnings.append(
                "no parseable level bullets found — block format may have changed"
            )
        elif not levels:
            warnings.append(
                "level bullets found but no directional labels matched "
                "(checked: Long bias 区 / Short bias 区 / Stretch long/short)"
            )

        return Plan(
            symbol=symbol,
            levels=levels,
            raw_block_md=raw_block_md,
            parse_warnings=warnings,
        )

    # --- helpers ---

    @staticmethod
    def _resolve_direction(label: str) -> str | None:
        """Map free-text label to canonical direction string."""
        label_lower = label.lower()
        for keyword, direction in _DIRECTION_LABELS:
            if keyword.lower() in label_lower:
                return direction
        return None

    @staticmethod
    def _parse_prices(text: str, source: str, direction: str) -> list[PlanLevel]:
        """Extract one or more PlanLevel from a prices-text fragment.

        Examples:
        - "7199.25" → 1 POINT
        - "7185–7195" → 1 ZONE (low=7185, high=7195, price=midpoint)
        - "7199.25 + 7185–7195" → 2 levels (POINT + ZONE)
        - "7271-7279.5" → 1 ZONE
        """
        # Split on '+' to allow multiple levels per bullet
        out: list[PlanLevel] = []
        for fragment in text.split("+"):
            fragment = fragment.strip()
            if not fragment:
                continue
            zone_match = _ZONE_RE.search(fragment)
            if zone_match:
                low = float(zone_match.group(1))
                high = float(zone_match.group(2))
                if low > high:
                    low, high = high, low
                out.append(
                    PlanLevel(
                        price=(low + high) / 2,
                        level_type="ZONE",
                        source=source,
                        direction=direction,  # type: ignore[arg-type]
                        zone_low=low,
                        zone_high=high,
                    )
                )
            else:
                price_match = _PRICE_RE.search(fragment)
                if price_match:
                    raw = price_match.group(1) or price_match.group(2)
                    try:
                        price = float(raw)
                        out.append(
                            PlanLevel(
                                price=price,
                                level_type="POINT",
                                source=source,
                                direction=direction,  # type: ignore[arg-type]
                            )
                        )
                    except ValueError:
                        pass
        return out
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_plan_parser.py -v`
Expected: 10 tests pass.

If any test fails because of regex edge cases, tweak the regex (don't relax the assertions).

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/eod/plan_parser.py tests/reports/eod/test_plan_parser.py
git commit -m "feat(eod): PremarketPlanParser handles **Long bias 区** / zones / Stretch labels"
```

---

## Task 4: TodayTradesQuery

**Files:**
- Create: `src/daytrader/reports/eod/trades_query.py`
- Create: `tests/reports/eod/test_trades_query.py`

- [ ] **Step 1: Write failing tests**

Create `tests/reports/eod/test_trades_query.py`:

```python
"""Unit tests for TodayTradesQuery."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.reports.eod.trades_query import TodayTradesQuery


def _init_journal_db(path: Path) -> sqlite3.Connection:
    """Create a minimal trades table matching the JournalTrade Pydantic shape."""
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE trades (
            id TEXT PRIMARY KEY,
            checklist_id TEXT,
            date TEXT,
            symbol TEXT,
            direction TEXT,
            setup_type TEXT,
            entry_time TEXT,
            entry_price REAL,
            stop_price REAL,
            target_price REAL,
            size INTEGER,
            exit_time TEXT,
            exit_price REAL,
            pnl_usd REAL,
            notes TEXT,
            violations TEXT,
            mode TEXT
        )"""
    )
    return conn


def _insert_trade(conn, **kwargs) -> None:
    defaults = {
        "id": "t1",
        "checklist_id": "c1",
        "date": "2026-05-04",
        "symbol": "MES",
        "direction": "short",
        "setup_type": "stacked_imbalance_reversal_at_level",
        "entry_time": "2026-05-04T13:30:00+00:00",
        "entry_price": 7272.75,
        "stop_price": 7273.25,
        "target_price": 7252.75,
        "size": 1,
        "exit_time": None,
        "exit_price": None,
        "pnl_usd": None,
        "notes": None,
        "violations": "[]",
        "mode": "real",
    }
    defaults.update(kwargs)
    conn.execute(
        """INSERT INTO trades (id, checklist_id, date, symbol, direction, setup_type,
            entry_time, entry_price, stop_price, target_price, size,
            exit_time, exit_price, pnl_usd, notes, violations, mode)
           VALUES (:id, :checklist_id, :date, :symbol, :direction, :setup_type,
            :entry_time, :entry_price, :stop_price, :target_price, :size,
            :exit_time, :exit_price, :pnl_usd, :notes, :violations, :mode)""",
        defaults,
    )
    conn.commit()


def test_returns_empty_for_no_trades(tmp_path):
    db = tmp_path / "journal.db"
    _init_journal_db(db).close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    assert trades == []


def test_returns_today_trades_only(tmp_path):
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t-today", date="2026-05-04")
    _insert_trade(conn, id="t-yesterday", date="2026-05-03")
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    assert len(trades) == 1
    assert trades[0]["id"] == "t-today"


def test_filters_to_real_mode_by_default(tmp_path):
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t-real", mode="real")
    _insert_trade(conn, id="t-dry", mode="dry_run")
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    ids = {t["id"] for t in trades}
    assert "t-real" in ids
    assert "t-dry" not in ids


def test_audit_summary_zero_trades(tmp_path):
    db = tmp_path / "journal.db"
    _init_journal_db(db).close()

    q = TodayTradesQuery(db)
    audit = q.audit_summary([])
    assert audit["count"] == 0
    assert audit["daily_r"] == 0.0
    assert audit["violations_total"] == 0
    assert audit["screenshots_complete"] == 0


def test_audit_summary_counts_violations(tmp_path):
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t1", violations='["ban_averaging_down"]', pnl_usd=-50.0)
    _insert_trade(conn, id="t2", violations="[]", pnl_usd=100.0)
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    audit = q.audit_summary(trades)
    assert audit["count"] == 2
    assert audit["violations_total"] == 1
    assert audit["daily_r"] == pytest.approx((-50.0 + 100.0) / 50.0)  # net 1R given R=$50


def test_audit_summary_screenshot_check_via_notes(tmp_path):
    """V1 placeholder: notes containing 'screenshots: yes' counts as
    §9-compliant (until JournalTrade model adds explicit fields)."""
    db = tmp_path / "journal.db"
    conn = _init_journal_db(db)
    _insert_trade(conn, id="t1", notes="screenshots: yes")
    _insert_trade(conn, id="t2", notes="forgot to screenshot")
    _insert_trade(conn, id="t3", notes=None)
    conn.close()

    q = TodayTradesQuery(db)
    trades = q.trades_for_date("2026-05-04")
    audit = q.audit_summary(trades)
    assert audit["screenshots_complete"] == 1


def test_handles_missing_db_gracefully(tmp_path):
    """If journal.db doesn't exist, return empty list (not a crash)."""
    q = TodayTradesQuery(tmp_path / "nonexistent.db")
    trades = q.trades_for_date("2026-05-04")
    assert trades == []
    audit = q.audit_summary(trades)
    assert audit["count"] == 0
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_trades_query.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `trades_query.py`**

```python
"""TodayTradesQuery — query journal DB for today's trades + run §6 / §9 audit."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


# R unit per Contract.md §1.
_R_UNIT_USD = 50.0


class TodayTradesQuery:
    """Read-only access to journal.db for EOD report."""

    def __init__(self, journal_db_path: Path) -> None:
        self._db_path = Path(journal_db_path)

    def trades_for_date(
        self, date_et: str, mode: str = "real"
    ) -> list[dict[str, Any]]:
        """Return list of trade dicts for the given ET date + mode.

        Returns dicts (not Pydantic models) to keep this query layer
        decoupled from the journal model — EOD only needs read-only views.
        """
        if not self._db_path.exists():
            return []

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM trades WHERE date = ? AND mode = ? ORDER BY entry_time ASC",
                (date_et, mode),
            )
            rows = [dict(r) for r in cur]
            conn.close()
            return rows
        except sqlite3.Error:
            return []

    @staticmethod
    def audit_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate audit summary for the trade list.

        Returns:
          - count: int
          - daily_r: float (sum of pnl_usd / R_UNIT)
          - violations_total: int (sum of len(violations) per trade)
          - screenshots_complete: int (count of trades with 'screenshots: yes' in notes)
          - per_trade_violations: dict[trade_id, list[str]]
        """
        if not trades:
            return {
                "count": 0,
                "daily_r": 0.0,
                "violations_total": 0,
                "screenshots_complete": 0,
                "per_trade_violations": {},
            }

        total_pnl = 0.0
        violations_total = 0
        screenshots_complete = 0
        per_trade_violations: dict[str, list[str]] = {}

        for t in trades:
            pnl = t.get("pnl_usd") or 0.0
            total_pnl += float(pnl)

            raw_violations = t.get("violations") or "[]"
            try:
                violation_list = json.loads(raw_violations)
                if not isinstance(violation_list, list):
                    violation_list = []
            except (json.JSONDecodeError, TypeError):
                violation_list = []
            violations_total += len(violation_list)
            per_trade_violations[t["id"]] = violation_list

            notes = (t.get("notes") or "").lower()
            if "screenshots: yes" in notes:
                screenshots_complete += 1

        return {
            "count": len(trades),
            "daily_r": total_pnl / _R_UNIT_USD,
            "violations_total": violations_total,
            "screenshots_complete": screenshots_complete,
            "per_trade_violations": per_trade_violations,
        }
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_trades_query.py -v`
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/eod/trades_query.py tests/reports/eod/test_trades_query.py
git commit -m "feat(eod): TodayTradesQuery + §6/§9 audit summary"
```

---

## Task 5: TradeSimulator

**Files:**
- Create: `src/daytrader/reports/eod/trade_simulator.py`
- Create: `tests/reports/eod/test_trade_simulator.py`

This is the algorithmic heart. The simulator takes one `PlanLevel` and the day's intraday bars, detects first touch, then walks forward to determine whether the simulated stop or target would have been hit first (with MFE/MAE for diagnostics).

**Simulator R definition (v1)**: Use the literal setup yaml geometry — `R_distance = sim_stop − sim_entry`. For POINT levels with entry at level price, R_distance = stop_offset_ticks × tick_size (small, ~0.5pt MES). For ZONE levels with entry at near edge, R_distance is roughly the zone width + offset (larger, ~5–15pt). The retrospective output shows entry/stop/target as actual prices so the user can sanity-check the geometry. v2 may add an `account_r` mode that overrides R_distance to a fixed account-level R.

- [ ] **Step 1: Write failing tests**

Create `tests/reports/eod/test_trade_simulator.py`:

```python
"""Unit tests for simulate_level."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from daytrader.reports.eod.plan_dataclasses import PlanLevel
from daytrader.reports.eod.trade_simulator import simulate_level


@dataclass
class _FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


def _bar(t: str, o: float, h: float, l: float, c: float) -> _FakeBar:
    """Helper: t='HH:MM' → bar at 2026-05-04 HH:MM PT."""
    hh, mm = t.split(":")
    ts = datetime(2026, 5, 4, int(hh), int(mm), tzinfo=timezone.utc)
    return _FakeBar(timestamp=ts, open=o, high=h, low=l, close=c)


def test_short_fade_point_target_hit():
    """short_fade POINT at 7272.75:
    - entry @ 7272.75 (level)
    - stop @ 7273.25 (level + 2 ticks × 0.25 = +0.5pt)
    - R_distance = 0.5pt
    - target @ 7272.75 - 2 × 0.5 = 7271.75
    """
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:30", 7250.0, 7255.0, 7248.0, 7252.0),
        _bar("06:53", 7269.0, 7273.50, 7268.0, 7270.0),  # touch (high >= 7272.75)
        _bar("07:00", 7270.0, 7271.0, 7270.5, 7270.5),    # low=7270.5 < 7271.75 target
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.triggered is True
    assert out.outcome == "target"
    assert out.sim_r == pytest.approx(2.0)
    assert out.sim_entry == pytest.approx(7272.75)
    assert out.sim_stop == pytest.approx(7273.25)
    assert out.sim_target == pytest.approx(7271.75)


def test_short_fade_point_stop_hit():
    """short_fade where price gaps up through stop after touch."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.50, 7270.0, 7273.0),   # touch entry
        _bar("06:54", 7273.0, 7275.0, 7273.0, 7274.5),    # high=7275 >= 7273.25 stop
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.outcome == "stop"
    assert out.sim_r == pytest.approx(-1.0)


def test_long_fade_point_target_hit():
    """long_fade POINT at 7240.75:
    - entry @ 7240.75
    - stop @ 7240.25 (level - 2 ticks × 0.25)
    - target @ 7240.75 + 2 × 0.5 = 7241.75
    """
    level = PlanLevel(
        price=7240.75, level_type="POINT", source="D low", direction="long_fade"
    )
    bars = [
        _bar("11:30", 7242.0, 7242.0, 7240.0, 7240.5),    # low=7240 <= 7240.75 → touch
        _bar("11:35", 7240.5, 7242.0, 7240.5, 7241.5),    # high=7242 >= 7241.75 target
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.outcome == "target"
    assert out.sim_r == pytest.approx(2.0)


def test_zone_fade_uses_far_edge_for_stop():
    """ZONE short_fade at 7271-7279.5: entry @ near-edge (7271 for short),
    stop = far_edge + offset = 7279.5 + 0.5 = 7280, target = entry - 2 × R_distance."""
    level = PlanLevel(
        price=7275.0,
        level_type="ZONE",
        source="4H R zone",
        direction="short_fade",
        zone_low=7271.0,
        zone_high=7279.5,
    )
    bars = [
        _bar("07:00", 7268.0, 7275.0, 7268.0, 7272.0),    # high>=7271 (near edge for short fade)
        _bar("07:05", 7272.0, 7272.0, 7253.0, 7254.0),    # large drop
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.triggered is True
    # entry = 7271 (near-edge for short fade), stop = 7280, R_distance = 9.0pt
    # target = 7271 - 2*9 = 7253 → hit at 07:05 (low=7253)
    assert out.sim_entry == pytest.approx(7271.0)
    assert out.sim_stop == pytest.approx(7280.0)
    assert out.sim_target == pytest.approx(7253.0)
    assert out.outcome == "target"


def test_untriggered_when_price_never_touches_level():
    level = PlanLevel(
        price=7400.0, level_type="POINT", source="far high", direction="short_fade"
    )
    bars = [
        _bar("06:30", 7250.0, 7260.0, 7248.0, 7255.0),
        _bar("12:00", 7250.0, 7270.0, 7240.0, 7260.0),
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.triggered is False
    assert out.outcome == "untriggered"
    assert out.sim_r == 0.0


def test_open_at_session_end():
    """Triggered but neither stop nor target hit — sim_r is partial."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.0, 7269.0, 7272.0),    # touch
        _bar("13:00", 7272.0, 7272.5, 7272.0, 7272.0),    # neither stop nor target
    ]
    out = simulate_level(level, bars, None, tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0)
    assert out.outcome == "open"
    # sim_r should be partial — based on (entry - close) / R_distance
    # entry=7272.75, last close=7272.0, r_distance=0.5 → sim_r = 1.5R favorable
    assert -1.0 < out.sim_r < 2.0


def test_target_capped_by_next_key_level_short():
    """short_fade with next_key_level closer than 2R — target = next_key_level."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.0, 7269.0, 7272.0),    # touch
        _bar("07:00", 7272.0, 7272.0, 7271.9, 7271.95),
    ]
    # 2R target = 7271.75; next_key_level = 7272.00 (closer to entry, more conservative)
    # target = max(7271.75, 7272.00) for short = 7272.00 (less aggressive)
    out = simulate_level(
        level, bars, next_key_level=7272.0,
        tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0,
    )
    assert out.sim_target == pytest.approx(7272.0)


def test_mfe_mae_computed():
    """MFE and MAE in R units track favorable/adverse excursion during open trade."""
    level = PlanLevel(
        price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"
    )
    bars = [
        _bar("06:53", 7270.0, 7273.0, 7269.0, 7272.0),    # touch + favorable down to 7269
        _bar("07:00", 7272.0, 7272.5, 7271.9, 7272.0),    # mfe to 7271.9
    ]
    out = simulate_level(
        level, bars, next_key_level=None,
        tick_size=0.25, stop_offset_ticks=2, target_r_multiple=2.0,
    )
    # entry=7272.75, R=0.5
    # mfe = (7272.75 - 7269.0) / 0.5 = 7.5R (favorable)
    # mae = (7272.75 - 7273.0) / 0.5 = -0.5R (adverse, brief touch above)
    assert out.mfe_r is not None and out.mfe_r > 0
    assert out.mae_r is not None and out.mae_r <= 0
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_trade_simulator.py -v`
Expected: FAIL — `simulate_level` not defined.

- [ ] **Step 3: Implement `trade_simulator.py`**

```python
"""TradeSimulator — per (PlanLevel, intraday_bars) → SimOutcome.

Algorithm:
  1. Detect first-touch bar (level price within bar's high/low range)
  2. Compute sim entry / stop / target from the level using literal setup yaml
     geometry (entry at level for POINT, near-edge for ZONE)
  3. Walk forward from touch bar; determine whether stop or target is hit first
  4. If neither, mark "open" and compute partial sim_r from last-bar close
  5. Track MFE / MAE in R units for diagnostics
"""

from __future__ import annotations

from typing import Any

from daytrader.reports.eod.plan_dataclasses import PlanLevel, SimOutcome


def simulate_level(
    level: PlanLevel,
    intraday_bars: list[Any],          # OHLCV-like; needs .high / .low / .close / .timestamp
    next_key_level: float | None,
    tick_size: float = 0.25,
    stop_offset_ticks: int = 2,
    target_r_multiple: float = 2.0,
) -> SimOutcome:
    """Simulate one level against today's intraday bars.

    `next_key_level` if provided caps the target — for short_fade target = max
    (more conservative) of (2R target, next_key_level); for long_fade target =
    min of the two.
    """
    if not intraday_bars:
        return SimOutcome.untriggered()

    # Step 1: detect first-touch bar
    touch_idx = _find_first_touch(level, intraday_bars)
    if touch_idx is None:
        return SimOutcome.untriggered()
    touch_bar = intraday_bars[touch_idx]

    # Step 2: compute entry / stop / target
    sim_entry = _entry_for_direction(level)
    sim_stop = _stop_for_level(level, sim_entry, tick_size, stop_offset_ticks)
    r_distance = abs(sim_stop - sim_entry)
    sim_target = _target_for_direction(
        level, sim_entry, r_distance, target_r_multiple, next_key_level
    )

    # Step 3: walk forward to determine outcome (stop / target / open)
    mfe_r = 0.0  # max favorable excursion in R units
    mae_r = 0.0  # max adverse excursion (negative)

    for bar in intraday_bars[touch_idx:]:
        if level.direction == "short_fade":
            # Adverse = price up; favorable = price down
            adverse = (bar.high - sim_entry) / r_distance if r_distance else 0.0
            favorable = (sim_entry - bar.low) / r_distance if r_distance else 0.0
            mfe_r = max(mfe_r, favorable)
            mae_r = min(mae_r, -adverse)
            if bar.high >= sim_stop:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "stop", -1.0, mfe_r, mae_r)
            if bar.low <= sim_target:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "target", target_r_multiple, mfe_r, mae_r)
        else:  # long_fade
            adverse = (sim_entry - bar.low) / r_distance if r_distance else 0.0
            favorable = (bar.high - sim_entry) / r_distance if r_distance else 0.0
            mfe_r = max(mfe_r, favorable)
            mae_r = min(mae_r, -adverse)
            if bar.low <= sim_stop:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "stop", -1.0, mfe_r, mae_r)
            if bar.high >= sim_target:
                return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "target", target_r_multiple, mfe_r, mae_r)

    # Step 4: open at session end — partial sim_r based on last close
    last_close = intraday_bars[-1].close
    if level.direction == "short_fade":
        partial_r = (sim_entry - last_close) / r_distance if r_distance else 0.0
    else:
        partial_r = (last_close - sim_entry) / r_distance if r_distance else 0.0
    return _outcome(touch_bar, sim_entry, sim_stop, sim_target, "open", partial_r, mfe_r, mae_r)


# --- helpers ---


def _find_first_touch(level: PlanLevel, bars: list[Any]) -> int | None:
    """Return index of first bar that touches the level (within bar's H/L range)."""
    if level.level_type == "POINT":
        target_price = level.price
        for i, bar in enumerate(bars):
            if level.direction == "short_fade":
                # short fade: price rises into level → high reaches level
                if bar.high >= target_price:
                    return i
            else:
                # long fade: price drops into level → low reaches level
                if bar.low <= target_price:
                    return i
        return None
    else:  # ZONE
        if level.direction == "short_fade":
            # short fade entry @ near-edge (lower edge of zone for short)
            target_price = level.zone_low if level.zone_low is not None else level.price
            for i, bar in enumerate(bars):
                if bar.high >= target_price:
                    return i
        else:
            # long fade entry @ near-edge (upper edge of zone for long)
            target_price = level.zone_high if level.zone_high is not None else level.price
            for i, bar in enumerate(bars):
                if bar.low <= target_price:
                    return i
        return None


def _entry_for_direction(level: PlanLevel) -> float:
    """Entry price assumption.

    POINT: at level.price (limit order at level).
    ZONE short_fade: at zone_low (near edge).
    ZONE long_fade: at zone_high (near edge).
    """
    if level.level_type == "POINT":
        return level.price
    if level.direction == "short_fade":
        return level.zone_low if level.zone_low is not None else level.price
    return level.zone_high if level.zone_high is not None else level.price


def _stop_for_level(
    level: PlanLevel,
    sim_entry: float,
    tick_size: float,
    stop_offset_ticks: int,
) -> float:
    """Stop placement per setup yaml.

    POINT: opposite_side_of_level + 2 ticks → for short_fade: level + offset.
    ZONE: opposite_side_of_zone (far edge) + 2 ticks.
    """
    offset = stop_offset_ticks * tick_size
    if level.level_type == "POINT":
        return level.price + offset if level.direction == "short_fade" else level.price - offset
    # ZONE
    if level.direction == "short_fade":
        far_edge = level.zone_high if level.zone_high is not None else level.price
        return far_edge + offset
    far_edge = level.zone_low if level.zone_low is not None else level.price
    return far_edge - offset


def _target_for_direction(
    level: PlanLevel,
    sim_entry: float,
    r_distance: float,
    target_r_multiple: float,
    next_key_level: float | None,
) -> float:
    """Target = entry +/- target_r_multiple * R_distance, capped by next_key_level
    (more conservative side)."""
    if level.direction == "short_fade":
        target_2r = sim_entry - target_r_multiple * r_distance
        if next_key_level is not None:
            return max(target_2r, next_key_level)  # closer to entry = more conservative for short
        return target_2r
    target_2r = sim_entry + target_r_multiple * r_distance
    if next_key_level is not None:
        return min(target_2r, next_key_level)  # closer to entry = more conservative for long
    return target_2r


def _outcome(
    touch_bar: Any,
    sim_entry: float,
    sim_stop: float,
    sim_target: float,
    outcome: str,
    sim_r: float,
    mfe_r: float,
    mae_r: float,
) -> SimOutcome:
    """Build SimOutcome with formatted touch time."""
    touch_time_pt = touch_bar.timestamp.strftime("%H:%M") if hasattr(touch_bar, "timestamp") else None
    return SimOutcome(
        triggered=True,
        touch_time_pt=touch_time_pt,
        touch_bar_high=touch_bar.high,
        touch_bar_low=touch_bar.low,
        sim_entry=sim_entry,
        sim_stop=sim_stop,
        sim_target=sim_target,
        outcome=outcome,  # type: ignore[arg-type]
        sim_r=sim_r,
        mfe_r=mfe_r if mfe_r != 0 else None,
        mae_r=mae_r if mae_r != 0 else None,
    )
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_trade_simulator.py -v`
Expected: 8 tests pass.

If any test fails because of touch-detection or target-cap math edge cases, debug carefully — these are the simulator's load-bearing logic.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/eod/trade_simulator.py tests/reports/eod/test_trade_simulator.py
git commit -m "feat(eod): TradeSimulator — first-touch + walk-forward stop/target/open + MFE/MAE"
```

---

## Task 6: PlanRetrospective + state DB schema

**Files:**
- Create: `src/daytrader/reports/eod/retrospective.py`
- Create: `tests/reports/eod/test_retrospective.py`
- Modify: `src/daytrader/core/state.py` (add `plan_retrospective_daily` table)

- [ ] **Step 1: Add `plan_retrospective_daily` table to state.py**

In `src/daytrader/core/state.py`, find the `initialize()` method that creates the `reports` table. Add this CREATE TABLE statement after the existing tables:

```python
# Plan Retrospective daily archive (Phase 5)
self._conn.execute(
    """CREATE TABLE IF NOT EXISTS plan_retrospective_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        symbol TEXT NOT NULL,
        total_levels INTEGER NOT NULL,
        triggered_count INTEGER NOT NULL,
        sim_total_r REAL NOT NULL,
        actual_total_r REAL NOT NULL,
        gap_r REAL NOT NULL,
        retrospective_json TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(date, symbol)
    )"""
)
```

The `UNIQUE(date, symbol)` constraint prevents double-inserts if EOD re-runs the same day.

- [ ] **Step 2: Write failing tests**

Create `tests/reports/eod/test_retrospective.py`:

```python
"""Unit tests for PlanRetrospective composition + persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from daytrader.reports.eod.plan_dataclasses import PlanLevel, SimOutcome
from daytrader.reports.eod.retrospective import PlanRetrospective


@dataclass
class _FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


def _init_state_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE plan_retrospective_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            total_levels INTEGER NOT NULL,
            triggered_count INTEGER NOT NULL,
            sim_total_r REAL NOT NULL,
            actual_total_r REAL NOT NULL,
            gap_r REAL NOT NULL,
            retrospective_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(date, symbol)
        )"""
    )
    conn.commit()
    conn.close()


def test_compose_and_persist_writes_one_row_per_symbol(tmp_path):
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)

    fake_parser = MagicMock()
    fake_parser.parse.return_value = MagicMock(
        symbol="MES",
        levels=[
            PlanLevel(price=7272.75, level_type="POINT", source="4H POC", direction="short_fade"),
        ],
        raw_block_md="...",
        parse_warnings=[],
    )

    fake_simulator = MagicMock()
    fake_simulator.return_value = SimOutcome(
        triggered=True, touch_time_pt="06:53",
        touch_bar_high=7273.5, touch_bar_low=7268.0,
        sim_entry=7272.75, sim_stop=7273.25, sim_target=7271.75,
        outcome="target", sim_r=2.0, mfe_r=2.0, mae_r=-0.4,
    )

    fake_bars = [
        _FakeBar(datetime(2026, 5, 4, 6, 53, tzinfo=timezone.utc), 7269, 7273.5, 7268, 7270),
    ]
    fake_bar_fetcher = MagicMock(return_value=fake_bars)

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {"daily_r": 0.0}

    retrospective = PlanRetrospective(
        plan_parser=fake_parser,
        trade_simulator=fake_simulator,
        intraday_bar_fetcher=fake_bar_fetcher,
        trades_query=fake_trades_query,
        state_db_path=db_path,
    )

    rows = retrospective.compose(
        plans={"MES": "raw block content"},
        symbols=["MES"],
        date_et="2026-05-04",
        tick_sizes={"MES": 0.25},
    )
    retrospective.persist(rows)

    # Verify row written to DB
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT date, symbol, total_levels, triggered_count, sim_total_r FROM plan_retrospective_daily")
    row = cur.fetchone()
    assert row is not None
    assert row == ("2026-05-04", "MES", 1, 1, 2.0)
    conn.close()


def test_aggregate_stats_match_outcomes(tmp_path):
    """gap_r = sim_total_r - actual_total_r."""
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)

    fake_parser = MagicMock()
    fake_parser.parse.return_value = MagicMock(
        symbol="MES",
        levels=[
            PlanLevel(price=7272.75, level_type="POINT", source="P1", direction="short_fade"),
            PlanLevel(price=7240.75, level_type="POINT", source="P2", direction="long_fade"),
        ],
        raw_block_md="", parse_warnings=[],
    )

    fake_simulator = MagicMock()
    fake_simulator.side_effect = [
        SimOutcome(True, "06:53", 7273, 7268, 7272.75, 7273.25, 7271.75, "target", 2.0, 2.0, -0.4),
        SimOutcome(True, "11:30", 7242, 7240, 7240.75, 7240.25, 7241.75, "stop", -1.0, 0.5, -1.0),
    ]
    fake_bar_fetcher = MagicMock(return_value=[])

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {"daily_r": 0.0}

    retrospective = PlanRetrospective(
        plan_parser=fake_parser, trade_simulator=fake_simulator,
        intraday_bar_fetcher=fake_bar_fetcher, trades_query=fake_trades_query,
        state_db_path=db_path,
    )
    rows = retrospective.compose(
        plans={"MES": "raw"},
        symbols=["MES"],
        date_et="2026-05-04",
        tick_sizes={"MES": 0.25},
    )
    row = rows["MES"]
    assert row.total_levels == 2
    assert row.triggered_count == 2
    assert row.sim_total_r == pytest.approx(2.0 + (-1.0))  # +1R net
    assert row.actual_total_r == 0.0
    assert row.gap_r == pytest.approx(1.0)


def test_no_plan_returns_empty_retrospective(tmp_path):
    """If plans dict is empty (premarket file missing), no rows."""
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)
    retrospective = PlanRetrospective(
        plan_parser=MagicMock(), trade_simulator=MagicMock(),
        intraday_bar_fetcher=MagicMock(), trades_query=MagicMock(),
        state_db_path=db_path,
    )
    rows = retrospective.compose(plans={}, symbols=["MES"], date_et="2026-05-04", tick_sizes={"MES": 0.25})
    assert rows == {}


def test_persist_idempotent_for_same_date_symbol(tmp_path):
    """If retrospective for (date, symbol) already exists, replace not duplicate."""
    db_path = tmp_path / "state.db"
    _init_state_db(db_path)

    retrospective = PlanRetrospective(
        plan_parser=MagicMock(), trade_simulator=MagicMock(),
        intraday_bar_fetcher=MagicMock(), trades_query=MagicMock(),
        state_db_path=db_path,
    )
    from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
    row = RetrospectiveRow(
        symbol="MES", date_et="2026-05-04", total_levels=1, triggered_count=0,
        sim_total_r=0.0, actual_total_r=0.0, gap_r=0.0, per_level_outcomes=[],
    )
    retrospective.persist({"MES": row})
    retrospective.persist({"MES": row})  # second call

    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT COUNT(*) FROM plan_retrospective_daily WHERE date='2026-05-04' AND symbol='MES'")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 1  # not 2
```

- [ ] **Step 3: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_retrospective.py -v`
Expected: FAIL — `PlanRetrospective` not defined.

- [ ] **Step 4: Implement `retrospective.py`**

```python
"""PlanRetrospective — compose Plan + simulator outcomes + actual trades into
per-symbol RetrospectiveRow; persist to state.db's plan_retrospective_daily table."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from daytrader.reports.eod.plan_dataclasses import (
    Plan,
    PlanLevel,
    RetrospectiveRow,
    SimOutcome,
)


class PlanRetrospective:
    """Orchestrate plan parsing → simulation → audit → persist."""

    def __init__(
        self,
        plan_parser: Any,                    # has .parse(raw_md, symbol) -> Plan
        trade_simulator: Callable,           # simulate_level signature
        intraday_bar_fetcher: Callable,      # (symbol, date_et) -> list[OHLCV]
        trades_query: Any,                   # has .trades_for_date / .audit_summary
        state_db_path: Path,
    ) -> None:
        self._plan_parser = plan_parser
        self._simulate = trade_simulator
        self._fetch_bars = intraday_bar_fetcher
        self._trades_query = trades_query
        self._db_path = Path(state_db_path)

    def compose(
        self,
        plans: dict[str, str],         # raw markdown blocks per symbol from PremarketPlanReader
        symbols: list[str],
        date_et: str,
        tick_sizes: dict[str, float],
    ) -> dict[str, RetrospectiveRow]:
        """Return {symbol: RetrospectiveRow} for each symbol whose plan was found."""
        if not plans:
            return {}

        # Today's actual trades for the actual_total_r computation
        actual_trades = self._trades_query.trades_for_date(date_et)
        actual_audit = self._trades_query.audit_summary(actual_trades)

        out: dict[str, RetrospectiveRow] = {}
        for symbol in symbols:
            raw_md = plans.get(symbol)
            if not raw_md:
                continue
            plan: Plan = self._plan_parser.parse(raw_md, symbol)
            if not plan.levels:
                continue

            intraday_bars = self._fetch_bars(symbol, date_et)
            tick_size = tick_sizes.get(symbol, 0.25)

            outcomes: list[tuple[PlanLevel, SimOutcome]] = []
            sim_total = 0.0
            triggered = 0
            for i, level in enumerate(plan.levels):
                # Find next key level for target cap (next level in same direction, sorted by price proximity)
                next_kl = self._find_next_key_level(level, plan.levels, exclude_idx=i)
                outcome = self._simulate(
                    level, intraday_bars, next_kl,
                    tick_size, plan.stop_offset_ticks, plan.target_r_multiple,
                )
                outcomes.append((level, outcome))
                sim_total += outcome.sim_r
                if outcome.triggered:
                    triggered += 1

            # Actual R for this symbol from journal
            symbol_actual_r = sum(
                (float(t.get("pnl_usd", 0) or 0) / 50.0)
                for t in actual_trades
                if t.get("symbol") == symbol
            )

            out[symbol] = RetrospectiveRow(
                symbol=symbol,
                date_et=date_et,
                total_levels=len(plan.levels),
                triggered_count=triggered,
                sim_total_r=sim_total,
                actual_total_r=symbol_actual_r,
                gap_r=sim_total - symbol_actual_r,
                per_level_outcomes=outcomes,
            )

        return out

    def persist(self, rows: dict[str, RetrospectiveRow]) -> None:
        """Insert / replace rows in plan_retrospective_daily table."""
        if not rows:
            return
        if not self._db_path.exists():
            return
        conn = sqlite3.connect(self._db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            for symbol, row in rows.items():
                # Serialize per-level outcomes for the json column
                serialized = json.dumps([
                    {
                        "level_price": pl.price,
                        "level_type": pl.level_type,
                        "source": pl.source,
                        "direction": pl.direction,
                        "outcome": so.outcome,
                        "sim_r": so.sim_r,
                        "touch_time_pt": so.touch_time_pt,
                    }
                    for pl, so in row.per_level_outcomes
                ])
                conn.execute(
                    """INSERT INTO plan_retrospective_daily
                       (date, symbol, total_levels, triggered_count,
                        sim_total_r, actual_total_r, gap_r,
                        retrospective_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(date, symbol) DO UPDATE SET
                         total_levels=excluded.total_levels,
                         triggered_count=excluded.triggered_count,
                         sim_total_r=excluded.sim_total_r,
                         actual_total_r=excluded.actual_total_r,
                         gap_r=excluded.gap_r,
                         retrospective_json=excluded.retrospective_json,
                         created_at=excluded.created_at""",
                    (
                        row.date_et, row.symbol,
                        row.total_levels, row.triggered_count,
                        row.sim_total_r, row.actual_total_r, row.gap_r,
                        serialized, now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _find_next_key_level(
        level: PlanLevel,
        all_levels: list[PlanLevel],
        exclude_idx: int,
    ) -> float | None:
        """Find the closest key level in the same direction beyond entry.

        For short_fade: next level BELOW entry (closer profit cap).
        For long_fade: next level ABOVE entry.
        """
        candidates: list[float] = []
        for i, other in enumerate(all_levels):
            if i == exclude_idx:
                continue
            if other.direction != level.direction:
                continue
            if level.direction == "short_fade" and other.price < level.price:
                candidates.append(other.price)
            elif level.direction == "long_fade" and other.price > level.price:
                candidates.append(other.price)
        if not candidates:
            return None
        # Return the closest one in the profit direction
        if level.direction == "short_fade":
            return max(candidates)  # highest of below-entry levels = closest to entry
        return min(candidates)
```

- [ ] **Step 5: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_retrospective.py -v`
Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/reports/eod/retrospective.py tests/reports/eod/test_retrospective.py src/daytrader/core/state.py
git commit -m "feat(eod): PlanRetrospective composition + persist to plan_retrospective_daily"
```

---

## Task 7: TomorrowPreliminaryPlan

**Files:**
- Create: `src/daytrader/reports/eod/tomorrow_plan.py`
- Create: `tests/reports/eod/test_tomorrow_plan.py`

This module composes input data for the AI to render the "📅 Tomorrow Preliminary Plan" section. It does NOT do any AI work itself — it produces structured markdown that the AI uses as input grounding.

- [ ] **Step 1: Write failing tests**

Create `tests/reports/eod/test_tomorrow_plan.py`:

```python
"""Unit tests for TomorrowPreliminaryPlan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
from daytrader.reports.eod.tomorrow_plan import TomorrowPreliminaryPlan


@dataclass
class _FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


def test_renders_today_levels_per_symbol():
    today_bars = {
        "MES": {
            "1D": [_FakeBar(datetime(2026, 5, 4), 7250, 7280, 7240, 7260)],
        },
        "MGC": {
            "1D": [_FakeBar(datetime(2026, 5, 4), 4530, 4550, 4515, 4535)],
        },
    }
    today_retros = {}  # empty for this test
    sentiment_md = "## D. 情绪面\n+1 / 10\n"

    planner = TomorrowPreliminaryPlan()
    md = planner.build_input_data(today_bars, today_retros, sentiment_md)

    # Should mention each symbol's today H/L/C
    assert "MES" in md
    assert "7280" in md   # today high
    assert "7240" in md   # today low
    assert "MGC" in md
    assert "4550" in md


def test_includes_retrospective_insight_when_available():
    today_bars = {"MES": {"1D": [_FakeBar(datetime(2026, 5, 4), 7250, 7280, 7240, 7260)]}}
    today_retros = {
        "MES": RetrospectiveRow(
            symbol="MES", date_et="2026-05-04",
            total_levels=4, triggered_count=2,
            sim_total_r=3.5, actual_total_r=0.0, gap_r=3.5,
            per_level_outcomes=[],
        )
    }
    planner = TomorrowPreliminaryPlan()
    md = planner.build_input_data(today_bars, today_retros, "")

    # Should reference today's plan accuracy
    assert "2/4" in md or "50" in md or "trigger" in md.lower()
    assert "3.5" in md or "+3" in md  # sim total R


def test_empty_inputs_produce_minimal_output():
    """Defensive: empty bars and empty retrospective shouldn't crash."""
    planner = TomorrowPreliminaryPlan()
    md = planner.build_input_data({}, {}, "")
    # Should produce at least a header / placeholder, not crash
    assert isinstance(md, str)
    assert len(md) > 0  # some minimal markdown
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_tomorrow_plan.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `tomorrow_plan.py`**

```python
"""TomorrowPreliminaryPlan — compose input data for AI's tomorrow section."""

from __future__ import annotations

from typing import Any

from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow


class TomorrowPreliminaryPlan:
    """Build markdown input for the AI's '📅 Tomorrow Preliminary Plan' section.

    The AI prompt template instructs the AI to use this input as ground-truth
    starting data; AI is asked to add econ event context (via web search) and
    render the section. This class does NOT call AI — it just assembles
    structured input data.
    """

    def build_input_data(
        self,
        today_bars: dict[str, dict[str, list[Any]]],   # per symbol per TF
        today_retrospective: dict[str, RetrospectiveRow],
        sentiment_md: str,
    ) -> str:
        """Compose markdown that the AI will use to render tomorrow's preliminary plan.

        Sections:
        - Per-symbol today's H/L/C (from 1D bars)
        - Retrospective insight per symbol (if available)
        - Sentiment shift indicator
        """
        lines: list[str] = []
        lines.append("### Today's H / L / C per symbol (for tomorrow level carryover)")
        if not today_bars:
            lines.append("- (no bars data available)")
        else:
            for symbol, by_tf in today_bars.items():
                d_bars = by_tf.get("1D") or []
                if not d_bars:
                    lines.append(f"- {symbol}: no daily bar")
                    continue
                last = d_bars[-1]
                lines.append(
                    f"- **{symbol}**: today H={last.high:.2f} / L={last.low:.2f} / "
                    f"C={last.close:.2f}"
                )

        lines.append("")
        lines.append("### Today's retrospective insight (per symbol)")
        if not today_retrospective:
            lines.append("- (no retrospective; today's premarket plan was unavailable)")
        else:
            for symbol, row in today_retrospective.items():
                trigger_pct = (
                    100.0 * row.triggered_count / row.total_levels
                    if row.total_levels else 0
                )
                lines.append(
                    f"- **{symbol}**: {row.triggered_count}/{row.total_levels} "
                    f"levels triggered ({trigger_pct:.0f}%); "
                    f"sim total {row.sim_total_r:+.1f}R, actual {row.actual_total_r:+.1f}R, "
                    f"gap {row.gap_r:+.1f}R"
                )

        lines.append("")
        lines.append("### Today's sentiment (carryover for tomorrow opening hypothesis)")
        if sentiment_md.strip():
            # Take just the macro line if present
            for line in sentiment_md.splitlines():
                if "Macro" in line or "总体" in line or "+/-" in line:
                    lines.append(f"- {line.strip()}")
                    break
            else:
                lines.append("- (sentiment available but not summarizable inline)")
        else:
            lines.append("- (no sentiment data)")

        lines.append("")
        lines.append("### Tomorrow econ events (AI: use web search to verify dates+times)")
        lines.append("- (AI fills in via web search)")

        return "\n".join(lines)
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_tomorrow_plan.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/eod/tomorrow_plan.py tests/reports/eod/test_tomorrow_plan.py
git commit -m "feat(eod): TomorrowPreliminaryPlan input composition"
```

---

## Task 8: EOD prompt template + PromptBuilder.build_eod + OutputValidator

**Files:**
- Create: `src/daytrader/reports/templates/eod.md`
- Modify: `src/daytrader/reports/core/prompt_builder.py` (add `build_eod`)
- Modify: `src/daytrader/reports/core/output_validator.py` (add `REQUIRED_SECTIONS["eod"]`)
- Modify: `tests/reports/test_prompt_builder.py` (add EOD tests)
- Modify: `tests/reports/test_output_validator.py` (add EOD tests)

- [ ] **Step 1: Create `src/daytrader/reports/templates/eod.md`**

```markdown
# EOD Daily Report Template

You are generating an end-of-day report. Today's market session has closed (RTH cash close at 13:00 PT for ES/NQ; futures globex still active).

## Required Sections (output MUST contain ALL of these in this order)

1. **🔒 Lock-in Metadata**: today's trades count update, daily R, week R, cool-off entering tomorrow
2. **📊 MES — Multi-TF (W / D / 4H)**: today's close updates per TF
3. **📊 MNQ — Multi-TF** (context only)
4. **📊 MGC — Multi-TF**
5. **🌐 Cross-Asset Narrative** (today past-tense; NO predictions)
6. **📰 Breaking News (today)** (web search if D. Sentiment block doesn't already cover it)
7. **F. 期货结构 / Futures Positioning** (post-cash-close basis + term + RTH-formed VP — embed verbatim from input)
8. **D. 情绪面 / Sentiment Index** (embed verbatim from sentiment_md input)
9. **今日交易档案 / Today's Trade Archive** (trade ledger table + §6 / §9 audit; if 0 trades, render "今天没交易. 原因: [analysis]")
10. **🔄 Plan Retrospective / 计划复盘** (per-level table per symbol + plan accuracy summary + iteration insight; embed verbatim from retrospective_md input)
11. **C. 计划复核 / Plan Adherence Assessment**: VERBATIM quote of today's premarket C-MES / C-MGC blocks (embed from today_plan_blocks input), then plan-vs-actual comparison
12. **B. 市场叙事 / Today's Narrative** (past-tense; FORBIDDEN: forward-looking predictions — that's premarket's job)
13. **📅 Tomorrow Preliminary Plan** (use tomorrow_preliminary_md input; mark "preliminary — premarket 06:00 PT will finalize")
14. **📑 数据快照 / Data Snapshot** (key numbers in compact table)

## CRITICAL Output Constraints

- **NO A. section** (decision aid is forbidden in EOD per spec §6).
- **B is past-tense**: describe what happened, NOT what will happen.
- **C must verbatim-quote today's premarket plan** before adding adherence commentary.
- **🔄 Plan Retrospective and 📅 Tomorrow Preliminary**: embed the input markdown VERBATIM; do NOT re-summarize.
- **Sources**: when web search is used (econ calendar for tomorrow, news verification), cite at least 3 real URLs at the end.

## Output Format Notes

- Use Chinese where input data is Chinese; mixed Chinese/English is acceptable.
- Total length 6.5–9K characters (per spec §2.2).
- No preamble; start directly with the # heading.
```

- [ ] **Step 2: Write failing tests for OutputValidator**

In `tests/reports/test_output_validator.py`, append these tests:

```python
def test_eod_validator_requires_all_sections():
    """An EOD report missing 'Plan Retrospective' or '今日交易档案' should fail validation."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    content = """# EOD Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
## F. 期货结构
## D. 情绪面
## C. 计划复核
## B. 市场叙事
## 数据快照
"""
    result = v.validate(content, "eod")
    assert not result.ok
    # Should call out missing 今日交易档案 + Plan Retrospective + Tomorrow
    missing_concat = " ".join(result.missing).lower()
    assert "交易档案" in " ".join(result.missing) or "trade archive" in missing_concat
    assert "retrospective" in missing_concat or "复盘" in " ".join(result.missing)
    assert "tomorrow" in missing_concat or "明天" in " ".join(result.missing)


def test_eod_validator_accepts_complete_report():
    """A complete EOD with all required sections passes."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    content = """# EOD Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
## F. 期货结构
## D. 情绪面
## 今日交易档案
## 🔄 Plan Retrospective
## C. 计划复核
## B. 市场叙事
## 📅 Tomorrow Preliminary Plan
## 数据快照
"""
    result = v.validate(content, "eod")
    assert result.ok, f"missing: {result.missing}"
```

- [ ] **Step 3: Add `REQUIRED_SECTIONS["eod"]` in output_validator.py**

In `src/daytrader/reports/core/output_validator.py`, find `REQUIRED_SECTIONS["premarket"]` and add an `"eod"` entry below it:

```python
REQUIRED_SECTIONS: dict[str, list[SectionSpec]] = {
    "premarket": [
        # ... existing entries ...
    ],
    "eod": [
        "Lock-in",
        ["MES", "📊 MES"],
        ["MNQ", "📊 MNQ"],
        ["MGC", "📊 MGC"],
        ["F. 期货结构", "F-MES", "Futures Positioning", "期货结构"],
        ["情绪面", "D. 情绪面", "Sentiment Index", "Sentiment"],
        ["今日交易档案", "Trade Archive", "Today's Trade"],
        ["Plan Retrospective", "🔄 Plan", "计划复盘"],
        ["C.", "计划复核", "Plan Adherence"],
        ["B.", "市场叙事", "Narrative"],
        ["Tomorrow Preliminary", "📅 Tomorrow", "明天初步预案", "明天预案"],
        ["数据快照", "Data Snapshot", "Snapshot"],
    ],
}
```

- [ ] **Step 4: Run validator tests**

Run: `uv run pytest tests/reports/test_output_validator.py -v`
Expected: all pass (existing + 2 new EOD tests).

- [ ] **Step 5: Add `build_eod()` to PromptBuilder**

In `src/daytrader/reports/core/prompt_builder.py`, add a new method following the `build_premarket` pattern:

```python
def build_eod(
    self,
    context: ReportContext,
    bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
    tradable_symbols: list[str],
    news_items: list[dict[str, Any]],
    run_timestamp_pt: str,
    run_timestamp_et: str,
    futures_data: "FuturesSection | None" = None,
    sentiment_md: str = "",
    today_plan_blocks: dict[str, str] | None = None,
    retrospective_md: str = "",
    today_trades_md: str = "",
    tomorrow_preliminary_md: str = "",
) -> list[dict[str, Any]]:
    """Build EOD prompt. Section order per spec §6 + brainstorm decisions:
    Lock-in → W/D/4H per symbol → F. → D. 情绪面 → 今日交易档案 →
    🔄 Plan Retrospective → C. 计划复核 → B. 市场叙事 →
    📅 Tomorrow Preliminary → 数据快照. A section explicitly excluded.
    """
    template = load_template("eod")  # loads templates/eod.md

    contract_section = (
        context.contract_text
        if context.contract_text is not None
        else "Contract.md: not yet filled by user"
    )

    futures_block = self._build_futures_section_block(futures_data)
    sentiment_block = sentiment_md.strip() if sentiment_md else ""
    retrospective_block = retrospective_md.strip() if retrospective_md else ""
    trades_block = today_trades_md.strip() if today_trades_md else ""
    tomorrow_block = tomorrow_preliminary_md.strip() if tomorrow_preliminary_md else ""

    # Verbatim plan blocks for C section
    plan_blocks = today_plan_blocks or {}
    plan_section_md = ""
    if plan_blocks:
        plan_section_md = "\n\n".join(
            f"### Today's premarket C-{sym} (verbatim)\n\n{block}"
            for sym, block in plan_blocks.items()
        )

    composed_blocks: list[str] = [futures_block]
    if sentiment_block:
        composed_blocks.append(sentiment_block)
    if trades_block:
        composed_blocks.append(trades_block)
    if retrospective_block:
        composed_blocks.append(retrospective_block)
    if plan_section_md:
        composed_blocks.append(plan_section_md)
    if tomorrow_block:
        composed_blocks.append("## 📅 Tomorrow Preliminary Plan (input grounding)\n\n" + tomorrow_block)
    composed_md = "\n\n".join(composed_blocks)

    # Compose system + user blocks (mirror build_premarket structure)
    system_blocks = [
        {"type": "text", "text": template, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": contract_section, "cache_control": {"type": "ephemeral"}},
    ]

    bars_md = self._format_bars_for_prompt(bars_by_symbol_and_tf, tradable_symbols)

    user_blocks = [
        {
            "type": "text",
            "text": (
                f"# EOD Run Context\n"
                f"Date (ET): {context.date_et}\n"
                f"Run time: {run_timestamp_pt} PT / {run_timestamp_et} ET\n\n"
                f"## Multi-TF bars per symbol\n\n{bars_md}\n\n"
                f"{composed_md}"
            ),
        }
    ]

    return [{"role": "system", "content": system_blocks},
            {"role": "user", "content": user_blocks}]
```

- [ ] **Step 6: Add a test for build_eod in test_prompt_builder.py**

```python
def test_build_eod_includes_all_input_blocks():
    from daytrader.reports.core.prompt_builder import PromptBuilder, ReportContext
    pb = PromptBuilder()
    ctx = ReportContext(date_et="2026-05-04", contract_text="contract content")
    msgs = pb.build_eod(
        context=ctx,
        bars_by_symbol_and_tf={"MES": {}},
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="14:00",
        run_timestamp_et="17:00",
        futures_data=None,
        sentiment_md="## D. 情绪面\n+1 / 10\n",
        today_plan_blocks={"MES": "**Long bias 区**: 7199.25"},
        retrospective_md="## 🔄 Plan Retrospective\n| MES | ... |",
        today_trades_md="## 今日交易档案\n0 trades today",
        tomorrow_preliminary_md="### Today's H/L/C\n- MES H=7280 L=7240 C=7260",
    )
    full_text = " ".join(
        b["text"] for m in msgs for b in m["content"] if isinstance(b, dict) and b.get("type") == "text"
    )
    assert "情绪面" in full_text
    assert "7199.25" in full_text
    assert "Plan Retrospective" in full_text
    assert "今日交易档案" in full_text
    assert "Tomorrow Preliminary" in full_text or "明天初步" in full_text or "7280" in full_text


def test_build_eod_omits_A_section_marker():
    """EOD prompt should NOT instruct AI to produce an A. section."""
    from daytrader.reports.core.prompt_builder import PromptBuilder, ReportContext
    pb = PromptBuilder()
    ctx = ReportContext(date_et="2026-05-04", contract_text="")
    msgs = pb.build_eod(
        context=ctx,
        bars_by_symbol_and_tf={},
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="14:00",
        run_timestamp_et="17:00",
    )
    # Template should mention "NO A. section" / "forbidden"
    template_text = msgs[0]["content"][0]["text"]
    assert "NO A" in template_text or "forbidden" in template_text.lower() or "A 段" in template_text
```

- [ ] **Step 7: Run all updated tests**

Run: `uv run pytest tests/reports/test_prompt_builder.py tests/reports/test_output_validator.py -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/daytrader/reports/templates/eod.md src/daytrader/reports/core/prompt_builder.py src/daytrader/reports/core/output_validator.py tests/reports/test_prompt_builder.py tests/reports/test_output_validator.py
git commit -m "feat(eod): build_eod prompt + REQUIRED_SECTIONS[eod] + template instructions"
```

---

## Task 9: EODGenerator

**Files:**
- Create: `src/daytrader/reports/types/eod.py`
- Create: `tests/reports/eod/test_eod_generator.py`

This is the orchestrator-facing facade for EOD pipeline (mirrors `PremarketGenerator`).

- [ ] **Step 1: Write failing tests**

Create `tests/reports/eod/test_eod_generator.py`:

```python
"""Unit tests for EODGenerator."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.reports.types.eod import EODGenerator
from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow


def test_eod_generator_calls_all_components():
    """EODGenerator.generate() should call: trades query → retrospective → AI."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = []  # all timeframes empty

    fake_ai = MagicMock()
    fake_ai.call.return_value = MagicMock(
        text="# EOD Report\n## Lock-in Metadata\n## 📊 MES\n## 📊 MNQ\n## 📊 MGC\n"
             "## F. 期货结构\n## 情绪面\n## 今日交易档案\n## Plan Retrospective\n"
             "## C. 计划复核\n## B. 市场叙事\n## 📅 Tomorrow Preliminary\n## 数据快照\n",
        input_tokens=0, output_tokens=0,
        cache_creation_tokens=0, cache_read_tokens=0,
    )

    fake_plan_reader = MagicMock()
    fake_plan_reader.read_today_plan.return_value = {"MES": "raw block"}

    fake_plan_parser = MagicMock()
    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {
        "count": 0, "daily_r": 0.0, "violations_total": 0,
        "screenshots_complete": 0, "per_trade_violations": {},
    }

    fake_retrospective = MagicMock()
    fake_retrospective.compose.return_value = {}
    fake_retrospective.persist = MagicMock()

    fake_tomorrow = MagicMock()
    fake_tomorrow.build_input_data.return_value = "tomorrow data"

    gen = EODGenerator(
        ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"], tradable_symbols=["MES", "MGC"],
        plan_reader=fake_plan_reader, plan_parser=fake_plan_parser,
        trades_query=fake_trades_query, retrospective=fake_retrospective,
        tomorrow_planner=fake_tomorrow,
    )

    from daytrader.reports.core.context_loader import ContextData
    ctx = ContextData(
        date_et="2026-05-04",
        contract_text="contract",
        instruments_data={"MES": {"1D": []}},
        news_items=[],
    )
    outcome = gen.generate(
        context=ctx,
        run_timestamp_pt="14:00",
        run_timestamp_et="17:00",
        sentiment_md="",
    )

    assert outcome is not None
    fake_plan_reader.read_today_plan.assert_called_once()
    fake_trades_query.trades_for_date.assert_called_once()
    fake_retrospective.compose.assert_called_once()
    fake_retrospective.persist.assert_called_once()
    fake_tomorrow.build_input_data.assert_called_once()
    fake_ai.call.assert_called_once()


def test_eod_generator_handles_missing_premarket_file_gracefully():
    """If premarket file missing, plan_reader returns {} and pipeline still completes."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = []
    fake_ai = MagicMock()
    fake_ai.call.return_value = MagicMock(
        text="# EOD\n## Lock-in\n## MES\n## MNQ\n## MGC\n## F.\n## 情绪面\n## 今日交易档案\n## Plan Retrospective\n## C.\n## B.\n## Tomorrow Preliminary\n## 数据快照",
        input_tokens=0, output_tokens=0, cache_creation_tokens=0, cache_read_tokens=0,
    )

    fake_plan_reader = MagicMock()
    fake_plan_reader.read_today_plan.return_value = {}  # premarket missing

    fake_retrospective = MagicMock()
    fake_retrospective.compose.return_value = {}
    fake_retrospective.persist = MagicMock()

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {"count": 0, "daily_r": 0.0, "violations_total": 0, "screenshots_complete": 0, "per_trade_violations": {}}

    fake_tomorrow = MagicMock()
    fake_tomorrow.build_input_data.return_value = "x"

    gen = EODGenerator(
        ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES"], tradable_symbols=["MES"],
        plan_reader=fake_plan_reader, plan_parser=MagicMock(),
        trades_query=fake_trades_query, retrospective=fake_retrospective,
        tomorrow_planner=fake_tomorrow,
    )

    from daytrader.reports.core.context_loader import ContextData
    ctx = ContextData(date_et="2026-05-04", contract_text="", instruments_data={"MES": {"1D": []}}, news_items=[])
    outcome = gen.generate(context=ctx, run_timestamp_pt="14:00", run_timestamp_et="17:00", sentiment_md="")

    # Should not raise. Should produce some report text (even if degraded).
    assert outcome is not None
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/reports/eod/test_eod_generator.py -v`
Expected: FAIL — `EODGenerator` not defined.

- [ ] **Step 3: Implement `eod.py`**

Create `src/daytrader/reports/types/eod.py`:

```python
"""EODGenerator — multi-symbol EOD report generation pipeline.

Mirrors PremarketGenerator pattern. Composes:
  - Multi-TF bars (W/D/4H per symbol)
  - FuturesSection (basis + term + RTH-formed VP, today's close)
  - SentimentSection (8h window)
  - PremarketPlanReader → PremarketPlanParser → Plan
  - TodayTradesQuery → trade ledger + audit
  - PlanRetrospective.compose → per-symbol retrospective
  - TomorrowPreliminaryPlan.build_input_data
  - AIAnalyst.call(prompt) → markdown report
  - OutputValidator.validate
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.reports.core.ai_analyst import AIAnalyst, AIResult
from daytrader.reports.core.context_loader import ContextData
from daytrader.reports.core.output_validator import OutputValidator, ValidationResult
from daytrader.reports.core.prompt_builder import PromptBuilder, ReportContext
from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow


@dataclass
class EODOutcome:
    """Output of EODGenerator.generate()."""
    report_text: str
    ai_result: AIResult
    validation: ValidationResult
    retrospective_rows: dict[str, RetrospectiveRow]


class EODGenerator:
    """Generate the EOD report — multi-symbol fetch + retrospective + AI + validate."""

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
        # EOD-specific deps:
        plan_reader=None,
        plan_parser=None,
        trades_query=None,
        retrospective=None,
        tomorrow_planner=None,
    ) -> None:
        if not symbols:
            raise ValueError("symbols must be non-empty")
        for s in tradable_symbols:
            if s not in symbols:
                raise ValueError(f"tradable {s!r} not in symbols {symbols}")

        self.ib_client = ib_client
        self.ai_analyst = ai_analyst
        self.symbols = list(symbols)
        self.tradable_symbols = list(tradable_symbols)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or OutputValidator()
        self.underlying_price_fetcher = underlying_price_fetcher
        self.term_price_fetcher = term_price_fetcher
        self.tick_sizes = tick_sizes or {s: 0.25 for s in symbols}
        self.plan_reader = plan_reader
        self.plan_parser = plan_parser
        self.trades_query = trades_query
        self.retrospective = retrospective
        self.tomorrow_planner = tomorrow_planner

    def generate(
        self,
        context: ContextData,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        sentiment_md: str = "",
    ) -> EODOutcome:
        date_et = context.date_et

        # Step 1: F-section (today's post-cash-close basis + term + VP)
        from daytrader.reports.futures_data.futures_section import build_futures_section
        try:
            tick_sizes = self.tick_sizes
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
                tick_sizes=tick_sizes,
            )
        except Exception as exc:
            print(f"[eod_generator] WARNING: F-section failed: {exc}", file=sys.stderr)
            futures_data = None

        # Step 2: read today's premarket plan
        today_plan_blocks: dict[str, str] = {}
        if self.plan_reader:
            try:
                today_plan_blocks = self.plan_reader.read_today_plan(date_et)
            except Exception as exc:
                print(f"[eod_generator] WARNING: plan_reader failed: {exc}", file=sys.stderr)

        # Step 3: query today's trades + audit
        trades = []
        trades_audit = {"count": 0, "daily_r": 0.0, "violations_total": 0, "screenshots_complete": 0, "per_trade_violations": {}}
        if self.trades_query:
            try:
                trades = self.trades_query.trades_for_date(date_et)
                trades_audit = self.trades_query.audit_summary(trades)
            except Exception as exc:
                print(f"[eod_generator] WARNING: trades_query failed: {exc}", file=sys.stderr)

        today_trades_md = self._render_trades_block(trades, trades_audit)

        # Step 4: plan retrospective + persist
        retrospective_rows: dict[str, RetrospectiveRow] = {}
        retrospective_md = ""
        if self.retrospective and today_plan_blocks:
            try:
                retrospective_rows = self.retrospective.compose(
                    plans=today_plan_blocks,
                    symbols=self.symbols,
                    date_et=date_et,
                    tick_sizes=self.tick_sizes,
                )
                self.retrospective.persist(retrospective_rows)
                retrospective_md = self._render_retrospective_block(retrospective_rows)
            except Exception as exc:
                print(f"[eod_generator] WARNING: retrospective failed: {exc}", file=sys.stderr)
        else:
            retrospective_md = "## 🔄 Plan Retrospective\n\n⚠️ 今日 premarket plan 未找到 (premarket 可能 fail) — 无法做 plan vs PA 复盘"

        # Step 5: tomorrow preliminary
        tomorrow_md = ""
        if self.tomorrow_planner:
            try:
                tomorrow_md = self.tomorrow_planner.build_input_data(
                    today_bars=context.instruments_data,
                    today_retrospective=retrospective_rows,
                    sentiment_md=sentiment_md,
                )
            except Exception as exc:
                print(f"[eod_generator] WARNING: tomorrow_planner failed: {exc}", file=sys.stderr)

        # Step 6: build prompt
        report_ctx = ReportContext(date_et=date_et, contract_text=context.contract_text)
        prompt = self.prompt_builder.build_eod(
            context=report_ctx,
            bars_by_symbol_and_tf=context.instruments_data,
            tradable_symbols=self.tradable_symbols,
            news_items=context.news_items,
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
            futures_data=futures_data,
            sentiment_md=sentiment_md,
            today_plan_blocks=today_plan_blocks,
            retrospective_md=retrospective_md,
            today_trades_md=today_trades_md,
            tomorrow_preliminary_md=tomorrow_md,
        )

        # Step 7: call AI + validate
        ai_result = self.ai_analyst.call(prompt)
        validation = self.validator.validate(ai_result.text, "eod")

        return EODOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
            retrospective_rows=retrospective_rows,
        )

    @staticmethod
    def _render_trades_block(trades: list[dict[str, Any]], audit: dict[str, Any]) -> str:
        if not trades:
            return (
                "## 今日交易档案 / Today's Trade Archive\n\n"
                "今天没交易（0/3）。\n\n"
                "**原因分析**: AI 应在此评估 — 是 setup 真不满足（discipline ✓），"
                "还是没在屏幕前（execution gap）？参考 🔄 Plan Retrospective 段对比。\n"
            )
        lines = [
            "## 今日交易档案 / Today's Trade Archive\n",
            "| # | symbol | side | entry | exit | pnl | violations | screenshots |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, t in enumerate(trades, start=1):
            lines.append(
                f"| {i} | {t.get('symbol')} | {t.get('direction')} | "
                f"{t.get('entry_price')} | {t.get('exit_price') or '-'} | "
                f"{t.get('pnl_usd') or '-'} | "
                f"{audit['per_trade_violations'].get(t['id'], [])} | "
                f"{'yes' if 'screenshots: yes' in (t.get('notes') or '').lower() else 'no'} |"
            )
        lines.append("")
        lines.append(f"**Audit summary**: {audit['count']} trades, "
                     f"daily R={audit['daily_r']:+.2f}, "
                     f"violations={audit['violations_total']}, "
                     f"screenshots complete={audit['screenshots_complete']}/{audit['count']}")
        return "\n".join(lines)

    @staticmethod
    def _render_retrospective_block(rows: dict[str, RetrospectiveRow]) -> str:
        if not rows:
            return "## 🔄 Plan Retrospective\n\n(no retrospective available)"
        lines = ["## 🔄 Plan Retrospective / 计划复盘"]
        for symbol, row in rows.items():
            lines.append(f"\n### {symbol}")
            lines.append("| # | level | type | direction | triggered? | touch | sim entry | sim stop | sim target | outcome | sim R |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for i, (lvl, out) in enumerate(row.per_level_outcomes, start=1):
                triggered = "✅" if out.triggered else "❌"
                lines.append(
                    f"| {i} | {lvl.price} ({lvl.source}) | {lvl.level_type} | {lvl.direction} | "
                    f"{triggered} | {out.touch_time_pt or '-'} | "
                    f"{out.sim_entry or '-'} | {out.sim_stop or '-'} | {out.sim_target or '-'} | "
                    f"{out.outcome} | {out.sim_r:+.2f} |"
                )
            lines.append(
                f"\n**{symbol} summary**: {row.triggered_count}/{row.total_levels} triggered, "
                f"sim total {row.sim_total_r:+.2f}R, actual {row.actual_total_r:+.2f}R, "
                f"gap {row.gap_r:+.2f}R"
            )
        lines.append("")
        lines.append("> Caveat: simulator assumes 'level touched = setup triggered'. "
                     "v1 has no footprint Level 3 / 5:1 / volume verification — "
                     "treat sim outcomes as upper-bound. v2 will integrate MotiveWave footprint replay.")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/reports/eod/test_eod_generator.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/reports/types/eod.py tests/reports/eod/test_eod_generator.py
git commit -m "feat(eod): EODGenerator orchestrates full EOD pipeline (mirrors PremarketGenerator)"
```

---

## Task 10: Orchestrator.run_eod + CLI dispatch

**Files:**
- Modify: `src/daytrader/reports/core/orchestrator.py` (add `run_eod`)
- Modify: `src/daytrader/cli/reports.py` (dispatch `--type eod`)
- Modify: `tests/reports/test_orchestrator.py` (add EOD tests)
- Modify: `tests/cli/test_reports_cli.py` (extend for eod dispatch)

- [ ] **Step 1: Add `run_eod` to Orchestrator**

In `src/daytrader/reports/core/orchestrator.py`, find `run_premarket()` method. Add `run_eod` below it with the same idempotency / state-DB / failure pattern:

```python
def run_eod(self, run_at: datetime) -> PipelineResult:
    """Execute one EOD pipeline run."""
    run_at_utc = run_at.astimezone(timezone.utc)
    date_et = run_at_utc.astimezone(ET).date().isoformat()
    time_pt_str = run_at_utc.astimezone(PT).strftime("%H:%M")
    time_et_str = run_at_utc.astimezone(ET).strftime("%H:%M")

    # Idempotency: same date EOD success → skip
    if self.state_db.already_generated_today("eod", date_et):
        return PipelineResult(success=True, report_id=None, report_path=None, skipped_idempotent=True)

    report_id = self.state_db.insert_report(
        report_type="eod", date_et=date_et,
        time_pt=time_pt_str, time_et=time_et_str,
        status="pending", created_at=run_at_utc,
    )

    try:
        start = time.perf_counter()

        # Load context (same as premarket — bars + contract + news)
        context = self.context_loader.load(date_et=date_et, symbols=self.symbols)

        # Sentiment with shorter window
        from daytrader.reports.sentiment import SentimentSection
        sentiment_section = SentimentSection(symbols=self.symbols, time_window="past 8h")
        sentiment_md = ""
        try:
            sentiment_result = sentiment_section.collect()
            sentiment_md = sentiment_section.render(sentiment_result)
        except Exception as exc:
            import sys
            print(f"[orchestrator] sentiment collect/render failed: {exc}", file=sys.stderr)

        # Build EODGenerator with all deps
        from daytrader.reports.types.eod import EODGenerator
        from daytrader.reports.eod.plan_reader import PremarketPlanReader
        from daytrader.reports.eod.plan_parser import PremarketPlanParser
        from daytrader.reports.eod.trades_query import TodayTradesQuery
        from daytrader.reports.eod.retrospective import PlanRetrospective
        from daytrader.reports.eod.tomorrow_plan import TomorrowPreliminaryPlan
        from daytrader.reports.eod.trade_simulator import simulate_level
        from daytrader.reports.futures_data.term_prices import TermPricesFetcher
        from daytrader.reports.futures_data.underlying_prices import UnderlyingPriceFetcher

        plan_reader = PremarketPlanReader(
            vault_path=self.vault_root,
            daily_folder=self.daily_folder,
        )
        plan_parser = PremarketPlanParser()
        trades_query = TodayTradesQuery(self.journal_db_path)
        retrospective = PlanRetrospective(
            plan_parser=plan_parser,
            trade_simulator=simulate_level,
            intraday_bar_fetcher=lambda sym, d: self.ib_client.get_bars(sym, timeframe="5m", bars=78),
            trades_query=trades_query,
            state_db_path=self.state_db.db_path,
        )
        tomorrow_planner = TomorrowPreliminaryPlan()

        generator = EODGenerator(
            ib_client=self.ib_client, ai_analyst=self.ai_analyst,
            symbols=self.symbols, tradable_symbols=self.tradable_symbols,
            underlying_price_fetcher=UnderlyingPriceFetcher(self.ib_client),
            term_price_fetcher=TermPricesFetcher(self.ib_client),
            plan_reader=plan_reader, plan_parser=plan_parser,
            trades_query=trades_query, retrospective=retrospective,
            tomorrow_planner=tomorrow_planner,
        )
        outcome = generator.generate(
            context=context,
            run_timestamp_pt=f"{time_pt_str} PT",
            run_timestamp_et=f"{time_et_str} ET",
            sentiment_md=sentiment_md,
        )

        if not outcome.validation.ok:
            self.state_db.update_report_status(
                report_id, status="failed",
                failure_reason=f"validation: missing {outcome.validation.missing}",
            )
            return PipelineResult(success=False, report_id=report_id, report_path=None,
                                  error=f"validation failed: {outcome.validation.missing}")

        # Write to Obsidian
        write_result = self.obsidian_writer.write(
            content=outcome.report_text,
            filename=f"{date_et}-eod.md",
        )

        duration = time.perf_counter() - start
        self.state_db.update_report_status(
            report_id, status="success",
            obsidian_path=str(write_result.path),
            tokens_input=outcome.ai_result.input_tokens,
            tokens_output=outcome.ai_result.output_tokens,
            duration_seconds=duration,
        )

        # Telegram (existing pattern)
        if self.telegram_pusher is not None:
            try:
                import asyncio
                asyncio.run(self.telegram_pusher.push(
                    text_messages=[outcome.report_text],
                    chart_paths=[],
                    pdf_path=None,
                ))
            except Exception as exc:
                import sys
                print(f"[orchestrator] EOD telegram failed: {exc}", file=sys.stderr)

        return PipelineResult(success=True, report_id=report_id, report_path=write_result.path)

    except Exception as exc:
        import sys
        print(f"[orchestrator] EOD pipeline crashed: {exc}", file=sys.stderr)
        self.state_db.update_report_status(report_id, status="failed", failure_reason=str(exc)[:200])
        return PipelineResult(success=False, report_id=report_id, report_path=None, error=str(exc))
```

- [ ] **Step 2: Add CLI dispatch**

In `src/daytrader/cli/reports.py`, find the `run_cmd` function. Replace the `if report_type != "premarket"` block with:

```python
if report_type not in ("premarket", "eod"):
    click.echo(f"Phase 5 implements premarket + eod. {report_type!r} is in a later phase.", err=True)
    ctx.exit(2)
```

Then in the orchestrator dispatch line, change:

```python
result = orchestrator.run_premarket(run_at=datetime.now(timezone.utc))
```

to:

```python
if report_type == "premarket":
    result = orchestrator.run_premarket(run_at=datetime.now(timezone.utc))
elif report_type == "eod":
    result = orchestrator.run_eod(run_at=datetime.now(timezone.utc))
```

- [ ] **Step 3: Add Orchestrator integration tests**

In `tests/reports/test_orchestrator.py`, add EOD tests parallel to existing premarket ones (mock all deps, assert run_eod calls EODGenerator + state_db lifecycle):

```python
def test_run_eod_idempotent(monkeypatch):
    """If state_db says EOD already done today, skip."""
    from daytrader.reports.core.orchestrator import Orchestrator, PipelineResult
    from datetime import datetime, timezone

    fake_state_db = MagicMock()
    fake_state_db.already_generated_today.return_value = True

    orchestrator = Orchestrator(
        state_db=fake_state_db, ib_client=MagicMock(), ai_analyst=MagicMock(),
        contract_path=Path("/tmp/c"), journal_db_path=Path("/tmp/j"),
        vault_root=Path("/tmp/v"), fallback_dir=Path("/tmp/f"),
        daily_folder="Daily", symbols=["MES"], tradable_symbols=["MES"],
    )
    result = orchestrator.run_eod(run_at=datetime.now(timezone.utc))
    assert result.skipped_idempotent is True
```

- [ ] **Step 4: Add CLI smoke test**

In `tests/cli/test_reports_cli.py`, ensure `--type eod` dispatch path is tested:

```python
def test_reports_run_eod_no_claude_cli_clearly_errors(monkeypatch, tmp_path):
    """Without claude CLI on PATH, run --type eod exits non-zero with clear message."""
    runner = CliRunner()
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["reports", "run", "--type", "eod"])
    assert result.exit_code != 0
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/reports/test_orchestrator.py tests/cli/test_reports_cli.py tests/reports/eod/ -v 2>&1 | tail -20`
Expected: all pass.

- [ ] **Step 6: Run full suite for no regressions**

Run: `uv run pytest tests/ --ignore=tests/research -q 2>&1 | tail -3`
Expected: 380+ tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/daytrader/reports/core/orchestrator.py src/daytrader/cli/reports.py tests/reports/test_orchestrator.py tests/cli/test_reports_cli.py
git commit -m "feat(eod): Orchestrator.run_eod + CLI dispatch (--type eod no longer stub)"
```

---

## Task 11: launchd integration

**Files:**
- Create: `scripts/run_eod_launchd.sh`
- Create: `scripts/launchd/com.daytrader.report.eod.1400pt.plist.template`
- Create: `scripts/install_eod_launchd.sh`
- Create: `scripts/uninstall_eod_launchd.sh`
- Modify: `.gitignore` (add `eod-*.log`)

Mirror Phase 7 v1 patterns exactly (premarket already has identical structure).

- [ ] **Step 1: Create `scripts/run_eod_launchd.sh`**

```bash
#!/usr/bin/env bash
# scripts/run_eod_launchd.sh
#
# Wrapper invoked by launchd at 14:00 PT weekdays. Mirrors run_premarket_launchd.sh
# pattern: source PATH → run preflight (real API handshake) → daytrader reports
# run --type eod --no-pdf.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
if [[ -d "$HOME/.local/bin" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

cd "$PROJECT_ROOT" || {
    echo "[run_eod_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/eod-$TS.log"

exec > >(tee "$RUN_LOG") 2>&1

echo "[run_eod_launchd] start $(date -Iseconds)"
echo "[run_eod_launchd] PATH=$PATH"
echo "[run_eod_launchd] PWD=$PROJECT_ROOT"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_eod_launchd] PREFLIGHT FAILED — send notification and exit"
    osascript -e 'display notification "EOD preflight failed at 14:00 PT — TWS / claude / config issue" with title "DayTrader EOD" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

echo "[run_eod_launchd] preflight ok, invoking reports run --type eod"
uv run daytrader reports run --type eod --no-pdf
rc=$?
echo "[run_eod_launchd] reports run exit=$rc"
echo "[run_eod_launchd] end $(date -Iseconds)"
exit "$rc"
```

- [ ] **Step 2: Create plist template**

Create `scripts/launchd/com.daytrader.report.eod.1400pt.plist.template`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.eod.1400pt</string>

    <key>ProgramArguments</key>
    <array>
        <string>__PROJECT_ROOT__/scripts/run_eod_launchd.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>__PROJECT_ROOT__/data/logs/launchd/eod.1400pt.out</string>
    <key>StandardErrorPath</key>
    <string>__PROJECT_ROOT__/data/logs/launchd/eod.1400pt.err</string>

    <key>WorkingDirectory</key>
    <string>__PROJECT_ROOT__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>__HOME__</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

- [ ] **Step 3: Create install/uninstall scripts**

Create `scripts/install_eod_launchd.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_ROOT/scripts/launchd/com.daytrader.report.eod.1400pt.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/com.daytrader.report.eod.1400pt.plist"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

sed \
    -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE" > "$TARGET_PLIST"

echo "[install_eod_launchd] wrote $TARGET_PLIST"

# Defensively chmod +x the wrapper
chmod +x "$PROJECT_ROOT/scripts/run_eod_launchd.sh"

GUI_DOMAIN="gui/$(id -u)"
LABEL="com.daytrader.report.eod.1400pt"

if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[install_eod_launchd] removing existing job $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
fi

echo "[install_eod_launchd] bootstrapping $LABEL"
launchctl bootstrap "$GUI_DOMAIN" "$TARGET_PLIST"

echo "[install_eod_launchd] done. Next firing: next weekday at 14:00 PT."
echo "Test fire: launchctl kickstart $GUI_DOMAIN/$LABEL"
```

Create `scripts/uninstall_eod_launchd.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

LABEL="com.daytrader.report.eod.1400pt"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"

if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[uninstall_eod_launchd] booting out $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL"
fi

if [[ -f "$TARGET_PLIST" ]]; then
    rm -f "$TARGET_PLIST"
    echo "[uninstall_eod_launchd] removed $TARGET_PLIST"
fi

echo "[uninstall_eod_launchd] done."
```

- [ ] **Step 4: chmod + syntax check + plist lint**

```bash
chmod +x scripts/run_eod_launchd.sh scripts/install_eod_launchd.sh scripts/uninstall_eod_launchd.sh
bash -n scripts/run_eod_launchd.sh
bash -n scripts/install_eod_launchd.sh
bash -n scripts/uninstall_eod_launchd.sh
plutil -lint scripts/launchd/com.daytrader.report.eod.1400pt.plist.template
```

Expected: all `OK` / no errors.

- [ ] **Step 5: Update .gitignore**

Append to `.gitignore`:

```
data/logs/launchd/eod-*.log
```

- [ ] **Step 6: Commit**

```bash
git add scripts/run_eod_launchd.sh scripts/launchd/com.daytrader.report.eod.1400pt.plist.template scripts/install_eod_launchd.sh scripts/uninstall_eod_launchd.sh .gitignore
git commit -m "feat(eod): launchd plist + wrapper + install/uninstall (14:00 PT Mon-Fri)"
```

---

## Task 12: End-to-end acceptance

**Files:** None (verification only).

- [ ] **Step 1: Full test suite passes**

Run: `uv run pytest tests/ --ignore=tests/research -q 2>&1 | tail -5`
Expected: 380+ tests pass (was ~351 + ~30 new EOD tests).

- [ ] **Step 2: Preflight passes**

Run: `uv run python scripts/preflight_check.py`
Expected: all 4 checks (port + API handshake + claude + config) pass.

- [ ] **Step 3: Live test fire — full EOD pipeline**

⚠️ Make sure TWS is running. The pipeline takes ~7-8 min total.

Run: `uv run daytrader reports run --type eod --no-pdf 2>&1 | tail -30`

Expected:
- Output ends with `Report generated: ...Daily/{TODAY}-eod.md`
- Exit 0

- [ ] **Step 4: Inspect generated report**

```bash
TODAY=$(date +%Y-%m-%d)
REPORT="$HOME/Documents/DayTrader Vault/Daily/${TODAY}-eod.md"
ls -la "$REPORT"
echo "=== sections ===" && grep -E "^##? " "$REPORT"
echo "=== retrospective ===" && awk '/Plan Retrospective/,/^## /' "$REPORT" | head -40
echo "=== tomorrow ===" && awk '/Tomorrow Preliminary/,/^## /' "$REPORT" | head -30
echo "=== A section absence check ===" && grep -E "^## A\." "$REPORT" || echo "✓ no A section (correct)"
```

Confirm:
- All required sections present per `REQUIRED_SECTIONS["eod"]`
- 🔄 Plan Retrospective populated (or graceful "premarket plan unavailable" if today's premarket failed)
- 📅 Tomorrow Preliminary present
- NO A. section
- C. section verbatim-quotes today's premarket plan

- [ ] **Step 5: Verify state DB row**

```bash
uv run python -c "
import sqlite3
db = sqlite3.connect('data/state.db')
cur = db.execute('SELECT id, report_type, date, status, duration_seconds FROM reports WHERE report_type=\"eod\" ORDER BY id DESC LIMIT 3')
for r in cur: print(r)
print('---')
cur = db.execute('SELECT date, symbol, total_levels, triggered_count, sim_total_r, gap_r FROM plan_retrospective_daily ORDER BY id DESC LIMIT 3')
for r in cur: print(r)
"
```

Expected: row in `reports` table with `status='success'`; row(s) in `plan_retrospective_daily` table.

- [ ] **Step 6: Install launchd job**

```bash
./scripts/install_eod_launchd.sh
launchctl print "gui/$(id -u)/com.daytrader.report.eod.1400pt" | head -30
```

Expected: state shows job loaded, schedule shows `Hour=14 Minute=0 Weekday=1..5`.

- [ ] **Step 7: (Optional) launchctl kickstart for live verification**

```bash
launchctl kickstart "gui/$(id -u)/com.daytrader.report.eod.1400pt"
sleep 30
tail -30 data/logs/launchd/eod-*.log
```

Expected: log shows preflight ok + reports run start; after ~7 min full report should appear.

- [ ] **Step 8: Push commits + verify PR**

```bash
git push 2>&1 | tail -3
gh pr view 4 --json number,state,commits --jq '{number, state, total_commits: (.commits|length)}'
```

Expected: push successful; PR has +12 commits (101 → 113-ish).

- [ ] **Step 9: Update spec status to Implemented**

Edit `docs/superpowers/specs/2026-05-04-reports-phase5-eod-design.md` line 4:

```
**Status:** Implemented (HEAD commit <SHA>)
```

Commit:

```bash
git add docs/superpowers/specs/2026-05-04-reports-phase5-eod-design.md
git commit -m "docs(eod): mark Phase 5 EOD spec as Implemented"
git push
```

---

## Summary

After Phase 5 v1 EOD:

- Daily EOD report fires at 14:00 PT Mon-Fri automatically
- Report includes: TA recap (W/D/4H + F + D 情绪面) + today's trade audit + 🔄 Plan Retrospective (per-level table + sim outcomes + execution gap) + verbatim plan adherence (C) + 📅 Tomorrow Preliminary
- No A section per spec
- Daily row written to `plan_retrospective_daily` for v2 multi-day stats
- launchd plist + wrapper + install/uninstall — same Phase 7 v1 pattern (preflight handshake auto-applies)
- Telegram push reuses existing pipeline
- Total wall time: ~7-8 min per fire

**Coverage vs spec:** v1 = 1/5 deferred cadences (the most valuable one). intraday-4h-1, intraday-4h-2, night, asia → Phase 5.5 next.

**Lock-in friction reduced**:
- Every "no trade today" day now has audit data (was it discipline or absence?)
- Every traded day has automatic §6 / §9 audit
- Plan quality has a closed-loop data feedback for the first time
- Tomorrow has data-driven first-draft 17 hours earlier than premarket

**Out of scope** (deferred):
- Multi-day aggregate stats / dashboards → Phase 5.5
- Footprint integration (Level 3 / 5:1 / volume verification) → v2
- AI plan iteration suggestions → v2
- Reverse causation analysis → v2

**Next**: After 30-trade lock-in completes + N=30 retrospective rows accumulated, run Phase 5.5 retrospective + v2 enhancement design pass.
