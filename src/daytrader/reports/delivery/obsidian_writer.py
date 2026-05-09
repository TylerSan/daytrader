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

    def _write_with_fallback(self, filename: str, content: str) -> WriteResult:
        """Vault → fallback failover used by intraday_4h / night / asia.

        Differs from write_premarket/write_eod in that it also falls back when
        ``vault_root`` does not exist as a directory (vault unavailable),
        rather than only on OSError/PermissionError. Phase 5.5 T6.
        """
        primary = self.vault_root / self.daily_folder / filename
        if self.vault_root.exists():
            try:
                primary.parent.mkdir(parents=True, exist_ok=True)
                primary.write_text(content)
                return WriteResult(success=True, path=primary, fallback_used=False)
            except (OSError, PermissionError):
                pass
        fallback = self.fallback_dir / filename
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(content)
        return WriteResult(success=True, path=fallback, fallback_used=True)

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
