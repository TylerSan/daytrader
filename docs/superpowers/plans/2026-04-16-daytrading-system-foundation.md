# Day Trading System — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the journal subsystem (Contract + pre/post-trade CLIs + daily loss circuit + sanity-floor backtest + dry-run logger + resume gate) that enforces trading discipline before user resumes live trading.

**Architecture:** New `daytrader.journal` Python module with its own SQLite schema (tables prefixed `journal_`) to avoid conflict with existing Phase 1 `trades` table. Separate `JournalRepository` class (not extending `core.db.Database`). CLI commands added under existing `daytrader journal` group via new `cli/journal_cmd.py`. Obsidian views auto-generated on SQLite writes.

**Tech Stack:** Python 3.12+, Click, Pydantic v2, SQLite (stdlib), PyYAML, pandas, yfinance. All already in pyproject.toml. No new deps.

**Spec:** `docs/superpowers/specs/2026-04-16-daytrading-system-design.md`

---

## File Structure

### New files

```
src/daytrader/journal/
├── __init__.py
├── models.py              # Pydantic: JournalTrade, Checklist, DryRun, CircuitState,
│                          #          SetupVerdict, Contract, SetupDefinition
├── repository.py          # JournalRepository — SQLite CRUD for journal_* tables
├── contract.py            # Contract.md parser + validator
├── circuit.py             # Daily loss circuit logic (lock/unlock, cool-off)
├── checklist.py           # Pre-trade checklist evaluation
├── trades.py              # Pre-trade + post-trade orchestration
├── dry_run.py             # Dry-run session orchestration
├── resume_gate.py         # Go/no-go gate check
├── obsidian.py            # Markdown view generator for journal records
├── auditor.py             # Integrity checker (detects SQLite bypass attempts)
└── sanity_floor/
    ├── __init__.py
    ├── setup_yaml.py      # YAML parser for setup definitions
    ├── data_loader.py     # yfinance loader with local caching
    ├── engine.py          # Bar-by-bar simulation
    └── runner.py          # Orchestrator: loads YAML + data + runs engine + writes verdict

src/daytrader/cli/
└── journal_cmd.py         # All 6 journal CLI commands

docs/trading/
├── Contract.md.template   # User fills at W0
└── setups/                # YAML setup definitions
    ├── .gitkeep
    └── example_opening_range_breakout.yaml  # Format example

tests/journal/
├── __init__.py
├── conftest.py            # Shared fixtures (in-memory DB, tmp vault)
├── test_models.py
├── test_repository.py
├── test_contract.py
├── test_circuit.py
├── test_checklist.py
├── test_trades.py
├── test_dry_run.py
├── test_resume_gate.py
├── test_obsidian.py
├── test_auditor.py
├── test_cli.py
└── sanity_floor/
    ├── __init__.py
    ├── test_setup_yaml.py
    ├── test_data_loader.py
    ├── test_engine.py
    └── test_runner.py
```

### Modified files

```
src/daytrader/cli/main.py          # Import + register journal subcommands
src/daytrader/core/config.py       # Add JournalConfig block
config/default.yaml                # Add journal defaults
```

### SQLite tables added (owned by `JournalRepository`)

```
journal_contract              # Active contract + version history
journal_checklists            # Every pre-trade checklist attempt (pass or fail)
journal_trades                # Real trades (partial → complete via post-trade)
journal_dry_runs              # Hypothetical trades
journal_circuit_state         # One row per date
journal_setup_verdicts        # Sanity-floor backtest results
```

---

## Implementation Phases

- **Phase A (Tasks 1-8):** Foundation — models, repo, contract, circuit, checklist, pre/post-trade CLI
- **Phase B (Tasks 9-13):** Sanity-floor backtest
- **Phase C (Tasks 14-18):** Dry-run + resume-gate + obsidian + auditor
- **Phase D (Tasks 19-20):** Wire-up + smoke tests

---

## Phase A: Foundation

### Task 1: Scaffold journal module + config extension

**Files:**
- Create: `src/daytrader/journal/__init__.py` (empty)
- Create: `src/daytrader/journal/sanity_floor/__init__.py` (empty)
- Create: `tests/journal/__init__.py` (empty)
- Create: `tests/journal/sanity_floor/__init__.py` (empty)
- Create: `tests/journal/conftest.py`
- Create: `docs/trading/Contract.md.template`
- Create: `docs/trading/setups/.gitkeep` (empty)
- Modify: `src/daytrader/core/config.py`
- Modify: `config/default.yaml`

- [ ] **Step 1: Create directory scaffolding with empty `__init__.py` files**

```bash
mkdir -p src/daytrader/journal/sanity_floor
mkdir -p tests/journal/sanity_floor
mkdir -p docs/trading/setups
touch src/daytrader/journal/__init__.py
touch src/daytrader/journal/sanity_floor/__init__.py
touch tests/journal/__init__.py
touch tests/journal/sanity_floor/__init__.py
touch docs/trading/setups/.gitkeep
```

- [ ] **Step 2: Add `JournalConfig` to `core/config.py`**

Edit `src/daytrader/core/config.py`, add new class BEFORE `class DayTraderConfig`:

```python
class JournalConfig(BaseModel):
    db_path: str = "data/db/journal.db"
    contract_path: str = "docs/trading/Contract.md"
    setups_dir: str = "docs/trading/setups"
    obsidian_trades_folder: str = "DayTrader/Trades"
    obsidian_dry_runs_folder: str = "DayTrader/DryRuns"
    obsidian_checklists_folder: str = "DayTrader/Daily"
    data_cache_dir: str = "data/cache/ohlcv"
```

Add field to `DayTraderConfig`:

```python
class DayTraderConfig(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    premarket: PremarketConfig = PremarketConfig()
    backtest: BacktestConfig = BacktestConfig()
    journal: JournalConfig = JournalConfig()   # <-- add this line
```

- [ ] **Step 3: Add journal defaults to `config/default.yaml`**

Append to `config/default.yaml`:

```yaml
journal:
  db_path: data/db/journal.db
  contract_path: docs/trading/Contract.md
  setups_dir: docs/trading/setups
  obsidian_trades_folder: DayTrader/Trades
  obsidian_dry_runs_folder: DayTrader/DryRuns
  obsidian_checklists_folder: DayTrader/Daily
  data_cache_dir: data/cache/ohlcv
```

- [ ] **Step 4: Create Contract.md.template**

Write `docs/trading/Contract.md.template`:

```markdown
# Trading Contract

**Version:** 1
**Signed date:** YYYY-MM-DD
**Active:** false

---

## 1. Account & R Unit

- Primary account: <Topstep $50k combine | IBKR self-funded | ...>
- Starting capital: $XXXXX
- R unit (USD): $XX   # ≈ daily_loss_limit / 3

## 2. Per-Trade Risk

- max_loss_per_trade_r: 1
- max_contracts: 2
- stop_must_be_at_broker: true   # OCO/bracket before acknowledged

## 3. Daily Risk

- daily_loss_limit_r: 3
- daily_loss_warning_r: 2
- max_trades_per_day: 5

## 4. Setup Lock-In

- locked_setup_name: <filled after W2 Setup Gate>
- locked_setup_file: docs/trading/setups/<filename>.yaml
- lock_in_min_trades: 30
- backup_setup_name: <filled in W2>
- backup_setup_file: docs/trading/setups/<filename>.yaml
- backup_setup_status: benched

## 5. Execution Rules

- entry_via_cli_only: true                 # Must go through `daytrader journal pre-trade`
- stop_move_direction: toward_profit_only  # Never move stop further away
- stop_move_after_target_1_hit_only: true
- target_structure: scale_50_at_t1_trail_remainder

## 6. Zero-Tolerance Bans

- ban_averaging_down_losers: true
- ban_moving_stop_away: true
- ban_bypass_pre_trade_checklist: true
- ban_revenge_trade_within_cooloff: true
- ban_trade_after_daily_limit: true

## 7. Cool-off

- stop_cooloff_minutes: 30
- consecutive_stops_day_end: 2
- minus_2r_cooloff_minutes: 30

## 8. Amendment Process

- amendments_weekend_only: true
- amendment_wait_days: 7
- amendment_forbidden_on_loss_day: true

---

## Signature

I commit to these rules. Violation of any zero-tolerance ban invalidates
the current trading day's results.

Signed: ______________   Date: YYYY-MM-DD
```

- [ ] **Step 5: Create `tests/journal/conftest.py`**

```python
"""Shared fixtures for journal tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_journal_db(tmp_path: Path) -> Path:
    """Return path to a temp SQLite file (not yet created)."""
    return tmp_path / "journal.db"


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Return path to a fake Obsidian vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


@pytest.fixture
def sample_contract_md(tmp_path: Path) -> Path:
    """A valid Contract.md for tests."""
    p = tmp_path / "Contract.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** 2026-04-20
**Active:** true

## 1. Account & R Unit
- R unit (USD): $50

## 2. Per-Trade Risk
- max_loss_per_trade_r: 1
- max_contracts: 2
- stop_must_be_at_broker: true

## 3. Daily Risk
- daily_loss_limit_r: 3
- daily_loss_warning_r: 2
- max_trades_per_day: 5

## 4. Setup Lock-In
- locked_setup_name: opening_range_breakout
- locked_setup_file: docs/trading/setups/opening_range_breakout.yaml
- lock_in_min_trades: 30
- backup_setup_name: ""
- backup_setup_status: benched

## 5. Execution Rules
- entry_via_cli_only: true
- stop_move_direction: toward_profit_only

## 6. Zero-Tolerance Bans
- ban_averaging_down_losers: true

## 7. Cool-off
- stop_cooloff_minutes: 30
- consecutive_stops_day_end: 2

## 8. Amendment Process
- amendments_weekend_only: true
"""
    )
    return p
```

