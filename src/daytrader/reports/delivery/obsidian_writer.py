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

    def write_eod(
        self,
        date_iso: str,
        content: str,
    ) -> WriteResult:
        """Write an EOD report markdown to the vault (Phase 5).

        Filename convention mirrors premarket: ``{date}-eod.md``. Same vault
        → fallback failover semantics.
        """
        filename = f"{date_iso}-eod.md"
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
