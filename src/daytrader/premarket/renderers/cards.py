"""Info-card image generator using baoyu-image-cards skill."""

from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path

from daytrader.premarket.collectors.base import CollectorResult

_log = logging.getLogger(__name__)
_CLAUDE_BIN = "/opt/homebrew/bin/claude"
_TIMEOUT = 120

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

    def generate_card(self, prompt: str, output_path: Path) -> Path | None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        full_prompt = (
            f"/image-cards\n\n"
            f"生成单张信息图卡片，保存为 WebP 格式到 {output_path}\n\n"
            f"{prompt}"
        )
        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "-p", full_prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                cwd=str(Path(__file__).resolve().parents[4]),
            )
            if result.returncode == 0 and output_path.exists():
                return output_path
            _log.warning("Card generation failed (rc=%d): %s", result.returncode, result.stderr[:200])
            return None
        except subprocess.TimeoutExpired:
            _log.warning("Card generation timed out after %ds", _TIMEOUT)
            return None
        except Exception as e:
            _log.warning("Card generation error: %s", e)
            return None

    def generate_premarket_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        paths = self.image_paths("premarket", target_date)
        generated: list[Path] = []

        prompt_builders = [
            ("overview", self.build_overview_prompt, {"results": results, "target_date": target_date}),
            ("sectors", self.build_sectors_prompt, {"results": results}),
            ("movers", self.build_movers_prompt, {"results": results}),
            ("levels", self.build_levels_prompt, {"results": results}),
        ]

        for card_name, builder, kwargs in prompt_builders:
            prompt = builder(**kwargs)
            if not prompt:
                continue
            result = self.generate_card(prompt, paths[card_name])
            if result:
                generated.append(result)

        return generated

    def generate_weekly_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        paths = self.image_paths("weekly", target_date)
        generated: list[Path] = []

        # Weekly uses overview, levels, and sectors (3 cards).
        # Note: the spec's "event risk calendar" card is deferred.
        prompt_builders = [
            ("overview", self.build_overview_prompt, {"results": results, "target_date": target_date}),
            ("levels", self.build_levels_prompt, {"results": results}),
            ("sectors", self.build_sectors_prompt, {"results": results}),
        ]

        for card_name, builder, kwargs in prompt_builders:
            prompt = builder(**kwargs)
            if not prompt:
                continue
            result = self.generate_card(prompt, paths[card_name])
            if result:
                generated.append(result)

        return generated
