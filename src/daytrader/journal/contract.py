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


_VAGUE_ASCII = (
    "careful", "cautious", "reasonable", "maybe", "perhaps",
    "usually", "sometimes", "mostly", "approximately",
)
_VAGUE_CJK = ("谨慎", "大概", "大约")

# Word-boundary match for ASCII (so "carefully" doesn't trigger "careful"),
# substring match for CJK (no word boundaries in CJK).
VAGUE_ASCII_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _VAGUE_ASCII) + r")\b",
    re.IGNORECASE,
)

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
    if m := VAGUE_ASCII_RE.search(text):
        raise ContractParseError(
            f"Contract contains vague/unmeasurable word {m.group(1)!r}. "
            "Every rule must be mechanically checkable."
        )
    for w in _VAGUE_CJK:
        if w in text:
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
        try:
            return int(bullets[k])
        except ValueError:
            raise ContractParseError(
                f"bullet {k!r} must be an integer, got {bullets[k]!r}"
            )

    def _opt_str(k: str, default: str = "") -> str:
        return bullets.get(k, default).strip().strip('"')

    try:
        version_int = int(header["version"])
    except ValueError:
        raise ContractParseError(
            f"Version must be an integer, got {header['version']!r}"
        )
    try:
        r_unit = Decimal(r_unit_raw)
    except Exception:
        raise ContractParseError(
            f"R unit (USD) must be numeric, got {r_unit_raw!r}"
        )

    bss = _opt_str("backup_setup_status", "benched")
    if bss not in ("benched", "active"):
        raise ContractParseError(
            f"backup_setup_status must be 'benched' or 'active', got {bss!r}"
        )
    lock_in_raw = bullets.get("lock_in_min_trades", "30")
    try:
        lock_in = int(lock_in_raw)
    except ValueError:
        raise ContractParseError(
            f"lock_in_min_trades must be an integer, got {lock_in_raw!r}"
        )

    return Contract(
        version=version_int,
        signed_date=date_type.fromisoformat(header["signed_date"]),
        active=_to_bool(header["active"]),
        r_unit_usd=r_unit,
        daily_loss_limit_r=_req_int("daily_loss_limit_r"),
        daily_loss_warning_r=_req_int("daily_loss_warning_r"),
        max_trades_per_day=_req_int("max_trades_per_day"),
        stop_cooloff_minutes=_req_int("stop_cooloff_minutes"),
        locked_setup_name=_opt_str("locked_setup_name") or None,
        locked_setup_file=_opt_str("locked_setup_file") or None,
        lock_in_min_trades=lock_in,
        backup_setup_name=_opt_str("backup_setup_name") or None,
        backup_setup_file=_opt_str("backup_setup_file") or None,
        backup_setup_status=bss,
    )
