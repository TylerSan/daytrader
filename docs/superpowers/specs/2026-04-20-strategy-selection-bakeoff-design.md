# W2 Setup Gate — 策略选择 Bake-off 设计

**日期:** 2026-04-20
**状态:** 设计完成,待用户审阅
**上下文阶段:** Phase 2 已合并(2026-04-18),W0 Contract 待签前需产出 `locked_setup`

**前置文档(必读):**
- [`2026-04-10-phase2-planning.md`](2026-04-10-phase2-planning.md) — 4 个候选方向
- [`2026-04-11-phase2-research-tools-strategies.md`](2026-04-11-phase2-research-tools-strategies.md) — 工具与策略调研(**leaning 而非决定**)
- [`2026-04-16-daytrading-system-design.md`](2026-04-16-daytrading-system-design.md) — Phase 2 设计,**明确把 order flow / Nautilus / mlfinlab 等研究基础设施推到 Phase 3+**,理由:"用户问题是握不住 edge,不是缺 edge;Nautilus 属于拖延症高级伪装"

**本 spec 的作用:**
在 Phase 2 纪律层合并后,产出 W0 签 Contract 所必需的 `locked_setup` + `backup_setup` 两栏,基于发表的学术/半学术证据 + 在 MES 上做独立样本外复测。**不是** 04-11 设想的 order flow 研究 —— 那条线仍按 04-16 的决定在 Phase 3+ 处理。

**命名:** "W2 Setup Gate" —— 复用 04-16 规划的术语。W0 = Contract 签约,W1 = 第一笔实盘,W2 = Setup 门槛,顺序是 W2 → W0 → W1。

---

## 0. TL;DR

在 MES 2022-01 至 2025-12 的 1-minute Databento 数据上,用 **pybroker** 做 walk-forward,把 **4 个候选策略** bake-off,按预设硬门槛筛选,winner 写进 Contract.md `locked_setup`,runner-up 进 `backup_setup`。**若 0 个过关,不签 Contract,返回 brainstorming。**

- 4 候选:Zarattini 2023 5-min ORB × {10× OR range target, EOD only};Zarattini-Aziz-Barbon 2024 "Beat the Market" Intraday Momentum × {1 trade/day, 5 trades/day}
- 引擎:pybroker(research)+ in-house sanity_floor(gate,冻结状态)
- 数据:Databento OHLCV-1m 一次性历史购买(预估 <$20)
- 评估:replication 窗口(2022-2024Q1)+ pure OOS(2024Q2-2025)分开报告,主决策看 pure OOS
- 硬门槛(pure OOS):Sharpe ≥ 1.0,Max DD ≤ 15%,Profit factor ≥ 1.3,n ≥ 100,DSR p < 0.10
- 明确允许"全部不过 → 不签 Contract"

---

## 1. 系统边界与架构

### 1.1 目标(唯一成功指标)

产出一条判决:4 个候选里的 **rank 1 / rank 2 / 其余** 是哪些;或 "0 个通过,不签 Contract"。判决可审计、可复现、可引用。

### 1.2 新增 vs 复用

```
新增 (src/daytrader/research/):
  └── bakeoff/
      ├── __init__.py
      ├── data.py                             # Databento loader → data/cache/ohlcv/
      ├── strategies/
      │   ├── s1_orb.py                       # S1a + S1b
      │   └── s2_intraday_momentum.py         # S2a + S2b
      ├── costs.py                            # MES 佣金/滑点模型(共享)
      ├── walkforward.py                      # pybroker orchestration + 结果汇总
      ├── metrics.py                          # Sharpe/Sortino/MDD/PF/expectancy/DSR/bootstrap CI
      ├── report.py                           # markdown + PNG 报告生成
      └── cli.py                              # `daytrader research bakeoff ...`

复用(既有):
  ├── daytrader.journal.models.SetupVerdict   # 判决写回 journal.db(经 promote 映射)
  ├── daytrader.journal.repository            # 持久化,新增 research_verdict 方法
  └── docs/trading/Contract.md.template       # locked_setup/backup_setup 字段已预留

保留但不扩展:
  └── daytrader.journal.sanity_floor.*        # 冻结在 ORB-only 玩具状态,作为"最低纪律门槛"保留
```

### 1.3 数据流

