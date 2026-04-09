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
        sections: list[str] = []
        now = datetime.now()

        # Obsidian-compatible YAML frontmatter
        sections.append("---")
        sections.append(f"date: {date.isoformat()}")
        sections.append(f"generated: {now.strftime('%Y-%m-%dT%H:%M:%S')}")
        sections.append("type: premarket")
        sections.append("tags: [trading, premarket, daily]")
        sections.append("---\n")

        sections.append(f"# 盘前分析报告 — {date.isoformat()}")
        sections.append(f"*生成时间: {now.strftime('%H:%M:%S')} UTC*\n")

        # ═══════════════════════════════════════
        # Section 1: 宏观环境
        # ═══════════════════════════════════════
        sections.append("---")
        sections.append("## 一、宏观环境\n")

        # 1.1 期货总览
        futures = results.get("futures")
        if futures and futures.success:
            sections.append("### 1.1 指数期货 & VIX\n")
            sections.append("| 品种 | 现价 | 涨跌幅 | 前收 | 日高 | 日低 |")
            sections.append("|------|------|--------|------|------|------|")
            for sym, data in futures.data.items():
                if not isinstance(data, dict):
                    continue
                price = data.get("price", "—")
                change = data.get("change_pct")
                prev = data.get("prev_close", "—")
                high = data.get("day_high", "—")
                low = data.get("day_low", "—")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                sections.append(f"| {sym} | {price} | {change_str} | {prev} | {high} | {low} |")
            sections.append("")

        # 1.2 隔夜走势
        if futures and futures.success:
            has_overnight = any(
                "overnight_high" in d
                for d in futures.data.values()
                if isinstance(d, dict)
            )
            if has_overnight:
                sections.append("### 1.2 隔夜走势（Globex）\n")
                sections.append("| 品种 | 隔夜高 | 隔夜低 | 区间 | 亚洲高 | 亚洲低 | 欧洲高 | 欧洲低 |")
                sections.append("|------|--------|--------|------|--------|--------|--------|--------|")
                for sym, data in futures.data.items():
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

        # 1.3 板块强弱
        sectors = results.get("sectors")
        if sectors and sectors.success:
            sections.append("### 1.3 板块强弱\n")
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            sections.append("| ETF | 板块 | 涨跌幅 |")
            sections.append("|-----|------|--------|")
            for sym, data in sorted_sectors:
                name = data.get("name", sym)
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                sections.append(f"| {sym} | {name} | {change_str} |")
            sections.append("")

        # ═══════════════════════════════════════
        # Section 2: 消息面
        # ═══════════════════════════════════════
        news = results.get("news")
        if news and news.success and news.data.get("headlines"):
            sections.append("---")
            sections.append("## 二、消息面\n")
            for item in news.data["headlines"]:
                title = item.get("title", "")
                publisher = item.get("publisher", "")
                summary = item.get("summary", "")
                pub_info = f" — *{publisher}*" if publisher else ""
                sections.append(f"- **{title}**{pub_info}")
                if summary:
                    sections.append(f"  > {summary}")
            sections.append("")

        # ═══════════════════════════════════════
        # Section 3: 盘前异动
        # ═══════════════════════════════════════
        movers = results.get("movers")
        if movers and movers.success and movers.data.get("movers"):
            sections.append("---")
            sections.append("## 三、盘前异动\n")
            sections.append("| 代码 | 名称 | 现价 | 缺口 | 量比 |")
            sections.append("|------|------|------|------|------|")
            for m in movers.data["movers"]:
                gap_str = f"{m['gap_pct']:+.2f}%"
                sections.append(
                    f"| {m['symbol']} | {m['name']} | {m['price']} | {gap_str} | {m['vol_ratio']}x |"
                )
            sections.append("")

        # ═══════════════════════════════════════
        # Section 4: 关键价位
        # ═══════════════════════════════════════
        levels = results.get("levels")
        if levels and levels.success:
            sections.append("---")
            sections.append("## 四、关键价位\n")
            for sym, lvls in levels.data.items():
                sections.append(f"### {sym}\n")
                sections.append("| 价位类型 | 价格 |")
                sections.append("|----------|------|")
                for level_name, price in lvls.items():
                    if price is not None:
                        label = level_name.replace("_", " ").title()
                        sections.append(f"| {label} | {price} |")
                sections.append("")

        # ═══════════════════════════════════════
        # Section 5: AI 技术分析（如有）
        # ═══════════════════════════════════════
        if ai_analysis:
            sections.append("---")
            sections.append("## 五、AI 技术分析 & 操盘建议\n")
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
