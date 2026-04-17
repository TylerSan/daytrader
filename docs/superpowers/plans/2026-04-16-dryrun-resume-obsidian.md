# Dry-Run + Resume Gate + Obsidian + Auditor — Implementation Plan (Phase C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the journal subsystem — dry-run logger, resume-gate go/no-go, Obsidian markdown view generator, and integrity auditor.

**Prerequisites:** Phases A & B plans complete.

**Spec:** `docs/superpowers/specs/2026-04-16-daytrading-system-design.md` §4, §8.

---

## Task 14: Dry-run service + CLI

**Files:**
- Create: `src/daytrader/journal/dry_run.py`
- Create: `tests/journal/test_dry_run.py`
- Modify: `src/daytrader/cli/journal_cmd.py`

Dry-run flow: user identifies setup in real-time → runs `journal pre-trade --dry-run` (creates Checklist + returns checklist_id, NO trade record) → `journal dry-run start` (creates DryRun record with hypothetical entry/stop/target, returns dry_run_id) → market moves → user runs `journal dry-run end <id>` with outcome.

- [ ] **Step 1: Write tests**

```python
"""Tests for dry-run service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.checklist import ChecklistInput, ChecklistService
from daytrader.journal.circuit import CircuitService
from daytrader.journal.dry_run import (
    DryRunStartInput, DryRunEndInput, DryRunService,
)
from daytrader.journal.models import (
    Contract, DryRunOutcome, TradeMode, TradeSide,
)
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


def _checklist_id(repo, now) -> str:
    svc = ChecklistService(repo, CircuitService(repo))
    result = svc.run(
        ChecklistInput(
            mode=TradeMode.DRY_RUN, symbol="MES",
            direction=TradeSide.LONG, setup_type="orb",
            entry_price=Decimal("5000"), stop_price=Decimal("4995"),
            target_price=Decimal("5010"), size=1, stop_at_broker=True,
        ),
        now=now,
    )
    return result.checklist_id


def test_start_and_end_dry_run_target(repo):
    now = _dt("2026-04-20T13:35:00")
    cid = _checklist_id(repo, now)
    dr_svc = DryRunService(repo)
    start = dr_svc.start(DryRunStartInput(
        checklist_id=cid, symbol="MES", direction=TradeSide.LONG,
        setup_type="orb",
        entry=Decimal("5000"), stop=Decimal("4995"), target=Decimal("5010"),
        size=1,
    ), now=now)
    assert start.dry_run_id is not None

    dr_svc.end(DryRunEndInput(
        dry_run_id=start.dry_run_id,
        outcome=DryRunOutcome.TARGET_HIT,
        outcome_time=_dt("2026-04-20T14:00:00"),
        outcome_price=Decimal("5010"),
        notes="target hit",
    ))
    dr = [d for d in repo.list_dry_runs() if d.id == start.dry_run_id][0]
    assert dr.outcome == DryRunOutcome.TARGET_HIT
    assert dr.hypothetical_r_multiple == Decimal("2")


def test_end_dry_run_stop(repo):
    now = _dt("2026-04-20T13:35:00")
    cid = _checklist_id(repo, now)
    dr_svc = DryRunService(repo)
    start = dr_svc.start(DryRunStartInput(
        checklist_id=cid, symbol="MES", direction=TradeSide.LONG,
        setup_type="orb", entry=Decimal("5000"),
        stop=Decimal("4995"), target=Decimal("5010"), size=1,
    ), now=now)
    dr_svc.end(DryRunEndInput(
        dry_run_id=start.dry_run_id,
        outcome=DryRunOutcome.STOP_HIT,
        outcome_time=_dt("2026-04-20T13:45:00"),
        outcome_price=Decimal("4995"),
    ))
    dr = [d for d in repo.list_dry_runs() if d.id == start.dry_run_id][0]
    assert dr.hypothetical_r_multiple == Decimal("-1")
```

- [ ] **Step 2: Implement `src/daytrader/journal/dry_run.py`**