```
Databento Historical API (OHLCV-1m)
  │ 一次性下载 ~500MB,$5-20
  ▼
data/cache/ohlcv/MES_1m_2022_2025.parquet
  │
  ▼
research.bakeoff.data.load_mes_1m(start, end)   # 含 rollover skip、TZ 校准、缺 bar 质检
  │
  ▼
pybroker Strategy (4 候选并列同成本模型)
  │
  ▼
research.bakeoff.metrics.compare(
      s1a, s1b, s2a, s2b,
      baseline = buy_and_hold_MES
  )
  │
  ▼
research_verdict × 4 行写入 journal.db
  │
  ▼
人工 `daytrader research bakeoff promote --verdict-id <id>`
  │
  ▼
setup_verdict 行(派生)+ Contract.md 手工填签
```

### 1.4 关键架构决定(带反驳)

1. **新包放 `src/daytrader/research/`,不放 `sanity_floor/`** —— 边界清晰,避免研究代码污染纪律代码。sanity_floor = gate,research = experiment。研究产出流向 sanity_floor,不反向。
2. **pybroker 做研究,nautilus 未来做执行** —— 不强行统一。04-11 调研中 Nautilus 因研究→实盘同构有优势,但那是 Phase 3+ 议程;当前 W2 只产出证据,不产出执行代码。pybroker 的 `Strategy.walkforward()` 是 OSS 里唯一一等公民 walk-forward API。
3. **sanity_floor 冻结但保留** —— 其 CLI + journal.db schema + test suite 是 Phase 2 纪律层一部分。研究路径完全绕开,未来 locked setup 的持续监控可走 sanity_floor 的 gate 入口。
4. **基线是 buy-and-hold MES,不是 SPY** —— 对齐品种,避免"和另一 universe 比"的常见错误。

---

## 2. 评估协议(科学严谨性)

### 2.1 核心判断:不做参数优化 → 整段 2022-2025 都是"样本外"

S1 和 S2 的参数全部从论文照搬,不再拟合。我们是在新数据上做 **replication(参数固定的样本外复测)**,不是 calibration。

S2 论文样本 2007-2024 Q1,S1 论文样本 2016-2023。我们回测窗口 2022-2025 有约 2.25 年是论文训练期的尾巴,必须独立汇报 **2024 Q2-2025 这段完全独立子期** 的指标,并以此为主要决策判据。

### 2.2 数据切分

```
+----------------------------------+----------------------+
| 2022-01 ── 2024 Q1 (~26 个月)    | 2024-Q2 ── 2025 末  |
|                                  |  (~21 个月)          |
| S1/S2 论文训练期的尾巴            |  完全样本外          |
| → 汇报为 "replication 窗口"       | → 汇报为 "pure OOS"  |
| → 参考用,不作为 lock-in 依据     | → 主要判据           |
+----------------------------------+----------------------+
```

**不做 rolling walk-forward 再优化** —— re-optimization 会毁掉"论文规则照搬"这个锚点。

**但做 6-month rolling 滚动绩效报告**(不改参数,只分段计算 Sharpe / DD)—— 用于发现 regime-conditional 表现(比如 S1 只在高波动期工作)。诊断用,不决策。

### 2.3 成本模型(共享给全部 4 候选)

| 项 | 数值 | 来源 |
|---|---|---|
| 佣金 | **$4 round-trip / contract MES** | Topstep 真实费用高端保守估计(IBKR ≈ $2.04) |
| 入场滑点 | **1 tick = 0.25 点 = $1.25 / contract** | market-on-open-bar 触发 |
| 止损滑点 | **2 ticks = 0.50 点 = $2.50 / contract** | market-on-stop,MES 流动性较 ES 略差 |
| 止盈滑点 | **0 ticks**(resting limit fill) | 止盈单 resting 假设 |
| MES 乘数 | $5 / point | CME spec |

S2 论文用 "net of costs" 但未拆分,我们**必须自己重建,不信论文的 net 数字**。

### 2.4 主要指标 + 硬门槛(pure OOS)

