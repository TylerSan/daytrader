"""Weekly trading plan generator."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector


class WeeklyPlanGenerator:
    def __init__(self, collector: MarketDataCollector, output_dir: str = "data/exports") -> None:
        self._collector = collector
        self._output_dir = Path(output_dir)

    async def generate(self, week_start: date | None = None) -> str:
        week_start = week_start or date.today()
        results = await self._collector.collect_all()

        sections = [
            f"# Weekly Trading Plan — Week of {week_start.isoformat()}\n",
            f"*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC*\n",
        ]

        sections.append("## Last Week Review\n")
        sections.append("*Requires trade journal data — will be auto-populated once journal module is active.*\n")

        sections.append("## Week Ahead Macro Context\n")

        futures = results.get("futures")
        if futures and futures.success:
            sections.append("### Index Futures\n")
            sections.append("| Symbol | Price | Change % |")
            sections.append("|--------|-------|----------|")
            for sym, data in futures.data.items():
                price = data.get("price", "N/A")
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"
                sections.append(f"| {sym} | {price} | {change_str} |")
            sections.append("")

        sectors = results.get("sectors")
        if sectors and sectors.success:
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            sections.append("### Sector Rotation\n")
            sections.append("**Leaders:** " + ", ".join(
                f"{d['name']} ({d['change_pct']:+.2f}%)"
                for _, d in sorted_sectors[:3]
                if d.get("change_pct") is not None
            ))
            sections.append("")
            sections.append("**Laggards:** " + ", ".join(
                f"{d['name']} ({d['change_pct']:+.2f}%)"
                for _, d in sorted_sectors[-3:]
                if d.get("change_pct") is not None
            ))
            sections.append("")

        levels = results.get("levels")
        if levels and levels.success:
            sections.append("## Weekly Key Levels\n")
            for sym, lvls in levels.data.items():
                sections.append(f"### {sym}\n")
                sections.append("| Level | Price |")
                sections.append("|-------|-------|")
                for name, price in lvls.items():
                    if price is not None:
                        label = name.replace("_", " ").title()
                        sections.append(f"| {label} | {price} |")
                sections.append("")

        sections.append("## Weekly Trading Plan\n")
        sections.append("### Bias Framework\n")
        sections.append("*Review index futures + sector data above to set weekly directional bias.*\n")
        sections.append("### Event Risk Windows\n")
        sections.append("*Check economic calendar for FOMC, CPI, NFP, earnings.*\n")
        sections.append("### Focus Goals\n")
        sections.append("- [ ] Goal 1: *(set based on last week review)*\n")
        sections.append("- [ ] Goal 2: *(set based on last week review)*\n")

        return "\n".join(sections)

    async def generate_and_save(self, week_start: date | None = None) -> Path:
        week_start = week_start or date.today()
        content = await self.generate(week_start)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"weekly-{week_start.isoformat()}.md"
        path.write_text(content)
        return path
