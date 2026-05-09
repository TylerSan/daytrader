"""Sentiment prompt template for claude -p with WebSearch."""

from __future__ import annotations


def build_sentiment_prompt(
    symbols: list[str],
    time_window: str = "past 24h",
) -> str:
    """Build the prompt for a sentiment-fetch claude -p call.

    The output format is strict markdown — see parser.py for the contract.

    Args:
        symbols: Instruments to analyze, e.g. ["MES", "MGC", "MNQ"].
        time_window: Lookback window for the search, e.g. "past 24h" or
            "past 7 days". Default suits daily premarket; weekly should
            pass "past 7 days".
    """
    symbols_str = ", ".join(symbols)
    table_rows = "\n".join(
        f"| {sym} | [-5..+5] | [-5..+5] | [-5..+5] | [短句] |"
        for sym in symbols
    )

    return f"""你是金融情绪分析师。请使用 web search，搜索 {time_window} 内：

1. 与 {symbols_str} 相关的财经新闻
   （Reuters / Bloomberg / CNBC / WSJ / FT / MarketWatch / Yahoo Finance / 路透 / 华尔街日报）
2. 这些 symbol 在 X (Twitter) / Reddit (r/wallstreetbets, r/futures, r/options)
   / StockTwits 上的讨论情绪
3. 影响这些 symbol 的宏观事件
   （Fed / CPI / NFP / PMI / 财报 / 地缘政治 / 大宗商品政策）

完成搜索后，按以下 EXACT markdown 格式输出（不加任何额外说明文字）：

### 🌐 Macro Sentiment
**总体 [偏多/中性/偏空] [+N/0/-N] / 10**（news +N, social +N）
- 主流叙事：[1 句]
- 风险点：[1 句]
- 关键事件（{time_window} 内）：[逗号分隔事件名]

### 📊 Per-Symbol
| Symbol | News | Social | Combined | 1-句叙事 |
|---|---|---|---|---|
{table_rows}

> 评分：-5 (极空) → 0 (中性) → +5 (极多)
> 综合权重：news 60% / social 40%
> Sources: [至少 5 个真实查到的 URL]

重要：
- 评分必须是 -5 到 +5 之间的整数
- 不要用 "very bullish" 这种描述性词代替数值
- Sources 必须是真实搜到的 URL，不要编造
"""