| 类别 | 指标 | 硬门槛 |
|---|---|---|
| 风险调整收益 | **Annualized Sharpe**(净成本后) | **≥ 1.0** |
| | Annualized Sortino | ≥ 1.5 |
| | Calmar ratio | ≥ 1.0 |
| 回撤 | Max drawdown(% of equity) | **≤ 15%** |
| | Longest DD duration | ≤ 60 交易日 |
| 交易结构 | Profit factor | **≥ 1.3** |
| | Win rate | 报告,不做硬指标 |
| | Expectancy (R) | ≥ 0.2 R |
| | n_trades (pure OOS) | **≥ 100** |
| 统计显著性 | **Deflated Sharpe Ratio p-value**(López de Prado) | **< 0.10** |
| | Bootstrap 95% CI of Sharpe(10k resample) | 下界 > 0 |
| 基线对比 | 超额 Sharpe vs buy-and-hold MES | > 0.3 |

**加粗 5 项 = 硬门槛,任一不过即不推荐锁定。** DSR `n_trials = 4`(S1a + S1b + S2a + S2b)。

**Baseline 定义:** "buy-and-hold MES" = 2022-01-03 到 2025-12-31 持有 1 手 MES 前月合约,按 Databento 标准 roll 日滚动(详见 §3,数据与 rollover 处理一致)。Sharpe 以扣除 roll 滑点后 equity curve 计算,不扣借贷成本(Micro contract 保证金占用极小,忽略)。

### 2.5 失败情景(明确允许"不签 Contract")

| 情景 | 系统行为 |
|---|---|
| 4 候选全过 | rank 1 → locked,rank 2 → backup,其余归档 |
| 2-3 过 | 通过者入 rank,未通过归档 |
| 仅 1 过 | winner 进 locked,backup 留空并标注"第二期 bake-off 前不签 backup" |
| 0 过 | **写全部 verdict 但 passed=0;promote 命令 refuse;产出失败报告;返回 brainstorming 扩大候选范围或质疑成本/数据假设。阻塞在 W2,不进入 30 笔 lock-in** |
| 数据获取失败 | **不写任何 verdict**(fail-loud,沿用 sanity_floor 既有策略) |

---

## 3. 策略规则机械化规范

### 3.1 候选矩阵

| 代号 | 家族 | 关键变种 | 来源 |
|---|---|---|---|
| **S1a** | Zarattini 5-min ORB | 止盈 = 10 × OR range OR EOD | Zarattini & Aziz 2023 SSRN 4416622(2023 版解读) |
| **S1b** | Zarattini 5-min ORB | 止盈 = EOD only | Zarattini, Barbon, Aziz 2024 SSRN 4729284(2024 版解读) |
| **S2a** | "Beat the Market" Intraday Momentum | 每日最多 1 笔 | Zarattini, Aziz, Barbon 2024 Swiss Finance Inst RP 24-97(保守) |
| **S2b** | "Beat the Market" Intraday Momentum | 每日最多 5 笔 | 同上(贴合 Contract `max_trades_per_day: 5` 上限,接近论文原意) |

### 3.2 S1 Zarattini 5-min ORB(裸核心,去 Stocks-in-Play)

| 规则 | 定义 | 可信度 |
|---|---|---|
| OR 窗口 | 09:30:00–09:35:00 ET(5 × 1-min bars) | 硬 |
| OR 高/低 | `or_high = max(high[09:30..09:34])`;`or_low = min(low[09:30..09:34])` | 硬 |
| 方向 | `close[09:34] − open[09:30] > 0` → long,< 0 → short,== 0 → 当日不交易 | 硬 |
| 入场 | 09:35:00 bar close,价格 = `close[09:35] + 1 tick slippage` | 硬 + 滑点假设 |
| 初始止损 | long: `or_low − 1 tick`;short: `or_high + 1 tick` | 硬 |
| **止盈(S1a)** | `entry ± 10 × (or_high − or_low)` 或 15:55 ET EOD,先触发者 | 软(2023 版解读) |
| **止盈(S1b)** | 无止盈,15:55 ET EOD 强平 | 软(2024 版解读) |
| 过滤 | `or_range_ticks ≥ 4`(过滤零波动日);**不用 Stocks-in-Play**(无法迁移单品种期货) | 硬 |
| 仓位 | 固定 1 contract MES | 我们定(不违反 Contract `max_contracts: 2`) |
| 日最大交易 | 1 笔 | 硬 |

**偏离论文处(显式承认):**
- 固定 1 contract 不按 ATR 缩放(论文用 vol-targeted sizing)——因 Contract `max_contracts` 硬顶
- 止盈用 OR range 倍数(S1a)—— 相比论文 ATR 倍数少一个自由度;敏感性实验单独对照原版 ATR 配置

