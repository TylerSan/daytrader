# Phase 2 调研：可参考/可使用的现有工具与策略

> 原则：不重新发明轮子。能用成熟、活跃维护的开源工具，就不自己写。

## 总体结论（一页摘要）

**推荐技术栈（Phase 2 的基础设施）：**

| 层 | 推荐工具 | 为什么 |
|---|---------|-------|
| **回测/执行引擎** | **Nautilus Trader** | 唯一一个 Rust 核心、原生 tick-level、L2/L3 订单簿建模、研究→实盘同构的开源框架 |
| **历史 tick 数据** | **Databento Python SDK** | 你已经在用，和 Nautilus 有官方 adapter |
| **实时 tick 数据** | **async_rithmic** | 活跃维护的 async Python Rithmic 客户端，带 protobuf，支持 live + historical tick |
| **订单流特征 (信息 bars)** | **mlfinlab**（Hudson & Thames） | Lopez de Prado《Advances in Financial ML》第 2 章的开源实现，包含 imbalance/tick/volume/dollar bars |
| **Volume / Market Profile** | **py-market-profile** + 自研 | Python 社区唯一靠谱的开源 Market Profile 库 |
| **订单流可视化** | **OrderflowChart** (plotly) 或 **stack-orderflow** (finplot) | 不用自己画 footprint |
| **性能分析** | **quantstats** + **pyfolio** | 回测指标、回撤曲线、因子分析标准工具 |
| **理论基础** | **Dalton《Mind Over Markets》+《Markets in Profile》** | Auction Market Theory 的圣经 |
| **学术锚点** | **Cont-Kukanov-Stoikov OFI**（2014） | 目前唯一有严格实证支持的订单流→价格模型 |

**我们需要自己写的部分（无法找到现成的）：**
1. Stacked imbalance 的具体检测逻辑（细节与品种相关，没有通用库）
2. 跨 Layer 的 setup 检测（VWAP 拒绝 + 订单流确认等复合判断）
3. 和 DayTrader 平台的集成层（journal / 报告 / obsidian 同步）

---

## 一、回测与执行引擎

### 🥇 Nautilus Trader — 强推

**为什么它是 Phase 2 的地基：**

- **Rust 核心 + Python API**：性能接近 C++，用起来像 Python
- **原生支持 tick 级 L2/L3 订单簿重放**：可以基于真实订单簿深度匹配订单，精确模拟 slippage
- **Deterministic / event-driven**：回测结果是可复现的（同一输入永远给同一输出）
- **研究到实盘同构**：同一个 Strategy 代码跑回测和实盘，不用翻译
- **Databento 官方 adapter**：一行代码加载 DBN 文件到 backtest engine
- **最近（2026 年 2 月）新增**：matching engine queue_position 追踪、L2/L3 book backtest 的 trade consumption seeding
- **官方 BookImbalanceActor 示例**：最近添加了订单簿 imbalance 的内建指标

**它不擅长的：**
- 没有内建的 footprint bar 聚合（需要我们在 Strategy 里自己聚合 ticks → footprint bars）
- 没有内建 Volume Profile（需要外部库或自研）
- 对新手学习曲线较陡（相比 backtrader）

**和现有工作的契合度：**
- Databento tick 数据 → 直接导入
- MGC 作为 futures instrument → 原生支持
- 实时接入 Rithmic → 需要写 custom adapter（中等工作量）

**仓库：** https://github.com/nautechsystems/nautilus_trader  
**文档：** https://nautilustrader.io/docs/latest/

### 🥈 QuantConnect LEAN — 备选

- 制度级别的成熟度，支持 70+ 品种 tick 数据
- C# 核心 + Python 绑定
- 有免费云端回测服务（QuantConnect.com）
- **劣势**：比 Nautilus 重、tick 级订单簿建模较弱、Python 和 C# 的混合令调试更复杂
- **适合**：如果你想用 cloud backtesting 节省本地机器资源

**仓库：** https://github.com/QuantConnect/Lean

### ❌ 不推荐（但值得提一下）

- **Backtrader** — 成熟但单线程、tick 级性能差，社区维护放缓
- **vectorbt / vectorbt pro** — 极快的向量化回测，但**不支持 tick level**，对订单流策略无效
- **zipline** — 原 Quantopian 框架，日线/分钟，不适合
- **bt** — 资产配置框架，完全不相关

