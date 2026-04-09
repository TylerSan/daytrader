"""Markdown report renderer for pre-market analysis."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult


class MarkdownRenderer:
    def __init__(self, output_dir: str = "data/exports") -> None:
        self._output_dir = Path(output_dir)

    def render(
        self,
        results: dict[str, CollectorResult],
        date: date,
        ai_analysis: str = "",
    ) -> str:
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

        # Overnight session data (from futures collector)
        futures_with_overnight = results.get("futures")
        if futures_with_overnight and futures_with_overnight.success:
            has_overnight = any(
                "overnight_high" in d
                for d in futures_with_overnight.data.values()
                if isinstance(d, dict)
            )
            if has_overnight:
                sections.append("## Overnight Session\n")
                sections.append("| Symbol | Overnight H | Overnight L | Range | Asia H | Asia L | Europe H | Europe L |")
                sections.append("|--------|------------|------------|-------|--------|--------|----------|----------|")
                for sym, data in futures_with_overnight.data.items():
                    if not isinstance(data, dict) or "overnight_high" not in data:
                        continue
                    oh = data.get("overnight_high", "—")
                    ol = data.get("overnight_low", "—")
                    rng = data.get("overnight_range", "—")
                    ah = data.get("asia_high", "—")
                    al = data.get("asia_low", "—")
                    eh = data.get("europe_high", "—")
                    el = data.get("europe_low", "—")
                    sections.append(f"| {sym} | {oh} | {ol} | {rng} | {ah} | {al} | {eh} | {el} |")
                sections.append("")

        # News headlines
        news = results.get("news")
        if news and news.success and news.data.get("headlines"):
            sections.append("## News Headlines\n")
            for item in news.data["headlines"]:
                title = item.get("title", "")
                publisher = item.get("publisher", "")
                symbol = item.get("symbol", "")
                sections.append(f"- **{title}** ({publisher}) [{symbol}]")
            sections.append("")

        # Pre-market movers
        movers = results.get("movers")
        if movers and movers.success and movers.data.get("movers"):
            sections.append("## Pre-Market Movers\n")
            sections.append("| Symbol | Name | Price | Gap % | Vol Ratio |")
            sections.append("|--------|------|-------|-------|-----------|")
            for m in movers.data["movers"]:
                gap_str = f"{m['gap_pct']:+.2f}%"
                sections.append(
                    f"| {m['symbol']} | {m['name']} | {m['price']} | {gap_str} | {m['vol_ratio']}x |"
                )
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

        # AI Analysis section
        if ai_analysis:
            sections.append("---\n")
            sections.append("## AI 技术分析 & 操盘建议\n")
            sections.append(ai_analysis)
            sections.append("")

        return "\n".join(sections)

    def render_and_save(
        self,
        results: dict[str, CollectorResult],
        date: date,
        ai_analysis: str = "",
    ) -> Path:
        content = self.render(results, date, ai_analysis=ai_analysis)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"premarket-{date.isoformat()}.md"
        path.write_text(content)
        return path