### 3.3 S2 Zarattini "Beat the Market" Intraday Momentum

**核心变量(按论文逐字):**

```
daily_open[d]            = price at 09:30:00 ET on day d
prev_close[d]            = price at 16:00:00 ET on day d−1
overnight_gap[d]         = daily_open[d] − prev_close[d]

avg_intraday_return[t]   = mean over last 14 trading days of:
                             (price[t,k] − daily_open[k]) / daily_open[k]

raw_upper[t, d] = daily_open[d] × (1 + |avg_intraday_return[t]|)
raw_lower[t, d] = daily_open[d] × (1 − |avg_intraday_return[t]|)

if overnight_gap[d] > 0:       # 向上 gap(昨收 < 今开)
    lower[t, d] = raw_lower[t, d] − overnight_gap[d]
    upper[t, d] = raw_upper[t, d]
elif overnight_gap[d] < 0:     # 向下 gap
    upper[t, d] = raw_upper[t, d] + |overnight_gap[d]|
    lower[t, d] = raw_lower[t, d]
else:
    upper, lower = raw_upper, raw_lower
```

| 规则 | 定义 | 可信度 |
|---|---|---|
| 检查时点 | 逢整点/半点:10:00, 10:30, 11:00, …, 15:30 ET(12 个) | 硬 |
| 入场 | `price[t] > upper[t,d]` → long;`price[t] < lower[t,d]` → short | 硬 |
| 已有持仓时再次触发 | **忽略**(不加仓、不反手) | 我们假设(论文未说) |
| 入场价 | `close[t] + 1 tick slippage` | 滑点假设 |
| 初始止损 | `entry ∓ 2 × ATR_14`(多用 −, 空用 +);**ATR_14 = 日线 true range 的 14 日 SMA**,每日收盘后更新 | 软 + 我们定(论文只说"dynamic trailing stop") |
| Trailing(Chandelier) | long:`stop = max(old_stop, highest_high_since_entry − 2 × ATR_14)`;short 对称 | 软 |
| 强平 | 15:55:00 ET | 硬 |
| 仓位 | 固定 1 contract MES | 我们定 |
| **日最大交易(S2a)** | 1 笔 | 我们定(保守) |
| **日最大交易(S2b)** | 5 笔(同 Contract 上限) | 我们定(接近论文原意) |

**ATR 定义的选择理由:** 1-min true range 的 14 根意义不大(只覆盖 14 分钟,信噪比极低)。日线 true range × 14 = 两周波动性,行业默认"ATR(14)"。

**S2 预热期:** `avg_intraday_return[t]` 需 14 日历史,ATR_14 也需 14 日。回测窗口首日起的前 **20 个交易日视为 warmup,不产出交易**,仅累积历史。反映到数据切分:有效 replication 窗口从 2022-02-01 起;有效 pure OOS 窗口 2024-04-01 起(2024-03 为 pure OOS 首月 warmup 缓冲)。

### 3.4 敏感性实验(诊断,不影响锁定决策)

| 实验 | 扫描 | 若结果如此 → |
|---|---|---|
| SE-1 Cost | 成本 × {0, 1, 2} | 2× 由正转负 → 边沿对滑点过敏,降低置信度 |
| SE-2 Signal reversal | 4 候选全部反转 long↔short | 反转也正期望 → 赚 long-bias 贝塔,**否决**该候选 |
| SE-3 OOS 季度稳定性 | pure OOS 拆 Q1..Q7 | 某季度 < −3% eq → 记录为 regime fragility |
| SE-4 S1 OR duration | {5, 10, 15, 30} min(延用 S1a 止盈) | 只有 5 min 过 → 过拟合指标,降 S1 置信度 |
| SE-5 S2 lookback | {7, 14, 21, 28} 天 | 仅 14 过 → 过拟合;都过 → 鲁棒加分 |
| SE-6 S2 ATR multiple | {1.5, 2.0, 2.5, 3.0} | 同 SE-5 |

**剔除的实验:**
- "仅交易 gap > X 的日子" —— data mining 风险;不加
- "FOMC/CPI/NFP 独立表现" —— Contract 已 skip 这些日子,回测同步 skip
- 多品种扩展 —— 留给未来独立 bake-off

