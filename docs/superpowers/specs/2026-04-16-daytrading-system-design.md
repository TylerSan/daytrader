# Phase 2 设计:日内交易系统(纪律优先)

**日期:** 2026-04-16
**状态:** 设计完成,待用户审阅
**前置文档:**
- `2026-04-10-phase2-planning.md`(4 个候选方向)
- `2026-04-11-phase2-research-tools-strategies.md`(技术栈调研)

---

## 1. 背景与诊断

### 1.1 用户交易者画像

- 有过实盘经验,当前**暂停**状态
- 交易品种:MES / MNQ / MGC(CME 微型期货)
- 账户:IBKR 自有资金 + Prop(Topstep/Apex)combine
- 时间预算:全职,6+ 小时/日
- 恢复交易目标时间:1-2 月内

### 1.2 暂停原因(用户自诊断,经扩展分析)

用户在 brainstorm 时报告的三个具体失败模式:

1. **无预设止损 / 凭感觉出场**(Q3 C)——亏损无上界
2. **加仓摊平**(Q3 D)——亏损指数放大,Martingale 陷阱
3. **刚到 0.5R 就平**(Q4 H)——盈利有硬顶

**加上行为层:**
- 策略换来换去(在任何 setup 收集足够样本前就切换)
- 不按计划执行(心态/意志力缺口)

**关键结论:** 这个组合**在数学上必亏**。即使胜率 60%,期望值 = 0.6 × 0.5R − 0.4 × (大亏) = 永远为负。
**用户问题不是缺 edge,是握不住 edge(纪律缺口)。**

### 1.3 设计核心命题

> Phase 2 的系统目的是**机械化地替代意志力**——把"容易被情绪破坏的规则"从用户脑中移到代码/经纪商/契约里。在此之上再谈策略 edge。

这改变了对"self-evolving trading system"的 framing:
- 传统 framing:系统发现 edge
- 本系统 framing:系统**强制执行纪律,让用户在任何中性 setup 上也能不爆仓**,从而**让 edge 发现成为可能**

---

## 2. Phase 2 范围边界

### 2.1 IN(前 6 周必做)

| # | 子系统 | 目的 | 形式 |
|---|--------|------|------|
| 1 | **Trading Contract** | 书面契约,固化所有硬规则 | Obsidian `Contract.md`,签名 + 日期 |
| 2 | **Pre-trade Checklist CLI** | 开仓前 5 项必 Y,否则不让继续 | `daytrader pre-trade` 交互命令 |
| 3 | **Post-trade Quick Log** | 出场立刻 1 句话 + 截图路径 | `daytrader post-trade` 命令 |
| 4 | **Daily Loss Circuit** | 日亏损达上限自动锁 no-trade 标志 | 状态表 + checklist 开头读取 |
| 5 | **Sanity-Floor Backtest** | 对候选 setup 做过去 90 天机械回测,期望值 ≥ 0 才允许选 | Python 脚本 + yfinance/Databento |
| 6 | **Dry-Run Logger** | 实盘 dry-run 时记录"假装入场"结果 | `daytrader dry-run` + SQLite |
| 7 | **Resume Gate** | go/no-go 机械检查 | `daytrader resume-gate check` |

### 2.2 OUT(延至 Phase 3+)

- 完整 journal 统计 dashboard(等有真实数据)
- Nautilus Trader / mlfinlab / py-market-profile(研究基础设施)
- Telegram / Discord 告警
- 多 setup 并行实盘
- 订单流可视化(OrderflowChart 等)
- 任何自动下单(保留手动摩擦)

### 2.3 关键取舍说明

- **为什么 Journal 延后?** Journal 是事后填,不改变交易当下行为。真正的纪律层是 **pre-trade 护栏 + OCO 经纪商强制 + circuit 熔断**
- **为什么 Dry-run 先做而非 paper trade?** Paper trade 零心理成本,不测心理层问题。Dry-run 实盘盯盘 + 假装入场,**看得到错过的盈利和躲掉的亏损**,有真实心理冲击但零金钱风险
- **为什么研究基础设施延后?** 用户问题是"握不住 edge",不是"缺 edge"。Nautilus 属于"发现新 edge",此阶段属**拖延症高级伪装**
- **为什么不做自动下单?** 用户问题不是"下单慢",是"下单冲动"。**保留人工摩擦反而是护栏**