---

## 二、订单流 / Footprint 可视化库

### 🥇 OrderflowChart — 用 plotly 画

- **仓库：** https://github.com/murtazayusuf/OrderflowChart
- 纯 Python，基于 Plotly
- 支持 imbalance 参数（可手动提供或自动计算）
- 输出交互式 HTML，能嵌入 Obsidian/报告
- **用途**：研究阶段可视化、报告里的 footprint 快照

### 🥈 stack-orderflow — 用 finplot/pyqtgraph 画

- **仓库：** https://github.com/tysonwu/stack-orderflow
- 桌面 GUI，实时刷新能力更强
- 作者说"填补了开源 orderflow 图表工具的空白"
- **用途**：如果未来想做实时盯盘桌面工具

### 🥉 srl-python-indicators — 综合工具包

- **仓库：** https://github.com/srlcarlg/srl-python-indicators
- 包含 Order Flow Ticks、Volume/TPO Profile、Weis & Wyckoff 系统
- 基于 mplfinance / plotly
- **用途**：一个仓库搞定多种指标可视化

**推荐组合：** 研究阶段用 **OrderflowChart**（易用、HTML 输出直接嵌报告），如果后期要做实时监控再考虑 **stack-orderflow**。

---

## 三、订单流特征 / 信息驱动 bars

### 🥇 mlfinlab (Hudson & Thames)

**直接实现了 Marcos Lopez de Prado 的《Advances in Financial Machine Learning》第 2 章：**

- **Imbalance bars**（我们要的就是这个）
- Tick bars、Volume bars、Dollar bars
- Run bars（基于买卖方向序列）
- 基于信息流的 bar 聚合（而不是时间）

**为什么这个很重要：**

你原系统用的是**固定 20 美元 range bars**。但 Lopez de Prado 的核心论点是：**时间和价格 range 都不是"信息均匀"的。一根 bar 在市场活跃时包含的信息远多于安静时的一根 bar**。Imbalance bars / volume bars 才是正确的采样方式。

用 imbalance bars 做回测，天然会让"安静时少采样、活跃时多采样"，信号质量更高。

- **仓库：** https://github.com/hudson-and-thames/mlfinlab
- **相关文件：** https://github.com/hudson-and-thames/mlfinlab/blob/master/mlfinlab/data_structures/imbalance_data_structures.py

### 🥈 CROBAT — Order Flow Imbalance (OFI) 实现

- **仓库：** https://github.com/orderbooktools/crobat
- 学术仓库，实现了 Cont-Kukanov-Stoikov 的 OFI 模型
- 针对 Coinbase 订单簿，但**数学逻辑可以直接移植到我们的 Databento 数据**
- Ed Silyantev 的 OFI BTC-USD 实证模型也在这里

### 🥉 LOB-feature-analysis

- **仓库：** https://github.com/nicolezattarin/LOB-feature-analysis
- 实现了 OFI 和 Multi-Level OFI (MLOFI) 作为价格预测器
- 基于 Cont-Kukanov-Stoikov 论文的 feature engineering

### 参考文章

- **Dean Markwick 博文**：https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html
- 实证演示 OFI 作为 HFT 信号，有完整代码

---

## 四、Volume Profile / Market Profile

### 🥇 py-market-profile

- **仓库：** https://github.com/bfolkens/py-market-profile
- Python 社区里**唯一一个靠谱的开源 Market Profile 实现**
- 支持 TPO 和 Volume Profile 双模式
- 能计算 POC / VAH / VAL / 70% Value Area

**限制：**
- 单品种大数据（2 年 1H）计算要 ~8 分钟 —— 需要优化或用于离线预计算

### 补充资源

- **QuantConnect Market Profile 实现讨论：** https://www.quantconnect.com/forum/discussion/7716/
- **Beinghorizontal Python Market Profile 文章：** https://medium.com/@beinghorizontal/market-profile-value-area-calculations-with-nifty-future-as-an-example-c6264526a536

**建议：** 用 `py-market-profile` 作为起点，如果性能不够再用 Numba/Cython 重写。

---

## 五、实时数据（Rithmic）

### 🥇 async_rithmic — 推荐