---

## 4. 与 Phase 2 journal / Contract.md 的集成

### 4.1 核心冲突与解决

现 `sanity_floor.setup_yaml` 只认 ORB 三件套,**S2 的 noise boundary + ATR trailing 根本塞不进**。不扩 schema(避免 YAML 变成半拉子 DSL)。

**解决:** 新 YAML schema v2,身份 + Python 模块引用,规则锁在 git 代码里。

```yaml
# docs/trading/setups/<name>.yaml (v2)
name: beat-the-market-mes-1trade
version: v1
symbols: [MES]

implementation:
  module: daytrader.research.bakeoff.strategies.s2_intraday_momentum
  class: S2_1TradePerDay
  config:
    atr_window_days: 14
    noise_boundary_lookback_days: 14
    atr_multiple: 2.0
    max_trades_per_day: 1

research:
  verdict_id: <uuid>
  bakeoff_report: data/research/bakeoff-2026-04-20/report.md
  paper_citation: "Zarattini, Aziz, Barbon (2024). Beat the Market..."
```

旧 schema(ORB example)保留不动;`setup_yaml.py` 加 `load_setup_v2(path)`,无 `implementation` 字段自动 fallback 到旧 loader。

### 4.2 journal.db 新表

```sql
CREATE TABLE research_verdict (
    id                 TEXT PRIMARY KEY,
    run_date           TEXT NOT NULL,
    candidate_code     TEXT NOT NULL,       -- S1a/S1b/S2a/S2b
    strategy_family    TEXT NOT NULL,
    symbol             TEXT NOT NULL,
    data_start         TEXT NOT NULL,
    data_end           TEXT NOT NULL,
    pure_oos_start     TEXT NOT NULL,
    pure_oos_end       TEXT NOT NULL,

    n_trades_oos       INTEGER NOT NULL,
    sharpe_oos         REAL NOT NULL,
    sortino_oos        REAL NOT NULL,
    calmar_oos         REAL NOT NULL,
    max_dd_oos         REAL NOT NULL,
    profit_factor_oos  REAL NOT NULL,
    expectancy_r_oos   REAL NOT NULL,
    dsr_pvalue         REAL NOT NULL,

    sharpe_replication REAL,
    n_trades_replication INTEGER,

    passed_hard_gates  INTEGER NOT NULL,    -- 0/1
    failed_gates       TEXT,                -- JSON list
    sensitivity_json   TEXT NOT NULL,

    bakeoff_rank       INTEGER,             -- 1=winner, 2=backup
    report_path        TEXT NOT NULL
);
CREATE INDEX idx_research_verdict_run    ON research_verdict(run_date);
CREATE INDEX idx_research_verdict_passed ON research_verdict(passed_hard_gates);
```

旧 `setup_verdict` 表**不动**;`promote` 命令在签 Contract 时派生一条 `setup_verdict` 行,映射:
- `sharpe_oos > 1.0 && max_dd_oos > −15% && ...` → `passed = 1`
- `n_trades_oos → n_samples`
- `expectancy_r_oos → avg_r`
- 从 trade list 重算 `win_rate → win_rate`

`resume_gate` 语义完全不变(只认 `setup_verdict` 表)。

### 4.3 Phase 2 既有模块改动面

| 模块 | 动不动 | 改动 |
|---|---|---|
| `sanity_floor.*`(engine/data_loader/runner) | 不动 | 冻结 |
| `sanity_floor.setup_yaml` | 小动 | 加 `load_setup_v2(path)`,不破坏旧入口 |
| `journal.models.SetupVerdict` | 不动 | 映射在 `promote` 时完成 |
| `journal.repository` | 加方法,不改旧表 | `save_research_verdict`, `get_research_verdict_by_id`, `list_latest_research_verdicts` |
| `journal.checklist` | 小动 | 若 `implementation` 字段在,展示 "backed by research_verdict <id>" |
| `journal.resume_gate` | 不动 | 由 `promote` 确保有对应 `setup_verdict` 行 |
| `Contract.md.template` | 加 1 行 | `research_verdict_id: <uuid>` 注释 |

**总计:旧代码改动行数 < 50;新增代码 ~1500-2500 行。**

### 4.4 CLI 表面