---

## 3. 组件架构

### 3.1 存储策略:Hybrid(SQLite + Obsidian)

- **SQLite** (`data/journal.db`) = 唯一真相源。表:`contract`, `trades`, `checklists`, `dry_runs`, `circuit_state`, `setup_verdicts`
- **Obsidian** = 自动生成的人类视图。每条 SQLite 记录写入后自动生成 `.md`
- **Contract.md** 例外:静态签名文档,人写,代码只读

### 3.2 数据流图

```
          ┌────────────────────────────────────┐
          │   Contract.md (Obsidian, 静态)     │
          │   - 日亏损上限、R 单位、setup 定义 │
          └────────┬───────────────────────────┘
                   │ read-only
     ┌─────────────┼─────────────┬─────────────────┐
     ▼             ▼             ▼                 ▼
┌─────────┐  ┌───────────┐  ┌────────────┐  ┌─────────────┐
│Pre-trade│  │Daily Loss │  │Dry-run     │  │Resume Gate  │
│Checklist│  │Circuit    │  │Logger      │  │(go/no-go)   │
└────┬────┘  └─────┬─────┘  └─────┬──────┘  └──────┬──────┘
     │             │              │                │
     ▼             ▼              ▼                ▼
  ┌──────────────────────────────────────────────────┐
  │  SQLite: trades / checklists / dry_runs /       │
  │          circuit_state / setup_verdicts /       │
  │          contract                                │
  └────────┬─────────────────────────────────────────┘
           │ on-write hook
           ▼
  ┌─────────────────────────────────────────┐
  │ Obsidian auto-generated views           │
  │  DayTrader/Trades/YYYY-MM-DD-{id}.md    │
  │  DayTrader/DryRuns/YYYY-MM-DD-{id}.md   │
  │  DayTrader/Daily/checklist-{date}.md    │
  └─────────────────────────────────────────┘

  (离线)
  ┌─────────────────────┐      ┌──────────────────┐
  │ Sanity-Floor        │─────►│ setup_verdicts   │
  │ Backtest (脚本)     │      │ (SQLite 表)      │
  └─────────┬───────────┘      └──────────────────┘
            │
            ▼
     yfinance / Databento 历史数据
```

### 3.3 CLI 表面(新增 6 个命令)

```
daytrader pre-trade              # 开仓前交互 checklist,强制全 Y
daytrader post-trade <trade_id>  # 出场后补记录
daytrader dry-run start          # 开始 dry-run
daytrader dry-run end <id>       # 收尾 dry-run + 结果
daytrader circuit status         # 今日 P&L vs 上限 + no-trade 标志
daytrader sanity run <setup>     # 对 setup 跑过去 90 天 backtest
daytrader resume-gate check      # 输出 go/no-go
```

### 3.4 Pre-trade 关键执行流

1. 读 Contract.md 取规则
2. 读 `circuit_state` 今日记录——若 `no_trade_flag=true`,**直接拒绝**
3. 逐项交互问 5 项:
   - [ ] 止损已挂到经纪商(OCO/bracket)?
   - [ ] 本笔最大亏损 ≤ 1R?
   - [ ] 这是契约 lock-in 的 setup 类型?
   - [ ] 今日已用 R 数 < 契约上限?
   - [ ] 距上次亏损 > 冷静期(30 min)?
4. 任一 N → 中断,记 `checklist.passed=false`
5. 全 Y → 创建 trade 记录(entry/stop/target **必填**),返 trade_id
6. 用户在经纪商实际下单(系统不管)
7. 出场后 `post-trade <trade_id>` 补 exit

### 3.5 错误处理原则

| 场景 | 策略 |
|------|------|
| 缺少止损价 | **Fail-loud**——拒绝记录 |
| Circuit state 文件坏 | **Fail-safe**——默认 no-trade |
| Obsidian 写入失败 | **Fail-open**——warning 不阻塞 SQLite |
| Sanity backtest 数据缺失 | **Fail-loud**——拒绝给 verdict,resume gate 自动 no-go |

---

## 4. Timeline + Gate 机制

6 周拆到日,每段有硬性 gate,不过 gate **不能进下一段**。诚实:代码 ≈ 10-14 日,瓶颈是 dry-run 样本积累。