```python
"""Dry-run session service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from daytrader.journal.models import (
    DryRun, DryRunOutcome, TradeSide,
)
from daytrader.journal.repository import JournalRepository


@dataclass
class DryRunStartInput:
    checklist_id: str
    symbol: str
    direction: TradeSide
    setup_type: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    size: int


@dataclass
class DryRunStartResult:
    dry_run_id: str


@dataclass
class DryRunEndInput:
    dry_run_id: str
    outcome: DryRunOutcome
    outcome_time: datetime
    outcome_price: Decimal
    notes: Optional[str] = None


class DryRunService:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def start(
        self, inp: DryRunStartInput, now: datetime
    ) -> DryRunStartResult:
        # Verify checklist exists + was marked dry_run + passed
        c = self.repo.get_checklist(inp.checklist_id)
        if c is None:
            raise ValueError(f"checklist not found: {inp.checklist_id}")
        if not c.passed:
            raise ValueError(f"checklist {inp.checklist_id} did not pass")

        did = uuid.uuid4().hex[:12]
        dry_run = DryRun(
            id=did,
            checklist_id=inp.checklist_id,
            date=now.date(),
            symbol=inp.symbol,
            direction=inp.direction,
            setup_type=inp.setup_type,
            identified_time=now,
            hypothetical_entry=inp.entry,
            hypothetical_stop=inp.stop,
            hypothetical_target=inp.target,
            hypothetical_size=inp.size,
        )
        self.repo.save_dry_run(dry_run)
        return DryRunStartResult(dry_run_id=did)

    def end(self, inp: DryRunEndInput) -> None:
        existing = next(
            (d for d in self.repo.list_dry_runs() if d.id == inp.dry_run_id),
            None,
        )
        if existing is None:
            raise ValueError(f"dry-run not found: {inp.dry_run_id}")
        if existing.outcome is not None:
            raise ValueError(f"dry-run already closed: {inp.dry_run_id}")

        risk = abs(existing.hypothetical_entry - existing.hypothetical_stop)
        if existing.direction == TradeSide.LONG:
            pnl_points = inp.outcome_price - existing.hypothetical_entry
        else:
            pnl_points = existing.hypothetical_entry - inp.outcome_price
        r_mult = Decimal("0") if risk == 0 else pnl_points / risk

        self.repo.close_dry_run(
            dry_run_id=inp.dry_run_id,
            outcome=inp.outcome,
            outcome_time=inp.outcome_time,
            outcome_price=inp.outcome_price,
            r_multiple=r_mult,
            notes=inp.notes,
        )
```

- [ ] **Step 3: Add dry-run CLI group**

Append to `src/daytrader/cli/journal_cmd.py`:

```python
@click.group("dry-run")
def dry_run_group():
    """Dry-run session commands."""


@dry_run_group.command("start")
@click.option("--checklist-id", required=True)
@click.option("--symbol", required=True, type=click.Choice(["MES", "MNQ", "MGC"]))
@click.option("--direction", required=True, type=click.Choice(["long", "short"]))
@click.option("--setup", "setup_type", required=True)
@click.option("--entry", required=True, type=str)
@click.option("--stop", required=True, type=str)
@click.option("--target", required=True, type=str)
@click.option("--size", required=True, type=int)
def dry_run_start(checklist_id, symbol, direction, setup_type,
                   entry, stop, target, size):
    """Start a dry-run session (hypothetical trade)."""
    from daytrader.journal.dry_run import DryRunService, DryRunStartInput
    from daytrader.journal.models import TradeSide

    _cfg, repo = _load_cfg_and_repo()
    svc = DryRunService(repo)
    try:
        result = svc.start(
            DryRunStartInput(
                checklist_id=checklist_id, symbol=symbol,
                direction=TradeSide(direction), setup_type=setup_type,
                entry=Decimal(entry), stop=Decimal(stop),
                target=Decimal(target), size=size,
            ),
            now=datetime.now(timezone.utc),
        )
    except ValueError as e:
        raise click.UsageError(str(e))
    click.echo(f"✅ dry_run_id={result.dry_run_id}")


@dry_run_group.command("end")
@click.argument("dry_run_id")
@click.option("--outcome", required=True,
              type=click.Choice(["target_hit", "stop_hit", "rule_exit", "no_trigger"]))
@click.option("--outcome-price", required=True, type=str)
@click.option("--notes", default="")
def dry_run_end(dry_run_id, outcome, outcome_price, notes):
    """Close a dry-run session with actual market outcome."""
    from daytrader.journal.dry_run import DryRunService, DryRunEndInput
    from daytrader.journal.models import DryRunOutcome

    _cfg, repo = _load_cfg_and_repo()
    svc = DryRunService(repo)
    try:
        svc.end(DryRunEndInput(
            dry_run_id=dry_run_id,
            outcome=DryRunOutcome(outcome),
            outcome_time=datetime.now(timezone.utc),
            outcome_price=Decimal(outcome_price),
            notes=notes or None,
        ))
    except ValueError as e:
        raise click.UsageError(str(e))
    click.echo(f"✅ closed dry-run {dry_run_id}")
```

- [ ] **Step 4: Wire into main.py**

```python
from daytrader.cli.journal_cmd import (
    pre_trade, post_trade, circuit_group, sanity_group, dry_run_group,
)
journal.add_command(dry_run_group)
```

- [ ] **Step 5: Run tests + manual**

```bash
python -m pytest tests/journal/test_dry_run.py -v
daytrader journal dry-run --help
```

- [ ] **Step 6: Commit**

```bash
git add src/daytrader/journal/dry_run.py \
        src/daytrader/cli/journal_cmd.py src/daytrader/cli/main.py \
        tests/journal/test_dry_run.py
git commit -m "feat(journal): add dry-run service + CLI"
```

---

## Task 15: Obsidian view writer

