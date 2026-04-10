"""Info-card image generator using baoyu-image-cards skill."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult

_STYLE_INSTRUCTIONS = """\
风格要求：
- 简洁现代风（Apple 风格）
- 白底 + 浅灰卡片背景
- 涨跌色：绿色（涨）/ 红色（跌）/ 灰色（平）
- 字体：无衬线、数字加粗突出
- 宽高比：1:1（方形）
- 语言：中文"""


class CardGenerator:
    def __init__(self, output_dir: str = "data/exports/images") -> None:
        self._output_dir = Path(output_dir)

    def build_overview_prompt(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> str:
        futures = results.get("futures")
        if not futures or not futures.success:
            return ""

        lines = [f"# 市场总览 — {target_date.isoformat()}\n"]
        for sym, data in futures.data.items():
            if not isinstance(data, dict):
                continue
            price = data.get("price", "—")
            change = data.get("change_pct")
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
            oh = data.get("overnight_high", "")
            ol = data.get("overnight_low", "")
            overnight = f"  隔夜区间: {ol}–{oh}" if oh and ol else ""
            lines.append(f"- **{sym}**: {price} ({change_str}){overnight}")

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：仪表盘网格，每个品种一个数据块，涨绿跌红，箭头指示方向。")
        return "\n".join(lines)

    def build_sectors_prompt(self, results: dict[str, CollectorResult]) -> str:
        sectors = results.get("sectors")
        if not sectors or not sectors.success:
            return ""

        sorted_sectors = sorted(
            sectors.data.items(),
            key=lambda x: x[1].get("change_pct") or 0,
            reverse=True,
        )

        lines = ["# 板块强弱\n"]
        for sym, data in sorted_sectors:
            name = data.get("name", sym)
            change = data.get("change_pct")
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
            lines.append(f"- {sym} ({name}): {change_str}")

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：水平柱状图/热力条，从强到弱渐变色排列。")
        return "\n".join(lines)

    def build_movers_prompt(self, results: dict[str, CollectorResult]) -> str:
        movers = results.get("movers")
        if not movers or not movers.success or not movers.data.get("movers"):
            return ""

        lines = ["# 盘前异动\n"]
        for m in movers.data["movers"]:
            gap_str = f"{m['gap_pct']:+.2f}%"
            lines.append(
                f"- **{m['symbol']}** ({m['name']}): 缺口 {gap_str}, 量比 {m['vol_ratio']}x"
            )

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：列表卡片，大号 gap 百分比突出显示，涨绿跌红。")
        return "\n".join(lines)

    def build_levels_prompt(self, results: dict[str, CollectorResult]) -> str:
        levels = results.get("levels")
        if not levels or not levels.success:
            return ""

        lines = ["# 关键价位\n"]
        for sym, lvls in levels.data.items():
            lines.append(f"\n**{sym}:**")
            for name, price in lvls.items():
                if price is not None:
                    label = name.replace("_", " ").title()
                    lines.append(f"- {label}: {price}")

        lines.append(f"\n{_STYLE_INSTRUCTIONS}")
        lines.append("\n布局：每个品种一行，价格标注在数轴示意上，支撑阻力清晰标注。")
        return "\n".join(lines)

    def image_paths(self, prefix: str, target_date: date) -> dict[str, Path]:
        """Return expected image paths for a given report date."""
        d = target_date.isoformat()
        return {
            "overview": self._output_dir / f"{prefix}-{d}-overview.webp",
            "sectors": self._output_dir / f"{prefix}-{d}-sectors.webp",
            "movers": self._output_dir / f"{prefix}-{d}-movers.webp",
            "levels": self._output_dir / f"{prefix}-{d}-levels.webp",
        }
