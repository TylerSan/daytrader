"""Markdown report renderer for pre-market analysis."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult


class MarkdownRenderer:
    def __init__(self, output_dir: str = "data/exports") -> None:
        self._output_dir = Path(output_dir)

    def render(self, results: dict[str, CollectorResult], date: date) -> str:
        sections = [
            f"# Pre-Market Report — {date.isoformat()}\n",
            f"*Generated at {datetime.now().strftime('%H:%M:%S')} UTC*\n",
        ]

        futures = results.get("futures")
        if futures and futures.success:
            sections.append("## Futures & VIX\n")
            sections.append("| Symbol | Price | Change % | Prev Close |")
            sections.append("|--------|-------|----------|------------|")
            for sym, data in futures.data.items():
                price = data.get("price", "N/A")
                change = data.get("change_pct", "N/A")
                prev = data.get("prev_close", "N/A")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else str(change)
                sections.append(f"| {sym} | {price} | {change_str} | {prev} |")
            sections.append("")

        sectors = results.get("sectors")
        if sectors and sectors.success:
            sections.append("## Sector Performance\n")
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            sections.append("| ETF | Sector | Change % |")
            sections.append("|-----|--------|----------|")
            for sym, data in sorted_sectors:
                name = data.get("name", sym)
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"
                sections.append(f"| {sym} | {name} | {change_str} |")
            sections.append("")

        levels = results.get("levels")
        if levels and levels.success:
            sections.append("## Key Levels\n")
            for sym, lvls in levels.data.items():
                sections.append(f"### {sym}\n")
                sections.append("| Level | Price |")
                sections.append("|-------|-------|")
                for level_name, price in lvls.items():
                    if price is not None:
                        label = level_name.replace("_", " ").title()
                        sections.append(f"| {label} | {price} |")
                sections.append("")

        return "\n".join(sections)

    def render_and_save(self, results: dict[str, CollectorResult], date: date) -> Path:
        content = self.render(results, date)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"premarket-{date.isoformat()}.md"
        path.write_text(content)
        return path
