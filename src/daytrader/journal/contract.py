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