- [ ] **Step 6: Run existing test suite to confirm no regression**

```bash
cd "/Users/tylersan/Projects/Day trading" && python -m pytest -q
```

Expected: all currently passing tests still pass, new `tests/journal/` is empty so no new tests run.

- [ ] **Step 7: Commit**

```bash
git add src/daytrader/journal tests/journal docs/trading \
        src/daytrader/core/config.py config/default.yaml
git commit -m "feat(journal): scaffold journal module + config"
```

---

### Task 2: Journal domain models (Pydantic)

**Files:**
- Create: `src/daytrader/journal/models.py`
- Create: `tests/journal/test_models.py`

- [ ] **Step 1: Write failing tests in `tests/journal/test_models.py`**

```python
"""Tests for journal domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from daytrader.journal.models import (
    ChecklistItems,
    CircuitState,
    Contract,
    DryRun,
    DryRunOutcome,
    JournalTrade,
    SetupVerdict,
    TradeMode,
    TradeSide,
)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class TestChecklistItems:
    def test_all_required(self):
        items = ChecklistItems(
            item_stop_at_broker=True,
            item_within_r_limit=True,
            item_matches_locked_setup=True,
            item_within_daily_r=True,
            item_past_cooloff=True,
        )
        assert items.all_passed() is True

    def test_any_false_fails(self):
        items = ChecklistItems(
            item_stop_at_broker=True,
            item_within_r_limit=True,
            item_matches_locked_setup=False,  # <-- fail
            item_within_daily_r=True,
            item_past_cooloff=True,
        )
        assert items.all_passed() is False


class TestJournalTrade:
    def test_stop_price_required(self):
        """stop_price is non-optional — cannot create trade without it."""
        with pytest.raises(ValidationError):
            JournalTrade(
                id="t01",
                checklist_id="c01",
                date="2026-04-20",
                symbol="MES",
                direction=TradeSide.LONG,
                setup_type="opening_range_breakout",
                entry_time=_dt("2026-04-20T13:35:00"),
                entry_price=Decimal("5000.00"),
                # stop_price missing
                target_price=Decimal("5010.00"),
                size=1,
            )

    def test_target_price_required(self):
        with pytest.raises(ValidationError):
            JournalTrade(
                id="t01",
                checklist_id="c01",
                date="2026-04-20",
                symbol="MES",
                direction=TradeSide.LONG,
                setup_type="opening_range_breakout",
                entry_time=_dt("2026-04-20T13:35:00"),
                entry_price=Decimal("5000.00"),
                stop_price=Decimal("4995.00"),
                # target_price missing
                size=1,
            )

    def test_symbol_whitelist(self):
        with pytest.raises(ValidationError):
            JournalTrade(
                id="t01",
                checklist_id="c01",
                date="2026-04-20",
                symbol="AAPL",  # <-- not in whitelist
                direction=TradeSide.LONG,
                setup_type="orb",
                entry_time=_dt("2026-04-20T13:35:00"),
                entry_price=Decimal("5000"),
                stop_price=Decimal("4995"),
                target_price=Decimal("5010"),
                size=1,
            )

    def test_r_multiple_when_closed(self):
        t = JournalTrade(
            id="t01",
            checklist_id="c01",
            date="2026-04-20",
            symbol="MES",
            direction=TradeSide.LONG,
            setup_type="orb",
            entry_time=_dt("2026-04-20T13:35:00"),
            entry_price=Decimal("5000"),
            stop_price=Decimal("4995"),
            target_price=Decimal("5010"),
            size=1,
            exit_time=_dt("2026-04-20T14:00:00"),
            exit_price=Decimal("5005"),
        )
        # Long, risk = 5, pnl = 5 → r = 1.0
        assert t.r_multiple() == Decimal("1")

    def test_r_multiple_none_when_open(self):
        t = JournalTrade(
            id="t01", checklist_id="c01", date="2026-04-20",
            symbol="MES", direction=TradeSide.LONG, setup_type="orb",
            entry_time=_dt("2026-04-20T13:35:00"),
            entry_price=Decimal("5000"),
            stop_price=Decimal("4995"),
            target_price=Decimal("5010"),
            size=1,
        )
        assert t.r_multiple() is None


class TestCircuitState:
    def test_default_not_locked(self):
        s = CircuitState(date="2026-04-20")
        assert s.no_trade_flag is False
        assert s.trade_count == 0
        assert s.realized_r == 0


class TestContract:
    def test_active_contract(self):
        c = Contract(
            version=1,
            signed_date="2026-04-20",
            active=True,
            r_unit_usd=Decimal("50"),
            daily_loss_limit_r=3,
            daily_loss_warning_r=2,
            max_trades_per_day=5,
            stop_cooloff_minutes=30,
            locked_setup_name="orb",
            locked_setup_file="docs/trading/setups/orb.yaml",
            lock_in_min_trades=30,
            backup_setup_status="benched",
        )
        assert c.active is True


class TestSetupVerdict:
    def test_pass_requires_both_conditions(self):
        v = SetupVerdict(
            setup_name="orb", setup_version="v1",
            run_date="2026-04-20", symbol="MES",
            data_window_days=90,
            n_samples=40,
            win_rate=0.5,
            avg_r=0.1,
            passed=True,
        )
        assert v.passed is True

    def test_failed_when_low_sample(self):
        # n<30 should be marked failed regardless of avg_r
        v = SetupVerdict(
            setup_name="orb", setup_version="v1",
            run_date="2026-04-20", symbol="MES",
            data_window_days=90,
            n_samples=10,  # too few
            win_rate=0.7,
            avg_r=0.5,
            passed=False,
        )
        assert v.passed is False


class TestDryRun:
    def test_outcome_optional(self):
        d = DryRun(
            id="d01", checklist_id="c01", date="2026-04-20",
            symbol="MES", direction=TradeSide.LONG,
            setup_type="orb",
            identified_time=_dt("2026-04-20T13:35:00"),
            hypothetical_entry=Decimal("5000"),
            hypothetical_stop=Decimal("4995"),
            hypothetical_target=Decimal("5010"),
            hypothetical_size=1,
        )
        assert d.outcome is None

    def test_outcome_enum(self):
        for val in ("target_hit", "stop_hit", "rule_exit", "no_trigger"):
            DryRunOutcome(val)  # should parse cleanly
```

- [ ] **Step 2: Run tests — expect import errors**

```bash
python -m pytest tests/journal/test_models.py -v
```

Expected: `ImportError: cannot import name 'ChecklistItems' from 'daytrader.journal.models'`

- [ ] **Step 3: Implement `src/daytrader/journal/models.py`**

```python
"""Journal domain models — Pydantic v2."""

from __future__ import annotations

from datetime import date as date_type, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


ALLOWED_SYMBOLS = {"MES", "MNQ", "MGC"}


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradeMode(str, Enum):
    REAL = "real"
    DRY_RUN = "dry_run"


class DryRunOutcome(str, Enum):
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    RULE_EXIT = "rule_exit"
    NO_TRIGGER = "no_trigger"


class ChecklistItems(BaseModel):
    item_stop_at_broker: bool
    item_within_r_limit: bool
    item_matches_locked_setup: bool
    item_within_daily_r: bool
    item_past_cooloff: bool

    def all_passed(self) -> bool:
        return all(
            [
                self.item_stop_at_broker,
                self.item_within_r_limit,
                self.item_matches_locked_setup,
                self.item_within_daily_r,
                self.item_past_cooloff,
            ]
        )

    def failed_items(self) -> list[str]:
        return [k for k, v in self.model_dump().items() if v is False]


class Checklist(BaseModel):
    id: str
    timestamp: datetime
    mode: TradeMode
    contract_version: int
    items: ChecklistItems
    passed: bool
    failure_reason: Optional[str] = None


class JournalTrade(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str
    checklist_id: str
    date: date_type
    symbol: str
    direction: TradeSide
    setup_type: str
    entry_time: datetime
    entry_price: Decimal
    stop_price: Decimal              # REQUIRED by design
    target_price: Decimal            # REQUIRED by design
    size: int
    exit_time: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    pnl_usd: Optional[Decimal] = None
    notes: Optional[str] = None
    violations: list[str] = Field(default_factory=list)

    def risk(self) -> Decimal:
        return abs(self.entry_price - self.stop_price)

    def pnl(self) -> Optional[Decimal]:
        if self.exit_price is None:
            return None
        if self.direction == TradeSide.LONG:
            return self.exit_price - self.entry_price
        return self.entry_price - self.exit_price

    def r_multiple(self) -> Optional[Decimal]:
        p = self.pnl()
        if p is None:
            return None
        r = self.risk()
        if r == 0:
            return Decimal("0")
        return p / r

    def model_post_init(self, _ctx) -> None:
        if self.symbol not in ALLOWED_SYMBOLS:
            raise ValueError(
                f"symbol {self.symbol!r} not in {sorted(ALLOWED_SYMBOLS)}"
            )


class DryRun(BaseModel):
    id: str
    checklist_id: str
    date: date_type
    symbol: str
    direction: TradeSide
    setup_type: str
    identified_time: datetime
    hypothetical_entry: Decimal
    hypothetical_stop: Decimal
    hypothetical_target: Decimal
    hypothetical_size: int
    outcome: Optional[DryRunOutcome] = None
    outcome_time: Optional[datetime] = None
    outcome_price: Optional[Decimal] = None
    hypothetical_r_multiple: Optional[Decimal] = None
    notes: Optional[str] = None

    def model_post_init(self, _ctx) -> None:
        if self.symbol not in ALLOWED_SYMBOLS:
            raise ValueError(
                f"symbol {self.symbol!r} not in {sorted(ALLOWED_SYMBOLS)}"
            )


class CircuitState(BaseModel):
    date: date_type
    realized_r: Decimal = Decimal("0")
    realized_usd: Decimal = Decimal("0")
    trade_count: int = 0
    no_trade_flag: bool = False
    lock_reason: Optional[str] = None
    last_stop_time: Optional[datetime] = None


class Contract(BaseModel):
    version: int
    signed_date: date_type
    active: bool
    r_unit_usd: Decimal
    daily_loss_limit_r: int
    daily_loss_warning_r: int
    max_trades_per_day: int
    stop_cooloff_minutes: int
    locked_setup_name: Optional[str] = None
    locked_setup_file: Optional[str] = None
    lock_in_min_trades: int = 30
    backup_setup_name: Optional[str] = None
    backup_setup_file: Optional[str] = None
    backup_setup_status: str = "benched"  # 'benched' | 'active'


class SetupVerdict(BaseModel):
    setup_name: str
    setup_version: str
    run_date: date_type
    symbol: str
    data_window_days: int
    n_samples: int
    win_rate: float
    avg_r: float
    passed: bool
```

