"""Weekly trading plan generator."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult, MarketDataCollector


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
    def __init__(self, collector: MarketDataCollector, output_dir: str = "data/exports") -> None:
        self._collector = collector
        self._output_dir = Path(output_dir)

    async def generate(self, week_start: date | None = None) -> tuple[str, str]:
        """Generate data report and AI prompt. Returns (data_report, ai_prompt)."""
        week_start = week_start or date.today()
        results = await self._collector.collect_all()

        data_report = self._render_data(results, week_start)
        ai_prompt = self._build_prompt(results, week_start)

        return data_report, ai_prompt

    async def generate_and_save(self, week_start: date | None = None) -> Path:
        week_start = week_start or date.today()
        data_report, _ = await self.generate(week_start)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"weekly-{week_start.isoformat()}.md"
        path.write_text(data_report)
        return path

    def _render_data(self, results: dict[str, CollectorResult], week_start: date) -> str:
        sections = [
            f"# 周度交易计划 — {week_start.isoformat()} 起\n",
            f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC*\n",
        ]

        sections.append("---")
        sections.append("## 市场数据概览\n")

        futures = results.get("futures")
        if futures and futures.success:
            sections.append("### 期货 & VIX\n")
            sections.append("| 品种 | 现价 | 涨跌幅 | 前收 |")
            sections.append("|------|------|--------|------|")
            for sym, data in futures.data.items():
                if not isinstance(data, dict):
                    continue
                price = data.get("price", "—")
                change = data.get("change_pct")
                prev = data.get("prev_close", "—")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                sections.append(f"| {sym} | {price} | {change_str} | {prev} |")
            sections.append("")

        sectors = results.get("sectors")
        if sectors and sectors.success:
            sorted_sectors = sorted(
                sectors.data.items(),
                key=lambda x: x[1].get("change_pct") or 0,
                reverse=True,
            )
            sections.append("### 板块强弱\n")
            sections.append("| ETF | 板块 | 涨跌幅 |")
            sections.append("|-----|------|--------|")
            for sym, data in sorted_sectors:
                name = data.get("name", sym)
                change = data.get("change_pct")
                change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
                sections.append(f"| {sym} | {name} | {change_str} |")
            sections.append("")

        levels = results.get("levels")
        if levels and levels.success:
            sections.append("### 关键价位\n")
            for sym, lvls in levels.data.items():
                sections.append(f"**{sym}:**")
                for name, price in lvls.items():
                    if price is not None:
                        label = name.replace("_", " ").title()
                        sections.append(f"- {label}: {price}")
                sections.append("")

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
