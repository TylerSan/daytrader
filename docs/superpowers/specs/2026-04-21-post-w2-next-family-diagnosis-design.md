# Post-W2 下一个策略家族 —— 诊断优先设计

**日期:** 2026-04-21
**状态:** 设计完成,待用户审阅
**上下文阶段:** W2 Setup Gate bake-off 已关闭(0 个 setup locked),W0 Contract 仍未签
**父级/前置文档:**
- [`2026-04-20-strategy-selection-bakeoff-design.md`](2026-04-20-strategy-selection-bakeoff-design.md) —— W2 bake-off 设计(已关闭)
- [`2026-04-21-plan3-bakeoff-closeout-design.md`](2026-04-21-plan3-bakeoff-closeout-design.md) —— W2 关盘决策
- [`../../research/bakeoff/2026-04-21-bakeoff-retrospective.md`](../../research/bakeoff/2026-04-21-bakeoff-retrospective.md) —— W2 回顾
- [`../../research/bakeoff/2026-04-21-plan3-findings.md`](../../research/bakeoff/2026-04-21-plan3-findings.md) —— W2 Plan 3 findings(提出三分支 handoff)

**本 spec 的作用:** W2 三分支 handoff 里的 **(a) 探索新策略家族**,但不直接跳家族 —— 先诊断、再机械决策、再选家族 bake-off。是 W2 的下游分叉,不覆盖 W2、不重写 W2 结论。

---

## 0. TL;DR

W2 null 之后最容易犯的错误是 "strategy hopping" —— 跳到下一篇论文再跑一遍。本 spec 用一条三阶段流程替代这个冲动:

**Phase 1 诊断(时间盒 4-6 工作日,双 workstream 并行):**
- **A 线(SPY 数据诊断,2-3 天):** 在现有 SPY 缓存和 W2 trade log 上跑 6 个诊断(D1-D6),回答"SPY intraday 究竟有什么结构"
- **B 线(MES 家族复测,2-3 天 —— loader 已有 Plan 1 遗产):** 跑 Databento pre-flight → 买 MES 1m 数据 → 调用既有 `load_mes_1m()` → 把 S1a/S1b 规则原样在 MES 上跑一遍(B1-B4),回答"家族对、品种错?"

**Phase 2 预承诺决策门(半天,机械走表):**
- 6 行决策表事先写死,Phase 1 结果进来按列机械匹配,不事后商量
- 最高优先级是 **MES 复测过关** → 家族对、品种错,直接启动 MES-native bake-off
- 其次依序是均值回归基线、多品种 trend、gap、event
- **全不过 → null memo,正式关闭机械研究分支**,转 handoff (b) 纪律化 discretionary 或 (c) 暂停

**Phase 3 —— 本 spec 不覆盖。** 由 Phase 2 决策触发后,按选中的家族另写 spec + plan,走 W2 同款 bake-off 纪律(pure OOS、5 硬门槛、SE-1..N、DSR)。

**关键预承诺:**
- Databento MES 数据 pre-flight 成本上限 \$20,超过 → 降级到 3 年窗口 (2022-01 → 2024-12)
- Phase 1 时间盒 6 天硬顶,到期未完成 → 用已有数据走决策门,剩余项记为 deferred
- 决策门阈值 = gross Sharpe ≥ 1.0(**Phase 1/2 是发现门,不是严格门**);DSR 和其它 4 条硬门槛留给 Phase 3
- Null memo 分支明文写明"这是第二次 null;下一轮新家族需要书面理由,不能是'再试一次'"

---

## 1. 系统边界与架构

### 1.1 目标(唯一成功指标)

