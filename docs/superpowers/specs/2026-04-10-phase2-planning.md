# Phase 2 规划（待讨论）

## Phase 1 回顾

**已交付：**
- `daytrader pre` — 日报（数据 + 4 张卡片 + 中英新闻 + AI 操盘建议）
- `daytrader weekly` — 周报（数据 + 3 张卡片 + 中英新闻 + AI 周度计划）
- Obsidian 双向同步（报告 + 图片）
- cron 自动化
- matplotlib 本地卡片渲染
- Claude CLI 集成（AI 分析 + 翻译）

**覆盖的环节：** 交易决策循环中的**"计划"**阶段（Plan）。

---

## 全局地图（项目预期范围）

`src/daytrader/cli/main.py` 里已经定义了完整的 CLI 模块骨架，说明项目规划的最终形态：

| 模块 | 用途 | Phase 1 状态 |
|------|------|-------------|
| `pre` | 盘前日报 | ✅ 已完成 |
| `weekly` | 周度计划 | ✅ 已完成 |
| `journal` | 交易日志与导入 | ⬜ 空 |
| `bt` | 策略回测 | ⬜ 空 |
| `stats` | 品种统计优势 | ⬜ 空 |
| `psych` | 交易心理系统 | ⬜ 空 |
| `evo` | 自主演化引擎 | ⬜ 空 |
| `prop` | Prop 公司账户管理 | ⬜ 空 |
| `learn` | 学习与内容聚合 | ⬜ 空 |
| `kb` | 知识库管理 | ⬜ 空 |
| `publish` | 内容发布管道 | ⬜ 空 |
| `book` | 书稿构建器 | ⬜ 空 |

项目的核心理念是"self-evolving day trading platform"，要实现这个需要一个完整的**反馈闭环**：

```
Plan（计划）→ Execute（执行）→ Record（记录）→ Review（复盘）→ Learn（学习）→ 更好的 Plan
   ↑ Phase 1                                                                  ↓
   └──────────────────────────────────────────────────────────────────────────┘
```

Phase 1 建好了 "Plan"。Phase 2 自然应该建 **Record + Review**，为之后的 Learn/Evo 打基础。

---

## Phase 2 候选方向（4 个选项）

### 🌟 方向 A：交易闭环（Trading Loop）

**聚焦：** 建立 `journal` + 盘后复盘，闭合从计划到执行到反馈的循环。

**核心交付：**

1. **`daytrader journal`** — 交易日志
   - `journal add` — 交互式录入一笔交易（品种、方向、入场、止损、目标、实际出场、理由、截图）
   - `journal list [--date] [--symbol]` — 查询
   - `journal import <broker>.csv` — 从经纪商 CSV 导入（IB / Tradovate / Alpaca）
   - `journal stats [--week]` — 基础统计（胜率、平均 R、盈亏比）
   - **存储：** SQLite（已在 pyproject 依赖里）+ Obsidian 双向同步（每笔一个 `.md` 文件，YAML frontmatter）
   - **Schema：** trade_id, date, symbol, direction, entry_price, stop, target, exit_price, size, pnl_usd, r_multiple, setup_type (stacked_imbalance / level_bounce / breakout), discipline_score (1-5), notes, screenshot_path

2. **`daytrader post`** — 盘后复盘报告
   - 每日收盘后运行（cron 4:30 PM ET）
   - 对照上午的 `pre` 报告，回答：
     - 预测的关键价位是否命中？（ES/NQ/SPY/QQQ）
     - AI 给的方向偏好是否正确？
     - 盘前异动的股票是否有跟进？
     - 板块轮动是否按预测发展？
   - 生成 4 张回顾卡片：
     - 今日画像（实际高/低/收 + 区间）
     - 预测命中率（计划价位 vs 实际触及）
     - 板块实际表现对比
     - 盘前异动跟进情况
   - AI 生成"今日市场总结"（3-5 段）
   - 同步到 Obsidian `Daily/postmarket-YYYY-MM-DD.md`

3. **周度业绩总结卡片**（加到周报）
   - 周报现有 3 张卡片基础上追加 1 张"上周业绩"
   - 从 `journal` 读取上周交易
   - 显示：周 P&L 曲线、胜率、最大回撤、A+ setup 执行率

**复杂度：** 中等（2-3 周工作量）
**价值：** 最高。没有这一步，整个"self-evolving"的定位无法实现。
**依赖：** 无。只用到已有的 yfinance + matplotlib + Claude CLI。

---

### 方向 B：数据层升级（Real-time Order Flow）

**聚焦：** 把数据源从日线 yfinance 升级到 tick 级订单流。

**核心交付：**
- 集成 Polygon.io 或 Databento 的 tick 数据
- 实现 footprint chart 数据结构（价格 × 时间 × 买卖量）
- 检测 stacked imbalance 信号
- 历史数据存储到 `data/tick/`（目录已存在）
- CLI: `daytrader tick replay --date --symbol`

**复杂度：** 高（3-5 周）+ 月度订阅费（Polygon 29-199 刀）
**价值：** 对订单流交易者的核心工具，但需要先验证策略可行再上
**建议：** **先不做**，因为：
1. 需要付费数据源
2. 没有 journal 来验证策略是否真能赚钱
3. 用户目前的日内决策可能已经足够（看日线级别 AI 建议）

---

### 方向 C：告警与实时监控（Alerts）

**聚焦：** 从"静态报告"升级到"事件驱动告警"。