- **仓库：** https://github.com/rundef/async_rithmic
- **PyPI：** https://pypi.org/project/async-rithmic/
- 活跃维护（PyPI 上有 1.2.4 版本）
- **Async-first 架构** — 和 DayTrader 平台现有 async 代码兼容
- 原生支持 Rithmic 的 Protocol Buffer API
- 支持 **tick market data（live + historical）+ order routing**
- 子毫秒级延迟，直连 CME / CBOT / NYMEX / COMEX

**适用场景：**
- 从 MotiveWave 外独立接入 Rithmic（不依赖 MotiveWave）
- Python 策略直连实时数据
- 通过 order routing 自动下单（未来阶段）

### 🥈 pyrithmic — 备选

- **仓库：** https://github.com/jacksonwoody/pyrithmic
- 同样实现了 Rithmic Protocol Buffer API
- 同步 API，社区活跃度略低于 async_rithmic

### 对比表

| 特性 | async_rithmic | pyrithmic |
|------|---------------|-----------|
| 异步 | ✅ | ❌ |
| 维护活跃度 | 高 | 中 |
| Tick 历史数据 | ✅ | ✅ |
| Order routing | ✅ | ✅ |
| PyPI 发布 | ✅ | ❌（源码）|

**推荐 async_rithmic**，它和我们现有的 `async/await` 架构一致。

---

## 六、Databento 集成

你已经在用 Databento，但可以更充分地利用它：

- **官方 Databento 示例：** https://databento.com/docs/examples
- **HFT 信号（含 imbalance 检测）：** https://medium.databento.com/building-high-frequency-trading-signals-in-python-with-databento-and-sklearn-2d7f66e893ae
- **Databento Nautilus Adapter：** https://nautilustrader.io/docs/latest/integrations/databento/

**重要：** Databento 有**官方的 Auction Imbalance 和 Order Imbalance 数据 schema**。你现有的 trades-only 数据是一个子集。如果预算允许，订阅 **MBP-10 或 MBO schema** 能获取真正的订单簿深度，那才是 stacked imbalance 该有的数据源。

---

## 七、理论基础 / 策略参考

### 📕 必读书（按优先级）

1. **Jim Dalton《Mind Over Markets》（1993，2013 更新版）**
   - Auction Market Theory 的原典
   - Market Profile / Value Area / POC 的定义来源
   - **这是我上次批判里提到的 "Context-first" 框架的理论基础**
   - PDF（作者免费版）：http://www.r-5.org/files/books/trading/charts/market-profile/James_Dalton-Markets_in_Profile-EN.pdf

2. **Jim Dalton《Markets in Profile》（2007）**
   - 进阶版，偏实操
   - 买：https://www.amazon.com/Markets-Profile-Profiting-Auction-Process/dp/0470039094

3. **Marcos Lopez de Prado《Advances in Financial Machine Learning》（2018）**
   - Imbalance bars / meta-labeling / walk-forward 的标准化方法
   - 为什么 "1-bar WR" 是错的指标，应该怎么做真正的验证
   - mlfinlab 就是这本书的配套代码

### 📑 必读论文

1. **Cont, Kukanov, Stoikov (2014) "The Price Impact of Order Book Events"**
   - arxiv：https://arxiv.org/abs/1011.6402
   - 建立了 Order Flow Imbalance → 价格变动的线性模型
   - 你原研究报告里引用的就是这篇
   - **是目前唯一有严格实证支持的 order flow → price 关系**

### 🎯 在线资源 / Playbook

1. **Tradingriot — Auction Market Theory 概览**
   - https://tradingriot.com/auction-market-theory/
   - 免费，实操导向，和 Dalton 的框架一致

2. **Topstep — Intro to AMT**
   - https://www.topstep.com/blog/intro-to-auction-market-theory-and-market-profile/
   - 入门级，适合快速建立心智模型

3. **Trader Dale — Stacked Imbalance Playbook**
   - https://www.trader-dale.com/order-flow-day-trading-strategy-stacked-imbalances/
   - 明确描述了 stacked imbalance 的**使用规则**（不是仅检测）
   - 关键：他的逻辑就是 **level-first**，不是 pattern-first

4. **ATAS — Auction Market Theory 教程**
   - https://atas.net/market-theory/the-auction-market-theory/
   - ATAS 是专业 order flow 平台，他们的教程质量高

### 🏢 付费但有价值的学习资源

