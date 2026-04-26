"""OutputValidator: enforce required-sections per report type.

Phase 2 covers premarket only. Later phases extend the table.
"""

from __future__ import annotations

from dataclasses import dataclass

# Section names as they appear in the generated markdown.
# Premarket uses Chinese section headings ("A. 建议") plus English TF labels.
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "premarket": [
        "Lock-in",
        "1W",
        "1D",
        "4H",
        "1H",
        "新闻",         # "Breaking news / 突发新闻"
        "C.",          # "C. 计划复核"
        "B.",          # "B. 市场叙事"
        "A.",          # "A. 建议"
        "数据快照",     # data snapshot
    ],
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]


class OutputValidator:
    """Section-presence check on AI-generated markdown."""

    def validate(self, content: str, report_type: str) -> ValidationResult:
        if report_type not in REQUIRED_SECTIONS:
            raise KeyError(f"No section list defined for report_type={report_type!r}")
        required = REQUIRED_SECTIONS[report_type]
        missing = [s for s in required if s not in content]
        return ValidationResult(ok=not missing, missing=missing)
