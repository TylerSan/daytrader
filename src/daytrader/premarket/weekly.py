"""Weekly trading plan generator."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import logging

from daytrader.premarket.analyzers.ai_analyst import invoke_claude_analysis
from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector
from daytrader.premarket.renderers.cards import CardGenerator
from daytrader.premarket.renderers.markdown import _wrap_callout

_log = logging.getLogger(__name__)


def _format_dict(data: dict, indent: int = 0) -> str:
    lines = []
    prefix = "  " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_format_dict(v, indent + 1))
        elif isinstance(v, float):
            lines.append(f"{prefix}{k}: {v:.4f}" if abs(v) < 1 else f"{prefix}{k}: {v}")
        else:
            lines.append(f"{prefix}{k}: {v}")
    return "\n".join(lines)


_WEEKLY_AI_PROMPT = """\
你是一位顶级交易计划分析师。请基于以下市场数据，为本周（{week_start}起）生成完整的周度交易计划。

## 本周市场数据

### 期货 & VIX
{futures_data}

### 板块表现
{sector_data}

### 关键价位
{levels_data}

---

请按以下结构生成完整周计划：

## 一、上周回顾

（基于当前市场位置推断上周走势）
- 上周主要指数表现总结
- 板块轮动特征
- 关键事件回顾（伊朗局势、Fed政策等）
- 本周需要延续关注的主题

## 二、本周宏观展望

### 经济日历
- 列出本周重要经济数据发布时间（CPI、PPI、初请、零售销售、FOMC纪要等）
- 标注具体日期和时间（ET）
- 评估各数据对市场的预期影响

### 市场结构分析
- 周线级别趋势方向（ES、NQ、GC）
- 周线关键支撑阻力区域
- VIX 当前水平（{vix}）对本周策略的影响

### 板块轮动展望
- 资金流向趋势（防御 vs 进攻）
- 领涨/领跌板块的延续性判断
- 本周关注的板块交易机会

### 跨市场信号
- 美元、美债、原油、黄金的相互关系
- 对股指的影响判断

## 三、本周交易计划

### 方向偏好框架
对每个主要品种（ES、NQ、GC）：
- 周度方向偏好（多/空/中性）
- 支撑理由
- 失效条件（什么情况下偏好翻转）

### 周线关键价位
- ES: 周阻力/周支撑
- NQ: 周阻力/周支撑
- GC: 周阻力/周支撑

### 事件风险窗口
- 本周需要避开或减仓的时段
- 高波动预期时段

### 本周聚焦主题
- 2-3 个本周重点关注的交易主题

## 四、本周个人目标