**核心交付：**
- Telegram bot（`python-telegram-bot` 已在可选依赖里）
- 早晨报告自动推送到 Telegram
- 盘中价格告警：
  - ES/NQ/SPY 触及 pre 报告里的关键价位时通知
  - VIX 突破阈值（>22 / <18）时通知
  - 盘前异动超过 5% 时通知
- 事件日历告警（FOMC / CPI 前 10 分钟提醒）

**复杂度：** 中低（1-2 周）
**价值：** 中等。单独的提醒系统让信息流更主动，但**不产生数据沉淀**，不构成闭环。
**建议：** 可作为方向 A 的**锦上添花**功能，不独立作为 Phase 2 主轴。

---

### 方向 D：Phase 1 深度打磨

**聚焦：** 不加新功能，把现有报告做到"极致"。

**候选项：**
- 历史对比（今日 vs 上周同日）
- 多时间框架关键价位（日/周/月）
- Intraday session 细化（伦敦盘 / 纽约盘 / 亚洲盘独立统计）
- 期权数据集成（盘前 put/call ratio、unusual options activity）
- 更多信息图（波动率历史、sector 热力矩阵、新闻情绪分数）
- 周报加"经济日历" skill 集成（FOMC/CPI 预期）

**复杂度：** 低（1-2 周）
**价值：** 低中。现有报告已经很好用了，边际收益递减。
**建议：** **不推荐作为 Phase 2 主轴**，可作为 Phase 2 中的补丁任务。

---

## 推荐方案：**方向 A + 方向 C 精简版**

### 阶段 2.1：Trade Journal 基础（第 1-2 周）

1. **数据模型与存储**
   - SQLite schema（trades 表）
   - Pydantic 模型 `Trade`
   - Obsidian markdown ↔ SQLite 双向同步
   
2. **CLI 命令**
   - `daytrader journal add` — 交互式录入
   - `daytrader journal list`
   - `daytrader journal stats`

3. **Obsidian 模板**
   - 每笔交易一个 `.md` 文件，YAML frontmatter
   - 复盘 dataview 查询

### 阶段 2.2：盘后复盘报告（第 2-3 周）

1. **`daytrader post run`** 命令
   - 拉取今日实际 OHLC（yfinance）
   - 读取上午的 pre 报告（或内存中的 results）
   - 对比：关键价位命中 / 方向偏好 / 异动跟进
   - 生成 4 张复盘卡片（matplotlib）
   - AI 生成"今日市场总结"
   - 输出 `postmarket-YYYY-MM-DD.md`

2. **cron 集成**
   - `postmarket-cron.sh`（16:35 ET Mon-Fri）
   - 和 `premarket-cron.sh` 对称

### 阶段 2.3：Telegram 告警（第 3-4 周，可选）

1. **早晨报告推送**
   - pre 报告生成后自动推送到 Telegram（标题 + 数据速览卡片 + AI 核心结论）
   - 只推关键信息，不推整个报告

2. **盘中关键价位告警**
   - 后台进程监控 ES/NQ/SPY
   - 触及预测关键价位时推送
   - 节流：同一价位 5 分钟内只推一次

### 阶段 2.4：周度业绩卡片（第 4 周）

- 周报中追加"上周业绩"卡片
- 从 journal 读取数据
- 显示胜率 / 盈亏比 / 最大回撤 / 执行纪律

---

## 需要用户决定的问题

1. **选哪个方向？** A（交易闭环 - 推荐）/ B（tick 数据）/ C（告警）/ D（打磨）/ 其他
2. **交易日志的存储偏好？** SQLite 为主（支持 stats 查询）/ 纯 Markdown（Obsidian 原生）/ 两者同步
3. **经纪商导入优先级？** 你主要用哪个平台？（Interactive Brokers / Tradovate / NinjaTrader / Alpaca / Topstep）
4. **盘后复盘是自动 cron 还是手动触发？**
5. **告警渠道优先级？** Telegram / Discord / iMessage（都已在 notifications 模块里）
6. **周度业绩卡片放在周报里，还是独立命令？**
7. **是否要更积极追加 `bt` / `stats` / `evo` 的 MVP**（这些是长期目标但不紧迫）
8. **Phase 2 预期交付时间？** 4 周？8 周？

---

## 风险与考量

1. **范围蔓延风险** — CLI 里 12 个模块的蓝图看起来诱人，但每个都实现会稀释注意力。Phase 2 最好**只做一个模块**（journal + post 作为一个整体）。

2. **交易日志的数据门槛** — journal 只有在真实使用后才产生价值。如果用户暂时还没开始实盘或只做少量交易，stats 部分可能几周都没有足够样本。建议 MVP 阶段就能支持"假数据"或者模拟交易。

3. **盘后复盘的时效性** — yfinance 收盘后数据有 15-20 分钟延迟。4:30 PM ET cron 运行时数据可能不完整，可能需要延后到 5:00 PM 或者隔天早上一起跑。

4. **cron 脚本越来越臃肿** — 当前 Mon-Fri 有 `premarket-cron.sh`，Sunday 有 `weekly-cron.sh`。Phase 2 会加 `postmarket-cron.sh`。到时候可能需要一个统一的 scheduler 框架或迁移到 launchd。

5. **Obsidian vault 目录结构** — 现在只有 `Daily/` 和 `Weekly/`。journal + post 会引入 `Trades/` 和 `Daily/postmarket-*`。需要规划好目录结构避免混乱。

---

## 下一步

明天早晨讨论，用户做方向决策，然后：
1. brainstorming skill 细化选定方向的 spec
2. writing-plans skill 写实施计划
3. subagent-driven-development 执行
