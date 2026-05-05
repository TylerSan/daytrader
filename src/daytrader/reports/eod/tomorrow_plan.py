"""TomorrowPreliminaryPlan — compose input data for AI's tomorrow section."""

from __future__ import annotations

from typing import Any

from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow


class TomorrowPreliminaryPlan:
    """Build markdown input for the AI's '📅 Tomorrow Preliminary Plan' section.

    The AI prompt template instructs the AI to use this input as ground-truth
    starting data; AI is asked to add econ event context (via web search) and
    render the section. This class does NOT call AI — it just assembles
    structured input data.
    """

    def build_input_data(
        self,
        today_bars: dict[str, dict[str, list[Any]]],   # per symbol per TF
        today_retrospective: dict[str, RetrospectiveRow],
        sentiment_md: str,
    ) -> str:
        """Compose markdown that the AI will use to render tomorrow's preliminary plan.

        Sections:
        - Per-symbol today's H/L/C (from 1D bars)
        - Retrospective insight per symbol (if available)
        - Sentiment shift indicator
        """
        lines: list[str] = []
        lines.append("### Today's H / L / C per symbol (for tomorrow level carryover)")
        if not today_bars:
            lines.append("- (no bars data available)")
        else:
            for symbol, by_tf in today_bars.items():
                d_bars = by_tf.get("1D") or []
                if not d_bars:
                    lines.append(f"- {symbol}: no daily bar")
                    continue
                last = d_bars[-1]
                lines.append(
                    f"- **{symbol}**: today H={last.high:.2f} / L={last.low:.2f} / "
                    f"C={last.close:.2f}"
                )

        lines.append("")
        lines.append("### Today's retrospective insight (per symbol)")
        if not today_retrospective:
            lines.append("- (no retrospective; today's premarket plan was unavailable)")
        else:
            for symbol, row in today_retrospective.items():
                trigger_pct = (
                    100.0 * row.triggered_count / row.total_levels
                    if row.total_levels else 0
                )
                lines.append(
                    f"- **{symbol}**: {row.triggered_count}/{row.total_levels} "
                    f"levels triggered ({trigger_pct:.0f}%); "
                    f"sim total {row.sim_total_r:+.1f}R, actual {row.actual_total_r:+.1f}R, "
                    f"gap {row.gap_r:+.1f}R"
                )

        lines.append("")
        lines.append("### Today's sentiment (carryover for tomorrow opening hypothesis)")
        if sentiment_md.strip():
            for line in sentiment_md.splitlines():
                if "Macro" in line or "总体" in line or "+/-" in line:
                    lines.append(f"- {line.strip()}")
                    break
            else:
                lines.append("- (sentiment available but not summarizable inline)")
        else:
            lines.append("- (no sentiment data)")

        lines.append("")
        lines.append("### Tomorrow econ events (AI: use web search to verify dates+times)")
        lines.append("- (AI fills in via web search)")

        return "\n".join(lines)
