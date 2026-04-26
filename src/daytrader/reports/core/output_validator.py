"""OutputValidator: enforce required-sections per report type.

Phase 2 covers premarket only. Later phases extend the table.

Each slot in REQUIRED_SECTIONS is either a single string (must appear
literally in the content) or a list of strings (any one of them must
appear). Lists allow alternate labelings — Claude often writes "### W"
instead of "### 1W", "周线" instead of "Weekly", etc., and we should
accept either as long as semantically the section is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Section names as they appear in the generated markdown.
# Premarket uses Chinese section headings plus per-TF labels.
SectionSpec = str | list[str]

REQUIRED_SECTIONS: dict[str, list[SectionSpec]] = {
    "premarket": [
        "Lock-in",
        # Weekly TF: accept "1W", "W ", "W(", "Weekly", "周线"
        ["1W", "## W", "### W ", "### W(", "Weekly", "周线"],
        # Daily TF: accept "1D", "D ", "D(", "Daily", "日线"
        ["1D", "## D", "### D ", "### D(", "Daily", "日线"],
        # 4-hour TF: accept "4H", "4 H", "4小时"
        ["4H", "4 H", "4小时"],
        # 1-hour TF: accept "1H", "1 H", "1小时", "Hourly"
        ["1H", "1 H", "1小时", "Hourly"],
        # Breaking news section: accept "新闻", "News", "Breaking"
        ["新闻", "News", "Breaking"],
        "C.",          # "C. 计划复核"
        "B.",          # "B. 市场叙事"
        "A.",          # "A. 建议"
        # Data snapshot: accept Chinese or English variants
        ["数据快照", "Data snapshot", "Snapshot"],
    ],
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]


def _slot_matches(content: str, slot: SectionSpec) -> bool:
    """A slot is satisfied if its literal (or ANY of its alternatives) appears."""
    if isinstance(slot, str):
        return slot in content
    return any(alt in content for alt in slot)


def _slot_label(slot: SectionSpec) -> str:
    """Human-readable label for missing-slot reporting."""
    if isinstance(slot, str):
        return slot
    return f"any of {slot}"


class OutputValidator:
    """Section-presence check on AI-generated markdown."""

    def validate(self, content: str, report_type: str) -> ValidationResult:
        if report_type not in REQUIRED_SECTIONS:
            raise KeyError(f"No section list defined for report_type={report_type!r}")
        required = REQUIRED_SECTIONS[report_type]
        missing = [
            _slot_label(slot) for slot in required if not _slot_matches(content, slot)
        ]
        return ValidationResult(ok=not missing, missing=missing)