| 周 | 内容 | 主要产出 | Gate |
|---|------|---------|------|
| **W0** | 契约草案 + setup 短名单 | `Contract.md` draft, 2-3 候选 setup | 契约每条规则**可测度**(不许"谨慎交易"虚词) |
| **W1** | 硬护栏代码层 | `pre-trade` / `post-trade` / `circuit` CLI + SQLite schema + Obsidian writer | **Code gate**:端到端跑通;故意触发 circuit 验证锁定 |
| **W2** | Sanity-Floor Backtest + setup 定选 | `sanity run` CLI + 对 2-3 候选跑 90 天 + verdict | **Setup gate**:至少 1 个 setup `n ≥ 30 且 avg_r ≥ 0`;setup 有**纯规则化** entry/stop/target |
| **W3-4** | Dry-run 期 | `dry-run` CLI + 实盘 dry-run ≥20 笔 + 每日 debrief | **Dry-run gate**(最硬):20+ 笔 / checklist 合规 100% / 原始期望值 ≥ 0 |
| **W5** | Resume Gate + combine 注册 | `resume-gate check` + prop combine 账户 | **Resume gate**:前 3 gate 全绿 + combine 开通 |
| **W6+** | Combine 实盘 | 用全套工具交易 | **Compliance gate**(ongoing):每周合规 ≥95%,低于即停 48 小时自审 |

### 4.1 Gate 的"硬"含义

- Gate 失败 → **回到上一阶段**,不是推迟一天
- Gate 状态由 SQLite 机械输出 go/no-go,**不许主观覆盖**
- 合规率"差一点就算了"**不接受**

### 4.2 关键节点风险提示

1. **W2 可能全部 sanity 失败** → 扩候选(Toby Crabel OR、Kaufman ST、Larry Connors 均值回归);再不行重审品种/regime 假设。不许"勉强选一个"
2. **W3-4 合规率 <100%** → 每次违规立刻写"违规归因",合规计数器归零重来。6 周内归零 3+ 次 → 暂缓 resume,回 W0
3. **W5 Combine 选型** → Topstep trailing drawdown 对日内多次 setup 不友好,若 setup 类型如此建议 Apex/Earn2Trade。根据 W2 结果决定,不预定
4. **"6 周"诚实性** → 预期 **6-8 周**,不是"恰好 6 周"

---

## 5. 数据模型

### 5.1 Contract.md 结构(模板)

```
1. Account & R Unit
   - 账户类型 + 起始规模
   - R 单位:$XX(= 日亏损上限的 1/3)

2. Per-Trade Risk
   - Max loss per trade: 1R
   - Max contracts: N
   - Stop MUST 先挂 OCO/bracket,否则不算入场

3. Daily Risk
   - Daily loss circuit: -3R(2R 警告 / 3R 锁死)
   - Daily max trades: 5

4. Setup Lock-in
   - 锁 1 个主 setup,前 30 笔不换
   - 主 setup 修改需:书面提案 + 20 笔 dry-run + 周末生效
   - **Backup setup 定义在附录 B 但封存**,激活需 Phase 3 解锁条件

5. Execution Rules
   - Entry: 只能经 `pre-trade` CLI 通过
   - Stop: 只允许向盈利方向 trail,且 target 1 达后
   - Target: 预定分批(如 50% T1,余 trail)

6. Zero-Tolerance Bans
   - 摊平亏损(加仓任何形式)
   - 止损反方向移动
   - Pre-trade checklist 跳过
   - 报复交易(止损后 30 分钟内)
   - 达上限后"再一笔"

7. Cool-off
   - 止损后 30 分钟无入场
   - 连续 2 次止损 → 当日结束
   - -2R 触发 30 分钟 + 复盘笔记

8. Amendment Process
   - 只能周末改
   - 改动后等 1 周生效
   - 亏损当日不得改

附录 A: Locked Primary Setup(W2 Setup Gate 过后填)
附录 B: Benched Backup Setup(W2 并行设计,封存待 Phase 3 激活)
```

**强制要求:每条规则必须是可检测的——"谨慎交易"这种虚词一律禁止。**

### 5.2 SQLite Schema 关键约束