- **Jim Dalton Trading Courses** — https://jimdaltontrading.com/courses/（视频课程，约 $300-500）
- **Axia Futures / SMB Capital** — YouTube 有大量 ES order flow 视频（免费）

---

## 八、开源策略库（参考现成策略）

### Awesome Quant / Best-of Lists

- **merovinh/best-of-algorithmic-trading** — https://github.com/merovinh/best-of-algorithmic-trading
- 定期更新的开源量化工具排名，覆盖回测、执行、数据、指标

### QuantConnect Algo Library

- **QuantConnect Community Algorithms** — https://www.quantconnect.com/forum/discussions
- 大量 LEAN 社区贡献的策略代码，包括 Market Profile 策略实现

### 针对我们场景的具体参考

- **Trader Dale 的 stacked imbalance 规则**（免费文章）
- **Axia Futures YouTube 频道**的 ES order flow 教程
- **Order Flow Trading (ATAS blog)** — https://atas.net/blog/

---

## 九、性能分析 / 回测评估

### 标配三件套

1. **QuantStats** — https://github.com/ranaroussi/quantstats
   - 一行代码生成完整 tearsheet（Sharpe、Sortino、回撤、月度表现）
   - 输出 HTML 报告
   
2. **pyfolio** — https://github.com/quantopian/pyfolio
   - Quantopian 留下的标准库
   - 因子分析、归因分析

3. **empyrical** — https://github.com/quantopian/empyrical
   - 纯粹的风险/绩效指标计算（Sharpe、Calmar、max DD 等）
   - QuantStats 和 pyfolio 都依赖它

**推荐默认用 QuantStats**（最易用），复杂分析再上 pyfolio。

---

## 十、我还没搜到（但需要自己写）的部分

1. **"Pattern + Context" 复合检测器** — 没有开源库做 "VWAP 拒绝 + 订单流失衡 + HTF 趋势同向" 的组合判断，这个必须自己写
2. **Setup-level trade journal 集成** — 我们的 journal 要记录 setup type，需要自己定义 schema 和同步逻辑
3. **Obsidian 模板与 DayTrader 平台的深度集成** — 没有现成的工具能直接用
4. **Human-in-the-loop 手动标注工具** — 我上次批判里提到的 "手动标注 setup" 工具，需要自己写（Jupyter + plotly + HTML form 的组合）
5. **MGC 品种特有的数据质量过滤** — 比如 "识别 GC↔MGC 跨品种套利造成的 tick" —— 这是 novel 的研究方向，没有现成工具

---

## 十一、建议的 Phase 2 技术栈（具体清单）

```toml
# 新增到 pyproject.toml 的依赖

[project.dependencies]
# 现有
click = ">=8.1"
pydantic = ">=2.0"
pandas = ">=2.2"
numpy = ">=1.26"
matplotlib = ">=3.8"
# ...

# Phase 2 新增
nautilus_trader = ">=1.208"   # 回测/执行引擎
databento = ">=0.40"          # 历史 tick 数据
async_rithmic = ">=1.2"       # 实时 Rithmic（需要时）
mlfinlab = ">=1.6"            # Imbalance bars + 信息驱动 bars
py-market-profile = ">=0.4"   # Volume/Market Profile
quantstats = ">=0.0.62"       # 性能 tearsheet
plotly = ">=5.18"             # 已有（orderflow 可视化）
```

**外部脚本层工具（可选）：**
- OrderflowChart（pip install，或 git clone）
- srl-python-indicators（git clone 到 vendor/）

---

## 十二、建议的研究路径

基于调研结果，Phase 2 的研究顺序**不变**（和我上次的提议一致），但**不从零实现**：

### Week 1 — 熟悉工具栈（非编码为主）

- 读 Nautilus Trader 的官方 backtesting tutorial（1 天）
- 看 mlfinlab 的 imbalance bars 示例代码（1 天）
- 试跑 py-market-profile 在 MGC 数据上的输出（1 天）
- 读 Dalton《Markets in Profile》前 5 章 + Cont-Kukanov-Stoikov 论文（2 天）

### Week 2 — 数据管道（站在 Nautilus + Databento 肩膀上）

- 用 Nautilus 的 Databento adapter 加载现有 MGC tick 数据
- 聚合 footprint bars（range bars / volume bars 两种试）
- 用 mlfinlab 生成 imbalance bars 作对比
- 用 py-market-profile 生成 daily volume profile（POC/VAH/VAL）

