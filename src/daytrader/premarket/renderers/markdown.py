"""Markdown report renderer for pre-market analysis."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult


def _wrap_callout(title: str, lines: list[str]) -> list[str]:
    """Wrap content lines in an Obsidian collapsible callout block.

    Returns lines including a trailing empty line (no prefix) to terminate
    the callout, so the next callout can start cleanly.
    """
    wrapped = [f"> [!info]- {title}"]
    for line in lines:
        if line == "":
            wrapped.append(">")
        else:
            wrapped.append(f"> {line}")
    wrapped.append("")  # empty line terminates the callout
    return wrapped


class MarkdownRenderer:
    def __init__(self, output_dir: str = "data/exports") -> None:
        self._output_dir = Path(output_dir)

    def render(
        self,
        results: dict[str, CollectorResult],
        date: date,
        ai_analysis: str = "",
        card_images: list[Path] | None = None,
    ) -> str:
        sections: list[str] = []
        now = datetime.now()
        has_cards = bool(card_images)

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
        # 数据速览 (card image snapshot section)
        # ═══════════════════════════════════════
        if has_cards:
            sections.append("---")
            sections.append("## 数据速览\n")
            for img in card_images:
                label = img.stem.split("-", 4)[-1] if "-" in img.stem else img.stem
                sections.append(f"![{label}](images/{img.name})")
            sections.append("")

        # ═══════════════════════════════════════
        # Section 1: 宏观环境
        # ═══════════════════════════════════════
        sections.append("---")
        sections.append("## 一、宏观环境\n")

        # 1.1 期货总览
        futures = results.get("futures")
        if futures and futures.success:
            header_lines = [
                "### 1.1 指数期货 & VIX",
                "| 品种 | 现价 | 涨跌幅 | 前收 | 日高 | 日低 |",
                "|------|------|--------|------|------|------|",
            ]
            data_lines: list[str] = []
            for sym, data in futures.data.items():
                if not isinstance(data, dict):
                    continue
                price = data.get("price", "—")
                change = data.get("change_pct")
                prev = data.get("prev_close", "—")
                high = data.get("day_high", "—")
                low = data.get("day_low", "—")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                data_lines.append(f"| {sym} | {price} | {change_str} | {prev} | {high} | {low} |")
            table_lines = header_lines + data_lines
            if has_cards:
                sections.extend(_wrap_callout("详细数据：指数期货 & VIX", table_lines))
            else:
                sections.extend(table_lines + [""])

        # 1.2 隔夜走势
        if futures and futures.success:
            has_overnight = any(
                "overnight_high" in d
                for d in futures.data.values()
                if isinstance(d, dict)
            )
            if has_overnight:
                header_lines = [
                    "### 1.2 隔夜走势（Globex）",
                    "| 品种 | 隔夜高 | 隔夜低 | 区间 | 亚洲高 | 亚洲低 | 欧洲高 | 欧洲低 |",
                    "|------|--------|--------|------|--------|--------|--------|--------|",
                ]
                data_lines = []
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
                    data_lines.append(f"| {sym} | {oh} | {ol} | {rng} | {ah} | {al} | {eh} | {el} |")
                table_lines = header_lines + data_lines
                if has_cards:
                    sections.extend(_wrap_callout("详细数据：隔夜走势", table_lines))
                else:
                    sections.extend(table_lines + [""])

        # 1.3 板块强弱
        sectors = results.get("sectors")
        if sectors and sectors.success:
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            header_lines = [
                "### 1.3 板块强弱",
                "| ETF | 板块 | 涨跌幅 |",
                "|-----|------|--------|",
            ]
            data_lines = []
            for sym, data in sorted_sectors:
                name = data.get("name", sym)
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                data_lines.append(f"| {sym} | {name} | {change_str} |")
            table_lines = header_lines + data_lines
            if has_cards:
                sections.extend(_wrap_callout("详细数据：板块强弱", table_lines))
            else:
                sections.extend(table_lines + [""])

        # ═══════════════════════════════════════
        # Section 2: 消息面
        # ═══════════════════════════════════════
        news = results.get("news")
        if news and news.success and news.data.get("headlines"):
            sections.append("---")
            sections.append("## 二、消息面\n")
            for item in news.data["headlines"]:
                title = item.get("title", "")
                title_zh = item.get("title_zh", "")
                publisher = item.get("publisher", "")
                pub_info = f" — *{publisher}*" if publisher else ""
                if title_zh:
                    sections.append(f"- **{title_zh}**{pub_info}")
                    sections.append(f"  > {title}")
                else:
                    sections.append(f"- **{title}**{pub_info}")
            sections.append("")

        # ═══════════════════════════════════════
        # Section 3: 盘前异动
        # ═══════════════════════════════════════
        movers = results.get("movers")
        if movers and movers.success and movers.data.get("movers"):
            sections.append("---")
            sections.append("## 三、盘前异动\n")
            header_lines = [
                "| 代码 | 名称 | 现价 | 缺口 | 量比 |",
                "|------|------|------|------|------|",
            ]
            data_lines = []
            for m in movers.data["movers"]:
                gap_str = f"{m['gap_pct']:+.2f}%"
                data_lines.append(
                    f"| {m['symbol']} | {m['name']} | {m['price']} | {gap_str} | {m['vol_ratio']}x |"
                )
            table_lines = header_lines + data_lines
            if has_cards:
                sections.extend(_wrap_callout("详细数据：盘前异动", table_lines))
            else:
                sections.extend(table_lines + [""])

        # ═══════════════════════════════════════
        # Section 4: 关键价位
        # ═══════════════════════════════════════
        levels = results.get("levels")
        if levels and levels.success:
            sections.append("---")
            sections.append("## 四、关键价位\n")
            for sym, lvls in levels.data.items():
                header_lines = [
                    f"### {sym}",
                    "| 价位类型 | 价格 |",
                    "|----------|------|",
                ]
                data_lines = []
                for level_name, price in lvls.items():
                    if price is not None:
                        label = level_name.replace("_", " ").title()
                        data_lines.append(f"| {label} | {price} |")
                table_lines = header_lines + data_lines
                if has_cards:
                    sections.extend(
                        _wrap_callout(f"详细数据：{sym} 关键价位", table_lines)
                    )
                else:
                    sections.extend(table_lines + [""])

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
        obsidian_path: Path | None = None,
        card_images: list[Path] | None = None,
    ) -> Path:
        content = self.render(results, date, ai_analysis=ai_analysis, card_images=card_images)

        # Save to default output dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"premarket-{date.isoformat()}.md"
        path.write_text(content)

        # Auto-sync to Obsidian vault
        if obsidian_path:
            obsidian_path.mkdir(parents=True, exist_ok=True)
            obs_file = obsidian_path / f"premarket-{date.isoformat()}.md"
            obs_file.write_text(content)

            # Also sync card images to Obsidian's images subfolder
            if card_images:
                obs_images_dir = obsidian_path / "images"
                obs_images_dir.mkdir(parents=True, exist_ok=True)
                for img in card_images:
                    if img.exists():
                        (obs_images_dir / img.name).write_bytes(img.read_bytes())

        return path