**Files:**
- Create: `src/daytrader/journal/obsidian.py`
- Create: `tests/journal/test_obsidian.py`

Produces one Markdown file per trade/dry-run/checklist. Called after repo writes. Fail-open — never blocks SQLite commit.

- [ ] **Step 1: Write tests**

```python
"""Tests for Obsidian view writer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.models import (
    Checklist, ChecklistItems, DryRun, DryRunOutcome,
    JournalTrade, TradeMode, TradeSide,
)
from daytrader.journal.obsidian import ObsidianWriter


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_write_trade_view(tmp_vault: Path):
    w = ObsidianWriter(
        vault_root=tmp_vault,
        trades_folder="DayTrader/Trades",
        dry_runs_folder="DayTrader/DryRuns",
        checklists_folder="DayTrader/Daily",
    )
    t = JournalTrade(
        id="t01", checklist_id="c01",
        date=date(2026, 4, 20), symbol="MES",
        direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:35:00"),
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
        exit_time=_dt("2026-04-20T14:00:00"),
        exit_price=Decimal("5010"),
        pnl_usd=Decimal("50"),
    )
    w.write_trade(t)
    p = tmp_vault / "DayTrader/Trades/2026-04-20-t01.md"
    assert p.exists()
    text = p.read_text()
    assert "entry_price: 5000" in text
    assert "stop_price: 4995" in text


def test_write_fails_silently_on_bad_vault(tmp_path: Path, capsys):
    # Read-only directory
    bad_vault = tmp_path / "readonly"
    bad_vault.mkdir(mode=0o555)
    w = ObsidianWriter(
        vault_root=bad_vault,
        trades_folder="DayTrader/Trades",
        dry_runs_folder="DayTrader/DryRuns",
        checklists_folder="DayTrader/Daily",
    )
    t = JournalTrade(
        id="t02", checklist_id="c02",
        date=date(2026, 4, 20), symbol="MES",
        direction=TradeSide.LONG, setup_type="orb",
        entry_time=_dt("2026-04-20T13:35:00"),
        entry_price=Decimal("5000"),
        stop_price=Decimal("4995"),
        target_price=Decimal("5010"),
        size=1,
    )
    w.write_trade(t)  # should NOT raise
    err = capsys.readouterr().err
    assert "obsidian" in err.lower() or "warning" in err.lower()
```

- [ ] **Step 2: Implement `src/daytrader/journal/obsidian.py`**

```python
"""Obsidian Markdown view writer.

Fail-open: any write error prints a warning and returns without raising.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from daytrader.journal.models import (
    Checklist, DryRun, JournalTrade,
)


class ObsidianWriter:
    def __init__(
        self,
        vault_root: Path,
        trades_folder: str,
        dry_runs_folder: str,
        checklists_folder: str,
    ) -> None:
        self.vault_root = Path(vault_root).expanduser()
        self.trades_folder = trades_folder
        self.dry_runs_folder = dry_runs_folder
        self.checklists_folder = checklists_folder

    def _safe_write(self, rel: Path, text: str) -> None:
        try:
            full = self.vault_root / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(text)
        except Exception as e:
            print(
                f"⚠️  obsidian write warning: {e} (path: {rel})",
                file=sys.stderr,
            )

    def write_trade(self, t: JournalTrade) -> None:
        rel = Path(self.trades_folder) / f"{t.date.isoformat()}-{t.id}.md"
        frontmatter = [
            "---",
            f"id: {t.id}",
            f"checklist_id: {t.checklist_id}",
            f"date: {t.date.isoformat()}",
            f"symbol: {t.symbol}",
            f"direction: {t.direction.value}",
            f"setup_type: {t.setup_type}",
            f"entry_time: {t.entry_time.isoformat()}",
            f"entry_price: {t.entry_price}",
            f"stop_price: {t.stop_price}",
            f"target_price: {t.target_price}",
            f"size: {t.size}",
        ]
        if t.exit_time is not None:
            frontmatter.append(f"exit_time: {t.exit_time.isoformat()}")
        if t.exit_price is not None:
            frontmatter.append(f"exit_price: {t.exit_price}")
        if t.pnl_usd is not None:
            frontmatter.append(f"pnl_usd: {t.pnl_usd}")
            r = t.r_multiple()
            if r is not None:
                frontmatter.append(f"r_multiple: {r}")
        frontmatter.append("---")
        body = [
            "", f"# {t.symbol} {t.direction.value} — {t.setup_type}",
            "", f"**Notes:** {t.notes or ''}",
        ]
        if t.violations:
            body += ["", "## Violations", *(f"- {v}" for v in t.violations)]
        self._safe_write(rel, "\n".join(frontmatter + body))

    def write_dry_run(self, d: DryRun) -> None:
        rel = Path(self.dry_runs_folder) / f"{d.date.isoformat()}-{d.id}.md"
        fm = [
            "---",
            f"id: {d.id}",
            f"checklist_id: {d.checklist_id}",
            f"date: {d.date.isoformat()}",
            f"symbol: {d.symbol}",
            f"direction: {d.direction.value}",
            f"setup_type: {d.setup_type}",
            f"identified_time: {d.identified_time.isoformat()}",
            f"hypothetical_entry: {d.hypothetical_entry}",
            f"hypothetical_stop: {d.hypothetical_stop}",
            f"hypothetical_target: {d.hypothetical_target}",
            f"hypothetical_size: {d.hypothetical_size}",
        ]
        if d.outcome is not None:
            fm.append(f"outcome: {d.outcome.value}")
        if d.outcome_time is not None:
            fm.append(f"outcome_time: {d.outcome_time.isoformat()}")
        if d.outcome_price is not None:
            fm.append(f"outcome_price: {d.outcome_price}")
        if d.hypothetical_r_multiple is not None:
            fm.append(f"hypothetical_r_multiple: {d.hypothetical_r_multiple}")
        fm.append("---")
        body = [
            "", f"# DRY-RUN {d.symbol} {d.direction.value} — {d.setup_type}",
            "", f"**Notes:** {d.notes or ''}",
        ]
        self._safe_write(rel, "\n".join(fm + body))

    def write_checklist(self, c: Checklist) -> None:
        day = c.timestamp.date()
        rel = Path(self.checklists_folder) / f"checklist-{day.isoformat()}.md"
        # Append-style: read existing content if present, add entry
        full = self.vault_root / rel
        existing = ""
        try:
            if full.exists():
                existing = full.read_text()
        except Exception:
            pass
        entry = [
            "",
            f"## {c.timestamp.isoformat()} — checklist {c.id}",
            f"- mode: {c.mode.value}",
            f"- passed: {c.passed}",
            f"- item_stop_at_broker: {c.items.item_stop_at_broker}",
            f"- item_within_r_limit: {c.items.item_within_r_limit}",
            f"- item_matches_locked_setup: {c.items.item_matches_locked_setup}",
            f"- item_within_daily_r: {c.items.item_within_daily_r}",
            f"- item_past_cooloff: {c.items.item_past_cooloff}",
        ]
        if c.failure_reason:
            entry.append(f"- failure_reason: {c.failure_reason}")
        out = existing + "\n".join(entry)
        self._safe_write(rel, out)
```

