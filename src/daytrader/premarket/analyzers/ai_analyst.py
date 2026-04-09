"""AI-powered technical analysis and trading suggestions using Claude API."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import yfinance as yf
from anthropic import AsyncAnthropic

from daytrader.premarket.collectors.base import CollectorResult


# Instruments that always get full AI analysis
CORE_INSTRUMENTS = {
    "ES=F": "E-mini S&P 500 Futures",
    "NQ=F": "E-mini Nasdaq 100 Futures",
    "GC=F": "Gold Futures",
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}

_SYSTEM_PROMPT = """\
You are an elite day trading analyst specializing in order flow and price action analysis \
for US stock and futures markets. Your audience is an experienced scalper who trades \
stacked imbalances on footprint charts with tight stops and high R:R.

Your analysis must be:
- Actionable and specific (exact price levels, not vague ranges)
- Multi-timeframe (weekly → daily → hourly → 5min context)
- Focused on levels where order flow imbalances are likely to appear
- Aware of the current VIX regime and its impact on strategy
- Written in concise, professional trading language

For each instrument, provide your analysis in the EXACT format below. Use Chinese for the output.\
"""

_ANALYSIS_PROMPT_TEMPLATE = """\
Based on the following market data, provide a complete pre-market technical analysis \
and trading plan for today's session.

## Current Market Data

### Futures & VIX
{futures_data}

### Sector Performance
{sector_data}

### Key Levels
{levels_data}

### Historical Price Data (recent sessions)
{history_data}

## Instructions

For EACH of these instruments: {instruments}

Provide analysis in this EXACT structure:

### [Instrument Name]

**多时间框架分析:**
- 周线: [趋势方向, 关键区域]
- 日线: [趋势, 近期形态, 关键MA位置]
- 小时线: [盘中结构, 趋势]
- 5分钟: [盘前走势, 开盘预期]

**关键价位:**
- 强阻力: [价位] — [原因]
- 弱阻力: [价位] — [原因]
- 枢轴点: [价位]
- 弱支撑: [价位] — [原因]
- 强支撑: [价位] — [原因]

**订单流关注点:**
- [描述在哪些价位最可能出现堆叠失衡信号, 以及预期方向]

**今日操盘建议:**
- 方向偏好: [多/空/观望] (置信度: [高/中/低])
- 理由: [1-2句核心逻辑]
- 关注入场区域: [具体价位区间]
- 止损参考: [价位]
- 目标位: T1=[价位], T2=[价位]
- 风险提示: [事件时间窗口, 异常情况等]

---

After all instruments, add a section:

### 今日市场总览
- 整体市场情绪: [风险偏好/风险厌恶/中性]
- VIX环境评估: [当前VIX={vix}意味着什么, 对策略的影响]
- 需要规避的时段: [如有重大数据发布]
- 板块轮动信号: [资金流向观察]
"""


def _format_dict(data: dict, indent: int = 0) -> str:
    """Format dict as readable text for the prompt."""
    lines = []
    prefix = "  " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_format_dict(v, indent + 1))
        else:
            lines.append(f"{prefix}{k}: {v}")
    return "\n".join(lines)


async def _fetch_history(symbols: list[str], period: str = "1mo") -> dict:
    """Fetch recent price history for AI context."""

    def _do_fetch() -> dict:
        result = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
                if hist.empty:
                    continue
                # Last 10 sessions summary
                recent = hist.tail(10)
                sessions = []
                for date_idx, row in recent.iterrows():
                    sessions.append({
                        "date": str(date_idx.date()),
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row["Volume"]),
                    })
                result[symbol] = sessions
            except Exception:
                result[symbol] = []
        return result

    return await asyncio.to_thread(_do_fetch)


class AIAnalyst:
    """Claude-powered market analyst for pre-market technical analysis."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        extra_symbols: list[str] | None = None,
    ) -> None:
        self._client = AsyncAnthropic()
        self._model = model
        self._extra_symbols = extra_symbols or []

    async def analyze(
        self,
        collected_data: dict[str, CollectorResult],
    ) -> str:
        """Run AI analysis on collected market data, return markdown analysis."""

        # Determine instruments to analyze
        all_symbols = list(CORE_INSTRUMENTS.keys()) + self._extra_symbols
        instrument_names = [
            f"{sym} ({CORE_INSTRUMENTS.get(sym, sym)})" for sym in all_symbols
        ]

        # Fetch historical data for AI context
        history = await _fetch_history(all_symbols)

        # Build prompt sections
        futures_data = "No data"
        if "futures" in collected_data and collected_data["futures"].success:
            futures_data = _format_dict(collected_data["futures"].data)

        sector_data = "No data"
        if "sectors" in collected_data and collected_data["sectors"].success:
            sector_data = _format_dict(collected_data["sectors"].data)

        levels_data = "No data"
        if "levels" in collected_data and collected_data["levels"].success:
            levels_data = _format_dict(collected_data["levels"].data)

        history_data = _format_dict(history) if history else "No historical data available"

        # Get VIX value
        vix = "N/A"
        if "futures" in collected_data and collected_data["futures"].success:
            vix_data = collected_data["futures"].data.get("^VIX", {})
            vix = vix_data.get("price", "N/A")

        prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
            futures_data=futures_data,
            sector_data=sector_data,
            levels_data=levels_data,
            history_data=history_data,
            instruments=", ".join(instrument_names),
            vix=vix,
        )

        # Call Claude API
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=8000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text