Phase 2 输出**一条判决**:选中的家族代号(B' / C / B / gap / event)+ 启动 Phase 3 的推荐,或"null memo + 关闭机械研究分支"。判决可审计、可复现,所有条件表达为 CSV 列 + 机械阈值。

**不是目标:** 签 Contract、写新 setup YAML、产出实盘可执行策略、替代 W2 结论。

### 1.2 新增 vs 复用

```
新增代码(最小化 —— B 线"loader 建设"被 Plan 1 既有资产消化):
  scripts/
    # A 线诊断
    ├── diagnose_d1_per_day.py                # D1: S1/S2 trade log × 日特征分解
    ├── diagnose_d2_signal_autocorr.py        # D2: SPY 1m forward-return 自相关 + 分布
    ├── diagnose_d3_meanrev_baseline.py       # D3: 朴素 fade-open 均值回归基线
    ├── diagnose_d4_gap_decomposition.py      # D4: 隔夜 gap 行为分解 + gap-fill 基线
    ├── diagnose_d5_multi_instrument.py       # D5: S1 在 QQQ / IWM 上的快速抽样
    ├── diagnose_d6_event_days.py             # D6: FOMC/CPI/NFP 日子集隔离

    # B 线 MES(全部"跑脚本",不建 loader)
    ├── mes_b1_preflight.py                   # B1: Databento get_cost() 预检
    ├── mes_b2_loader_smoke.py                # B2: 调用既有 load_mes_1m() 跑全窗口拉取 + 质检
    ├── mes_b3_run_s1.py                      # B3: S1a + S1b 全 replication + pure OOS
    └── mes_b4_compare_to_spy.py              # B4: MES vs SPY 并排对照表

  docs/research/post-w2/
    ├── YYYY-MM-DD-phase1-findings.md         # Phase 1 聚合发现报告(日期 = 完成日填入)
    ├── YYYY-MM-DD-phase2-decision.md         # Phase 2 决策门结果(同上)
    ├── d1..d6 raw CSVs                       # 详见 §2 各诊断 "输出" 小节
    └── mes_b3_*.csv + mes_b4_compare.md      # MES 回测产出

复用(既有,**全部不改一行**):
  research/bakeoff/data.py                    # ⭐ Plan 1 era MES loader:MesDatabentoLoader +
                                              #    load_mes_1m() + detect_rollover_skip_dates() +
                                              #    filter_rth() + data_quality_report()
                                              #    已 14 个单元测试(tests/research/bakeoff/test_data.py)
  strategies/_orb_core.py                     # ORB 机械核心(MES 上直接复用)
  strategies/_s1_orb.py                       # S1a + S1b 策略类
  strategies/_s2_core.py                      # S2 核心(D1 需要读 S2 trade log)
  strategies/_known_answer.py                 # summary_stats 函数
  costs.py                                    # Legacy MES + Plan 3 SPY helpers 都用
  metrics.py                                  # Sharpe/Sortino/Calmar/MDD/PF/expectancy/DSR/bootstrap
  scripts/_plan3_trade_utils.py               # filter/flip/equity_curve/daily_returns
  data_spy.py + data_spy_daily.py             # SPY 缓存,A 线诊断直接读
```

**总计:新增代码 ~500-700 行(10 个诊断/MES 脚本 × 50-70 行),不含测试。不改任何既有代码。MES loader 本身是 Plan 1 遗产,本 spec 只是终于让它发挥原本设计的用途。**

### 1.3 数据流

```
A 线(SPY 诊断,只读)
  SPY 1m/daily 缓存(W2 已下)
    + W2 Plan 3 trade log(已在 plan3_main_report.csv)
      ├── D1 per_day
      ├── D2 signal autocorr
      ├── D3 mean-rev baseline
      ├── D4 gap decomposition
      ├── D5 QQQ/IWM 抽样(需要下 QQQ/IWM 1m,成本 < $1 估,pre-flight 确认)
      └── D6 event days
                ▼
          d1..d6.csv

B 线(MES,双写)
  Databento GLBX.MDP3 MES 1m continuous c-1
    ▼ pre-flight cost check (B1)
    ▼ if ≤ $20 → pull 2018-05 → 2024-12
    ▼ if > $20 → 降级 3y 或停
  data/cache/ohlcv/mes_1m_<window>.parquet
    ▼ 既有 data.py loader(load_mes_1m → MesDataset,含 rollover + RTH + QA)
  MES 1m DataFrame
    ▼ 现有 _s1_orb 规则(不改)+ legacy costs.py MES 参数
  S1a + S1b trade log(MES)
    ▼ 现有 metrics.py
  mes_b3_s1a.csv + mes_b3_s1b.csv

合流
  Phase 2 决策脚本
    ▼ 按决策表逐行匹配(见 §3)
  phase2-decision.md  →  后续 Phase 3 spec 或 null memo
```

### 1.4 关键架构决定(带反驳)

1. **诊断脚本,不是框架。** Plan 3 已经验证"scan script + CSV + markdown"模式对时间盒项目最省事。不建 diagnostic engine、不抽诊断基类。每个脚本独立可跑、独立可 review。
2. **MES 数据进 bakeoff 缓存目录,不单独分家。** `data/cache/ohlcv/mes_1m_*.parquet` 与 SPY 缓存同级;loader API shape 对齐 `data_spy.py`,便于未来 Phase 3 直接读。
3. **Rollover 交给 Databento continuous schema,不自建 roll 表。** Databento `continuous` 提供 `c-1`(front month by OI)定义 + 官方 roll 日期;我们直接读,额外再加"rollover 当日 + 前 1 个交易日 skip"的安全带(排除 trade log,不仅是 skip 入场)。
4. **Session filter 统一 09:30-16:00 ET RTH。** MES 23h 交易,但本 spec 只测 day-trading 家族;overnight 行为留给 Phase 3 如果 gap family 被选中。
5. **Phase 1 发现门是 gross Sharpe ≥ 1.0,不加 DSR。** 此阶段目标是**筛掉显著无信号的方向**,不是"选定签约对象"。DSR 和其余 4 条硬门槛留给 Phase 3 的正式 bake-off。**加反驳:** 这会放过 1-2 条"看着有 edge 实际是 luck"的方向;但 Phase 3 会用完整硬门槛截住,总体误判成本低。
6. **决策表预承诺、机械走表。** Plan 3 §6 已证明这个模式能抑制"事后调参"诱惑。决策代码和阈值在 Phase 1 开跑前 git commit,Phase 2 只 load + match。

---

## 2. Phase 1 诊断清单(逐项规范)

每项格式:**输入 → 逻辑 → 输出 → 决策门引用**。决策门字段用**粗体 + 反引号**,便于 §3 机械引用。

### A 线 —— SPY 数据诊断

#### D1. 按天分解(S1/S2 trade log × 日特征)

- **输入:** `plan3_main_report.csv`(已有 S1a+S1b pure OOS trade log);W2 Plan 2c 的 S2 trade log(如果在 repo,否则跳 S2);SPY daily bars(算 prev-day range);VIX daily(若有,否则记录并 skip);FOMC/CPI/NFP 事件日历(静态 CSV,2024 年,手工维护即可,~30 行)
- **逻辑:** 按日聚合每日 S1/S2 PnL;每日标注 VIX 档(低/中/高三分位)、overnight gap 方向/幅度、前日 range 档、day-of-week、是否事件日
- **输出:** `d1_per_day.csv`(date + 每 strategy 当日 pnl + 6 个日特征列);`d1_feature_table.md`(每 feature × 每 bucket 的 win_rate + mean_pnl + n)
- **决策门引用:** 无硬门槛;产出供 Phase 3 spec 写 regime-gate 时参考

#### D2. 信号自相关与分布

- **输入:** SPY 1m ARCX.PILLAR 全窗口(已缓存)
- **逻辑:** 对每个 RTH 1m bar 计算 `forward_return_5bar` = (close_{t+5} - close_t) / close_t;同样 `forward_return_15bar`;计算 `bar_return` = (close - open) / open;算 lag-1 / lag-5 / lag-15 的自相关(全样本 + 按小时 bucket)
- **输出:** `d2_signal.csv`(bar-level);`d2_autocorr.md`(聚合表:lag × hour bucket × autocorr)
- **决策门引用:** 无硬门槛;诊断信息。`|autocorr| > 0.05` 跨多个 bucket → 家族 C 加分;`|autocorr| < 0.01` 跨所有 → SPY intraday 基本白噪声

#### D3. 均值回归基线(**关键决策门输入**)

- **输入:** SPY 1m 全窗口
- **逻辑(保持朴素,不调参):**
  - 09:35 ET bar:若 close[09:34] > open[09:30] → **short** 1 单位;反之 → **long** 1 单位;相等 → skip
  - 入场价:close[09:35]
  - 出场(以下任一先触发):
    - **止盈:** 当前 bar close 回到"当日累积 VWAP"的反向 —— 即 long 仓位:price ≥ day_cumulative_vwap;short 仓位:price ≤ day_cumulative_vwap
    - **强平:** 15:55 ET 当 bar close
  - **无止损**(故意,看"裸"均值回归是否存在;止损 = Phase 3 事)
  - **无成本**(gross)
- **输出:**
  - `d3_mr.csv`:trade log
  - `d3_mr_summary.csv`:单行表,列 = `{window, sharpe_gross, sortino_gross, mdd, pf, n, win_rate}`,两行(pure_oos + full_window)。**决策门消费此 CSV**
  - `d3_mr_summary.md`:同数据的人类可读叙述
- **决策门引用:** **`d3_mr_summary.csv` 中 `window=pure_oos` 行的 `sharpe_gross` ≥ 1.0** → 家族 C 触发

#### D4. 隔夜 gap 分解与 gap-fill 基线(**关键决策门输入**)

- **输入:** SPY daily OHLCV 全窗口 + 1m 当日前 30 分钟(用来算 gap-fill 触发点)
- **逻辑:**
  - 每日:gap_pct = (open - prev_close) / prev_close
  - 分类:|gap_pct| < 0.1% → no-gap;其余按符号分 up-gap / down-gap
  - **基线策略:** 若 up-gap,09:30 open short 1 单位,止盈 = prev_close 价位,EOD 强平,无止损
  - down-gap 对称(long)
  - no-gap 日 skip
- **输出:**
  - `d4_gap.csv`:trade log + 每笔 gap 分类
  - `d4_gap_summary.csv`:单 CSV,两行(pure_oos + full_window),列同 D3
  - `d4_gap_summary.md`:人类可读叙述
- **决策门引用:** **`d4_gap_summary.csv` 中 `window=pure_oos` 行的 `sharpe_gross` ≥ 1.0** → gap family 触发

#### D5. 多品种 S1 抽样(**关键决策门输入**)

- **输入:** Databento 拉 QQQ + IWM 1m ARCX.PILLAR,**只拉 pure OOS 2024-04 → 2024-12**(约 9 个月 × 2 符号)
- **Pre-flight:** 先跑 `client.metadata.get_cost()`;两个符号总价预计 < $0.5;超过 $3 即停并报告
- **逻辑:** 现有 `_s1_orb` 规则类不改,换符号 + 换数据源,同款 Plan 3 metrics 管道
- **输出:**
  - `d5_qqq_s1a.csv`、`d5_qqq_s1b.csv`、`d5_iwm_s1a.csv`、`d5_iwm_s1b.csv`:trade logs
  - `d5_compare.csv`:4 行(一行一个 symbol×variant),列 = `{symbol, variant, sharpe_gross, n, ...}`,**决策门消费此 CSV**
  - `d5_compare.md`:人类可读叙述
- **决策门引用:** **`d5_compare.csv` 中 max(`sharpe_gross`) ≥ 1.0** → 家族 B 触发

#### D6. 事件日隔离

- **输入:** Plan 3 S1 trade log + FOMC/CPI/NFP 事件日历(同 D1,复用)
- **逻辑:** 把 trade 按"是否事件日"分成两组;每组分别算 summary_stats
- **输出:**
  - `d6_events.csv`:每笔 trade 带 `is_event_day` 标签
  - `d6_events_summary.csv`:两行(on_event / off_event),列 = `{partition, sharpe_gross, n, win_rate, mean_pnl}`,**决策门消费此 CSV**
  - `d6_events_summary.md`:人类可读叙述
- **决策门引用:** **`d6_events_summary.csv` 中 `partition=on_event` 行同时满足 `sharpe_gross` ≥ 1.0 **且** `n` ≥ 30** → event-conditional family 触发

### B 线 —— MES 家族复测

#### B1. Databento MES pre-flight 成本

- **输入:** Databento `GLBX.MDP3`,symbol `MES.c.0`(continuous c-1),schema `ohlcv-1m`,窗口 2018-05-01 → 2024-12-31
- **逻辑:** 调 `client.metadata.get_cost(...)`(不真拉);打印 USD 估计
- **输出:** `mes_preflight.txt`(USD 数字 + 元数据)
- **硬 gate:**
  - **≤ \$20 → 继续 B2**
  - **\$20 < cost ≤ \$50 → 降级 3 年窗口 (2022-01 → 2024-12),重跑 B1 → ≤ \$20 继续**
  - **> \$50 → B 线 abort,Phase 2 决策表跳过第 1 行,记录 MES 未测**

#### B2. 既有 loader 全窗口拉取 + 健康检查

**关键点:** `research/bakeoff/data.py` 的 `load_mes_1m()` 已经在 Plan 1 era 完整实现并有 14 个单元测试。本步**不写新 loader**,只调用既有 API 做两件事:

- **步骤:**
  1. 先跑既有测试套件(`pytest tests/research/bakeoff/test_data.py`)—— 确保 Plan 1 loader 还能用(半年未 exercise,可能有 lib 漂移);若失败 → 修回绿再继续
  2. 调用 `load_mes_1m(start=2018-05-01, end=2024-12-31, api_key=..., cache_dir=data/cache/ohlcv)` 做**全窗口一次拉取**(cache-first,已下部分自动跳过)
  3. 拿到 `MesDataset`,检查:
     - `bars` 行数合理(6.5y × ~390 RTH bars/day × ~252 trading days/year ≈ 640k 行,容忍 ± 10%)
     - `rollover_skip_dates` 数量合理(MES 季度 roll,~26 个 roll × 2 天 ≈ 52 个 skip 日期,容忍 ± 10)
     - `quality_report['flag_low_coverage']` 为 True 的日子 < 3%(否则 Databento 数据源可能有洞)
- **输出:** `mes_b2_healthcheck.md`(PASS/FAIL + 上述三项实际值)
- **硬 gate:** **任一检查 FAIL → B 线 abort**,决策表第 1 行跳过

#### B3. MES 全窗口 S1 复测

- **输入:** B2 返回的 `MesDataset`(`bars` + `rollover_skip_dates` + `quality_report`)
- **逻辑:**
  - 在喂给策略前,从 `bars` 剔除 `rollover_skip_dates` 和 `quality_report.flag_low_coverage=True` 的日期(遵守 `MesDataset` docstring 里"callers MUST intersect"的契约)
  - S1a + S1b 策略类**不改**,仅传入已过滤的 MES DataFrame 和 legacy `costs.py` MES 参数
  - 成本:commission \$4 RT + entry 1 tick + stop 2 ticks + target 0 ticks(legacy 常量)
  - 同 Plan 3 full metrics 管道(Sharpe/Sortino/Calmar/MDD/PF/expectancy/DSR n_trials=2/bootstrap CI)
  - **分段报告:** replication 窗口 (2018-05 → 2024-03) + pure OOS (2024-04 → 2024-12) 各一份
- **输出:**
  - `mes_b3_s1a.csv`、`mes_b3_s1b.csv`:trade logs
  - `mes_b3_report.csv`:2 行(S1a + S1b)× 13 列(对齐 Plan 3 main report 13 列格式),**决策门消费此 CSV**
  - `mes_b3_report.md`:人类可读叙述
- **决策门引用:** **`mes_b3_report.csv` 中 max(`sharpe_pure_oos_gross`) ≥ 1.0** → 家族 B' 触发(最高优先级)

#### B4. MES vs SPY 对照

- **输入:** Plan 3 main report + B3 MES report
- **逻辑:** 并排表格,每行一个 metric,列 = {SPY-S1a, SPY-S1b, MES-S1a, MES-S1b};最后加一列 "diff 信号"(MES > SPY by X%? 标记是否"品种改变事情")
- **输出:** `mes_vs_spy_compare.md`(纯文档产出,不进决策门)

---

## 3. Phase 2 预承诺决策门

### 3.1 决策表(逐行机械匹配,首行匹配胜出)

每行条件的"数据源"是 §2 里已定义的 CSV;"列 × 筛选"给出了对该 CSV 的确切聚合规则。

| # | 数据源 CSV | 列 × 筛选 | 阈值 | 匹配 → 行动 |
|---|---|---|---|---|
| **1** | `mes_b3_report.csv` | `max(sharpe_pure_oos_gross)` over 2 行 (S1a, S1b) | **≥ 1.0** | **家族 B' (MES-native trend)** → 启动 Phase 3 spec: MES S1 bake-off 参照 W2 纪律 |
| 2 | `d3_mr_summary.csv` | `sharpe_gross` where `window=pure_oos` | ≥ 1.0 | 家族 C (均值回归) → Phase 3 spec:SPY mean-reversion bake-off |
| 3 | `d5_compare.csv` | `max(sharpe_gross)` over 4 行 (QQQ × {S1a,S1b} + IWM × {S1a,S1b}) | ≥ 1.0 | 家族 B (多品种 trend) → Phase 3 spec:多 ETF S1 bake-off |
| 4 | `d4_gap_summary.csv` | `sharpe_gross` where `window=pure_oos` | ≥ 1.0 | overnight gap family → Phase 3 spec:SPY gap-fill bake-off |
| 5 | `d6_events_summary.csv` | `sharpe_gross` AND `n` where `partition=on_event` | `sharpe_gross` ≥ 1.0 **AND** `n` ≥ 30 | event-conditional family → Phase 3 spec:event-day subset bake-off |
| **6** | 以上全不匹配 | — | — | **Null memo** → 关闭机械研究分支,user 走 handoff (b) 或 (c);新家族触发需要书面新证据 |

**优先级说明:**
- 第 1 行(MES)**绝对最高优先**,因为它回答的是 W2 未闭合的"家族对、品种错"假设。MES 过关等于 W2 结论"家族没 edge"被证伪;此时其它家族都不应启动。
- 第 2-5 行按预期先验概率从高到低排(均值回归 > 多品种 > gap > event)。
- 多行同时满足(罕见):按行号取最小(= 最高优先级)。**不用"取最高 Sharpe"**;优先级是对"为什么这个信号有意义"的先验排序,不是"哪个数字大"。
- 第 6 行 null 分支**硬性要求**后续任何新家族引入必须附带书面理由(e.g. "用户找到新论文 + 关键数据点"),**不能是"我想再试一下"**。

### 3.2 Phase 2 执行过程

- Phase 1 时间盒到达(第 4-6 天)且所有脚本退出(或 deferred)
- 运行 `scripts/phase2_decide.py`(待实现于 Phase 1 期间,< 60 行):
  1. Load 所有 d*.csv 和 mes_b3_report.csv
  2. 逐行匹配决策表
  3. 输出 `phase2-decision.md`:选中的分支 + 所有数据源值 + 未触发分支的值
- User 读 decision.md,**签字(git commit 一行"approved by user YYYY-MM-DD")**,进 Phase 3 或写 null memo

### 3.3 禁止事项(代码 + 评审双层约束)

1. **不修改阈值** —— 决策表阈值一旦 Phase 1 开跑(git tag `phase1-frozen`)即冻结;修改需要新 commit + review + 重新 tag。
2. **不新增行** —— 运行期间发现"D7 也应该算一条"→ 记录到下一版 spec,不影响当前决策。
3. **不事后降阈值** —— "差 0.05 就过了"= 没过。
4. **不删除未触发行** —— 未触发行的数字要一起写进 decision.md,供 future review 参考。

---

## 4. 测试策略

| 层 | 对象 | 通过标准 |
|---|---|---|
| 回归 | 既有 `tests/research/bakeoff/test_data.py`(14 tests) | 全绿 —— 半年未 exercise,先验证 Plan 1 loader 没被依赖漂移破坏 |
| 回归 | 其余既有 bake-off 测试(_strategies、_costs、_metrics) | 全绿 —— 确保复用的旧代码都能跑 |
| 集成 | B2 全窗口 health check | 参见 §2 B2 硬 gate |
| 集成 | 诊断脚本 D1-D6 + B3 + B4 在小样本 fixture 上都能产出非空 CSV | 每脚本对应 `tests/test_diagnose_*.py` smoke(5-10 行级别,不追求严密)|
| 端到端 | Phase 2 decide 脚本:给定 fixture 数据匹配每一行决策表 | 6 个测试用例 × 6 行决策,每行至少一个 hit、至少一个 miss |

**不做:**
- 新写 MES loader 单元测试(`data.py` 已有 14 tests,复用即可)
- 策略规则的论文复现 KAT(S1a/S1b 已在 W2 KAT,直接复用)
- D3/D4 朴素基线的论文对齐(**没有 paper answer 可对**,它们本来就是 synthetic 诊断)

---

## 5. 风险登记册

| ID | 风险 | 缓解 |
|---|---|---|
| R1 | MES rollover 产生假突破(上一合约低 × 新合约高 = 假 break) | **已由 Plan 1 既有代码处理:** `detect_rollover_skip_dates()`(`instrument_id` 变化检测)+ `MesDataset.rollover_skip_dates` 契约 + 14 个既有单元测试;本 spec 只保证 B3 正确消费这个契约(§2 B3 明文调用) |
| R2 | 诊断 cherry-pick —— 跑完数据后"发现 D7 也应该算" | git tag `phase1-frozen` + 决策表冻结规则(§3.3) |
| R3 | Phase 1 超 6 天 | 硬止损:第 6 天收盘时 Phase 2 决策仍需跑,未完成项记录为 deferred 并在 decision.md 标注 |
| R4 | Databento pre-flight > \$20 | 降级到 3 年窗口(§B1 硬 gate);仍 > \$20 → abort B 线,决策表跳过第 1 行 |
| R5 | D3 均值回归基线"故意朴素"→ 即使过关也可能是假 edge | 决策门只到 Phase 3 启动决策;Phase 3 spec 用真实版(加止损/过滤/更严格 window),届时 5 硬门槛把关 |
| R6 | B' 过关但不会搭 MES Contract 基础设施(新 YAML、新 cost tier、Topstep 账户规则) | Phase 3 spec 的事,不在本 spec 范围;Phase 2 只输出"pursue B'",不写 setup YAML |
| R7 | **Null memo 出来后心痒"再试一下"** | Null memo 模板强制包含:"这是第二次 null;下一家族的 git commit 信息里必须有书面新证据引用" |
| R8 | D3/D4 基线用 gross Sharpe 而非 net,可能给 false positive | 本 spec 明文:Phase 1/2 是**发现门**不是**严格门**,gross 过关只是 Phase 3 的启动许可,不是最终判决。W2 的 5 硬门槛仍等着 |
| R9 | MES 成本模型失准(legacy Topstep 数字不是当前 2026 真实数字) | B3 期间查一次当前 Topstep + IBKR 费率;偏差 < 20% → legacy 值留用;≥ 20% → 更新 legacy 常量 + 记录到 decision.md 附录 |
| R10 | 多品种 (D5) QQQ/IWM 数据拉失败或成本意外 | pre-flight check;失败则决策表第 3 行直接跳过不参与匹配,decision.md 记录"D5 deferred" |

---

## 6. 里程碑与退出条件

### 6.1 里程碑

| M | 产出 | 估时 | 依赖 |
|---|---|---|---|
| M1 | 诊断脚本 10 个全部 scaffold(空壳 + smoke 测试)+ 决策表代码冻结 + `phase1-frozen` git tag + 既有 `test_data.py` 回归绿 | 0.5 天 | — |
| M2 | B1 pre-flight 通过;MES 数据全窗口下完;B2 health check 绿 | 0.5 天 | M1 |
| M3 | Workstream A 完成(D1-D6 全部跑完,输出 6 组 CSV + md) | 2-3 天 | M1(D5 也依赖 M2 的 pre-flight 结果) |
| M4 | Workstream B 完成(B3 + B4 全跑完) | 1.5-2 天 | M2(loader 已有,策略不改,纯跑回测 + 出报告) |
| M5 | Phase 1 findings 聚合文档 `phase1-findings.md` | 0.5 天 | M3 + M4 |
| M6 | Phase 2 决策门运行 + `phase2-decision.md` 产出 + user 签字 | 0.5 天 | M5 |

**M3 与 M4 并行;总估时 4-6 工作日**(比最初估的 5-7 天短 1 天,因为 B 线 loader 建设被 Plan 1 消化)。

### 6.2 退出条件(提前终止)

| 条件 | 动作 |
|---|---|
| B1 pre-flight 成本 > \$50 | B 线 abort,决策表第 1 行跳过,仅 A 线结果驱动决策 |
| B2 loader smoke 任一检查 FAIL | B 线 abort,同上 |
| 第 6 天收盘 Phase 1 仍未完成 | 立刻 freeze 现有输出,用已有数据跑 Phase 2 决策,未完成项在 decision.md 标注 |
| 任一诊断脚本持续报错 > 2h 无进展 | 该项标 deferred,决策表对应行跳过 |
| user 中途否定决策表 | 停止,回到 brainstorming 重新设计决策表,本 spec 废弃 |

---

## 7. 与 W2 spec 的关系(明文备案)

- **不覆盖 W2 结论。** W2 Plan 3 Branch 1 定性"S1 在 SPY 上没 edge"有效。本 spec 的 MES 复测(B 线)是**不同自变量的独立实验**,哪怕过了也不是"W2 错了",而是"W2 在 SPY 上正确、在 MES 上不一定正确"。
- **不扩 W2 code。** 所有 W2 既有模块(strategies、costs、metrics、trade utils)本 spec 只**读不改**。
- **不写新 Contract.md。** Contract 签约是 Phase 3 之后的事;本 spec 里不涉及 YAML v2、promote CLI、setup_verdict 表新写入。
- **复用 W2 的"预承诺决策表 + 时间盒"方法论。** 这是 W2 Plan 3 §6 成功经验的直接迁移。
- **复用 W2 基础设施。** metrics.py、costs.py、_orb_core、Trade wire format、known-answer 模式 —— W2 回顾里列的"可复用资产"在本 spec 的 A+B 线都在用。

---

## 附录 A:被本次淘汰的候选方向

| 候选 | 淘汰理由 |
|---|---|
| 直接启动均值回归 bake-off(不做诊断) | 复刻 "strategy hopping"。D3 基线用半天就能给出是否值得追的证据,省一次可能浪费的 bake-off |
| 直接启动多 ETF bake-off(B 不经 D5 抽样) | 同上,D5 一天就能给出 QQQ/IWM 先验 |
| 引入 order flow / Nautilus / mlfinlab | 2026-04-16 系统设计已把这类推到 Phase 3+;user 问题是"握不住 edge"非"缺 edge";本 spec 不推翻 |
| 以新论文家族(非 Zarattini)启动 bake-off | 同样有 overfitting 风险(另一篇论文的样本期也可能正好覆盖 training leakage);若 Phase 2 决策落到某家族,Phase 3 spec 可在里面选论文或自研规则 |
| Multi-factor 组合(ORB × VIX × after-FOMC 等) | Phase 2 第 5 行 event-conditional 触发后再在 Phase 3 展开;过早 committed 是 data mining |
| 重跑 W2 不同成本假设 | Plan 3 SE-1 已经 × {0, 1, 2} 扫过了;再扫是明确的浪费 |
| 扩 S2 规则变体在 MES 上跑 | Plan 2c 的 `avg_MFE_R < 0.35` 是 intraday momentum 信号的结构性缺陷,不是 SPY-specific microstructure;B 线只测 S1 |

## 附录 B:关于发现门(gross Sharpe ≥ 1.0)与严格门(Phase 3 5 硬门槛)的分离

Phase 1/2 的单一阈值(gross Sharpe ≥ 1.0)**看似宽松,其实是设计选择**:

- **为什么不是 DSR?** DSR 对 n_trials 敏感;Phase 1 里到底算几个 trials(5 行决策表里每行都是独立 hypothesis?D3 的 fade-open 算不算一个 trial?)边界模糊。与其在此阶段钉死,不如推到 Phase 3,按选定家族的 candidate 数量正确赋 n_trials。
- **为什么不是 net?** 诊断基线(D3、D4)本就不是"完整策略",没止损没过滤,成本模型不清晰;用 gross 代表"信号本身有没有方向性"。Phase 3 用 net + 完整硬门槛截第二道。
- **为什么阈值是 1.0?** 对齐 W2 的风险调整收益硬门槛。gross ≥ 1.0 是 net ≥ 1.0 的必要条件(几乎一定);gross < 1.0 的方向在 net 下几乎不可能 ≥ 1.0,所以这是**排除门**,不是**承诺门**。
- **误判代价:** false positive(gross 过、net 不过)→ 浪费一个 Phase 3 sprint,约 1-2 周;false negative(gross 不过但 net 可能过)→ 漏一个方向。在当前阶段,false positive 代价更低(被硬门槛截),所以偏 loose 是合理的。

## 附录 C:引用

- W2 spec(见顶部前置文档列表)
- Databento `GLBX.MDP3` continuous schema 文档 —— https://databento.com/docs
- López de Prado, M. (2018). *Advances in Financial Machine Learning* —— DSR 定义(引用在 metrics.py,不在本 spec 新加)
- 用户自动化 memory `reference_databento_preflight_cost.md` —— pre-flight cost API 使用纪律