```sql
-- 契约版本
CREATE TABLE contract (
    version INTEGER PRIMARY KEY,
    signed_date DATE NOT NULL,
    r_unit_usd REAL NOT NULL,
    daily_loss_limit_r REAL NOT NULL,
    max_trades_per_day INTEGER NOT NULL,
    stop_cooloff_minutes INTEGER NOT NULL,
    locked_setup_name TEXT,
    locked_setup_file TEXT,
    backup_setup_name TEXT,
    backup_setup_status TEXT DEFAULT 'benched',  -- 'benched' | 'active'
    active BOOLEAN NOT NULL
);

-- Pre-trade checklists
CREATE TABLE checklists (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('real', 'dry_run')),
    contract_version INTEGER NOT NULL,
    item_stop_at_broker BOOLEAN NOT NULL,
    item_within_r_limit BOOLEAN NOT NULL,
    item_matches_locked_setup BOOLEAN NOT NULL,
    item_within_daily_r BOOLEAN NOT NULL,
    item_past_cooloff BOOLEAN NOT NULL,
    passed BOOLEAN NOT NULL,
    failure_reason TEXT,
    FOREIGN KEY (contract_version) REFERENCES contract(version)
);

-- 真实 trades
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    date DATE NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol IN ('MES','MNQ','MGC')),
    direction TEXT NOT NULL CHECK (direction IN ('long','short')),
    setup_type TEXT NOT NULL,
    entry_time DATETIME NOT NULL,
    entry_price REAL NOT NULL,
    stop_price REAL NOT NULL,       -- 数据库层强制止损
    target_price REAL NOT NULL,     -- 数据库层强制目标
    size INTEGER NOT NULL,
    exit_time DATETIME,
    exit_price REAL,
    pnl_usd REAL,
    r_multiple REAL,
    notes TEXT,
    violations TEXT,                -- JSON array
    FOREIGN KEY (checklist_id) REFERENCES checklists(id)
);

-- Dry-run(结构与 trades 对称但前缀 hypothetical)
CREATE TABLE dry_runs (
    id TEXT PRIMARY KEY,
    checklist_id TEXT NOT NULL,
    date DATE NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    identified_time DATETIME NOT NULL,
    hypothetical_entry REAL NOT NULL,
    hypothetical_stop REAL NOT NULL,
    hypothetical_target REAL NOT NULL,
    hypothetical_size INTEGER NOT NULL,
    outcome TEXT CHECK (outcome IN ('target_hit','stop_hit','rule_exit','no_trigger')),
    outcome_time DATETIME,
    outcome_price REAL,
    hypothetical_r_multiple REAL,
    notes TEXT,
    FOREIGN KEY (checklist_id) REFERENCES checklists(id)
);

-- 每日熔断状态
CREATE TABLE circuit_state (
    date DATE PRIMARY KEY,
    realized_r REAL NOT NULL DEFAULT 0,
    realized_usd REAL NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    no_trade_flag BOOLEAN NOT NULL DEFAULT 0,
    lock_reason TEXT,
    last_stop_time DATETIME
);

-- Sanity-Floor verdict
CREATE TABLE setup_verdicts (
    setup_name TEXT NOT NULL,
    setup_version TEXT NOT NULL,
    run_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    data_window_days INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_r REAL NOT NULL,
    passed BOOLEAN NOT NULL,
    PRIMARY KEY (setup_name, setup_version, run_date, symbol)
);
```

### 5.3 Setup 定义格式(YAML,机器可读)

所有 setup 必须写成 YAML,**强制机器可执行的规则语言**——不许"突破 + 确认"这种含糊词。

示例(仅格式,非最终选择):

```yaml
name: opening_range_breakout
version: v1
symbols: [MES, MNQ]
session_window:
  start: "09:30 America/New_York"
  end: "11:30 America/New_York"
opening_range:
  duration_minutes: 15
entry:
  direction: long_if_above_or_short_if_below
  trigger: price_closes_beyond_or_by_ticks
  ticks: 2
stop:
  rule: opposite_side_of_or
  offset_ticks: 2
target:
  rule: multiple_of_or_range
  multiple: 2.0
filters:
  - no_entry_after: "11:00 America/New_York"
  - min_or_range_ticks: 8
  - max_or_range_ticks: 40
  - skip_if_event: [fomc, cpi, nfp]
```