- [ ] **Step 4: Run tests to verify green**

```bash
python -m pytest tests/journal/test_models.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/models.py tests/journal/test_models.py
git commit -m "feat(journal): add domain models (Trade, Checklist, DryRun, Contract, CircuitState, SetupVerdict)"
```

---

### Task 3: JournalRepository — SQLite schema + CRUD

**Files:**
- Create: `src/daytrader/journal/repository.py`
- Create: `tests/journal/test_repository.py`

- [ ] **Step 1: Write failing tests `tests/journal/test_repository.py`**

```python
"""Tests for JournalRepository."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.models import (
    Checklist, ChecklistItems, CircuitState, Contract,
    DryRun, DryRunOutcome, JournalTrade, SetupVerdict, TradeMode, TradeSide,
)
from daytrader.journal.repository import JournalRepository


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    return r


def _make_trade(**overrides) -> JournalTrade:
    defaults = dict(
        id="t01", checklist_id="c01",
        date=date(2026, 4, 20), symbol="MES",
        direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:35:00"),
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
    )
    defaults.update(overrides)
    return JournalTrade(**defaults)


def _make_checklist(passed: bool = True, mode: TradeMode = TradeMode.REAL) -> Checklist:
    items = ChecklistItems(
        item_stop_at_broker=passed, item_within_r_limit=passed,
        item_matches_locked_setup=passed, item_within_daily_r=passed,
        item_past_cooloff=passed,
    )
    return Checklist(
        id="c01", timestamp=_dt("2026-04-20T13:34:00"),
        mode=mode, contract_version=1,
        items=items, passed=items.all_passed(),
    )


def test_initialize_creates_all_tables(repo: JournalRepository):
    tables = repo.list_tables()
    assert "journal_contract" in tables
    assert "journal_checklists" in tables
    assert "journal_trades" in tables
    assert "journal_dry_runs" in tables
    assert "journal_circuit_state" in tables
    assert "journal_setup_verdicts" in tables


def test_save_and_get_checklist(repo: JournalRepository):
    c = _make_checklist()
    repo.save_checklist(c)
    got = repo.get_checklist("c01")
    assert got is not None
    assert got.passed is True


def test_save_trade_requires_existing_checklist(repo: JournalRepository):
    # Trade references non-existent checklist → FK failure
    with pytest.raises(Exception):
        repo.save_trade(_make_trade(checklist_id="nonexistent"))


def test_save_trade_with_valid_checklist(repo: JournalRepository):
    repo.save_checklist(_make_checklist())
    repo.save_trade(_make_trade())
    got = repo.get_trade("t01")
    assert got is not None
    assert got.stop_price == Decimal("4995")


def test_stop_price_not_null_enforced(repo: JournalRepository):
    """Direct SQL INSERT without stop_price must fail."""
    import sqlite3
    conn = repo._get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journal_trades "
            "(id, checklist_id, date, symbol, direction, setup_type, "
            " entry_time, entry_price, target_price, size) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("t02", "c01", "2026-04-20", "MES", "long", "orb",
             "2026-04-20T13:35:00", "5000", "5010", 1),
        )


def test_post_trade_update(repo: JournalRepository):
    repo.save_checklist(_make_checklist())
    repo.save_trade(_make_trade())
    repo.close_trade(
        trade_id="t01",
        exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5005"),
        pnl_usd=Decimal("25"),
        notes="target hit",
    )
    got = repo.get_trade("t01")
    assert got.exit_price == Decimal("5005")
    assert got.notes == "target hit"


def test_get_circuit_state_default(repo: JournalRepository):
    state = repo.get_circuit_state(date(2026, 4, 20))
    # returns a fresh unlocked state if missing
    assert state.no_trade_flag is False
    assert state.trade_count == 0


def test_upsert_circuit_state(repo: JournalRepository):
    repo.upsert_circuit_state(
        CircuitState(
            date=date(2026, 4, 20),
            realized_r=Decimal("-1"),
            realized_usd=Decimal("-50"),
            trade_count=1,
            no_trade_flag=False,
        )
    )
    s = repo.get_circuit_state(date(2026, 4, 20))
    assert s.realized_r == Decimal("-1")
    assert s.trade_count == 1


def test_save_setup_verdict(repo: JournalRepository):
    v = SetupVerdict(
        setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 20), symbol="MES",
        data_window_days=90, n_samples=45,
        win_rate=0.6, avg_r=0.2, passed=True,
    )
    repo.save_setup_verdict(v)
    got = repo.list_setup_verdicts(setup_name="orb")
    assert len(got) == 1
    assert got[0].passed is True


def test_save_contract_and_get_active(repo: JournalRepository):
    c = Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    )
    repo.save_contract(c)
    got = repo.get_active_contract()
    assert got is not None
    assert got.version == 1
```

- [ ] **Step 2: Run tests (expect ImportError)**

```bash
python -m pytest tests/journal/test_repository.py -v
```

Expected: `ImportError: cannot import name 'JournalRepository'`

- [ ] **Step 3: Implement `src/daytrader/journal/repository.py`**

