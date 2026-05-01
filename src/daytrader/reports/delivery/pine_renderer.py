"""Pine Script renderer for TradingView key-level annotations.

Phase 2.5 addition. Generates `.pine` files that the user pastes into
TradingView's Pine Editor → "Add to chart" to overlay key price levels
on the corresponding instrument's chart.

Source data comes from IB (via IBClient) — replaces the Phase 1a Yahoo-
based renderer at `premarket/renderers/pinescript.py` which doesn't work
for futures. POINT-only in this version (hline). ZONE support (box.new)
is deferred to Phase 3 once HTF zone identification is mechanized.

Usage (CLI):
    daytrader reports pine             # all symbols from instruments.yaml
    daytrader reports pine --symbol MES --symbol MGC

Output:
    data/exports/pine/levels-{SYMBOL}-{YYYY-MM-DD}.pine
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path

from daytrader.core.ib_client import IBClient


@dataclass(frozen=True)
class KeyLevels:
    """Mechanically computed key price levels for a symbol.

    Each field may be None if the source bars are unavailable.
    Phase 2.5 covers POINT levels only. Zones (htf_demand_zone /
    htf_supply_zone) require additional analysis (swing detection +
    user filtering) and are deferred to Phase 3.
    """
    prior_day_high: float | None = None
    prior_day_low: float | None = None
    prior_day_close: float | None = None
    weekly_high: float | None = None
    weekly_low: float | None = None


class LevelExtractor:
    """Compute KeyLevels from IB bars."""

    def __init__(self, ib_client: IBClient) -> None:
        self.ib_client = ib_client

    def extract(self, symbol: str) -> KeyLevels:
        # 1D bars: take the most recent COMPLETED daily bar as "prior day"
        daily_bars = self.ib_client.get_bars(symbol=symbol, timeframe="1D", bars=2)
        # 1W bars: most recent completed weekly bar gives weekly H/L
        weekly_bars = self.ib_client.get_bars(symbol=symbol, timeframe="1W", bars=2)

        pdh = pdl = pdc = wh = wl = None

        if daily_bars:
            last_daily = daily_bars[-1]
            pdh = last_daily.high
            pdl = last_daily.low
            pdc = last_daily.close

        if weekly_bars:
            last_weekly = weekly_bars[-1]
            wh = last_weekly.high
            wl = last_weekly.low

        return KeyLevels(
            prior_day_high=pdh,
            prior_day_low=pdl,
            prior_day_close=pdc,
            weekly_high=wh,
            weekly_low=wl,
        )


# Pine Script color/style mapping per level type
_LEVEL_FORMAT: dict[str, tuple[str, str, str]] = {
    # field_name : (label, color, line_style)
    "prior_day_high":  ("PDH",  "color.red",                       "hline.style_solid"),
    "prior_day_low":   ("PDL",  "color.green",                     "hline.style_solid"),
    "prior_day_close": ("PDC",  "color.gray",                      "hline.style_dashed"),
    "weekly_high":     ("WH",   "color.new(color.red, 50)",        "hline.style_dashed"),
    "weekly_low":      ("WL",   "color.new(color.green, 50)",      "hline.style_dashed"),
}


class PineScriptRenderer:
    """Emit Pine Script v5 source with one `hline()` per non-None level."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)

    def render(
        self, levels: KeyLevels, symbol: str, today: date_cls
    ) -> str:
        """Return Pine Script source as a string."""
        lines = [
            "//@version=5",
            f'indicator("DayTrader Levels — {symbol} ({today.isoformat()})", overlay=true)',
            "",
        ]

        # Iterate dataclass fields in declared order so hlines render predictably
        for field_name, (label, color, style) in _LEVEL_FORMAT.items():
            price = getattr(levels, field_name, None)
            if price is None:
                continue
            lines.append(f'hline({price}, "{label}", {color}, {style}, 1)')

        lines.append("")
        return "\n".join(lines)

    def render_and_save(
        self, levels: KeyLevels, symbol: str, today: date_cls
    ) -> Path:
        """Render and write to `<output_dir>/levels-{SYMBOL}-{YYYY-MM-DD}.pine`."""
        code = self.render(levels=levels, symbol=symbol, today=today)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_symbol = symbol.replace("=", "").replace("^", "")
        path = self.output_dir / f"levels-{safe_symbol}-{today.isoformat()}.pine"
        path.write_text(code)
        return path