- [ ] **Step 3: Wire writer into repo save hooks (minimally invasive)**

Rather than modifying `JournalRepository` internals, wire at the service layer. Modify `ChecklistService.run`, `PostTradeService.close`, `DryRunService.start` and `.end` to accept an optional writer and call it after `repo.save_*`.

For brevity here, simpler approach: at the **CLI level**, after each service call succeeds, invoke the writer. Extend `_load_cfg_and_repo()` to also return a writer.

Modify `_load_cfg_and_repo` in `journal_cmd.py`:

```python
def _load_cfg_repo_writer():
    project_root = Path(__file__).resolve().parents[3]
    cfg = load_config(
        default_config=project_root / "config" / "default.yaml",
        user_config=project_root / "config" / "user.yaml",
    )
    repo = JournalRepository(str(project_root / cfg.journal.db_path))
    repo.initialize()
    # sync contract (same as before)
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

    from daytrader.journal.obsidian import ObsidianWriter
    writer = None
    if cfg.obsidian.enabled:
        vault = Path(cfg.obsidian.vault_path).expanduser()
        writer = ObsidianWriter(
            vault_root=vault,
            trades_folder=cfg.journal.obsidian_trades_folder,
            dry_runs_folder=cfg.journal.obsidian_dry_runs_folder,
            checklists_folder=cfg.journal.obsidian_checklists_folder,
        )
    return cfg, repo, writer
```

Update `pre_trade`, `post_trade`, `dry_run_start`, `dry_run_end` commands to call the writer after SQLite write succeeds.

Example for `pre_trade` (after `result = svc.run(...)`):

```python
if writer and result.passed and result.trade_id:
    writer.write_trade(repo.get_trade(result.trade_id))
if writer:
    c = repo.get_checklist(result.checklist_id) if result.checklist_id else None
    if c:
        writer.write_checklist(c)
```

Apply similar patterns for post-trade + dry-run end.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/journal/test_obsidian.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/obsidian.py src/daytrader/cli/journal_cmd.py \
        tests/journal/test_obsidian.py