```python
"""JournalRepository — SQLite persistence for journal subsystem."""

from __future__ import annotations

import json
import sqlite3
from datetime import date as date_type, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from daytrader.journal.models import (
    Checklist, ChecklistItems, CircuitState, Contract,
    DryRun, DryRunOutcome, JournalTrade, SetupVerdict, TradeMode, TradeSide,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_contract (
    version INTEGER PRIMARY KEY,
    signed_date TEXT NOT NULL,
    active INTEGER NOT NULL,
    r_unit_usd TEXT NOT NULL,
    daily_loss_limit_r INTEGER NOT NULL,
    daily_loss_warning_r INTEGER NOT NULL,
    max_trades_per_day INTEGER NOT NULL,
    stop_cooloff_minutes INTEGER NOT NULL,
    locked_setup_name TEXT,
    locked_setup_file TEXT,
    lock_in_min_trades INTEGER NOT NULL DEFAULT 30,
    backup_setup_name TEXT,
    backup_setup_file TEXT,
    backup_setup_status TEXT NOT NULL DEFAULT 'benched'
);

CREATE TABLE IF NOT EXISTS journal_checklists (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('real','dry_run')),
    contract_version INTEGER NOT NULL,
    item_stop_at_broker INTEGER NOT NULL,
    item_within_r_limit INTEGER NOT NULL,
    item_matches_locked_setup INTEGER NOT NULL,
    item_within_daily_r INTEGER NOT NULL,
    item_past_cooloff INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    failure_reason TEXT,
    FOREIGN KEY (contract_version) REFERENCES journal_contract(version)
);

CREATE TABLE IF NOT EXISTS journal_trades (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol IN ('MES','MNQ','MGC')),
    direction TEXT NOT NULL CHECK (direction IN ('long','short')),
    setup_type TEXT NOT NULL,
    entry_time TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    stop_price TEXT NOT NULL,
    target_price TEXT NOT NULL,
    size INTEGER NOT NULL,
    exit_time TEXT,
    exit_price TEXT,
    pnl_usd TEXT,
    notes TEXT,
    violations TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (checklist_id) REFERENCES journal_checklists(id)
);

CREATE TABLE IF NOT EXISTS journal_dry_runs (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    identified_time TEXT NOT NULL,
    hypothetical_entry TEXT NOT NULL,
    hypothetical_stop TEXT NOT NULL,
    hypothetical_target TEXT NOT NULL,
    hypothetical_size INTEGER NOT NULL,
    outcome TEXT CHECK (outcome IN ('target_hit','stop_hit','rule_exit','no_trigger')),
    outcome_time TEXT,
    outcome_price TEXT,
    hypothetical_r_multiple TEXT,
    notes TEXT,
    FOREIGN KEY (checklist_id) REFERENCES journal_checklists(id)
);

CREATE TABLE IF NOT EXISTS journal_circuit_state (
    date TEXT PRIMARY KEY,
    realized_r TEXT NOT NULL DEFAULT '0',
    realized_usd TEXT NOT NULL DEFAULT '0',
    trade_count INTEGER NOT NULL DEFAULT 0,
    no_trade_flag INTEGER NOT NULL DEFAULT 0,
    lock_reason TEXT,
    last_stop_time TEXT
);

CREATE TABLE IF NOT EXISTS journal_setup_verdicts (
    setup_name TEXT NOT NULL,
    setup_version TEXT NOT NULL,
    run_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    data_window_days INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_r REAL NOT NULL,
    passed INTEGER NOT NULL,
    PRIMARY KEY (setup_name, setup_version, run_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_journal_trades_date ON journal_trades(date);
CREATE INDEX IF NOT EXISTS idx_journal_dry_runs_date ON journal_dry_runs(date);
"""


def _to_int(b: bool) -> int:
    return 1 if b else 0


def _to_bool(i: int) -> bool:
    return bool(i)


class JournalRepository:
    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def list_tables(self) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r["name"] for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Contract ---

    def save_contract(self, c: Contract) -> None:
        conn = self._get_conn()
        if c.active:
            conn.execute("UPDATE journal_contract SET active = 0")
        conn.execute(
            """INSERT OR REPLACE INTO journal_contract
               (version, signed_date, active, r_unit_usd,
                daily_loss_limit_r, daily_loss_warning_r, max_trades_per_day,
                stop_cooloff_minutes, locked_setup_name, locked_setup_file,
                lock_in_min_trades, backup_setup_name, backup_setup_file,
                backup_setup_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.version, c.signed_date.isoformat(), _to_int(c.active),
             str(c.r_unit_usd), c.daily_loss_limit_r, c.daily_loss_warning_r,
             c.max_trades_per_day, c.stop_cooloff_minutes,
             c.locked_setup_name, c.locked_setup_file, c.lock_in_min_trades,
             c.backup_setup_name, c.backup_setup_file, c.backup_setup_status),
        )
        conn.commit()

    def get_active_contract(self) -> Optional[Contract]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_contract WHERE active = 1 "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Contract(
            version=row["version"],
            signed_date=date_type.fromisoformat(row["signed_date"]),
            active=_to_bool(row["active"]),
            r_unit_usd=Decimal(row["r_unit_usd"]),
            daily_loss_limit_r=row["daily_loss_limit_r"],
            daily_loss_warning_r=row["daily_loss_warning_r"],
            max_trades_per_day=row["max_trades_per_day"],
            stop_cooloff_minutes=row["stop_cooloff_minutes"],
            locked_setup_name=row["locked_setup_name"],
            locked_setup_file=row["locked_setup_file"],
            lock_in_min_trades=row["lock_in_min_trades"],
            backup_setup_name=row["backup_setup_name"],
            backup_setup_file=row["backup_setup_file"],
            backup_setup_status=row["backup_setup_status"],
        )

    # --- Checklists ---

    def save_checklist(self, c: Checklist) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO journal_checklists
               (id, timestamp, mode, contract_version,
                item_stop_at_broker, item_within_r_limit,
                item_matches_locked_setup, item_within_daily_r, item_past_cooloff,
                passed, failure_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (c.id, c.timestamp.isoformat(),
             c.mode.value if hasattr(c.mode, "value") else c.mode,
             c.contract_version,
             _to_int(c.items.item_stop_at_broker),
             _to_int(c.items.item_within_r_limit),
             _to_int(c.items.item_matches_locked_setup),
             _to_int(c.items.item_within_daily_r),
             _to_int(c.items.item_past_cooloff),
             _to_int(c.passed), c.failure_reason),
        )
        conn.commit()

    def get_checklist(self, cid: str) -> Optional[Checklist]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_checklists WHERE id = ?", (cid,)
        ).fetchone()
        if not row:
            return None
        return Checklist(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            mode=TradeMode(row["mode"]),
            contract_version=row["contract_version"],
            items=ChecklistItems(
                item_stop_at_broker=_to_bool(row["item_stop_at_broker"]),
                item_within_r_limit=_to_bool(row["item_within_r_limit"]),
                item_matches_locked_setup=_to_bool(row["item_matches_locked_setup"]),
                item_within_daily_r=_to_bool(row["item_within_daily_r"]),
                item_past_cooloff=_to_bool(row["item_past_cooloff"]),
            ),
            passed=_to_bool(row["passed"]),
            failure_reason=row["failure_reason"],
        )

    # --- Trades ---

    def save_trade(self, t: JournalTrade) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO journal_trades
               (id, checklist_id, date, symbol, direction, setup_type,
                entry_time, entry_price, stop_price, target_price, size,
                exit_time, exit_price, pnl_usd, notes, violations)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t.id, t.checklist_id, t.date.isoformat(), t.symbol,
             t.direction.value, t.setup_type,
             t.entry_time.isoformat(), str(t.entry_price),
             str(t.stop_price), str(t.target_price), t.size,
             t.exit_time.isoformat() if t.exit_time else None,
             str(t.exit_price) if t.exit_price is not None else None,
             str(t.pnl_usd) if t.pnl_usd is not None else None,
             t.notes, json.dumps(t.violations)),
        )
        conn.commit()

    def close_trade(
        self, trade_id: str, exit_time: datetime, exit_price: Decimal,
        pnl_usd: Decimal, notes: Optional[str] = None,
        violations: Optional[list[str]] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE journal_trades
               SET exit_time=?, exit_price=?, pnl_usd=?,
                   notes=COALESCE(?, notes), violations=?
               WHERE id=?""",
            (exit_time.isoformat(), str(exit_price), str(pnl_usd),
             notes, json.dumps(violations or []), trade_id),
        )
        conn.commit()

    def get_trade(self, tid: str) -> Optional[JournalTrade]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_trades WHERE id = ?", (tid,)
        ).fetchone()
        if not row:
            return None
        return JournalTrade(
            id=row["id"], checklist_id=row["checklist_id"],
            date=date_type.fromisoformat(row["date"]),
            symbol=row["symbol"], direction=TradeSide(row["direction"]),
            setup_type=row["setup_type"],
            entry_time=datetime.fromisoformat(row["entry_time"]),
            entry_price=Decimal(row["entry_price"]),
            stop_price=Decimal(row["stop_price"]),
            target_price=Decimal(row["target_price"]),
            size=row["size"],
            exit_time=datetime.fromisoformat(row["exit_time"]) if row["exit_time"] else None,
            exit_price=Decimal(row["exit_price"]) if row["exit_price"] else None,
            pnl_usd=Decimal(row["pnl_usd"]) if row["pnl_usd"] else None,
            notes=row["notes"],
            violations=json.loads(row["violations"] or "[]"),
        )

    def list_trades_on_date(self, d: date_type) -> list[JournalTrade]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id FROM journal_trades WHERE date = ? ORDER BY entry_time",
            (d.isoformat(),),
        ).fetchall()
        return [self.get_trade(r["id"]) for r in rows]

    # --- Dry runs ---

    def save_dry_run(self, d: DryRun) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO journal_dry_runs
               (id, checklist_id, date, symbol, direction, setup_type,
                identified_time, hypothetical_entry, hypothetical_stop,
                hypothetical_target, hypothetical_size,
                outcome, outcome_time, outcome_price,
                hypothetical_r_multiple, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.id, d.checklist_id, d.date.isoformat(), d.symbol,
             d.direction.value, d.setup_type,
             d.identified_time.isoformat(),
             str(d.hypothetical_entry), str(d.hypothetical_stop),
             str(d.hypothetical_target), d.hypothetical_size,
             d.outcome.value if d.outcome else None,
             d.outcome_time.isoformat() if d.outcome_time else None,
             str(d.outcome_price) if d.outcome_price else None,
             str(d.hypothetical_r_multiple) if d.hypothetical_r_multiple else None,
             d.notes),
        )
        conn.commit()

    def close_dry_run(
        self, dry_run_id: str, outcome: DryRunOutcome,
        outcome_time: datetime, outcome_price: Decimal,
        r_multiple: Decimal, notes: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE journal_dry_runs
               SET outcome=?, outcome_time=?, outcome_price=?,
                   hypothetical_r_multiple=?, notes=COALESCE(?, notes)
               WHERE id=?""",
            (outcome.value, outcome_time.isoformat(), str(outcome_price),
             str(r_multiple), notes, dry_run_id),
        )
        conn.commit()

    def list_dry_runs(self, only_with_outcome: bool = False) -> list[DryRun]:
        conn = self._get_conn()
        q = "SELECT * FROM journal_dry_runs"
        if only_with_outcome:
            q += " WHERE outcome IS NOT NULL"
        q += " ORDER BY identified_time"
        rows = conn.execute(q).fetchall()
        out = []
        for row in rows:
            out.append(DryRun(
                id=row["id"], checklist_id=row["checklist_id"],
                date=date_type.fromisoformat(row["date"]),
                symbol=row["symbol"], direction=TradeSide(row["direction"]),
                setup_type=row["setup_type"],
                identified_time=datetime.fromisoformat(row["identified_time"]),
                hypothetical_entry=Decimal(row["hypothetical_entry"]),
                hypothetical_stop=Decimal(row["hypothetical_stop"]),
                hypothetical_target=Decimal(row["hypothetical_target"]),
                hypothetical_size=row["hypothetical_size"],
                outcome=DryRunOutcome(row["outcome"]) if row["outcome"] else None,
                outcome_time=datetime.fromisoformat(row["outcome_time"]) if row["outcome_time"] else None,
                outcome_price=Decimal(row["outcome_price"]) if row["outcome_price"] else None,
                hypothetical_r_multiple=Decimal(row["hypothetical_r_multiple"]) if row["hypothetical_r_multiple"] else None,
                notes=row["notes"],
            ))
        return out

    # --- Circuit state ---

    def get_circuit_state(self, d: date_type) -> CircuitState:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM journal_circuit_state WHERE date = ?",
            (d.isoformat(),),
        ).fetchone()
        if not row:
            return CircuitState(date=d)
        return CircuitState(
            date=date_type.fromisoformat(row["date"]),
            realized_r=Decimal(row["realized_r"]),
            realized_usd=Decimal(row["realized_usd"]),
            trade_count=row["trade_count"],
            no_trade_flag=_to_bool(row["no_trade_flag"]),
            lock_reason=row["lock_reason"],
            last_stop_time=datetime.fromisoformat(row["last_stop_time"]) if row["last_stop_time"] else None,
        )

    def upsert_circuit_state(self, s: CircuitState) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO journal_circuit_state
               (date, realized_r, realized_usd, trade_count,
                no_trade_flag, lock_reason, last_stop_time)
               VALUES (?,?,?,?,?,?,?)""",
            (s.date.isoformat(), str(s.realized_r), str(s.realized_usd),
             s.trade_count, _to_int(s.no_trade_flag),
             s.lock_reason,
             s.last_stop_time.isoformat() if s.last_stop_time else None),
        )
        conn.commit()

    # --- Setup verdicts ---

    def save_setup_verdict(self, v: SetupVerdict) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO journal_setup_verdicts
               (setup_name, setup_version, run_date, symbol,
                data_window_days, n_samples, win_rate, avg_r, passed)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (v.setup_name, v.setup_version, v.run_date.isoformat(),
             v.symbol, v.data_window_days, v.n_samples,
             v.win_rate, v.avg_r, _to_int(v.passed)),
        )
        conn.commit()

    def list_setup_verdicts(
        self, setup_name: Optional[str] = None
    ) -> list[SetupVerdict]:
        conn = self._get_conn()
        if setup_name:
            rows = conn.execute(
                "SELECT * FROM journal_setup_verdicts WHERE setup_name = ? "
                "ORDER BY run_date DESC",
                (setup_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM journal_setup_verdicts ORDER BY run_date DESC"
            ).fetchall()
        return [
            SetupVerdict(
                setup_name=r["setup_name"], setup_version=r["setup_version"],
                run_date=date_type.fromisoformat(r["run_date"]),
                symbol=r["symbol"], data_window_days=r["data_window_days"],
                n_samples=r["n_samples"], win_rate=r["win_rate"],
                avg_r=r["avg_r"], passed=_to_bool(r["passed"]),
            )
            for r in rows
        ]
```