### Week 3-4 — 第一个 setup 的人机协同研究

- 选一个 setup 开始（我建议 **"VAL 吸收反弹"** 或 **"IB Low Failure"**，因为它们都是经典的 Dalton 框架 setup）
- 用 OrderflowChart 画出可视化
- **手动标注** 2-3 个月数据里出现该 setup 的所有实例（目标 50+ 样本）
- 统计手动标注样本的表现（不靠代码自动检测，先看真实分布）

### Week 5-6 — 自动检测 + 回测

- 把手动标注规则编码成 Nautilus Strategy
- 用 Nautilus backtest engine 做 tick-level 精确回测（带 slippage）
- 对比自动检测 vs 手动标注的重合度（目标 >80%）
- 用 QuantStats 生成完整 tearsheet

### Week 7-8 — 扩展 + 验证

- 如果第一个 setup 验证 OK，扩展到第二个、第三个
- 用正确的 IS/OOS 分割验证
- 加入 prop firm 风控规则（daily loss limit, max positions）

---

## 附录 A：被淘汰的替代方案（供参考）

| 工具 | 为什么不选 |
|------|-----------|
| **Backtrader** | 慢、单线程、tick-level 能力弱，社区维护放缓 |
| **vectorbt / VBT Pro** | 不支持 tick level，订单流策略完全不适用 |
| **Zipline** | 日线/分钟为主，futures 支持弱 |
| **FreqTrade** | 加密货币专用 |
| **Jesse** | 加密货币专用 |
| **PyAlgoTrade** | 维护放缓，不支持 L2 订单簿 |
| **Custom ClickHouse + Pandas** | 可以做，但工作量大 15 倍，没必要 |

## 附录 B：关键 GitHub 仓库速查