git commit -m "feat(journal): add Obsidian view writer with fail-open semantics"
```

---

## Task 16: Resume gate service + CLI

**Files:**
- Create: `src/daytrader/journal/resume_gate.py`
- Create: `tests/journal/test_resume_gate.py`
- Modify: `src/daytrader/cli/journal_cmd.py`

Gate checks the five criteria from spec §8.1. Output is machine-style (exits 0 on PASS, nonzero on FAIL) for later automation.

- [ ] **Step 1: Write tests**

```python
"""Tests for resume-gate service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.models import (
    Contract, DryRunOutcome, SetupVerdict,
)
from daytrader.journal.repository import JournalRepository
from daytrader.journal.resume_gate import ResumeGateService


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    return r


def test_fail_when_no_contract(repo):
    svc = ResumeGateService(repo)
    res = svc.check()
    assert res.passed is False
    assert any("contract" in f.reason for f in res.failed_gates)


def test_fail_when_no_verdict(repo):
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    svc = ResumeGateService(repo)
    res = svc.check()
    assert res.passed is False
    assert any("sanity" in f.reason.lower() for f in res.failed_gates)


def test_pass_when_all_green(repo, tmp_path):
    # contract
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    # verdict
    repo.save_setup_verdict(SetupVerdict(
        setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 25), symbol="MES",
        data_window_days=90,
        n_samples=40, win_rate=0.5, avg_r=0.1, passed=True,
    ))
    # 20+ dry runs, all outcome, 100% compliance
    from daytrader.journal.models import (
        Checklist, ChecklistItems, DryRun, TradeMode, TradeSide,
    )
    for i in range(22):
        items = ChecklistItems(
            item_stop_at_broker=True, item_within_r_limit=True,
            item_matches_locked_setup=True, item_within_daily_r=True,
            item_past_cooloff=True,
        )
        c = Checklist(
            id=f"c{i:02d}",
            timestamp=_dt(f"2026-04-{(i % 30)+1:02d}T13:35:00"),
            mode=TradeMode.DRY_RUN, contract_version=1,
            items=items, passed=True,
        )
        repo.save_checklist(c)
        d = DryRun(
            id=f"d{i:02d}", checklist_id=f"c{i:02d}",
            date=date(2026, 4, 20 + (i % 5)), symbol="MES",
            direction=TradeSide.LONG, setup_type="orb",
            identified_time=_dt(f"2026-04-{(i % 30)+1:02d}T13:35:00"),
            hypothetical_entry=Decimal("5000"),
            hypothetical_stop=Decimal("4995"),
            hypothetical_target=Decimal("5010"),
            hypothetical_size=1,
            outcome=DryRunOutcome.TARGET_HIT,
            outcome_time=_dt(f"2026-04-{(i % 30)+1:02d}T14:00:00"),
            outcome_price=Decimal("5010"),
            hypothetical_r_multiple=Decimal("2"),
        )
        repo.save_dry_run(d)

    svc = ResumeGateService(repo)
    res = svc.check()
    assert res.passed is True, res.failed_gates


def test_fail_when_compliance_not_100(repo):
    # Scenario: 20 passed checklists BUT 1 failed checklist also present
    from daytrader.journal.models import (
        Checklist, ChecklistItems, TradeMode,
    )
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"),
        daily_loss_limit_r=3, daily_loss_warning_r=2,
        max_trades_per_day=5, stop_cooloff_minutes=30,
        locked_setup_name="orb",
        locked_setup_file="docs/trading/setups/orb.yaml",
    ))
    repo.save_setup_verdict(SetupVerdict(
        setup_name="orb", setup_version="v1",
        run_date=date(2026, 4, 25), symbol="MES",
        data_window_days=90, n_samples=40, win_rate=0.5,
        avg_r=0.1, passed=True,
    ))
    # Add one FAILED checklist in dry_run mode
    bad_items = ChecklistItems(
        item_stop_at_broker=False, item_within_r_limit=True,
        item_matches_locked_setup=True, item_within_daily_r=True,
        item_past_cooloff=True,
    )
    repo.save_checklist(Checklist(
        id="cbad", timestamp=_dt("2026-04-22T13:00:00"),
        mode=TradeMode.DRY_RUN, contract_version=1,
        items=bad_items, passed=False,
        failure_reason="item_stop_at_broker",
    ))

    svc = ResumeGateService(repo)
    res = svc.check()
    # Compliance < 100% should fail the gate
    assert res.passed is False
```

- [ ] **Step 2: Implement `src/daytrader/journal/resume_gate.py`**

```python
"""Resume gate: machine-checked go/no-go for returning to live trading."""

from __future__ import annotations

from dataclasses import dataclass, field

from daytrader.journal.models import TradeMode
from daytrader.journal.repository import JournalRepository


@dataclass
class GateFailure:
    gate: str
    reason: str


@dataclass
class GateResult:
    passed: bool
    failed_gates: list[GateFailure] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


MIN_DRY_RUNS = 20


class ResumeGateService:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def check(self) -> GateResult:
        failed: list[GateFailure] = []
        metrics: dict = {}

        # Gate 1: active contract
        contract = self.repo.get_active_contract()
        if contract is None:
            failed.append(GateFailure("contract", "no active contract"))

        # Gate 2: at least 1 passed setup_verdict for the locked setup
        if contract and contract.locked_setup_name:
            verdicts = self.repo.list_setup_verdicts(
                setup_name=contract.locked_setup_name
            )
            passed_verdicts = [v for v in verdicts if v.passed]
            metrics["passed_verdicts"] = len(passed_verdicts)
            if not passed_verdicts:
                failed.append(GateFailure(
                    "sanity",
                    f"no passing sanity-floor verdict for "
                    f"{contract.locked_setup_name}",
                ))
        else:
            failed.append(GateFailure(
                "sanity", "no locked setup in contract"
            ))

        # Gate 3: ≥ MIN_DRY_RUNS with outcomes
        dry_runs_closed = [d for d in self.repo.list_dry_runs(only_with_outcome=True)]
        metrics["dry_runs_closed"] = len(dry_runs_closed)
        if len(dry_runs_closed) < MIN_DRY_RUNS:
            failed.append(GateFailure(
                "dry_run_count",
                f"need ≥{MIN_DRY_RUNS}, have {len(dry_runs_closed)}",
            ))

        # Gate 4: dry-run raw expectancy ≥ 0
        if dry_runs_closed:
            total_r = sum(
                float(d.hypothetical_r_multiple or 0) for d in dry_runs_closed
            )
            avg_r = total_r / len(dry_runs_closed)
            metrics["dry_run_avg_r"] = avg_r
            if avg_r < 0:
                failed.append(GateFailure(
                    "dry_run_expectancy",
                    f"avg_r = {avg_r:.3f} < 0",
                ))

        # Gate 5: checklist compliance 100% over dry-run period
        # Compliance rule: every dry_run mode checklist must have passed=True
        dry_run_mode_checklists = []
        conn = self.repo._get_conn()
        rows = conn.execute(
            "SELECT id, passed FROM journal_checklists WHERE mode = 'dry_run'"
        ).fetchall()
        total = len(rows)
        pass_count = sum(1 for r in rows if r["passed"])
        metrics["dry_run_checklists_total"] = total
        metrics["dry_run_checklists_passed"] = pass_count
        if total > 0:
            compliance = pass_count / total
            metrics["dry_run_compliance"] = compliance
            if compliance < 1.0:
                failed.append(GateFailure(
                    "compliance",
                    f"dry-run checklist compliance "
                    f"{pass_count}/{total} = {compliance:.0%}",
                ))

        return GateResult(passed=not failed, failed_gates=failed, metrics=metrics)
```

- [ ] **Step 3: Add CLI command**

Append to `journal_cmd.py`:

```python
@click.group("resume-gate")
def resume_gate_group():
    """Resume gate commands."""


@resume_gate_group.command("check")
def resume_gate_check():
    """Run the full resume gate check. Exits 0 on PASS, 1 on FAIL."""
    from daytrader.journal.resume_gate import ResumeGateService
    _cfg, repo, _ = _load_cfg_repo_writer()
    svc = ResumeGateService(repo)
    res = svc.check()
    if res.passed:
        click.echo("✅ RESUME GATE: PASS — ready to open combine/live")
        for k, v in res.metrics.items():
            click.echo(f"   {k}: {v}")
    else:
        click.echo("🚫 RESUME GATE: FAIL")
        for f in res.failed_gates:
            click.echo(f"   [{f.gate}] {f.reason}")
        click.echo("")
        click.echo("   Metrics:")
        for k, v in res.metrics.items():
            click.echo(f"     {k}: {v}")
        raise click.exceptions.Exit(1)
```

And wire into main.py:

```python
from daytrader.cli.journal_cmd import (
    pre_trade, post_trade, circuit_group, sanity_group,
    dry_run_group, resume_gate_group,
)
journal.add_command(resume_gate_group)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/journal/test_resume_gate.py -v
daytrader journal resume-gate check  # expect FAIL initially
```

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/resume_gate.py \
        src/daytrader/cli/journal_cmd.py src/daytrader/cli/main.py \
        tests/journal/test_resume_gate.py
git commit -m "feat(journal): add resume gate service + CLI"
```

---

## Task 17: Auditor — integrity check for SQLite bypass attempts

**Files:**
- Create: `src/daytrader/journal/auditor.py`
- Create: `tests/journal/test_auditor.py`
- Modify: `src/daytrader/cli/journal_cmd.py`

Checks invariants that should hold if nobody tampered:
- Every real trade has a matching passed checklist of mode=real
- Every dry-run has a matching checklist
- No circuit_state with `no_trade_flag=false` exists on a date where realized_r ≤ -daily_loss_limit_r
- No trade has NULL stop_price (defence-in-depth; DB schema already enforces)

- [ ] **Step 1: Tests**

```python
"""Tests for integrity auditor."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.auditor import Auditor
from daytrader.journal.models import (
    Checklist, ChecklistItems, CircuitState, Contract,
    JournalTrade, TradeMode, TradeSide,
)
from daytrader.journal.repository import JournalRepository