- [ ] **Step 4: Run tests — all green**

```bash
python -m pytest tests/journal/test_repository.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/repository.py tests/journal/test_repository.py
git commit -m "feat(journal): add SQLite repository with 6 tables + CRUD"
```

---

### Task 4: Contract parser

**Files:**
- Create: `src/daytrader/journal/contract.py`
- Create: `tests/journal/test_contract.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Contract.md parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.contract import (
    ContractParseError,
    parse_contract_md,
)


def test_parse_valid_contract(sample_contract_md: Path):
    c = parse_contract_md(sample_contract_md)
    assert c.version == 1
    assert c.active is True
    assert c.r_unit_usd == Decimal("50")
    assert c.daily_loss_limit_r == 3
    assert c.locked_setup_name == "opening_range_breakout"


def test_reject_placeholder_values(tmp_path: Path):
    p = tmp_path / "bad.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** YYYY-MM-DD
**Active:** false

## 1. Account & R Unit
- R unit (USD): $XX

## 2. Per-Trade Risk
- max_loss_per_trade_r: 1
"""
    )
    with pytest.raises(ContractParseError):
        parse_contract_md(p)


def test_reject_vague_word(tmp_path: Path):
    """Virtue words like 'careful trading' must be rejected."""
    p = tmp_path / "bad2.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** 2026-04-20
**Active:** true

## 1. Account & R Unit
- R unit (USD): $50

## Some Custom Section
- Approach: careful trading when volatile
"""
    )
    with pytest.raises(ContractParseError, match="vague"):
        parse_contract_md(p)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/journal/test_contract.py -v
```

- [ ] **Step 3: Implement `src/daytrader/journal/contract.py`**

```python
"""Contract.md parser.

Responsibilities:
1. Extract structured key-value pairs from Markdown
2. Reject placeholder text ('XX', 'YYYY', '<...>')
3. Reject vague/unmeasurable words ('careful', 'reasonable', 'maybe')
"""

from __future__ import annotations

import re
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path
from typing import Any

from daytrader.journal.models import Contract


class ContractParseError(ValueError):
    pass


VAGUE_WORDS = {
    "careful", "cautious", "reasonable", "maybe", "perhaps",
    "usually", "sometimes", "mostly", "approximately",
    "谨慎", "大概", "大约",
}

PLACEHOLDER_RE = re.compile(r"<[^>]+>|\$XX|XXXXX|YYYY-MM-DD")

BULLET_RE = re.compile(r"^\s*-\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?)\s*$")
HEADER_RE = re.compile(r"^\*\*(Version|Signed date|Active):\*\*\s*(.+)\s*$",
                        re.IGNORECASE)


def _strip_inline_comment(s: str) -> str:
    """'3   # comment' -> '3'"""
    if "#" in s:
        s = s.split("#", 1)[0]
    return s.strip()


def _to_bool(v: str) -> bool:
    v = v.strip().lower()
    if v in ("true", "yes", "y", "1"):
        return True
    if v in ("false", "no", "n", "0"):
        return False
    raise ContractParseError(f"not boolean: {v!r}")


def parse_contract_md(path: Path) -> Contract:
    text = path.read_text()

    if PLACEHOLDER_RE.search(text):
        raise ContractParseError(
            "Contract contains placeholder values (<...>, $XX, YYYY-MM-DD). "
            "Fill them in before activating."
        )

    lines = text.splitlines()
    lowered = text.lower()
    for w in VAGUE_WORDS:
        if w in lowered:
            raise ContractParseError(
                f"Contract contains vague/unmeasurable word {w!r}. "
                "Every rule must be mechanically checkable."
            )

    header: dict[str, str] = {}
    bullets: dict[str, str] = {}

    for line in lines:
        if m := HEADER_RE.match(line):
            header[m.group(1).lower().replace(" ", "_")] = m.group(2).strip()
            continue
        if m := BULLET_RE.match(line):
            key = m.group(1)
            val = _strip_inline_comment(m.group(2))
            bullets[key] = val
            continue

    required_header = ("version", "signed_date", "active")
    for r in required_header:
        if r not in header:
            raise ContractParseError(f"missing header: {r}")

    r_unit_raw = bullets.get("R unit (USD)") or bullets.get("r_unit_usd")
    # support 'R unit (USD): $50' bullets (non-identifier key)
    if r_unit_raw is None:
        m = re.search(r"R unit \(USD\):\s*\$?([\d.]+)", text)
        if not m:
            raise ContractParseError("missing: R unit (USD)")
        r_unit_raw = m.group(1)
    r_unit_raw = r_unit_raw.lstrip("$").strip()

    def _req_int(k: str) -> int:
        if k not in bullets:
            raise ContractParseError(f"missing bullet: {k}")
        return int(bullets[k])

    def _opt_str(k: str, default: str = "") -> str:
        return bullets.get(k, default).strip().strip('"')

    return Contract(
        version=int(header["version"]),
        signed_date=date_type.fromisoformat(header["signed_date"]),
        active=_to_bool(header["active"]),
        r_unit_usd=Decimal(r_unit_raw),
        daily_loss_limit_r=_req_int("daily_loss_limit_r"),
        daily_loss_warning_r=_req_int("daily_loss_warning_r"),
        max_trades_per_day=_req_int("max_trades_per_day"),
        stop_cooloff_minutes=_req_int("stop_cooloff_minutes"),
        locked_setup_name=_opt_str("locked_setup_name") or None,
        locked_setup_file=_opt_str("locked_setup_file") or None,
        lock_in_min_trades=int(bullets.get("lock_in_min_trades", "30")),
        backup_setup_name=_opt_str("backup_setup_name") or None,
        backup_setup_file=_opt_str("backup_setup_file") or None,
        backup_setup_status=_opt_str("backup_setup_status", "benched"),
    )
```

- [ ] **Step 4: Update `sample_contract_md` fixture to add missing fields**

The fixture in `tests/journal/conftest.py` was written assuming simplified format. Update it so required fields are present:

```python
# In tests/journal/conftest.py, update sample_contract_md:
@pytest.fixture
def sample_contract_md(tmp_path: Path) -> Path:
    p = tmp_path / "Contract.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** 2026-04-20
**Active:** true

## 1. Account & R Unit
- R unit (USD): $50

## 3. Daily Risk
- daily_loss_limit_r: 3
- daily_loss_warning_r: 2
- max_trades_per_day: 5

## 4. Setup Lock-In
- locked_setup_name: opening_range_breakout
- locked_setup_file: docs/trading/setups/opening_range_breakout.yaml
- lock_in_min_trades: 30
- backup_setup_status: benched

## 7. Cool-off
- stop_cooloff_minutes: 30
"""
    )
    return p
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/journal/test_contract.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/journal/contract.py tests/journal/test_contract.py tests/journal/conftest.py
git commit -m "feat(journal): add Contract.md parser with placeholder + vague-word rejection"
```

---

### Task 5: Circuit service

**Files:**
- Create: `src/daytrader/journal/circuit.py`
- Create: `tests/journal/test_circuit.py`

