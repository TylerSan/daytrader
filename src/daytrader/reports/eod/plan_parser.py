"""PremarketPlanParser — raw C-block markdown → structured Plan."""

from __future__ import annotations

import re

from daytrader.reports.eod.plan_dataclasses import Plan, PlanLevel


# Direction-bearing labels and their semantics.
_DIRECTION_LABELS: list[tuple[str, str]] = [
    ("Long bias 区", "long_fade"),
    ("Short bias 区", "short_fade"),
    ("Stretch long", "long_fade"),
    ("Stretch short", "short_fade"),
]

# Two-pass parsing strategy:
#
# Pass 1 — _LINE_RE: Match any **label**: rest-of-line bullet (nested or top-level).
#   Captures `label` and `rest` (everything after the colon).
#
# Pass 2 — strip paren content for source, then parse prices.
#   This avoids the monolithic regex problem where lazy quantifiers stop too
#   early before full-width 全角 characters.
#
# Tolerates:
#   - Full-width parens 全角 （） or ASCII ()
#   - Leading spaces (nested bullets)
#   - ASCII colon or full-width colon ：
#   - Multiple price entries separated by '+' on a single line

_LINE_RE = re.compile(
    r"^\s*-\s*\*\*\s*(?P<label>[^*\n]+?)\s*\*\*\s*[:：]\s*(?P<rest>.+)$",
    re.MULTILINE,
)

# Extract text inside parens (full-width or ASCII).  First match = primary source.
_PAREN_RE = re.compile(r"[（(]([^）)\n]*)[）)]")

# Zone: two prices separated by dash variants.
_ZONE_RE = re.compile(r"(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)")

# Single price: decimal or 4+-digit integer.
_PRICE_RE = re.compile(r"\b(\d+\.\d+|\d{4,})\b")


class PremarketPlanParser:
    """Parse C-block raw markdown into structured Plan.

    Defensive: when format varies from expectations, emit `parse_warnings`
    rather than raise. Empty block → Plan with empty levels + warning.
    Unrecognized format → empty levels + warning.
    """

    def parse(self, raw_block_md: str, symbol: str) -> Plan:
        if not raw_block_md or not raw_block_md.strip():
            return Plan(
                symbol=symbol,
                levels=[],
                raw_block_md=raw_block_md,
                parse_warnings=["empty C block — premarket may have failed today"],
            )

        levels: list[PlanLevel] = []
        warnings: list[str] = []

        any_match = False
        for m in _LINE_RE.finditer(raw_block_md):
            any_match = True
            label = m.group("label").strip()
            rest = m.group("rest").strip()

            direction = self._resolve_direction(label)
            if direction is None:
                # Non-directional bullets: Setup, Stop, Target, Direction, Entry header
                continue

            # Extract source from first parenthetical group.
            paren_m = _PAREN_RE.search(rest)
            source = paren_m.group(1).strip() if paren_m else ""

            # Strip ALL paren groups so '+' in source text doesn't corrupt price split.
            prices_text = _PAREN_RE.sub("", rest).strip()

            for plevel in self._parse_prices(prices_text, source, direction):
                levels.append(plevel)

        if not any_match:
            warnings.append(
                "no parseable level bullets found — block format may have changed"
            )
        elif not levels:
            warnings.append(
                "level bullets found but no directional labels matched "
                "(checked: Long bias 区 / Short bias 区 / Stretch long/short)"
            )

        return Plan(
            symbol=symbol,
            levels=levels,
            raw_block_md=raw_block_md,
            parse_warnings=warnings,
        )

    # --- helpers ---

    @staticmethod
    def _resolve_direction(label: str) -> str | None:
        """Map free-text label to canonical direction string."""
        label_lower = label.lower()
        for keyword, direction in _DIRECTION_LABELS:
            if keyword.lower() in label_lower:
                return direction
        return None

    @staticmethod
    def _parse_prices(text: str, source: str, direction: str) -> list[PlanLevel]:
        """Extract one or more PlanLevel from a prices-text fragment.

        Examples:
        - "7199.25" → 1 POINT
        - "7185–7195" → 1 ZONE (low=7185, high=7195, price=midpoint)
        - "7199.25+ 7185–7195" → 2 levels (POINT + ZONE)
        - "7271-7279.5" → 1 ZONE
        """
        # Split on '+' to handle multiple entries per bullet.
        # Paren content has already been stripped by the caller, so '+' inside
        # source strings (e.g., "4H R + D high reject 区") won't appear here.
        out: list[PlanLevel] = []
        for fragment in text.split("+"):
            fragment = fragment.strip()
            if not fragment:
                continue
            zone_match = _ZONE_RE.search(fragment)
            if zone_match:
                low = float(zone_match.group(1))
                high = float(zone_match.group(2))
                if low > high:
                    low, high = high, low
                out.append(
                    PlanLevel(
                        price=(low + high) / 2,
                        level_type="ZONE",
                        source=source,
                        direction=direction,  # type: ignore[arg-type]
                        zone_low=low,
                        zone_high=high,
                    )
                )
            else:
                price_match = _PRICE_RE.search(fragment)
                if price_match:
                    raw = price_match.group(1)
                    try:
                        price = float(raw)
                        out.append(
                            PlanLevel(
                                price=price,
                                level_type="POINT",
                                source=source,
                                direction=direction,  # type: ignore[arg-type]
                            )
                        )
                    except ValueError:
                        pass
        return out