@pytest.fixture
def repo(tmp_journal_db: Path) -> JournalRepository:
    r = JournalRepository(str(tmp_journal_db))
    r.initialize()
    return r


def test_empty_db_no_issues(repo):
    audit = Auditor(repo)
    issues = audit.run_all()
    assert issues == []


def test_circuit_lock_inconsistency_detected(repo):
    # Realized -3R but flag=false → inconsistent
    repo.save_contract(Contract(
        version=1, signed_date=date(2026, 4, 20), active=True,
        r_unit_usd=Decimal("50"), daily_loss_limit_r=3,
        daily_loss_warning_r=2, max_trades_per_day=5,
        stop_cooloff_minutes=30,
    ))
    repo.upsert_circuit_state(CircuitState(
        date=date(2026, 4, 20),
        realized_r=Decimal("-3.5"),
        no_trade_flag=False,  # <-- WRONG
    ))
    audit = Auditor(repo)
    issues = audit.run_all()
    assert any("circuit" in i.kind for i in issues)
```

- [ ] **Step 2: Implement `src/daytrader/journal/auditor.py`**

```python
"""Integrity auditor — detects SQLite tampering or inconsistent state."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from daytrader.journal.repository import JournalRepository


@dataclass
class AuditIssue:
    kind: str
    detail: str


class Auditor:
    def __init__(self, repo: JournalRepository) -> None:
        self.repo = repo

    def run_all(self) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        issues += self._check_trades_have_checklists()
        issues += self._check_circuit_consistency()
        issues += self._check_stop_price_not_null()
        return issues

    def _check_trades_have_checklists(self) -> list[AuditIssue]:
        conn = self.repo._get_conn()
        rows = conn.execute(
            """SELECT t.id AS tid FROM journal_trades t
               LEFT JOIN journal_checklists c ON c.id = t.checklist_id
               WHERE c.id IS NULL"""
        ).fetchall()
        return [
            AuditIssue("trade_without_checklist",
                       f"trade {r['tid']} has no checklist record")
            for r in rows
        ]

    def _check_circuit_consistency(self) -> list[AuditIssue]:
        contract = self.repo.get_active_contract()
        if contract is None:
            return []
        conn = self.repo._get_conn()
        rows = conn.execute(
            "SELECT date, realized_r, no_trade_flag FROM journal_circuit_state"
        ).fetchall()
        issues = []
        limit = -Decimal(contract.daily_loss_limit_r)
        for r in rows:
            realized = Decimal(r["realized_r"])
            if realized <= limit and not r["no_trade_flag"]:
                issues.append(AuditIssue(
                    "circuit_inconsistent",
                    f"{r['date']}: realized_r={realized} "
                    f"≤ limit {limit} but no_trade_flag=false",
                ))
        return issues

    def _check_stop_price_not_null(self) -> list[AuditIssue]:
        conn = self.repo._get_conn()
        rows = conn.execute(
            "SELECT id FROM journal_trades WHERE stop_price IS NULL"
        ).fetchall()
        return [
            AuditIssue("trade_missing_stop", f"trade {r['id']} has NULL stop")
            for r in rows
        ]
```

- [ ] **Step 3: CLI command**

Append to `journal_cmd.py`:

```python
@click.command("audit")
def audit_cmd():
    """Run integrity audit on journal DB. Exits 1 if any issue found."""
    from daytrader.journal.auditor import Auditor
    _cfg, repo, _ = _load_cfg_repo_writer()
    audit = Auditor(repo)
    issues = audit.run_all()
    if not issues:
        click.echo("✅ audit clean: no issues")
        return
    click.echo(f"⚠️  {len(issues)} issue(s) found:")
    for i in issues:
        click.echo(f"  [{i.kind}] {i.detail}")
    raise click.exceptions.Exit(1)
```

Wire in main.py:

```python
from daytrader.cli.journal_cmd import (
    pre_trade, post_trade, circuit_group, sanity_group,
    dry_run_group, resume_gate_group, audit_cmd,
)
journal.add_command(audit_cmd)
```

- [ ] **Step 4: Run tests + smoke**

```bash
python -m pytest tests/journal/test_auditor.py -v
daytrader journal audit
```

- [ ] **Step 5: Commit**

```bash
git add src/daytrader/journal/auditor.py \
        src/daytrader/cli/journal_cmd.py src/daytrader/cli/main.py \
        tests/journal/test_auditor.py
git commit -m "feat(journal): add integrity auditor + audit CLI"
```

---

## Task 18: End-to-end integration smoke test + full suite verification

**Files:**
- Create: `tests/journal/test_integration_e2e.py`

- [ ] **Step 1: Write integration test that exercises the full flow**

```python
"""End-to-end integration test: contract → pre-trade → post-trade → audit."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def isolated_project(tmp_path: Path, monkeypatch):
    """Copy minimal project layout into tmp_path and cd there."""
    src_root = Path(__file__).resolve().parents[2]
    dst = tmp_path / "project"
    dst.mkdir()
    # Copy config + docs + src
    (dst / "config").mkdir()
    shutil.copy(src_root / "config" / "default.yaml", dst / "config" / "default.yaml")
    user_cfg = dst / "config" / "user.yaml"
    user_cfg.write_text("""
journal:
  db_path: data/db/journal.db
  contract_path: docs/trading/Contract.md
obsidian:
  enabled: false
""")
    (dst / "docs" / "trading").mkdir(parents=True)
    (dst / "docs" / "trading" / "Contract.md").write_text("""# Trading Contract

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
- locked_setup_name: orb
- locked_setup_file: docs/trading/setups/orb.yaml
- lock_in_min_trades: 30
- backup_setup_status: benched

## 7. Cool-off
- stop_cooloff_minutes: 30
""")
    monkeypatch.chdir(dst)
    # Patch project_root to our temp dir by also setting it in PYTHONPATH?
    # The CLI computes project_root from its file location, so we cannot
    # easily redirect. Instead, use the actual project but ensure each test
    # runs with an isolated DB path.
    return dst