```
daytrader research bakeoff run \
    --start 2022-01-03 --end 2025-12-31 \
    --symbol MES \
    --output data/research/bakeoff-2026-04-20/

daytrader research bakeoff list
daytrader research bakeoff show <verdict_id>
daytrader research bakeoff promote --verdict-id <id>
```

**没有 `auto-promote`。签 Contract 必须人工。** 这是 Phase 2 纪律层边界:机器产出证据,人对自己的钱签字。

---

## 5. 测试、风险、里程碑

### 5.1 测试策略

| 层 | 样本 | 通过标准 |
|---|---|---|
| 策略信号(单元) | 每策略 10-20 条人造 OHLCV fixture | 触发时点 / 方向 / 价格逐字匹配 |
| 成本模型(单元) | 多/空 × target/stop/EOD 3 种退出 | PnL 手工可算准 |
| 数据层(集成) | Databento 2024-01 MES 1m vs CME 官方 daily | 日内 H/L/volume 偏差 < 0.05% |
| 回测器 determinism | 同输入两次 | 成交列表 bit-by-bit 相同 |
| 端到端 smoke | 单月 MES,S1a 满配 | 无异常,metrics 可算 |
| **论文复现校验** | Zarattini 2023/2024 论文各 2-3 个数据点,在 **SPY** 上跑(非 MES) | **偏差 < 15%** 视为规则解读正确 |
| 敏感性端到端 | 3 个月样本跑 6 个 SE | 报告字段齐全 |

"论文复现校验"是唯一规则正确性检测 —— **必须在 M3/M4 人工 checkpoint 通过,否则停**。

### 5.2 风险登记册

| ID | 风险 | 缓解 |
|---|---|---|
| R1 | MES 连续合约 rollover 产生假突破 | 用 Databento `continuous` schema 的 `c-1` 定义(ranked by open interest),提取官方 rollover 日期列表;rollover 日及前 1 日 skip 不交易(不仅是 skip 交易,还从 pure OOS 计数里排除) |
| R2 | S2 "dynamic trailing stop" 公式误解 | (a) SPY known-answer 测试必过;(b) SE-5/SE-6 可检参数依赖;(c) 失败回退问作者 |
| R3 | RTH 缺 bar | 缺失 > 1% 的日整天剔除 |
| R4 | 成本模型失准 | SE-1 cost × {0, 1, 2} 强制通过 |
| R5 | pybroker 小众单一维护者 | 保存 raw trade parquet 可替换引擎 replay;策略类只依赖 pandas + numpy |
| R6 | MES 规格错误 | 从 CME 官方 spec 硬编码 + unit test 锁死 |
| R7 | **过拟合数据** | **bake-off 第一次跑完后,成本/过滤规则冻结 git tag `bakeoff-run-1`,后续改动新开 `bakeoff-2026-XX-XX/` 目录** |
| R8 | 单 MES 过拟合 | 接受;扩品种独立 bake-off |
| R9 | **情绪风险**:0 过关时绕过走捷径"选最像的那个签算了" | `promote` 命令代码级 refuse;不是文档级约束 |

### 5.3 里程碑

| M | 产出 | 估时 | 人工 checkpoint |
|---|---|---|---|
| M1 | `research.bakeoff.data` + Databento 下载 + 质检 + 单元测试 | 2-3 天 | 看质检报告:缺 bar 率、rollover 计数、TZ 校验 |
| M2 | 成本模型 + baseline buy-and-hold 验证 | 1 天 | 基线 Sharpe ≈ MES 真实 0.5,否则框架有 bug |
| M3 | **S1a 实现 + SPY 上 Zarattini 2023 known-answer** | 2-3 天 | **gate:复现偏差 < 15% 才继续** |
| M4 | S1b / S2a / S2b + 各自 known-answer | 3-4 天 | 同 M3 |
| M5 | 评估框架:metrics + DSR + bootstrap + 报告器 | 2-3 天 | 合成"已知 Sharpe"数据喂入验证 |
| M6 | **主 bake-off MES 2022-2025 × 4 候选** | 0.5-1 天跑 + 0.5 天读 | **冻结 git tag `bakeoff-run-1`** |
| M7 | 6 个敏感性实验 | 1-2 天 | 看是否动摇 M6 结论 |
| M8 | `promote` CLI + YAML v2 + Contract.md 填写指南 | 1-2 天 | **最终决定:签哪个 Contract,或不签** |