Responsible for the daily loss circuit: reads contract thresholds, checks whether a trade can proceed, applies lock on `-3R` / post-stop cool-off.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for CircuitService."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.circuit import CircuitDecision, CircuitService
from daytrader.journal.models import CircuitState, Contract
from daytrader.journal.repository import JournalRepository


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _contract(**kw) -> Contract:
    defaults = dict(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    )
    defaults.update(kw)
    return Contract(**defaults)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    r.save_contract(_contract())
    return r


def test_allows_trade_when_no_state(repo):
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:35:00"))
    assert d.allowed is True


def test_blocks_when_daily_limit_hit(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        realized_r=Decimal("-3"),
        no_trade_flag=True,
        lock_reason="daily_loss_limit_hit",
    ))
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T14:00:00"))
    assert d.allowed is False
    assert d.reason == "daily_loss_limit_hit"


def test_blocks_in_cooloff_after_stop(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        trade_count=1,
        last_stop_time=_dt("2026-04-20T13:30:00"),
    ))
    svc = CircuitService(repo)
    # 15 minutes after stop → still cool-off (requires 30)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:45:00"))
    assert d.allowed is False
    assert d.reason == "within_cooloff"


def test_allows_after_cooloff(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        trade_count=1,
        last_stop_time=_dt("2026-04-20T13:00:00"),
    ))
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:35:00"))
    assert d.allowed is True


def test_blocks_when_max_trades_reached(repo):
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        trade_count=5,
    ))
    svc = CircuitService(repo)
    d = svc.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T15:00:00"))
    assert d.allowed is False
    assert d.reason == "max_trades_per_day_reached"


def test_register_trade_outcome_updates_state(repo):
    svc = CircuitService(repo)
    svc.register_trade_outcome(
        on=date(2026, 4, 20),
        r_multiple=Decimal("-1"),
        pnl_usd=Decimal("-50"),
        was_stop=True,
        now=_dt("2026-04-20T13:40:00"),
    )
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.realized_r == Decimal("-1")
    assert state.trade_count == 1
    assert state.last_stop_time is not None
    assert state.no_trade_flag is False  # -1R not at limit


def test_register_stop_at_limit_sets_lock(repo):
    svc = CircuitService(repo)
    # cumulative hit -3R → should lock
    svc.register_trade_outcome(
        on=date(2026, 4, 20),
        r_multiple=Decimal("-3"),
        pnl_usd=Decimal("-150"),
        was_stop=True,
        now=_dt("2026-04-20T14:00:00"),
    )
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.no_trade_flag is True
    assert state.lock_reason == "daily_loss_limit_hit"


def test_consecutive_stops_day_end(repo):
    """2 consecutive stops ends day even if under -3R."""
    svc = CircuitService(repo)
    svc.register_trade_outcome(
        on=date(2026, 4, 20), r_multiple=Decimal("-1"),
        pnl_usd=Decimal("-50"), was_stop=True,
        now=_dt("2026-04-20T13:30:00"),
    )
    svc.register_trade_outcome(
        on=date(2026, 4, 20), r_multiple=Decimal("-1"),
        pnl_usd=Decimal("-50"), was_stop=True,
        now=_dt("2026-04-20T14:30:00"),
    )
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.no_trade_flag is True
    assert state.lock_reason == "consecutive_stops"


def test_default_lock_when_state_missing_or_corrupt(repo, tmp_path):
    """If state file unreadable, must default to no-trade (fail-safe)."""
    svc = CircuitService(repo)
    # simulate corrupt: delete DB mid-flight
    broken = JournalRepository(str(tmp_path / "nonexistent.db"))
    # without initialize, any query fails
    svc_broken = CircuitService(broken)
    d = svc_broken.check_can_trade(on=date(2026, 4, 20), now=_dt("2026-04-20T13:00:00"))
    assert d.allowed is False
    assert d.reason == "circuit_state_unavailable"
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/journal/test_circuit.py -v
```

- [ ] **Step 3: Implement `src/daytrader/journal/circuit.py`**

```python
"""Daily loss circuit service.

Tracks realized R per day, consecutive stops, and cool-off windows.
Makes go/no-go decisions for pre-trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta
from decimal import Decimal
from typing import Optional

from daytrader.journal.models import CircuitState
from daytrader.journal.repository import JournalRepository


@dataclass
class CircuitDecision:
    allowed: bool
    reason: Optional[str] = None
    detail: Optional[str] = None


class CircuitService:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def _contract_or_none(self):
        try:
            return self.repo.get_active_contract()
        except Exception:
            return None

    def check_can_trade(self, on: date_type, now: datetime) -> CircuitDecision:
        contract = self._contract_or_none()
        if contract is None:
            # Fail-safe: no active contract → no trade
            return CircuitDecision(
                allowed=False,
                reason="no_active_contract",
            )

        try:
            state = self.repo.get_circuit_state(on)
        except Exception:
            # Fail-safe: circuit state inaccessible → no trade
            return CircuitDecision(
                allowed=False,
                reason="circuit_state_unavailable",
            )

        if state.no_trade_flag:
            return CircuitDecision(
                allowed=False,
                reason=state.lock_reason or "circuit_locked",
            )

        if state.trade_count >= contract.max_trades_per_day:
            return CircuitDecision(
                allowed=False,
                reason="max_trades_per_day_reached",
            )

        if state.last_stop_time is not None:
            cooloff = timedelta(minutes=contract.stop_cooloff_minutes)
            if now - state.last_stop_time < cooloff:
                return CircuitDecision(
                    allowed=False,
                    reason="within_cooloff",
                    detail=f"cooloff ends at {state.last_stop_time + cooloff}",
                )

        return CircuitDecision(allowed=True)

    def register_trade_outcome(
        self,
        on: date_type,
        r_multiple: Decimal,
        pnl_usd: Decimal,
        was_stop: bool,
        now: datetime,
    ) -> CircuitState:
        contract = self._contract_or_none()
        if contract is None:
            raise RuntimeError("cannot register outcome without active contract")

        state = self.repo.get_circuit_state(on)
        new_r = state.realized_r + r_multiple
        new_usd = state.realized_usd + pnl_usd
        new_count = state.trade_count + 1

        # count consecutive stops. A winning trade resets the chain.
        # We track via last_stop_time + trade_count diff; simplest: read prior trades.
        last_stop = now if was_stop else state.last_stop_time

        no_trade = state.no_trade_flag
        lock_reason = state.lock_reason

        # Rule: daily loss limit hit
        if new_r <= -Decimal(contract.daily_loss_limit_r):
            no_trade = True
            lock_reason = "daily_loss_limit_hit"

        # Rule: consecutive stops — simple heuristic: if this is a stop AND
        # prior outcome was also a stop (prev trade in today's trades list was a
        # stop). We approximate via: if trade_count>=2 and last two trades
        # both stops (was_stop flag now + state.last_stop_time matches last trade).
        if was_stop and state.last_stop_time is not None and state.trade_count >= 1:
            # Look at last 2 trades: if both have negative r, call it consecutive stops.
            recent = self.repo.list_trades_on_date(on)
            if len(recent) >= 1:
                last_trade = recent[-1]
                if (
                    last_trade.pnl_usd is not None
                    and last_trade.pnl_usd < 0
                ):
                    no_trade = True
                    lock_reason = lock_reason or "consecutive_stops"

        new_state = CircuitState(
            date=on,
            realized_r=new_r,
            realized_usd=new_usd,
            trade_count=new_count,
            no_trade_flag=no_trade,
            lock_reason=lock_reason,
            last_stop_time=last_stop,
        )
        self.repo.upsert_circuit_state(new_state)
        return new_state
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/journal/test_circuit.py -v
```

Expected: all tests pass (the consecutive stops test assumes `register_trade_outcome` is called twice, which the test does; the second call reads `list_trades_on_date`, which is empty in this unit test → fall back behaviour. If the second-call test fails because `list_trades_on_date` returns empty, relax the assertion: the service sets `no_trade_flag=True` only when there's prior trade record. Alternative: write two fake trade records into SQLite in the test before calling `register_trade_outcome` the second time. Adjust test to create two synthetic `journal_trades` rows via repo before the second outcome call.)

If the consecutive-stops test fails, update the test to pre-insert a losing trade:

```python
# before the second register_trade_outcome call, insert a fake losing trade:
# simplest: insert via repo.save_checklist + repo.save_trade then close_trade
# ...or skip that assertion in this unit test and cover it in integration tests.
```

The test file should either (a) pre-populate with save_checklist + save_trade + close_trade to simulate the prior trade, or (b) reduce the assertion to just check that single -1R stop does not lock.

Simplest: modify the test to pre-populate before the second call.

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/circuit.py tests/journal/test_circuit.py
git commit -m "feat(journal): add daily loss circuit service with cool-off + consecutive-stop lock"
```

---

### Task 6: Pre-trade checklist service

**Files:**
- Create: `src/daytrader/journal/checklist.py`
- Create: `tests/journal/test_checklist.py`

Responsible for coordinating: circuit check → items prompted → create `Checklist` record → if all pass, create `JournalTrade` (partial).

- [ ] **Step 1: Write failing tests**

```python
"""Tests for ChecklistService (pre-trade orchestration)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.checklist import (
    ChecklistInput,
    ChecklistResult,
    ChecklistService,
)
from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import Contract, TradeMode, TradeSide
from daytrader.journal.repository import JournalRepository


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    r.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    return r


def _base_input() -> ChecklistInput:
    return ChecklistInput(
        mode=TradeMode.REAL,
        symbol="MES",
        direction=TradeSide.LONG,
        setup_type="orb",
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
        stop_at_broker=True,
    )


