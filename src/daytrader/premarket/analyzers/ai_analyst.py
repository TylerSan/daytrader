"""AI analysis prompt builder — generates structured prompts for Claude Code to analyze."""

from __future__ import annotations

from daytrader.premarket.collectors.base import CollectorResult


# Instruments that always get full AI analysis
CORE_INSTRUMENTS = {
    "ES=F": "E-mini S&P 500 Futures",
    "NQ=F": "E-mini Nasdaq 100 Futures",
    "GC=F": "Gold Futures",
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}

_ANALYSIS_PROMPT = """\
你是一位顶级日内交易分析师，专注于订单流和价格行为分析。你的受众是一位经验丰富的超短线交易者，\
使用 footprint 图表上的堆叠失衡信号进行交易，紧止损、高盈亏比。

请基于以下实时市场数据，为今日盘前提供完整的技术分析和操盘建议。

## 实时市场数据

### 期货 & VIX
{futures_data}

### 板块表现
{sector_data}

### 关键价位
{levels_data}

---

请对以下每个品种进行分析: {instruments}

对每个品种使用以下结构:

### [品种名称]

**多时间框架分析:**
- 周线: [趋势方向, 关键区域]
- 日线: [趋势, 近期形态, 关键MA位置]
- 小时线: [盘中结构, 趋势]

**关键价位:**
- 强阻力: [价位] — [原因]
- 弱阻力: [价位] — [原因]
- 枢轴点: [价位]
- 弱支撑: [价位] — [原因]
- 强支撑: [价位] — [原因]

**订单流关注点:**
- [在哪些价位最可能出现堆叠失衡信号, 预期方向]

**今日操盘建议:**
- 方向偏好: [多/空/观望] (置信度: [高/中/低])
- 理由: [1-2句核心逻辑]
- 关注入场区域: [具体价位区间]
- 止损参考: [价位]
- 目标位: T1=[价位], T2=[价位]
- 风险提示: [事件时间窗口, 异常情况等]

---

最后增加:

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


def build_analysis_prompt(
    collected_data: dict[str, CollectorResult],
    extra_symbols: list[str] | None = None,
) -> str:
    """Build the AI analysis prompt from collected market data.

    Returns a prompt string that can be passed to Claude Code for analysis.
    """
    all_symbols = list(CORE_INSTRUMENTS.keys()) + (extra_symbols or [])
    instrument_names = [
        f"{sym} ({CORE_INSTRUMENTS.get(sym, sym)})" for sym in all_symbols
    ]

    futures_data = "No data"
    if "futures" in collected_data and collected_data["futures"].success:
        futures_data = _format_dict(collected_data["futures"].data)

    sector_data = "No data"
    if "sectors" in collected_data and collected_data["sectors"].success:
        sector_data = _format_dict(collected_data["sectors"].data)

    levels_data = "No data"
    if "levels" in collected_data and collected_data["levels"].success:
        levels_data = _format_dict(collected_data["levels"].data)

    vix = "N/A"
    if "futures" in collected_data and collected_data["futures"].success:
        vix_data = collected_data["futures"].data.get("^VIX", {})
        vix = vix_data.get("price", "N/A")

    return _ANALYSIS_PROMPT.format(
        futures_data=futures_data,
        sector_data=sector_data,
        levels_data=levels_data,
        instruments=", ".join(instrument_names),
        vix=vix,
    )
