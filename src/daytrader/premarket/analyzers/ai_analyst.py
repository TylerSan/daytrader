"""AI analysis prompt builder — generates structured prompts for Claude Code to analyze."""

from __future__ import annotations

from daytrader.premarket.collectors.base import CollectorResult


# Instruments grouped by type to prevent level confusion
FUTURES_INSTRUMENTS = {
    "ES=F": "E-mini S&P 500 Futures",
    "NQ=F": "E-mini Nasdaq 100 Futures",
    "GC=F": "Gold Futures",
}

ETF_INSTRUMENTS = {
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}

_ANALYSIS_PROMPT = """\
你是一位顶级日内交易分析师，专注于订单流和价格行为分析。你的受众是一位经验丰富的超短线交易者，\
使用 footprint 图表上的堆叠失衡信号进行交易，紧止损、高盈亏比。

请基于以下实时市场数据，为今日盘前提供完整的技术分析和操盘建议。

⚠️ 关键规则: 期货品种（ES=F, NQ=F, GC=F）必须使用期货合约自身的价位进行分析，\
ETF品种（SPY, QQQ）使用ETF自身的价位。绝对不可混用！ES=F 交易在 ~6800 级别，SPY 交易在 ~676 级别，\
这是完全不同的价格尺度。

## 实时市场数据

### 期货数据（含隔夜盘）
{futures_data}

### 板块表现
{sector_data}

### ETF 关键价位
{levels_data}

---

## 第一部分：隔夜市场回顾

请先总结隔夜交易情况:
- **亚洲盘（18:00-02:00 ET）:** 各期货品种的亚洲时段高低点、走势方向、成交特征
- **欧洲盘（02:00-08:00 ET）:** 各期货品种的欧洲时段高低点、走势方向、关键突破/回落
- **隔夜总结:** 隔夜整体方向、关键价位是否被测试、对美盘开盘的暗示

---

## 第二部分：期货品种分析

对以下期货品种进行分析（使用期货合约自身价位）: {futures_list}

对每个期货品种:

### [品种名称]（期货合约价位）

**隔夜走势:**
- 亚洲盘: 高=[期货价位], 低=[期货价位], 方向=[上涨/下跌/震荡]
- 欧洲盘: 高=[期货价位], 低=[期货价位], 方向=[上涨/下跌/震荡]
- 隔夜总区间: [期货价位] - [期货价位]

**多时间框架分析:**
- 周线: [趋势方向, 关键区域（期货价位）]
- 日线: [趋势, 近期形态, 关键MA位置（期货价位）]
- 小时线: [盘中结构, 趋势]

**关键价位（期货合约价位）:**
- 强阻力: [期货价位] — [原因]
- 弱阻力: [期货价位] — [原因]
- 枢轴点: [期货价位]
- 弱支撑: [期货价位] — [原因]
- 强支撑: [期货价位] — [原因]

**订单流关注点:**
- [在哪些期货价位最可能出现堆叠失衡信号, 预期方向]

**今日操盘建议:**
- 方向偏好: [多/空/观望] (置信度: [高/中/低])
- 理由: [1-2句核心逻辑]
- 关注入场区域: [期货价位区间]
- 止损参考: [期货价位]
- 目标位: T1=[期货价位], T2=[期货价位]
- 风险提示: [事件时间窗口, 异常情况等]

---

## 第三部分：ETF 品种分析

对以下 ETF 进行分析（使用 ETF 自身价位）: {etf_list}

对每个 ETF:

### [品种名称]（ETF 价位）

**关键价位（ETF 价位）:**
- 强阻力: [ETF价位] — [原因]
- 弱阻力: [ETF价位] — [原因]
- 枢轴点: [ETF价位]
- 弱支撑: [ETF价位] — [原因]
- 强支撑: [ETF价位] — [原因]

**今日操盘建议:**
- 方向偏好: [多/空/观望] (置信度: [高/中/低])
- 关注入场区域: [ETF价位区间]
- 止损参考: [ETF价位]
- 目标位: T1=[ETF价位], T2=[ETF价位]

---

## 第四部分：今日市场总览

- 整体市场情绪: [风险偏好/风险厌恶/中性]
- VIX环境评估: [当前VIX={vix}意味着什么, 对堆叠失衡策略的具体影响]
- 隔夜关键信息: [亚欧盘留下的关键信号]
- 需要规避的时段: [重大数据发布的具体时间]
- 板块轮动信号: [资金流向观察, 对选股的启示]
"""


def _format_dict(data: dict, indent: int = 0) -> str:
    """Format dict as readable text for the prompt."""
    lines = []
    prefix = "  " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_format_dict(v, indent + 1))
        elif isinstance(v, float):
            lines.append(f"{prefix}{k}: {v:.4f}" if abs(v) < 1 else f"{prefix}{k}: {v}")
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
    futures_list = [
        f"{sym} ({name})" for sym, name in FUTURES_INSTRUMENTS.items()
    ]
    etf_list = [
        f"{sym} ({name})" for sym, name in ETF_INSTRUMENTS.items()
    ]

    if extra_symbols:
        for sym in extra_symbols:
            futures_list.append(sym)

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
        futures_list=", ".join(futures_list),
        etf_list=", ".join(etf_list),
        vix=vix,
    )