基于市场环境，建议：
- 交易纪律目标（如：每日最大交易次数）
- 风控目标（如：单日最大亏损）
- 改善目标（如：只在A+setup入场）
"""


class WeeklyPlanGenerator:
    def __init__(
        self,
        collector: MarketDataCollector,
        output_dir: str = "data/exports",
        obsidian_weekly_path: Path | None = None,
        cards_output_dir: str = "data/exports/images",
    ) -> None:
        self._collector = collector
        self._output_dir = Path(output_dir)
        self._obsidian_path = obsidian_weekly_path
        self._card_generator = CardGenerator(output_dir=cards_output_dir)

    def _generate_cards(
        self, results: dict[str, CollectorResult], week_start: date
    ) -> list[Path]:
        """Generate info cards; never raises."""
        try:
            return self._card_generator.generate_weekly_cards(results, week_start)
        except Exception as e:
            _log.warning("Weekly card generation failed: %s", e)
            return []

    async def generate(self, week_start: date | None = None) -> tuple[str, str]:
        """Generate data report and AI prompt. Returns (data_report, ai_prompt)."""
        week_start = week_start or date.today()
        results = await self._collector.collect_all()
        card_images = self._generate_cards(results, week_start)

        data_report = self._render_data(results, week_start, card_images=card_images)
        ai_prompt = self._build_prompt(results, week_start)

        return data_report, ai_prompt

    async def generate_full(self, week_start: date | None = None) -> str:
        """Run full pipeline: data + cards + AI analysis, merged into one report.

        Invokes Claude CLI to generate the weekly AI analysis. On failure the
        report is still saved (without the AI section).
        """
        week_start = week_start or date.today()
        results = await self._collector.collect_all()
        card_images = self._generate_cards(results, week_start)

        data_report = self._render_data(results, week_start, card_images=card_images)
        ai_prompt = self._build_prompt(results, week_start)

        _log.info("Invoking Claude for weekly AI analysis (may take 1-3 minutes)...")
        ai_analysis = invoke_claude_analysis(ai_prompt)
        if ai_analysis:
            _log.info("Weekly AI analysis received (%d chars)", len(ai_analysis))
            full_report = (
                data_report
                + "\n---\n"
                + "## AI 周度分析 & 交易计划\n\n"
                + ai_analysis
                + "\n"
            )
        else:
            _log.warning("Weekly AI analysis unavailable; saving data report only")
            full_report = data_report

        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"weekly-{week_start.isoformat()}.md"
        path.write_text(full_report)

        # Auto-sync to Obsidian vault
        if self._obsidian_path:
            self._obsidian_path.mkdir(parents=True, exist_ok=True)
            obs_file = self._obsidian_path / f"weekly-{week_start.isoformat()}.md"
            obs_file.write_text(full_report)

            if card_images:
                obs_images_dir = self._obsidian_path / "images"
                obs_images_dir.mkdir(parents=True, exist_ok=True)
                for img in card_images:
                    if img.exists():
                        (obs_images_dir / img.name).write_bytes(img.read_bytes())

        return full_report

    async def generate_and_save(self, week_start: date | None = None) -> Path:
        week_start = week_start or date.today()
        results = await self._collector.collect_all()
        card_images = self._generate_cards(results, week_start)

        data_report = self._render_data(results, week_start, card_images=card_images)

        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"weekly-{week_start.isoformat()}.md"
        path.write_text(data_report)

        # Auto-sync to Obsidian vault
        if self._obsidian_path:
            self._obsidian_path.mkdir(parents=True, exist_ok=True)
            obs_file = self._obsidian_path / f"weekly-{week_start.isoformat()}.md"
            obs_file.write_text(data_report)

            # Sync card images to Obsidian
            if card_images:
                obs_images_dir = self._obsidian_path / "images"
                obs_images_dir.mkdir(parents=True, exist_ok=True)
                for img in card_images:
                    if img.exists():
                        (obs_images_dir / img.name).write_bytes(img.read_bytes())

        return path

    def _render_data(
        self,
        results: dict[str, CollectorResult],
        week_start: date,
        card_images: list[Path] | None = None,
    ) -> str:
        now = datetime.now()
        has_cards = bool(card_images)
        sections = [
            "---",
            f"date: {week_start.isoformat()}",
            f"generated: {now.strftime('%Y-%m-%dT%H:%M:%S')}",
            "type: weekly",
            "tags: [trading, weekly, plan]",
            "---\n",
            f"# 周度交易计划 — {week_start.isoformat()} 起\n",
            f"*生成时间: {now.strftime('%Y-%m-%d %H:%M')} UTC*\n",
        ]

        # 数据速览 (card image snapshot section)
        if has_cards:
            sections.append("---")
            sections.append("## 数据速览\n")
            for img in card_images:
                label = img.stem.split("-", 4)[-1] if "-" in img.stem else img.stem
                sections.append(f"![{label}](images/{img.name})")
            sections.append("")

        sections.append("---")
        sections.append("## 市场数据概览\n")

        futures = results.get("futures")
        if futures and futures.success:
            header_lines = [
                "### 期货 & VIX",
                "| 品种 | 现价 | 涨跌幅 | 前收 |",
                "|------|------|--------|------|",
            ]
            data_lines: list[str] = []
            for sym, data in futures.data.items():
                if not isinstance(data, dict):
                    continue
                price = data.get("price", "—")
                change = data.get("change_pct")
                prev = data.get("prev_close", "—")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                data_lines.append(f"| {sym} | {price} | {change_str} | {prev} |")
            table_lines = header_lines + data_lines
            if has_cards:
                sections.extend(_wrap_callout("详细数据：期货 & VIX", table_lines))
            else:
                sections.extend(table_lines + [""])

        sectors = results.get("sectors")
        if sectors and sectors.success:
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            header_lines = [
                "### 板块强弱",
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

        levels = results.get("levels")
        if levels and levels.success:
            header_lines = ["### 关键价位"]
            data_lines = []
            for sym, lvls in levels.data.items():
                data_lines.append(f"**{sym}:**")
                for name, price in lvls.items():
                    if price is not None:
                        label = name.replace("_", " ").title()
                        data_lines.append(f"- {label}: {price}")
                data_lines.append("")
            table_lines = header_lines + data_lines
            if has_cards:
                sections.extend(_wrap_callout("详细数据：关键价位", table_lines))
            else:
                sections.extend(table_lines)

        sections.append("---")
        sections.append("*运行 `daytrader weekly analyze` 或发送 \"执行周计划AI分析\" 获取完整智能分析*\n")

        return "\n".join(sections)

    def _build_prompt(self, results: dict[str, CollectorResult], week_start: date) -> str:
        futures_data = "No data"
        if "futures" in results and results["futures"].success:
            futures_data = _format_dict(results["futures"].data)

        sector_data = "No data"
        if "sectors" in results and results["sectors"].success:
            sector_data = _format_dict(results["sectors"].data)

        levels_data = "No data"
        if "levels" in results and results["levels"].success:
            levels_data = _format_dict(results["levels"].data)

        vix = "N/A"
        if "futures" in results and results["futures"].success:
            vix_data = results["futures"].data.get("^VIX", {})
            if isinstance(vix_data, dict):
                vix = vix_data.get("price", "N/A")

        return _WEEKLY_AI_PROMPT.format(
            week_start=week_start.isoformat(),
            futures_data=futures_data,
            sector_data=sector_data,
            levels_data=levels_data,
            vix=vix,
        )
