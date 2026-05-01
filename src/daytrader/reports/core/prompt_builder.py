"""PromptBuilder: assemble Anthropic Messages API request from context + data.

Produces a list of message dicts (system + user) ready to pass to
AIAnalyst.call_claude(). System blocks use cache_control = ephemeral
on stable parts (template + Contract.md); dynamic data is uncached.
"""

from __future__ import annotations

from typing import Any

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.templates import load_template


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