| 分类 | 仓库 | 用途 |
|------|------|------|
| Backtest | [nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 主引擎 |
| Backtest | [LEAN](https://github.com/QuantConnect/Lean) | 备选引擎 |
| Footprint | [OrderflowChart](https://github.com/murtazayusuf/OrderflowChart) | Plotly 可视化 |
| Footprint | [stack-orderflow](https://github.com/tysonwu/stack-orderflow) | Qt GUI |
| Footprint | [srl-python-indicators](https://github.com/srlcarlg/srl-python-indicators) | 综合指标 |
| ML Finance | [mlfinlab](https://github.com/hudson-and-thames/mlfinlab) | Imbalance bars |
| OFI | [crobat](https://github.com/orderbooktools/crobat) | OFI 实现 |
| OFI | [LOB-feature-analysis](https://github.com/nicolezattarin/LOB-feature-analysis) | 特征工程 |
| Market Profile | [py-market-profile](https://github.com/bfolkens/py-market-profile) | VP/POC/VA |
| Rithmic | [async_rithmic](https://github.com/rundef/async_rithmic) | 实时数据 |
| Rithmic | [pyrithmic](https://github.com/jacksonwoody/pyrithmic) | 实时数据备选 |
| Performance | [quantstats](https://github.com/ranaroussi/quantstats) | Tearsheet |
| Awesome List | [best-of-algorithmic-trading](https://github.com/merovinh/best-of-algorithmic-trading) | 工具大全 |

## 附录 C：一句话 FAQ

- **Q: Nautilus Trader 学习曲线陡吗？** A: 是，但有详细文档和示例。第一周可能吃力，第二周就熟了。
- **Q: 能不能用现成的 footprint 库画图就好，不用 Nautilus？** A: 可以，但你需要自己写回测框架，工作量大得多。建议还是 Nautilus。
- **Q: mlfinlab 稳定吗？** A: Hudson & Thames 是个商业公司但有开源版，社区活跃。可以放心用。
- **Q: 需要付费数据吗？** A: 短期 Databento 够用。长期如果要做实盘需要 Rithmic 订阅（$20/月起）。
- **Q: Nautilus 能接 MotiveWave 吗？** A: 不能直接接。但通过 Rithmic，Nautilus 可以**替代** MotiveWave 的实时数据角色。
- **Q: 这套栈可以规模化到多品种吗？** A: 完全可以。Nautilus 支持多品种/多场所并发。MGC 验证通过后可以扩到 GC、ES、NQ。

---

## Sources（调研参考链接）

### 回测引擎
- [Nautilus Trader GitHub](https://github.com/nautechsystems/nautilus_trader)
- [Nautilus Trader Docs - Backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/)
- [Nautilus Trader - Databento Integration](https://nautilustrader.io/docs/latest/integrations/databento/)
- [QuantConnect LEAN GitHub](https://github.com/QuantConnect/Lean)
- [Nautilus vs LEAN comparison](https://odemeridian.com/blog/institutional-grade-backtesting)

### Footprint 可视化
- [OrderflowChart](https://github.com/murtazayusuf/OrderflowChart)
- [stack-orderflow](https://github.com/tysonwu/stack-orderflow)
- [srl-python-indicators](https://github.com/srlcarlg/srl-python-indicators)
- [flowsurface (Rust)](https://github.com/flowsurface-rs/flowsurface)

### 订单流特征库
- [mlfinlab](https://github.com/hudson-and-thames/mlfinlab)
- [mlfinlab imbalance_data_structures.py](https://github.com/hudson-and-thames/mlfinlab/blob/master/mlfinlab/data_structures/imbalance_data_structures.py)
- [Hudson & Thames](https://hudsonthames.org/)
- [crobat OFI implementation](https://github.com/orderbooktools/crobat)
- [LOB-feature-analysis](https://github.com/nicolezattarin/LOB-feature-analysis)
- [Dean Markwick - Order Flow Imbalance](https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html)

### Volume/Market Profile
- [py-market-profile](https://github.com/bfolkens/py-market-profile)
- [QuantConnect Market Profile discussion](https://www.quantconnect.com/forum/discussion/7716/)
- [Beinghorizontal Market Profile Python](https://medium.com/@beinghorizontal/market-profile-value-area-calculations-with-nifty-future-as-an-example-c6264526a536)

### Rithmic 实时数据
- [async_rithmic](https://github.com/rundef/async_rithmic)
- [async_rithmic docs](https://async-rithmic.readthedocs.io/en/latest/realtime_data.html)
- [async_rithmic PyPI](https://pypi.org/project/async-rithmic/1.2.4/)
- [pyrithmic](https://github.com/jacksonwoody/pyrithmic)
- [Rithmic APIs page](https://www.rithmic.com/apis)

### Databento
- [Databento API examples](https://databento.com/docs/examples)
- [Databento Tick Data](https://databento.com/tick-data)
- [Building HFT signals with Databento + sklearn](https://medium.databento.com/building-high-frequency-trading-signals-in-python-with-databento-and-sklearn-2d7f66e893ae)
- [Databento Live Tick TRIN example](https://databento.com/docs/examples/basics-live/live-tick-trin)

### 理论资源
- [Markets in Profile PDF (Dalton)](http://www.r-5.org/files/books/trading/charts/market-profile/James_Dalton-Markets_in_Profile-EN.pdf)
- [Markets in Profile (Amazon)](https://www.amazon.com/Markets-Profile-Profiting-Auction-Process/dp/0470039094)
- [Mind Over Markets (Amazon)](https://www.amazon.com/Mind-Over-Markets-Generated-Information/dp/1118531736)
- [Jim Dalton Trading Courses](https://jimdaltontrading.com/courses/)
- [Cont-Kukanov-Stoikov (2014) - Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
- [Topstep - Intro to AMT](https://www.topstep.com/blog/intro-to-auction-market-theory-and-market-profile/)
- [Tradingriot - AMT](https://tradingriot.com/auction-market-theory/)
- [Trader Dale - Stacked Imbalance Strategy](https://www.trader-dale.com/order-flow-day-trading-strategy-stacked-imbalances/)
- [ATAS - AMT Theory](https://atas.net/market-theory/the-auction-market-theory/)

### 开源策略 / Awesome Lists
- [best-of-algorithmic-trading](https://github.com/merovinh/best-of-algorithmic-trading)
- [trading-strategies GitHub topic](https://github.com/topics/trading-strategies?l=python)
- [OpenAlgo](https://github.com/marketcalls/openalgo)

### 性能分析
- [QuantStats](https://github.com/ranaroussi/quantstats)
- [pyfolio](https://github.com/quantopian/pyfolio)
- [empyrical](https://github.com/quantopian/empyrical)