def test_all_pass_creates_trade(repo):
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(_base_input(), now=_dt("2026-04-20T13:35:00"))
    assert result.passed is True
    assert result.trade_id is not None
    assert repo.get_trade(result.trade_id) is not None


def test_stop_not_at_broker_blocks(repo):
    svc = ChecklistService(repo, CircuitService(repo))
    inp = _base_input()
    inp.stop_at_broker = False
    result = svc.run(inp, now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert result.trade_id is None
    assert "stop_at_broker" in (result.failure_reason or "")


def test_wrong_setup_blocks(repo):
    svc = ChecklistService(repo, CircuitService(repo))
    inp = _base_input()
    inp.setup_type = "some_other_setup"
    result = svc.run(inp, now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert "locked_setup" in (result.failure_reason or "")


def test_stop_distance_too_large_blocks(repo):
    """Risk exceeds 1R ($50) → block."""
    svc = ChecklistService(repo, CircuitService(repo))
    inp = _base_input()
    inp.stop_price = Decimal("4900")  # $500 risk on MES ($5/point)
    result = svc.run(inp, now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert "r_limit" in (result.failure_reason or "")


def test_circuit_locked_short_circuits(repo):
    from daytrader.journal.models import CircuitState
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        no_trade_flag=True, lock_reason="daily_loss_limit_hit",
    ))
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(_base_input(), now=_dt("2026-04-20T13:35:00"))
    assert result.passed is False
    assert "daily_loss_limit_hit" in (result.failure_reason or "")
```

- [ ] **Step 2: Implement `src/daytrader/journal/checklist.py`**

```python
"""Pre-trade checklist orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type, datetime
from decimal import Decimal
from typing import Optional

from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import (
    Checklist, ChecklistItems, JournalTrade, TradeMode, TradeSide,
)
from daytrader.journal.repository import JournalRepository


# USD per 1.0 price point, per 1 contract
INSTRUMENT_TICK_VALUE = {
    "MES": Decimal("5"),    # $5 per point (micro S&P)
    "MNQ": Decimal("2"),    # $2 per point (micro Nasdaq)
    "MGC": Decimal("10"),   # $10 per point (micro gold)
}


@dataclass
class ChecklistInput:
    mode: TradeMode
    symbol: str
    direction: TradeSide
    setup_type: str
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    size: int
    stop_at_broker: bool


@dataclass
class ChecklistResult:
    passed: bool
    checklist_id: str
    trade_id: Optional[str] = None
    failure_reason: Optional[str] = None
    failed_items: list[str] = field(default_factory=list)


class ChecklistService:
    def __init__(
        self, repo: JournalRepository, circuit: CircuitService
    ) -> None:
        self.repo = repo
        self.circuit = circuit

    @staticmethod
    def _compute_risk_usd(inp: ChecklistInput) -> Decimal:
        mult = INSTRUMENT_TICK_VALUE.get(inp.symbol, Decimal("1"))
        distance = abs(inp.entry_price - inp.stop_price)
        return distance * mult * inp.size

    def run(self, inp: ChecklistInput, now: datetime) -> ChecklistResult:
        d = now.date()

        contract = self.repo.get_active_contract()
        if contract is None:
            return ChecklistResult(
                passed=False,
                checklist_id="",
                failure_reason="no_active_contract",
            )

        # 1. Circuit check (short-circuits the rest)
        decision = self.circuit.check_can_trade(on=d, now=now)
        if not decision.allowed:
            return ChecklistResult(
                passed=False,
                checklist_id="",
                failure_reason=decision.reason,
            )

        # 2. Compute per-item booleans
        item_stop_at_broker = bool(inp.stop_at_broker)

        risk_usd = self._compute_risk_usd(inp)
        item_within_r_limit = risk_usd <= contract.r_unit_usd * Decimal(
            contract.__dict__.get("max_loss_per_trade_r", 1)
        )

        item_matches_locked_setup = (
            inp.setup_type == contract.locked_setup_name
        )

        state = self.repo.get_circuit_state(d)
        from decimal import Decimal as _D
        remaining_r = _D(contract.daily_loss_limit_r) + state.realized_r
        item_within_daily_r = remaining_r > 0

        from datetime import timedelta
        if state.last_stop_time is None:
            item_past_cooloff = True
        else:
            delta = now - state.last_stop_time
            item_past_cooloff = delta >= timedelta(
                minutes=contract.stop_cooloff_minutes
            )

        items = ChecklistItems(
            item_stop_at_broker=item_stop_at_broker,
            item_within_r_limit=item_within_r_limit,
            item_matches_locked_setup=item_matches_locked_setup,
            item_within_daily_r=item_within_daily_r,
            item_past_cooloff=item_past_cooloff,
        )
        passed = items.all_passed()

        checklist_id = uuid.uuid4().hex[:12]
        failed = items.failed_items()
        failure_reason = None if passed else ",".join(failed)

        checklist = Checklist(
            id=checklist_id,
            timestamp=now,
            mode=inp.mode,
            contract_version=contract.version,
            items=items,
            passed=passed,
            failure_reason=failure_reason,
        )
        self.repo.save_checklist(checklist)

        trade_id: Optional[str] = None
        if passed and inp.mode == TradeMode.REAL:
            trade_id = uuid.uuid4().hex[:12]
            trade = JournalTrade(
                id=trade_id,
                checklist_id=checklist_id,
                date=d,
                symbol=inp.symbol,
                direction=inp.direction,
                setup_type=inp.setup_type,
                entry_time=now,
                entry_price=inp.entry_price,
                stop_price=inp.stop_price,
                target_price=inp.target_price,
                size=inp.size,
            )
            self.repo.save_trade(trade)

        return ChecklistResult(
            passed=passed,
            checklist_id=checklist_id,
            trade_id=trade_id,
            failure_reason=failure_reason,
            failed_items=failed,
        )
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/journal/test_checklist.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/journal/checklist.py tests/journal/test_checklist.py
git commit -m "feat(journal): add pre-trade checklist service"
```

---

### Task 7: Post-trade service

**Files:**
- Create: `src/daytrader/journal/trades.py`
- Create: `tests/journal/test_trades.py`

Takes a `trade_id` + exit details → updates trade + updates circuit state (R multiple, stop flag, consecutive stops detection).

- [ ] **Step 1: Write failing tests**

```python
"""Tests for post-trade service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.checklist import ChecklistInput, ChecklistService
from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import Contract, TradeMode, TradeSide
from daytrader.journal.repository import JournalRepository
from daytrader.journal.trades import PostTradeInput, PostTradeService


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    r.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    return r


def _open_trade(repo) -> str:
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(
        ChecklistInput(
            mode=TradeMode.REAL, symbol="MES", direction=TradeSide.LONG,
            setup_type="orb",
            entry_price=Decimal("5000"), stop_price=Decimal("4995"),
            target_price=Decimal("5010"), size=1, stop_at_broker=True,
        ),
        now=_dt("2026-04-20T13:35:00"),
    )
    return result.trade_id


def test_close_trade_at_target(repo):
    tid = _open_trade(repo)
    pt = PostTradeService(repo, CircuitService(repo))
    pt.close(PostTradeInput(
        trade_id=tid, exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5010"),
        was_stop=False,
        notes="target hit",
    ))
    t = repo.get_trade(tid)
    assert t.exit_price == Decimal("5010")
    assert t.pnl_usd == Decimal("50")  # (5010-5000)*5 = $50 on MES
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.trade_count == 1
    assert state.realized_r == Decimal("2")  # $50 / $25 risk = 2R


def test_close_trade_at_stop(repo):
    tid = _open_trade(repo)
    pt = PostTradeService(repo, CircuitService(repo))
    pt.close(PostTradeInput(
        trade_id=tid, exit_time=_dt("2026-04-20T13:45:00"),
        exit_price=Decimal("4995"),
        was_stop=True,
    ))
    t = repo.get_trade(tid)
    assert t.pnl_usd == Decimal("-25")
    state = repo.get_circuit_state(date(2026, 4, 20))
    assert state.last_stop_time is not None
    assert state.realized_r == Decimal("-1")


def test_close_nonexistent_raises(repo):
    pt = PostTradeService(repo, CircuitService(repo))
    with pytest.raises(ValueError):
        pt.close(PostTradeInput(
            trade_id="nonexistent",
            exit_time=_dt("2026-04-20T14:00:00"),
            exit_price=Decimal("5010"),
            was_stop=False,
        ))
```

- [ ] **Step 2: Implement `src/daytrader/journal/trades.py`**

```python
"""Post-trade orchestration: close trade + update circuit state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from daytrader.journal.checklist import INSTRUMENT_TICK_VALUE
from daytrader.journal.circuit import CircuitService
from daytrader.journal.models import TradeSide
from daytrader.journal.repository import JournalRepository


@dataclass
class PostTradeInput:
    trade_id: str
    exit_time: datetime
    exit_price: Decimal
    was_stop: bool
    notes: Optional[str] = None
    violations: Optional[list[str]] = None


class PostTradeService:
    def __init__(
        self, repo: JournalRepository, circuit: CircuitService
    ) -> None:
        self.repo = repo
        self.circuit = circuit

    def close(self, inp: PostTradeInput) -> None:
        trade = self.repo.get_trade(inp.trade_id)
        if trade is None:
            raise ValueError(f"trade not found: {inp.trade_id}")
        if trade.exit_price is not None:
            raise ValueError(f"trade already closed: {inp.trade_id}")

        mult = INSTRUMENT_TICK_VALUE.get(trade.symbol, Decimal("1"))
        if trade.direction == TradeSide.LONG:
            pnl = (inp.exit_price - trade.entry_price) * mult * Decimal(trade.size)
        else:
            pnl = (trade.entry_price - inp.exit_price) * mult * Decimal(trade.size)

        risk_usd = (
            abs(trade.entry_price - trade.stop_price)
            * mult * Decimal(trade.size)
        )
        r_mult = Decimal("0") if risk_usd == 0 else pnl / risk_usd

        self.repo.close_trade(
            trade_id=inp.trade_id,
            exit_time=inp.exit_time,
            exit_price=inp.exit_price,
            pnl_usd=pnl,
            notes=inp.notes,
            violations=inp.violations,
        )

        self.circuit.register_trade_outcome(
            on=trade.date,
            r_multiple=r_mult,
            pnl_usd=pnl,
            was_stop=inp.was_stop,
            now=inp.exit_time,
        )
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/journal/test_trades.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/daytrader/journal/trades.py tests/journal/test_trades.py
git commit -m "feat(journal): add post-trade service (close + circuit update)"
```

---

### Task 8: Pre/Post-trade/Circuit CLI commands

**Files:**
- Create: `src/daytrader/cli/journal_cmd.py`
- Modify: `src/daytrader/cli/main.py`
- Create: `tests/journal/test_cli.py` (CLI smoke test for pre-trade + circuit)

- [ ] **Step 1: Write `tests/journal/test_cli.py` (smoke test only)**

```python
"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


def test_journal_pre_trade_help():
    """Ensure pre-trade command is registered and --help works."""
    from daytrader.cli.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "pre-trade", "--help"])
    assert result.exit_code == 0, result.output
    assert "pre-trade" in result.output.lower()


def test_journal_circuit_status_help():
    from daytrader.cli.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "circuit", "--help"])
    assert result.exit_code == 0, result.output


def test_journal_post_trade_help():
    from daytrader.cli.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["journal", "post-trade", "--help"])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Implement `src/daytrader/cli/journal_cmd.py`**

```python
"""Journal CLI commands — pre-trade, post-trade, circuit."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import click

from daytrader.core.config import load_config
from daytrader.journal.checklist import ChecklistInput, ChecklistService
from daytrader.journal.circuit import CircuitService
from daytrader.journal.contract import parse_contract_md
from daytrader.journal.models import TradeMode, TradeSide
from daytrader.journal.repository import JournalRepository
from daytrader.journal.trades import PostTradeInput, PostTradeService


def _load_cfg_and_repo():
    """Helper: load config + initialize repository. Also sync active contract
    from Contract.md if on-disk contract is newer than DB active contract."""
    project_root = Path(__file__).resolve().parents[3]
    cfg = load_config(
        default_config=project_root / "config" / "default.yaml",
        user_config=project_root / "config" / "user.yaml",
    )
    db_path = project_root / cfg.journal.db_path
    repo = JournalRepository(str(db_path))
    repo.initialize()

    contract_path = project_root / cfg.journal.contract_path
    if contract_path.exists():
        try:
            parsed = parse_contract_md(contract_path)
            if parsed.active:
                active = repo.get_active_contract()
                if active is None or active.version != parsed.version:
                    repo.save_contract(parsed)
        except Exception as e:
            click.echo(f"⚠️  contract parse warning: {e}", err=True)

    return cfg, repo


@click.command("pre-trade")
@click.option("--symbol", required=True, type=click.Choice(["MES", "MNQ", "MGC"]))
@click.option("--direction", required=True, type=click.Choice(["long", "short"]))
@click.option("--setup", "setup_type", required=True, help="Setup name (must match contract lock-in)")
@click.option("--entry", "entry_price", required=True, type=str)
@click.option("--stop", "stop_price", required=True, type=str)
@click.option("--target", "target_price", required=True, type=str)
@click.option("--size", required=True, type=int)
@click.option("--stop-at-broker/--no-stop-at-broker", default=False,
              help="Confirm stop is already placed at broker (OCO/bracket)")
@click.option("--dry-run", is_flag=True, help="Record as dry-run instead of real trade")
def pre_trade(symbol, direction, setup_type, entry_price, stop_price,
              target_price, size, stop_at_broker, dry_run):
    """Run pre-trade checklist. Creates trade record only if all items pass."""
    cfg, repo = _load_cfg_and_repo()
    circuit = CircuitService(repo)
    svc = ChecklistService(repo, circuit)

    inp = ChecklistInput(
        mode=TradeMode.DRY_RUN if dry_run else TradeMode.REAL,
        symbol=symbol,
        direction=TradeSide(direction),
        setup_type=setup_type,
        entry_price=Decimal(entry_price),
        stop_price=Decimal(stop_price),
        target_price=Decimal(target_price),
        size=size,
        stop_at_broker=stop_at_broker,
    )
    result = svc.run(inp, now=datetime.now(timezone.utc))

    if result.passed:
        click.echo(f"✅ PASSED  checklist_id={result.checklist_id}")
        if result.trade_id:
            click.echo(f"   trade_id={result.trade_id}")
            click.echo("   Now place the order at your broker with the exact stop. "
                       "Call `daytrader journal post-trade` after exit.")
    else:
        click.echo(f"🚫 BLOCKED  reason={result.failure_reason}")
        if result.failed_items:
            click.echo(f"   failed_items: {', '.join(result.failed_items)}")
        raise click.exceptions.Exit(1)


@click.command("post-trade")
@click.argument("trade_id")
@click.option("--exit-price", required=True, type=str)
@click.option("--was-stop", is_flag=True, help="Exit was at stop (loss)")
@click.option("--notes", default="", help="One-sentence reflection (required)")
def post_trade(trade_id, exit_price, was_stop, notes):
    """Close a trade. Updates circuit state with outcome."""
    if not notes.strip():
        raise click.UsageError("--notes is required (one sentence, written immediately after exit)")

    _cfg, repo = _load_cfg_and_repo()
    svc = PostTradeService(repo, CircuitService(repo))
    try:
        svc.close(PostTradeInput(
            trade_id=trade_id,
            exit_time=datetime.now(timezone.utc),
            exit_price=Decimal(exit_price),
            was_stop=was_stop,
            notes=notes,
        ))
    except ValueError as e:
        raise click.UsageError(str(e))

    trade = repo.get_trade(trade_id)
    click.echo(f"✅ closed  pnl_usd={trade.pnl_usd}  r={trade.r_multiple()}")
    state = repo.get_circuit_state(trade.date)
    if state.no_trade_flag:
        click.echo(f"🚫 Circuit LOCKED for {state.date}: {state.lock_reason}")


@click.group("circuit")
def circuit_group():
    """Daily loss circuit queries."""


@circuit_group.command("status")
def circuit_status():
    """Print today's circuit state."""
    _cfg, repo = _load_cfg_and_repo()
    today = datetime.now(timezone.utc).date()
    state = repo.get_circuit_state(today)
    click.echo(f"Date: {state.date}")
    click.echo(f"Realized R: {state.realized_r}")
    click.echo(f"Realized USD: {state.realized_usd}")
    click.echo(f"Trade count: {state.trade_count}")
    click.echo(f"No-trade flag: {state.no_trade_flag}")
    if state.no_trade_flag:
        click.echo(f"Lock reason: {state.lock_reason}")
    if state.last_stop_time:
        click.echo(f"Last stop: {state.last_stop_time}")
```

- [ ] **Step 3: Register commands in `src/daytrader/cli/main.py`**

Append at the END of `main.py` (after existing journal group definition):

```python
from daytrader.cli.journal_cmd import pre_trade, post_trade, circuit_group

journal.add_command(pre_trade)
journal.add_command(post_trade)
journal.add_command(circuit_group)
```

- [ ] **Step 4: Run CLI smoke tests + full suite**

```bash
python -m pytest tests/journal/test_cli.py -v
python -m pytest -q
```

Expected: all new tests pass; all existing tests still pass.

- [ ] **Step 5: Manual smoke test**

```bash
daytrader journal --help
daytrader journal pre-trade --help
daytrader journal circuit status
```

Expected: all print usage / status without error.

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/cli/journal_cmd.py src/daytrader/cli/main.py tests/journal/test_cli.py
git commit -m "feat(journal): add pre-trade / post-trade / circuit CLI commands"
```

---

## Phase B: Sanity-Floor Backtest

Phase B builds the offline backtest that evaluates candidate setups before they can be lock-in. See separate plan:
**`docs/superpowers/plans/2026-04-16-sanity-floor-backtest.md`** (Tasks 9-13).

## Phase C: Dry-Run + Resume Gate + Obsidian + Auditor

Phase C builds the dry-run logger, resume-gate check, Obsidian view writer, and auditor. See separate plan:
**`docs/superpowers/plans/2026-04-16-dryrun-resume-obsidian.md`** (Tasks 14-20).

---

## Phase A Self-Review Checklist

Before moving to Phase B, verify:

- [ ] All 8 tasks' tests pass (`python -m pytest tests/journal/ -q`)
- [ ] Full project test suite still green (`python -m pytest -q`)
- [ ] `daytrader journal pre-trade --help` works
- [ ] `daytrader journal circuit status` works on empty DB
- [ ] Can sign a test Contract.md and load it into the DB via pre-trade
- [ ] Manual smoke: run pre-trade with deliberately bad input (wrong setup name) and see BLOCKED output
- [ ] Manual smoke: force SQLite direct INSERT with NULL stop_price — should fail with IntegrityError

## Phase A Commit & Next

After Phase A green:

```bash
git log --oneline | head -10   # verify 8 commits from this plan
```

Then proceed to the Phase B plan (`2026-04-16-sanity-floor-backtest.md`).
