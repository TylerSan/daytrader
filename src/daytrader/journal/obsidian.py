"""Obsidian Markdown view writer.

Fail-open: any write error prints a warning and returns without raising.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
                f"Warning: obsidian write error: {e} (path: {rel})",
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
            "",
            f"# {t.symbol} {t.direction.value} — {t.setup_type}",
            "",
            f"**Notes:** {t.notes or ''}",
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
            "",
            f"# DRY-RUN {d.symbol} {d.direction.value} — {d.setup_type}",
            "",
            f"**Notes:** {d.notes or ''}",
        ]
        self._safe_write(rel, "\n".join(fm + body))

    def write_checklist(self, c: Checklist) -> None:
        day = c.timestamp.date()
        rel = Path(self.checklists_folder) / f"checklist-{day.isoformat()}.md"
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