**总计 13-20 工作日(2-4 日历周)。**

用户侧工作:M1 下 Databento 订单 + 付款;M3/M4 若复现失败协助决策;M6-M8 读报告做签约决定。

### 5.4 退出条件(何时认定方案失败)

1. **M3 失败**(S1 在 SPY 上对不齐 Zarattini 2023)→ 回 brainstorming,重读论文或换候选
2. **M4 失败**(S2 在 SPY 上对不齐 Beat the Market 2024)→ 同上
3. **M6 后 0 候选过** → 失败报告 → 回 brainstorming 讨论是否扩候选/质疑成本/换品种。**不签 Contract**
4. **M7 后 winner 对单参数极敏**(SE-4/5/6 任一失败)→ 降级 winner,若无稳健候选 → **不签 Contract**

---

## 6. 与 04-11 / 04-16 的关系(明文备案)

- **04-11 倾向的 order flow / AMT / Nautilus / mlfinlab 路线**,04-16 已明确决定延至 **Phase 3+**,理由:"用户问题是握不住 edge,不是缺 edge;Nautilus 属于拖延症高级伪装"。本 spec 不推翻该决定。
- **W2 Setup Gate 产出的 locked setup 是 Phase 2 纪律层上线所需的最小 edge**,不承诺是最终 edge。30 笔 lock-in 后可以(也应该)基于实盘数据 + 04-11 列出的 order flow 工具做升级研究,那是 Phase 3。
- **本 spec 的 4 候选选型策略**(Zarattini ORB / Intraday Momentum)**不是** 04-11 recommended direction。选择理由:(a) 规则机械度高,贴合 Phase 2 纪律化目标;(b) 有发表统计数据可作 replication baseline;(c) 只需 1-min OHLCV,不依赖 tick / L2,成本和学习曲线都低于 04-11 列的 order flow 工具栈。**若用户想在 W2 就上 AMT / order flow 路线,需要先推翻 04-16 的延期决定 —— 本 spec 不替代那个讨论。**

---

## 附录 A:被本次淘汰的候选

| 候选 | 淘汰理由 |
|---|---|
| Gao-Han-Li-Zhou 2018 JFE 原版 Intraday Momentum | 多方证据 OOS decay;S2 "Beat the Market" 可视为其工程化修正版 |
| Crabel NR7/NR4 + ORB combo | 无现代长样本公开回测;pattern 频率过低 |
| 传统 VWAP 均值回归 | 仅 practitioner 博客证据,未达发表门槛 |
| Overnight drift / close-to-open | 与"纯日内"约束不符;post-cost Sharpe 边沿 |
| Zarattini "VWAP Holy Grail" | 样本短(5.5 年),信号与 ORB 高度重叠,加入提升有限 |

## 附录 B:被本次淘汰的引擎

| 引擎 | 淘汰理由 |
|---|---|
| backtrader | 主作者 2021-23 后脱手,社区分叉 |
| vectorbt OSS | 无原生期货 primitives,维护放缓,Commons Clause |
| backtesting.py | AGPL 传染,无 walk-forward |
| zipline-reloaded | 股票基因,futures 二等公民 |
| bt (pmorissette) | 组合再平衡框架,非 intraday |
| fastquant | 可能废弃,包装废弃的 backtrader |
| nautilus-trader | **保留给 Phase 3+ 执行层**,不用于本次研究(学习曲线 + LGPL 管理成本超过本次需求) |

## 附录 C:引用

- Zarattini, C., & Aziz, A. (2023). *Can Day Trading Really Be Profitable? Evidence of Sustainable Long-term Profits from Opening Range Breakout (ORB) Day Trading Strategy vs. Benchmark in the US Stock Market.* SSRN 4416622.
- Zarattini, C., Barbon, A., & Aziz, A. (2024). *A Profitable Day Trading Strategy For The U.S. Equity Market.* SSRN 4729284.
- Zarattini, C., Aziz, A., & Barbon, A. (2024). *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY).* Swiss Finance Institute Research Paper No. 24-97.
- Gao, L., Han, Y., Li, S. Z., & Zhou, G. (2018). Market intraday momentum. *Journal of Financial Economics*, 129(2), 394-414.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. (for Deflated Sharpe Ratio)
