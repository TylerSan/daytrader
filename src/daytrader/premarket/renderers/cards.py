"""Info-card image generator using matplotlib for local rendering."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

from daytrader.premarket.collectors.base import CollectorResult

_log = logging.getLogger(__name__)

# --- Style constants ---
BG_COLOR = "#FFFFFF"
CARD_BG = "#F5F5F7"
UP_COLOR = "#34C759"
DOWN_COLOR = "#FF3B30"
NEUTRAL_COLOR = "#86868B"
TEXT_DARK = "#1D1D1F"
TEXT_GRAY = "#86868B"
FIGSIZE = (8, 8)
DPI = 100

# Chinese font support — macOS uses Hiragino, Linux uses Noto Sans CJK
matplotlib.rcParams["font.family"] = [
    "Hiragino Sans GB",       # macOS
    "Noto Sans CJK SC",       # Linux (apt install fonts-noto-cjk)
    "Noto Sans SC",            # Linux alternate name
    "WenQuanYi Micro Hei",    # Linux fallback
    "Arial Unicode MS",        # Windows/macOS fallback
    "sans-serif",
]
matplotlib.rcParams["axes.unicode_minus"] = False


def _change_color(val: float | None) -> str:
    if val is None:
        return NEUTRAL_COLOR
    if val > 0:
        return UP_COLOR
    if val < 0:
        return DOWN_COLOR
    return NEUTRAL_COLOR


def _arrow(val: float | None) -> str:
    if val is None:
        return ""
    if val > 0:
        return "▲"
    if val < 0:
        return "▼"
    return ""


class CardGenerator:
    def __init__(self, output_dir: str = "data/exports/images") -> None:
        self._output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------

    def _extract_overview_data(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> dict | None:
        futures = results.get("futures")
        if not futures or not futures.success or not futures.data:
            return None

        instruments = []
        for sym, data in futures.data.items():
            if not isinstance(data, dict):
                continue
            oh = data.get("overnight_high")
            ol = data.get("overnight_low")
            overnight_range = f"{ol}–{oh}" if oh is not None and ol is not None else None
            instruments.append(
                {
                    "symbol": sym,
                    "price": data.get("price"),
                    "change_pct": data.get("change_pct"),
                    "overnight_range": overnight_range,
                }
            )

        if not instruments:
            return None

        return {"date": target_date, "instruments": instruments}

    def _extract_sectors_data(
        self, results: dict[str, CollectorResult]
    ) -> list[tuple] | None:
        sectors = results.get("sectors")
        if not sectors or not sectors.success or not sectors.data:
            return None

        sorted_sectors = sorted(
            sectors.data.items(),
            key=lambda x: x[1].get("change_pct") or 0,
            reverse=True,
        )

        result = []
        for sym, data in sorted_sectors:
            name = data.get("name", sym)
            pct = data.get("change_pct")
            result.append((sym, name, pct))

        return result if result else None

    def _extract_movers_data(
        self, results: dict[str, CollectorResult]
    ) -> list[dict] | None:
        movers = results.get("movers")
        if not movers or not movers.success or not movers.data.get("movers"):
            return None

        return list(movers.data["movers"]) or None

    def _extract_levels_data(
        self, results: dict[str, CollectorResult]
    ) -> dict | None:
        levels = results.get("levels")
        if not levels or not levels.success or not levels.data:
            return None

        return dict(levels.data)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render_overview_card(self, data: dict, output_path: Path) -> Path:
        instruments = data["instruments"]
        target_date = data["date"]

        fig = plt.figure(figsize=FIGSIZE, facecolor=BG_COLOR)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        fig.patch.set_facecolor(BG_COLOR)

        # Title
        ax.text(
            0.5, 0.94,
            f"市场总览 — {target_date.isoformat()}",
            ha="center", va="top",
            fontsize=22, fontweight="bold", color=TEXT_DARK,
            transform=ax.transAxes,
        )

        n = len(instruments)
        cols = 3 if n > 2 else 2
        rows = (n + cols - 1) // cols

        tile_w = 0.28
        tile_h = 0.20
        h_gap = (1.0 - cols * tile_w) / (cols + 1)
        v_gap = 0.04

        # Available vertical space: from 0.06 to 0.88
        v_start = 0.88
        total_h = rows * tile_h + (rows - 1) * v_gap
        top_y = v_start - (v_start - 0.06 - total_h) / 2

        for idx, inst in enumerate(instruments):
            row = idx // cols
            col = idx % cols
            x0 = h_gap + col * (tile_w + h_gap)
            y0 = top_y - row * (tile_h + v_gap) - tile_h

            # Tile background
            fancy = FancyBboxPatch(
                (x0, y0), tile_w, tile_h,
                boxstyle="round,pad=0.01",
                facecolor=CARD_BG, edgecolor="none",
                transform=ax.transAxes, zorder=1,
            )
            ax.add_patch(fancy)

            sym = inst["symbol"]
            price = inst["price"]
            change_pct = inst["change_pct"]
            overnight_range = inst.get("overnight_range")

            cx = x0 + tile_w / 2
            price_str = f"{price:,.2f}" if price is not None else "—"
            pct_str = (
                f"{_arrow(change_pct)} {change_pct:+.2f}%"
                if isinstance(change_pct, (int, float))
                else "—"
            )
            color = _change_color(change_pct)

            # Symbol label
            ax.text(
                x0 + 0.012, y0 + tile_h - 0.012, sym,
                ha="left", va="top", fontsize=10, color=TEXT_GRAY,
                transform=ax.transAxes, zorder=2,
            )
            # Price
            ax.text(
                cx, y0 + tile_h * 0.52, price_str,
                ha="center", va="center", fontsize=26, fontweight="bold", color=TEXT_DARK,
                transform=ax.transAxes, zorder=2,
            )
            # Change %
            ax.text(
                cx, y0 + tile_h * 0.22, pct_str,
                ha="center", va="center", fontsize=15, color=color,
                transform=ax.transAxes, zorder=2,
            )
            # Overnight range subtitle
            if overnight_range:
                ax.text(
                    cx, y0 + 0.01, overnight_range,
                    ha="center", va="bottom", fontsize=8, color=TEXT_GRAY,
                    transform=ax.transAxes, zorder=2,
                )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
        plt.close(fig)
        return output_path

    def _render_sectors_card(self, data: list, output_path: Path) -> Path:
        symbols = [f"{sym} {name}" for sym, name, _ in data]
        pcts = [p if isinstance(p, (int, float)) else 0.0 for _, _, p in data]
        colors = [UP_COLOR if p >= 0 else DOWN_COLOR for p in pcts]

        fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG_COLOR)
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)

        y_pos = range(len(symbols))
        ax.barh(list(y_pos), pcts, color=colors, height=0.6, zorder=2)
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(symbols, fontsize=11, color=TEXT_DARK)
        ax.axvline(0, color=TEXT_GRAY, linewidth=0.8, zorder=1)
        ax.set_xlabel("变动 %", fontsize=10, color=TEXT_GRAY)

        # Value labels on bars
        for i, (val, bar_y) in enumerate(zip(pcts, y_pos)):
            ha = "left" if val >= 0 else "right"
            offset = 0.05 if val >= 0 else -0.05
            ax.text(
                val + offset, bar_y, f"{val:+.2f}%",
                va="center", ha=ha, fontsize=9, color=TEXT_DARK,
            )

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="x", colors=TEXT_GRAY)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#E5E5EA", linewidth=0.5, zorder=0)

        ax.set_title("板块强弱", fontsize=22, fontweight="bold", color=TEXT_DARK, pad=16)

        fig.tight_layout(pad=1.5)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
        plt.close(fig)
        return output_path

    def _render_movers_card(self, data: list, output_path: Path) -> Path:
        movers = data[:8]  # cap at 8

        fig = plt.figure(figsize=FIGSIZE, facecolor=BG_COLOR)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        fig.patch.set_facecolor(BG_COLOR)

        ax.text(
            0.5, 0.95,
            "盘前异动",
            ha="center", va="top",
            fontsize=22, fontweight="bold", color=TEXT_DARK,
            transform=ax.transAxes,
        )

        n = len(movers)
        row_h = 0.09
        v_start = 0.88
        margin_x = 0.05
        row_w = 1 - 2 * margin_x

        for idx, m in enumerate(movers):
            y0 = v_start - idx * (row_h + 0.02)

            fancy = FancyBboxPatch(
                (margin_x, y0 - row_h), row_w, row_h,
                boxstyle="round,pad=0.008",
                facecolor=CARD_BG, edgecolor="none",
                transform=ax.transAxes, zorder=1,
            )
            ax.add_patch(fancy)

            sym = m.get("symbol", "")
            name = m.get("name", "")
            gap_pct = m.get("gap_pct")
            vol_ratio = m.get("vol_ratio")
            color = _change_color(gap_pct)

            gap_str = (
                f"{_arrow(gap_pct)} {gap_pct:+.2f}%"
                if isinstance(gap_pct, (int, float))
                else "—"
            )
            vol_str = f"量比 {vol_ratio:.2f}x" if isinstance(vol_ratio, (int, float)) else ""

            cy = y0 - row_h / 2

            # Symbol
            ax.text(
                margin_x + 0.015, cy, sym,
                ha="left", va="center", fontsize=17, fontweight="bold", color=TEXT_DARK,
                transform=ax.transAxes, zorder=2,
            )
            # Name
            ax.text(
                margin_x + 0.015, cy - 0.025, name,
                ha="left", va="center", fontsize=9, color=TEXT_GRAY,
                transform=ax.transAxes, zorder=2,
            )
            # Gap %
            ax.text(
                0.5, cy, gap_str,
                ha="center", va="center", fontsize=22, color=color,
                transform=ax.transAxes, zorder=2,
            )
            # Vol ratio
            if vol_str:
                ax.text(
                    0.93, cy, vol_str,
                    ha="right", va="center", fontsize=10, color=TEXT_GRAY,
                    transform=ax.transAxes, zorder=2,
                )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
        plt.close(fig)
        return output_path

    def _render_levels_card(self, data: dict, output_path: Path) -> Path:
        """Render key levels as a clean table: rows = level types, cols = symbols."""
        symbols = list(data.keys())

        level_order = [
            ("weekly_high", "周高", "#FF9500"),
            ("prior_day_high", "前日高", DOWN_COLOR),
            ("prior_day_close", "前日收", TEXT_DARK),
            ("approx_vwap_5d", "VWAP 5D", "#5AC8FA"),
            ("prior_day_low", "前日低", UP_COLOR),
            ("weekly_low", "周低", "#5856D6"),
        ]

        # Build table data
        row_labels = []
        row_colors = []
        cell_text: list[list[str]] = []
        for key, label, color in level_order:
            has_any = any(data[sym].get(key) is not None for sym in symbols)
            if not has_any:
                continue
            row_labels.append(label)
            row_colors.append(color)
            row = []
            for sym in symbols:
                val = data[sym].get(key)
                row.append(f"{val:.2f}" if val is not None else "—")
            cell_text.append(row)

        fig = plt.figure(figsize=FIGSIZE, facecolor=BG_COLOR)
        fig.patch.set_facecolor(BG_COLOR)
        fig.suptitle("关键价位", fontsize=22, fontweight="bold", color=TEXT_DARK, y=0.95)

        ax = fig.add_axes([0.08, 0.08, 0.84, 0.78])
        ax.axis("off")
        ax.set_facecolor(BG_COLOR)

        table = ax.table(
            cellText=cell_text,
            rowLabels=row_labels,
            colLabels=symbols,
            loc="center",
            cellLoc="center",
            rowLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(14)
        table.scale(1.0, 2.4)

        # Style header row (column labels)
        n_cols = len(symbols)
        n_rows = len(row_labels)
        for col in range(n_cols):
            cell = table[0, col]
            cell.set_facecolor(CARD_BG)
            cell.set_text_props(
                color=TEXT_DARK, fontweight="bold", fontsize=16
            )
            cell.set_edgecolor("#D2D2D7")
            cell.set_linewidth(0.5)
            cell.set_height(0.09)

        # Style row labels (level type names) with their color
        for row_idx, color in enumerate(row_colors, start=1):
            cell = table[row_idx, -1]
            cell.set_facecolor(CARD_BG)
            cell.set_text_props(color=color, fontweight="bold", fontsize=13)
            cell.set_edgecolor("#D2D2D7")
            cell.set_linewidth(0.5)

        # Style data cells
        for row_idx in range(1, n_rows + 1):
            for col_idx in range(n_cols):
                cell = table[row_idx, col_idx]
                cell.set_facecolor(BG_COLOR)
                cell.set_text_props(
                    color=TEXT_DARK, fontweight="bold", fontsize=15
                )
                cell.set_edgecolor("#E5E5EA")
                cell.set_linewidth(0.5)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
        plt.close(fig)
        return output_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def image_paths(self, prefix: str, target_date: date) -> dict[str, Path]:
        """Return expected image paths for a given report date."""
        d = target_date.isoformat()
        return {
            "overview": self._output_dir / f"{prefix}-{d}-overview.webp",
            "sectors": self._output_dir / f"{prefix}-{d}-sectors.webp",
            "movers": self._output_dir / f"{prefix}-{d}-movers.webp",
            "levels": self._output_dir / f"{prefix}-{d}-levels.webp",
        }

    def generate_premarket_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        """Generate 4 cards. Skip any where extraction returns None or empty."""
        paths = self.image_paths("premarket", target_date)
        generated: list[Path] = []

        tasks = [
            ("overview", self._extract_overview_data, self._render_overview_card,
             {"results": results, "target_date": target_date}),
            ("sectors", self._extract_sectors_data, self._render_sectors_card,
             {"results": results}),
            ("movers", self._extract_movers_data, self._render_movers_card,
             {"results": results}),
            ("levels", self._extract_levels_data, self._render_levels_card,
             {"results": results}),
        ]

        for card_name, extractor, renderer, kwargs in tasks:
            try:
                data = extractor(**kwargs)
                if not data:
                    continue
                path = renderer(data, paths[card_name])
                generated.append(path)
            except Exception as exc:
                _log.warning("Failed to generate %s card: %s", card_name, exc)

        return generated

    def generate_weekly_cards(
        self, results: dict[str, CollectorResult], target_date: date
    ) -> list[Path]:
        """Generate 3 cards: overview, levels, sectors."""
        paths = self.image_paths("weekly", target_date)
        generated: list[Path] = []

        tasks = [
            ("overview", self._extract_overview_data, self._render_overview_card,
             {"results": results, "target_date": target_date}),
            ("levels", self._extract_levels_data, self._render_levels_card,
             {"results": results}),
            ("sectors", self._extract_sectors_data, self._render_sectors_card,
             {"results": results}),
        ]

        for card_name, extractor, renderer, kwargs in tasks:
            try:
                data = extractor(**kwargs)
                if not data:
                    continue
                path = renderer(data, paths[card_name])
                generated.append(path)
            except Exception as exc:
                _log.warning("Failed to generate %s card: %s", card_name, exc)

        return generated
