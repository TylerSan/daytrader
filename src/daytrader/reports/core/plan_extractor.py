"""PlanExtractor: parse today's plan out of a generated premarket report.

The premarket prompt asks the AI to use a fixed structure; this module
parses that structure into an ExtractedPlan dataclass that the orchestrator
saves into StateDB.plans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedPlan:
    """Today's plan as parsed from a premarket report."""
    setup_name: str
    direction: str  # long | short | neutral
    entry: float
    stop: float
    target: float
    r_unit_dollars: float
    invalidations: list[str]
    raw_text: str


_FIELD_PATTERNS = {
    "setup_name": re.compile(r"^- Setup:\s*(.+?)\s*$", re.MULTILINE),
    "direction": re.compile(r"^- Direction:\s*(.+?)\s*$", re.MULTILINE),
    "entry": re.compile(r"^- Entry:\s*([\d.]+)", re.MULTILINE),
    "stop": re.compile(r"^- Stop:\s*([\d.]+)", re.MULTILINE),
    "target": re.compile(r"^- Target:\s*([\d.]+)", re.MULTILINE),
    "r_unit": re.compile(r"^- R unit:\s*\$?([\d.]+)", re.MULTILINE),
}

_INVALIDATION_BLOCK = re.compile(
    r"\*\*Invalidation conditions\*\*[^\n]*\n((?:\s*\d+\.\s+.+\n?)+)",
)
_INVALIDATION_LINE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$", re.MULTILINE)


class PlanExtractor:
    """Parse the C-section plan into structured fields."""

    def extract(self, report_text: str) -> ExtractedPlan | None:
        # Locate the Today's plan block — if it's missing key fields, return None
        setup_match = _FIELD_PATTERNS["setup_name"].search(report_text)
        entry_match = _FIELD_PATTERNS["entry"].search(report_text)
        stop_match = _FIELD_PATTERNS["stop"].search(report_text)
        if not (setup_match and entry_match and stop_match):
            return None

        target_match = _FIELD_PATTERNS["target"].search(report_text)
        if not target_match:
            return None

        direction_match = _FIELD_PATTERNS["direction"].search(report_text)
        r_unit_match = _FIELD_PATTERNS["r_unit"].search(report_text)

        invalidations: list[str] = []
        block_match = _INVALIDATION_BLOCK.search(report_text)
        if block_match:
            for line_match in _INVALIDATION_LINE.finditer(block_match.group(1)):
                invalidations.append(line_match.group(1))

        return ExtractedPlan(
            setup_name=setup_match.group(1).strip(),
            direction=direction_match.group(1).strip() if direction_match else "unknown",
            entry=float(entry_match.group(1)),
            stop=float(stop_match.group(1)),
            target=float(target_match.group(1)),
            r_unit_dollars=float(r_unit_match.group(1)) if r_unit_match else 0.0,
            invalidations=invalidations,
            raw_text=report_text,
        )

    def extract_per_instrument(
        self, report_text: str, instruments: list[str]
    ) -> dict[str, ExtractedPlan]:
        """Extract per-instrument plans by splitting on '### C-{INSTRUMENT}' headers.

        Returns a dict from symbol → ExtractedPlan. Symbols without a parseable
        plan block are omitted.
        """
        result: dict[str, ExtractedPlan] = {}
        for symbol in instruments:
            marker = f"### C-{symbol}"
            idx = report_text.find(marker)
            if idx == -1:
                continue
            after = report_text[idx + len(marker):]
            # Block extends until next "### C-" or "## " or end of text
            next_block_relative = -1
            for end_marker in ("\n### C-", "\n## "):
                pos = after.find(end_marker)
                if pos != -1 and (next_block_relative == -1 or pos < next_block_relative):
                    next_block_relative = pos
            if next_block_relative == -1:
                block_text = after
            else:
                block_text = after[:next_block_relative]
            plan = self.extract(block_text)
            if plan is not None:
                result[symbol] = plan
        return result
