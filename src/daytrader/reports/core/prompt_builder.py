"""PromptBuilder: assemble Anthropic Messages API request from context + data.

Produces a list of message dicts (system + user) ready to pass to
AIAnalyst.call_claude(). System blocks use cache_control = ephemeral
on stable parts (template + Contract.md); dynamic data is uncached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.templates import load_template

if TYPE_CHECKING:
    from daytrader.reports.futures_data.futures_section import FuturesSection


class PromptBuilder:
    """Assemble Anthropic Messages API prompts."""

    def build_premarket(
        self,
        context: ReportContext,
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
        tradable_symbols: list[str],
        news_items: list[dict[str, Any]],
        run_timestamp_pt: str,
        run_timestamp_et: str,
        futures_data: "FuturesSection | None" = None,
    ) -> list[dict[str, Any]]:
        template = load_template("premarket")
        contract_section = (
            context.contract_text
            if context.contract_text is not None
            else "Contract.md: not yet filled by user"
        )

        system_blocks = [
            {
                "type": "text",
                "text": template,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"## Contract.md content\n\n{contract_section}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        lock_in_block = self._build_lock_in_block(context)
        bars_block = self._build_multi_symbol_bars_block(bars_by_symbol_and_tf)
        futures_block = self._build_futures_section_block(futures_data)
        news_block = self._build_news_block(news_items)
        tradable_block = (
            f"## Tradable symbols (count toward 30-trade lock-in)\n"
            f"{', '.join(tradable_symbols)}\n\n"
            f"All other symbols are context-only — generate analysis but NO plan."
        )

        user_text = (
            f"# Premarket Daily Report — generation context\n\n"
            f"**Run time**: {run_timestamp_pt} ({run_timestamp_et})\n\n"
            f"{lock_in_block}\n\n"
            f"{tradable_block}\n\n"
            f"{bars_block}\n\n"
            f"{futures_block}\n\n"
            f"{news_block}\n\n"
            f"Please generate the full multi-instrument premarket report following "
            f"the system prompt template. Output in Chinese."
        )

        return [
            {"role": "system", "content": system_blocks},
            {"role": "user", "content": user_text},
        ]

    @staticmethod
    def _build_lock_in_block(ctx: ReportContext) -> str:
        return (
            f"## Lock-in status\n"
            f"- contract_status: {ctx.contract_status.value}\n"
            f"- trades_done: {ctx.lock_in_trades_done}/{ctx.lock_in_target}\n"
            f"- cumulative_r: {ctx.cumulative_r if ctx.cumulative_r is not None else 'n/a'}\n"
            f"- last_trade_date: {ctx.last_trade_date or 'n/a'}\n"
            f"- last_trade_r: {ctx.last_trade_r if ctx.last_trade_r is not None else 'n/a'}\n"
            f"- streak (last 5): {ctx.streak or 'n/a'}\n"
        )

    @staticmethod
    def _build_multi_symbol_bars_block(
        bars_by_symbol_and_tf: dict[str, dict[str, list[OHLCV]]],
    ) -> str:
        """Format per-symbol multi-TF bar data."""
        lines = ["## Multi-TF bar data (per instrument)"]
        for symbol in bars_by_symbol_and_tf:
            lines.append(f"\n### Symbol: {symbol}")
            tfs = bars_by_symbol_and_tf[symbol]
            for tf in ("1W", "1D", "4H", "1H"):
                bars = tfs.get(tf, [])
                if not bars:
                    lines.append(f"\n#### {tf}\n(no bars available)")
                    continue
                lines.append(f"\n#### {tf} ({len(bars)} bars, oldest first)")
                for b in bars[-10:]:
                    lines.append(
                        f"- {b.timestamp.isoformat()}: O={b.open} H={b.high} "
                        f"L={b.low} C={b.close} V={b.volume}"
                    )
        return "\n".join(lines)

    @staticmethod
    def _build_news_block(news_items: list[dict[str, Any]]) -> str:
        if not news_items:
            return "## Breaking news (past ~12h)\n\n(no news items)"
        lines = ["## Breaking news (past ~12h)"]
        for item in news_items[:20]:
            title = item.get("title", "(no title)")
            ts = item.get("published_at", "?")
            url = item.get("url", "")
            lines.append(f"- [{ts}] {title} {url}")
        return "\n".join(lines)

    @staticmethod
    def _build_futures_section_block(
        futures_data: "FuturesSection | None",
    ) -> str:
        if futures_data is None:
            return "## F. 期货结构 (futures positioning)\n\n(no F-section data available)"
        lines = ["## F. 期货结构 (futures positioning) — raw data per symbol"]
        for symbol, data in futures_data.per_symbol.items():
            lines.append(f"\n### {symbol}")
            if data.open_interest:
                oi = data.open_interest
                lines.append(
                    f"- OI: today={oi.today:.0f}, yesterday={oi.yesterday:.0f}, "
                    f"delta={oi.delta:+.0f} ({oi.delta_pct:+.2%})"
                )
            else:
                lines.append("- OI: unavailable")
            if data.basis:
                lines.append(
                    f"- Basis: future={data.basis.future_price:.2f}, "
                    f"underlying={data.basis.underlying_price:.2f}, "
                    f"spread={data.basis.basis:+.2f}"
                )
            else:
                lines.append("- Basis: unavailable")
            if data.term_structure:
                ts = data.term_structure
                structure_label = "contango" if ts.contango else "backwardation"
                lines.append(
                    f"- Term structure: front={ts.front:.2f}, next={ts.next:.2f}, "
                    f"far={ts.far:.2f} → {structure_label} "
                    f"(spread front→next: {ts.spread_front_next:+.2f})"
                )
            else:
                lines.append("- Term structure: unavailable")
            if data.volume_profile:
                vp = data.volume_profile
                lines.append(
                    f"- Volume profile (today, RTH): POC={vp.poc:.2f}, "
                    f"VAH={vp.vah:.2f}, VAL={vp.val:.2f} "
                    f"(total volume {vp.total_volume:.0f})"
                )
            else:
                lines.append("- Volume profile: unavailable")
        lines.append(
            "\nGenerate the F. 期货结构 section in the report by interpreting "
            "the above raw data into bullish/bearish positioning paragraphs per symbol."
        )
        return "\n".join(lines)