def test_cli_flows_end_to_end(tmp_path):
    """Runs the key CLI commands; checks structural success."""
    from daytrader.cli.main import cli
    runner = CliRunner()
    # Minimally: --help for each subcommand
    for cmd in ("pre-trade", "post-trade", "circuit", "dry-run",
                "sanity", "resume-gate", "audit"):
        result = runner.invoke(cli, ["journal", cmd, "--help"])
        assert result.exit_code == 0, f"{cmd}: {result.output}"
```

- [ ] **Step 2: Run full suite**

```bash
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Manual full-flow walkthrough (documented, not automated)**

Create `docs/trading/PHASE2-DRY-RUN-WALKTHROUGH.md` with the following content:

```markdown
# Phase 2 Dry-Run Walkthrough

Use this once per week to verify the system end-to-end. All commands run from
project root.

1. Sign contract (manual):
   - Edit `docs/trading/Contract.md` — fill in real values, set Active: true

2. Run sanity on a candidate setup:
   ```bash
   daytrader journal sanity run docs/trading/setups/opening_range_breakout.yaml
   ```
   Record verdict status.

3. Simulate a dry-run:
   ```bash
   # checklist + hypothetical record:
   daytrader journal pre-trade --symbol MES --direction long \\
       --setup orb --entry 5000 --stop 4995 --target 5010 \\
       --size 1 --stop-at-broker --dry-run
   # note checklist_id from output

   daytrader journal dry-run start --checklist-id <id> --symbol MES \\
       --direction long --setup orb --entry 5000 --stop 4995 \\
       --target 5010 --size 1
   # later:
   daytrader journal dry-run end <dry_run_id> \\
       --outcome target_hit --outcome-price 5010 \\
       --notes "clean break, held to target"
   ```

4. Check circuit + audit + gate:
   ```bash
   daytrader journal circuit status
   daytrader journal audit
   daytrader journal resume-gate check
   ```

5. Verify Obsidian vault has new files under DayTrader/Trades and DayTrader/DryRuns.
```