---

## 6. Sanity-Floor Backtest

### 6.1 算法(伪代码)

```
input: setup.yaml + 过去 90 天的 1-minute OHLCV
output: 一行 setup_verdicts

for each day × symbol:
    按 session_window 加载 bars
    算 opening range(若适用)
    跑 filters → 不符则跳过
    扫描 entry trigger 条件
    若触发:
        entry/stop/target 按 YAML 规则算
        逐 bar 模拟 forward(bar high/low 先击中谁)
        记录 r_multiple(扣除 commission + slippage)

aggregate:
    n_samples, win_rate, avg_r
    passed = (n ≥ 30) AND (avg_r ≥ 0)
```

### 6.2 保守假设

- Commission: $4 round-trip / 合约(实际约 $1.5-$2.5 为保守)
- Slippage: 止损单滑 1 tick,限价目标 0 tick
- 无隔夜持仓
- 1-minute bar 粒度(不做 tick-level)

### 6.3 诚实声明(必须显式写入每次 report)

> 这不是"好的回测"。它是 sanity floor——**只筛掉明显负期望的 setup**。通过 sanity floor 的 setup **不等于有 edge**,只等于**"值得拿到 dry-run 阶段去测试"**。**不许**用 sanity floor 的 avg_r 估算实盘盈利。

### 6.4 数据源选择

- MES / MNQ:yfinance(免费,1-minute 日内有限回溯)或 Polygon 免费 tier
- MGC:项目已有 Databento 订阅覆盖(tick 聚合到 1-minute)
- 当 yfinance 1-minute 历史不足 90 天时,降级到 5-minute 并在 verdict 里注明粒度

---

## 7. 测试策略

### 7.1 代码正确性(pytest)

| 测试 | 断言 |
|------|------|
| Pre-trade checklist | 任一 item=N → 拒绝创建 trade |
| SQLite NOT NULL | 尝试 INSERT 无 stop_price → 失败 |
| Circuit lock | 构造 -3R 状态 → pre-trade 拒绝 |
| 冷静期 | 构造 last_stop_time = 29 分钟前 → 拒绝 |
| Setup YAML parser | 规则含模糊词 → 解析失败 |
| Sanity-floor 算法 | 合成数据(已知 10 个 1R 赢,5 个 -1R 亏)→ verdict 精确复现 |
| Obsidian writer | 写入失败不阻塞 SQLite commit |

### 7.2 行为完整性(手工 + auditor 脚本)

| 攻击场景 | 预期 |
|---------|------|
| 绕过 CLI 直接写 SQLite trade 表 | FK + NOT NULL 阻止;auditor 脚本事后检出异常 |
| 改 setup 名字(绕 lock-in) | pre-trade 从 contract 表校验,不匹配即拒 |
| 手动改 `circuit_state.no_trade_flag=false` | auditor 脚本每日检查日志↔状态一致性,不一致发告警 |

### 7.3 关键诚实声明

**审计只能事后发现绕过,不能事前阻止**(用户是 root 用户)。这条靠**契约的"技术绕过 = 当日无效"条款**兜底。**自律不能 100% 外包给代码,代码提高作弊成本到"你明知违反契约"**。

---

## 8. 成功标准与 Phase 3 解锁

### 8.1 Phase 2 成功标准(6 周末评估,全部满足)

1. Contract.md 签名,所有条款可机器检测
2. 6 个 CLI 命令端到端跑通,pytest 全绿
3. ≥1 个 setup 通过 sanity floor(n ≥ 30, avg_r ≥ 0)
4. Dry-run ≥20 笔 / checklist 合规 100% / 原始期望值 ≥ 0
5. Prop combine 账户开通
6. 进入 combine 后首 20 笔合规率 ≥95%

### 8.2 Phase 3 解锁条件(combine 阶段后评估)

- ≥100 笔实盘 trades(combine 或 funded)
- Rolling 30 日 checklist 合规率 ≥95%
- 净期望值 > commission
- 0 次情绪驱动的契约修订

### 8.3 Phase 3 解锁菜单(满足后按需选取)

- **Backup Setup 激活** → 经 20 笔 dry-run 后允许上实盘
- 第 3 个 setup 研究
- Nautilus / mlfinlab 研究基础设施
- 完整 journal stats dashboard
- Telegram / Discord 告警
- IBKR API 自动下单(最后解锁,需加倍自律保障)

