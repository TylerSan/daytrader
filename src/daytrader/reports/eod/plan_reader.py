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
