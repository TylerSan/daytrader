"""SentimentSection — orchestrator-facing facade with collect() + render()."""

from __future__ import annotations

from daytrader.reports.sentiment.collector import SentimentCollector
from daytrader.reports.sentiment.dataclasses import SentimentResult


class SentimentSection:
    """Facade: orchestrator calls .collect() to fetch, .render() to format.

    Mirrors the FuturesSection pattern from Phase 4. Always returns a string
    from render() even if the result is unavailable — no exceptions cross the
    facade boundary.
    """

    def __init__(
        self,
        symbols: list[str],
        collector: SentimentCollector | None = None,
        time_window: str = "past 24h",
    ) -> None:
        self._symbols = list(symbols)
        self._time_window = time_window
        self._collector = collector or SentimentCollector(
            symbols=symbols, time_window=time_window
        )

    def collect(self) -> SentimentResult:
        return self._collector.collect()

    def render(self, result: SentimentResult) -> str:
        if result.unavailable:
            return self._render_unavailable(result)
        return self._render_happy(result)

    # ---------- private renderers ----------

    def _render_unavailable(self, result: SentimentResult) -> str:
        return (
            "## D. 情绪面 / Sentiment Index\n\n"
            f"⚠️ **情绪数据本次不可用** — {result.unavailable_reason}\n\n"
            "主报告其余章节正常生成；可手动跑 `uv run daytrader reports run "
            "--type premarket` 或检查 `claude -p` 状态后重试。\n"
        )

    def _render_happy(self, result: SentimentResult) -> str:
        assert result.macro is not None  # type narrowing
        macro = result.macro

        themes = "; ".join(macro.main_themes) if macro.main_themes else "(none)"
        risks = "; ".join(macro.risks) if macro.risks else "(none)"
        events = ", ".join(macro.upcoming_events) if macro.upcoming_events else "(none)"

        header = (
            "## D. 情绪面 / Sentiment Index\n\n"
            f"### 🌐 Macro Sentiment\n"
            f"**总体综合 {self._fmt_score(macro.score.combined)} / 10**"
            f"（news {self._fmt_score(macro.score.news)}, "
            f"social {self._fmt_score(macro.score.social)}）\n"
            f"- 主流叙事：{themes}\n"
            f"- 风险点：{risks}\n"
            f"- 关键事件（{self._time_window} 内）：{events}\n\n"
        )

        rows: list[str] = ["| Symbol | News | Social | Combined | 1-句叙事 |",
                            "|---|---|---|---|---|"]
        present = {s.symbol for s in result.per_symbol}
        for s in result.per_symbol:
            rows.append(
                f"| {s.symbol} "
                f"| {self._fmt_score(s.score.news)} "
                f"| {self._fmt_score(s.score.social)} "
                f"| {self._fmt_score(s.score.combined)} "
                f"| {s.score.narrative} |"
            )

        per_symbol_block = "### 📊 Per-Symbol\n" + "\n".join(rows) + "\n\n"

        # Note any expected-but-missing symbols
        missing = [sym for sym in self._symbols if sym not in present]
        missing_note = ""
        if missing:
            missing_note = (
                f"> ⚠️ 以下 symbol 数据在本次 fetch 中缺失："
                f"{', '.join(missing)}（按 'unavailable' 处理）\n\n"
            )

        sources_lines = "\n".join(f"- {url}" for url in result.sources)
        footer = (
            "> 评分：-5 (极空) → 0 (中性) → +5 (极多)\n"
            "> 综合权重：news 60% / social 40%\n\n"
            "**Sources:**\n"
            f"{sources_lines if sources_lines else '(none)'}\n"
        )

        return header + per_symbol_block + missing_note + footer

    @staticmethod
    def _fmt_score(n: int) -> str:
        return f"+{n}" if n > 0 else str(n)
