"""Chart renderer for premarket reports.

Generates matplotlib PNGs:
- TF stack: 4 stacked subplots (W/D/4H/1H) per symbol; line plot of close prices
- Future: context chart (key levels overlaid)

Phase 6 keeps it simple — line plots, no candlesticks (mplfinance is heavy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt

from daytrader.core.ib_client import OHLCV


@dataclass(frozen=True)
class ChartArtifacts:
    tf_stack_paths: dict[str, Path] = field(default_factory=dict)


class ChartRenderer:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_tf_stack(
        self,
        symbol: str,
        bars_by_tf: dict[str, list[OHLCV]],
        today: str,
    ) -> Path:
        fig, axes = plt.subplots(nrows=4, ncols=1, figsize=(10, 8), sharex=False)
        for ax, tf in zip(axes, ("1W", "1D", "4H", "1H")):
            bars = bars_by_tf.get(tf, [])
            if not bars:
                ax.text(0.5, 0.5, f"{tf}: no data",
                        ha="center", va="center", transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                xs = list(range(len(bars)))
                ys = [b.close for b in bars]
                ax.plot(xs, ys, linewidth=1.0)
                ax.set_title(f"{tf}", fontsize=9, loc="left")
                ax.tick_params(labelsize=7)
            ax.grid(True, alpha=0.3)

        fig.suptitle(f"{symbol} — TF stack ({today})", fontsize=11)
        fig.tight_layout()

        path = self.output_dir / f"tf-stack-{symbol}-{today}.png"
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return path

    def render_all(
        self,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        today: str,
    ) -> ChartArtifacts:
        paths: dict[str, Path] = {}
        for symbol, bars in bars_by_symbol_and_tf.items():
            paths[symbol] = self.render_tf_stack(
                symbol=symbol, bars_by_tf=bars, today=today
            )
        return ChartArtifacts(tf_stack_paths=paths)
