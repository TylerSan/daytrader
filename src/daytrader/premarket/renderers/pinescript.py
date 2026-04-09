"""Pine Script generator for TradingView key level annotations."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult

_LEVEL_COLORS = {
    "prior_day_high": "color.red",
    "prior_day_low": "color.green",
    "prior_day_close": "color.gray",
    "premarket_price": "color.orange",
    "weekly_high": "color.new(#ff0000, 50)",
    "weekly_low": "color.new(#00ff00, 50)",
    "approx_vwap_5d": "color.purple",
}

_LEVEL_STYLES = {
    "prior_day_high": "hline.style_solid",
    "prior_day_low": "hline.style_solid",
    "prior_day_close": "hline.style_dashed",
    "premarket_price": "hline.style_dotted",
    "weekly_high": "hline.style_dashed",
    "weekly_low": "hline.style_dashed",
    "approx_vwap_5d": "hline.style_dotted",
}


class PineScriptRenderer:
    def __init__(self, output_dir: str = "scripts") -> None:
        self._output_dir = Path(output_dir)

    def render(self, results: dict[str, CollectorResult], symbol: str) -> str:
        levels_data = results.get("levels")
        if not levels_data or not levels_data.success or symbol not in levels_data.data:
            return ""

        levels = levels_data.data[symbol]
        today = date.today().isoformat()

        lines = [
            "//@version=5",
            f'indicator("DayTrader Levels — {symbol} ({today})", overlay=true)',
            "",
        ]

        for level_name, price in levels.items():
            if price is None:
                continue
            label = level_name.replace("_", " ").upper()
            color = _LEVEL_COLORS.get(level_name, "color.gray")
            style = _LEVEL_STYLES.get(level_name, "hline.style_dashed")
            lines.append(f'hline({price}, "{label}", {color}, {style}, 1)')

        lines.append("")
        return "\n".join(lines)

    def render_and_save(self, results: dict[str, CollectorResult], symbol: str) -> Path:
        code = self.render(results, symbol=symbol)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        path = self._output_dir / f"levels-{symbol}-{today}.pine"
        path.write_text(code)
        return path