### 8.4 设计意图

过去"策略换来换去"的病根是太早允许多样化。**"解锁制"把"想加东西"的冲动和"证据支持"绑定,替代情绪驱动。**

---

## 9. 失败场景与早期信号

| 风险 | 检测点 | 应对 |
|------|--------|------|
| **R1** 无 setup 过 sanity floor | W2 末所有 verdict = FAIL | 扩候选(Crabel OR、Connors 均值回归、Kaufman ST);再不行重审 regime/品种假设;timeline 延 1-2 周 |
| **R2** Dry-run 合规率卡在 85-95% | W4 末 | 分析违规归因(特定规则/时段/情绪);针对性加护栏;连续 2 次延期未过 → **Phase 2 暂停,考虑 trading coach** |
| **R3** Sanity 过 + dry-run 过,但 combine 崩 | W6-8 首次 combine 失败 | 若重复 C/D/H 模式 → 契约失效,回 W0;若新失败模式 → 契约补加禁令 |
| **R4** 时间表全部延误 >2 周 | 任何阶段 | **质疑"1-2 月恢复"本身**,考虑推到 3-6 月再决策 |

**原则:把失败路径显式化**——不是悲观,是让"出问题时怎么办"有预设答案,避免情绪驱动的权宜决策。

---

## 10. Backup Setup 并行设计(Amendment)

**W2 允许并行设计第二个 setup:**

- W0 识别 2-3 个候选 setup,W2 sanity-floor 对全部候选并行评估,共享数据加载。从通过 sanity floor 的候选中,**排名最高者 → 主 setup(lock-in);第二高者 → 备 setup(benched)**;其余弃用
- Dry-run 阶段(W3-4)**只跑主 setup**,备 setup YAML 完成但**不参与 dry-run**
- 契约 Section 4 + 附录 B 明确声明 "Backup setup = benched,激活需 Phase 3 解锁条件"
- SQLite `contract` 表含 `backup_setup_name`, `backup_setup_status='benched'`
- Phase 3 解锁后,备 setup 经 20 笔 dry-run 才能上实盘

**为什么允许:** Setup 1 在 W2 若 sanity 失败,有 Setup 2 候补省 1-2 周。研究成本低(YAML + backtest 数据复用)。契约明确封存,**反而强化 lock-in**——把"想切换"的冲动预定在规则里。

**明确禁止:** 并行 dry-run 或并行实盘 2 个 setup。这直接违反用户"策略换来换去"的核心病因诊断,不允许。

---

## 11. 非目标(明确声明)

- **不追求"发现新 edge"**——那是 Phase 3+ 研究工作
- **不追求"全自动化"**——人工下单是护栏不是缺陷
- **不追求"尽可能快恢复交易"**——timeline 服从 gate 合规,不服从情绪急迫性
- **不追求"完美的回测"**——sanity floor 是否决工具,不是证明工具
- **不追求"同时做多个 setup"**——lock-in 比多样化更重要

---

## 12. 下一步

1. 用户审阅本 spec,提修改 / 批准
2. 批准后进入 writing-plans skill,产出具体实施计划(W0-W6 逐周任务、依赖关系、验收准则)
3. 实施阶段使用 executing-plans skill 按计划执行

---

## 附录:开放问题(给用户复审参考)

以下问题 spec 未最终定,留到实施阶段或由用户在签契约时填:

1. **R 单位具体金额** —— 建议 $30-$50(基于 Topstep $50k 的 1% 日亏损 = $500,取 ~10%)
2. **日亏损熔断阈值具体** —— 建议 -3R,但 Topstep combine 规则可能更严,按实际 combine 的 daily loss limit 取较保守值
3. **冷静期时长** —— 建议 30 分钟,可调
4. **主品种优先级** —— MES/MNQ/MGC 三选一作为 setup 主品种?还是多品种同 setup?(建议:一个 setup 先锁定一个主品种,其他品种 opt-in)
5. **Dry-run 目标样本量** —— 最低 20,是否要求 30 以获更稳定统计?
6. **Combine 平台选型** —— W5 根据 setup 类型决定(Topstep / Apex / Earn2Trade),不预定