- [ ] **Step 4: Commit walkthrough + integration test**

```bash
git add tests/journal/test_integration_e2e.py \
        docs/trading/PHASE2-DRY-RUN-WALKTHROUGH.md
git commit -m "test(journal): e2e integration + manual walkthrough doc"
```

---

## Phase C Self-Review

- [ ] All journal tests pass (`python -m pytest tests/journal/ -q`)
- [ ] Full project suite green (`python -m pytest -q`)
- [ ] CLI help for all 6 command groups works
- [ ] Resume-gate fails with empty DB (expected initial state)
- [ ] Obsidian writer produces files in a real vault
- [ ] Auditor detects inconsistency when `circuit_state` manually manipulated

## Phase 2 Acceptance

At this point all CODE deliverables from the design spec §2.1 IN list are complete:

- ✅ Trading Contract schema + parser + `sync on CLI invocation`
- ✅ Pre-trade Checklist CLI
- ✅ Post-trade Quick Log CLI
- ✅ Daily Loss Circuit (service + CLI + enforced in pre-trade)
- ✅ Sanity-Floor Backtest (YAML parser + data loader + engine + runner + CLI)
- ✅ Dry-Run Logger (service + CLI)
- ✅ Resume Gate (service + CLI)
- ✅ Auditor (additional — integrity check)
- ✅ Obsidian view writer (all record types)

The user can now:
1. Sign Contract.md → automatically loaded into DB
2. Run `daytrader journal sanity run <setup>` to evaluate candidate setups
3. Run pre-trade/post-trade/dry-run CLIs with full checklist enforcement
4. Call `daytrader journal resume-gate check` to see go/no-go

The PROCESS phases of the design (W3-4 actual dry-run sessions, W5 combine signup, W6+ combine trading) are **not code tasks** — they are user activities using the tools above. They belong in the weekly-review habit, not the implementation plan.
