# Jigsaw / Peter Davies 订单流体系重建笔记

> 基于公开材料重建，整理日期 2026-09-15。
> 状态：**研究材料，非交易规则。Contract 30 笔期间禁止将本文任何内容混入实盘决策（§8 隔离条款）。**

## 0. 材料基础与可信度

| 来源 | 性质 | 备注 |
|---|---|---|
| 免费 11 课 tape reading 课程（2011） | 一手文字 | L9/L10 纯视频无文字 |
| 四份原始方法论 PDF（2013-14，61 页，经 Wayback 取回，官网已下架） | 一手原典 | `sources/*.pdf`；ConfirmingLevels 最可操作 |
| 100 Trading Rules 博客 #1-#23（2025-26） | 一手文字 | #16/#21 署名 Gonzalo Rivero 非 Davies |
| 14 支 YouTube 视频 ASR 字幕（2012-2025） | 一手转写 | `sources/transcripts/`；自动字幕有错词，正式引用须回听；**2025 年 drill 系列为另一位讲师，非 Davies 本人** |

**已知内部矛盾/时效**：① L3 允许 SIM 学习 vs Pt2 明写 "No SIM trading"（未解释）；② Davies 2026 年亲口降级自己 2013 年的 delta 理论（"since COVID, this is less reliable"）；③ 教学核心素材录于 2015 前后低波动环境（口碑调研中两位独立用户的同一指控）；④ 2025 新 drill 视频比 Davies 本人更强调 absorption 入场——而 Davies 反复警告不要单靠 absorption。

## 1. 体系总览

三句话版本：

1. **"Cake = Trade Location，Icing = Order Flow。"** 订单流是确认层不是体系本身；先有位置（隔夜高低/前高低/profile step/关键位），订单流只回答"到了位置之后这笔单成不成立"。
2. **"A change in order flow comes BEFORE a change in price."** 价值主张不是提高胜率，而是**更早知道自己错了**→降低单笔风险。
3. **Edge 的定义**："Seeing something occur that moves the market in time to take advantage of it."——事件（event）驱动，图表形态只是事件的一种。

**INTENT vs ACTUAL 二分**（正式定义，Pt2）：INTENT = 挂单（Market Depth、Depth & Sales，唯一能提前看到的意图）；ACTUAL = 成交（Tape、Footprint、Cumulative Delta）。**footprint 的 stacked imbalance 属 ACTUAL 半边**；三层视野："delta 是万英尺，footprint 是千英尺，DOM 是十英尺。"

**Anomaly 框架**（信号的最简定义）：只有两类异常值得注意——**速度异常**（momentum）与**成交量异常**（单价位一次性吃掉远超常态的量）。异常给的不是胜率是**盈亏比**："it doesn't give me a 90% probability trade, but a really good risk reward trade."

**流动性物理学**：市价单必须吃掉流动性价格才能动；挂单可以撤（假），成交不能（真）——"378 were real"。单向行情在身后留下流动性真空，回撤因此必然。

## 2. 核心概念定义（原话依据）

| 概念 | 定义与量化门槛 |
|---|---|
| **Absorption** | 一侧挂单顶住持续攻击、**一次性**（"this time round"，非全天累计）成交 ≥ 常态 **3 倍**（ES 常态 200-500/档时找 700-1000+）；delta 涨而价格不涨。薄市场跨多档完成。两个维度：**pace + quantity**。 |
| **Sellers/Buyers Fade** | 多次回到同一档但几乎不成交（"3-4 分钟对手就该闻到血腥味"）；offer 越小越显著。 |
| **The Roll** | 对手方"凭空出现"开始打——三要素中最难及时识别，最不激进。三者不互斥。 |
| **Iceberg** | 随成交**over time**刷新的限价单（瞬时刷新不算）。"冰山自己挡不住狂奔的市场，它是吸收的标志之一"；**对侧有 spoof 时更显著**；震荡市里到处是冰山（无意义），趋势里的连串冰山**应无视**。 |
| **Spoof/Flip** | "被操纵恰恰是 DOM 有用的原因"；ES 级厚市约 75% 挂单是 spoof。**Flip** = 只在**死盘区间**发生的组合戏法：spoof 推价出区间套住突破者 + 对侧 iceberg 真吸货。不建议直接交易，但做反向单时必须警惕。Flash spoof（亚秒级）是算法钓鱼，无视。 |
| **Trapped traders** | "每笔成交都有买卖双方，absorption 的全部意义是总有一边被套；他们的离场单给反向行情加燃料。"**大单被困比大单本身更有用**：连续大单推不动市场（boom-boom-no move）→ 停顿 → 反向。 |
| **Stop run** | 级联式止损触发（多为短线客被扫，含移动止损，"数止损单次数很蠢"）。识别：明显位置（前波段低点，**区间中部不会有**）+ 凭空的极快行情 + delta 剧烈单边。**核心价值在回访**："回到车祸现场"——被扫的人不会原价再进场，形成**未来失衡**，该区首次回测通常守住。趋势中破小区间的 stop run = 延续，非反转。 |
| **高低参与区** | 趋势结构 = 推进段（失衡 1.5-3×）+ 堆量停顿区交替；**高量区首次回测会守住；首次失守 = 反转警报的唯一定义**（"买家第一次被止损"）。但先排除 range expansion（假反转）。低参与区被低估：没人愿意成交的价位**更难被操纵**。 |
| **Liquidity vacuum** | 单向行情后 2-3 tick 的"吸回"；depth 消失时可顺势打进真空，或等吸回停住后顺大方向进。 |
| **Cumulative delta** | 只说明"用的是市价还是限价单"。否定 divergence 玩法（"one-rule system"）。他**唯一**用法：好行情回撤时 **delta 走平 = 无参与度 → 延续概率大**；真反转伴随 delta 大幅换向。⚠️ 2026 年本人降级："since COVID, less reliable"。 |
| **高低点必然失衡** | "日高必有 offers 堆叠、日低必有 bids 堆叠"——所以高低点的失衡本身不是信息。 |
| **关键位挂单的正确读法**（反直觉核心） | 支撑下方/阻力上方出现**大于常态**的挂单 ≠ 会守住，而 = **别人也在看这个位置 = 你的位置分析被验证**。反之，"接近你的位置时挂单完全正常、无异常 → 不该期待任何反应，该反思这个位置怎么画出来的"。 |

## 3. 他的完整交易流程（Rule #11 自述日程 + DOM 执行技术）

```
盘前：查新闻定聚焦市场 → 画位置（隔夜高低/长期转折位）——位置本身不交易
  ↓
事件：离开位置的一根【相对当日明显更大、更快、更高量】的摆动 → 只用来设方向 bias
  ↓（"I would never personally buy support or sell resistance"）
等待：弱回撤（小幅、低量、低参与）
  ↓
入场：回撤末端顺 bias 进（"then I become a momentum trader"），订单流站在自己一边
  ↓
执行技术（Level Break）：想买时等 offer 缩减/停止刷新才打进去——"这一条就是省钱机器"
  ↓
入场后（前几分钟像鹰一样盯）：
  · DOM 重置 current trades → 区分"价格逆行"与"订单流逆行"
  · 参与度判据：做多后买方市价单应 ≥ 2× 卖方；只有几百手对几百手 = 无意义
  · "Did the market earn it?"——没兑现入场假设就不给它时间
  ↓
止损：随波动率放大、同时缩仓位；触发离场也用 Level Break（等档位破，不恐慌市价）
  "You should be closing out before you get to your stop loss"
  ↓
目标：分批止盈；第一批成交 → 保本；第一批都打不到 → 让它保本出（"该有 pop 没 pop 就走"）
  跑得快 → 目标外移。ATR 陷阱：RTH 开盘后 30 分钟内 ATR 不可用
```

方向过滤：长周期订单流偏多时忽略空单信号（他在 ES 上用 cumulative delta 做这个，但见 §2 降级注）。交易时段：开盘前+开盘后至动能衰竭（10-11 点），"once it fades, I'm out"。

## 4. 具名可操作规则

| 规则 | 背景/位置 | 订单流确认 | 入场 | 止损/管理 |
|---|---|---|---|---|
| **Absorption 反转**（ConfirmingLevels 最完整） | **必须**在预期转向区（"Fading all absorption will fail"） | 3× 常态量一次性成交；tape 上激进卖压要先烧尽；打穿 2-4 tick 时量应递减 | 激进=见量即进；保守三分支：回穿时进 / 直接拉起等回测 / 高 4-6 tick 出新量簇则在新簇等回测 | 大买家须被困并快速下砸确认；卖方持续打不动 → 走 |
| **Sellers Fade** | 预期转向低点区 | 多次触档极小成交；"只打一次低量不算" | 不抢 low+1 tick，等确认；上方大卖单是燃料不是威胁 | 失败模式：不打低点却在上方堆量 = 转区间 |
| **Buyers Jump In** | 低点快速拉离 6-12 tick | 买方 1.5-2× 卖方、有大单、显不耐烦 | **绝不追**；等 second chance 回到低点区再进 | 回撤中不得出现大卖单/快节奏（除非被套） |
| **Backstop（冰山最实用场景）** | 上涨中的 volume cluster，之后**几乎没回调** | 回到 cluster 顶部 | 在 backstop 进，风险极明确 | "不是最高胜率，但盈亏比定义极好" |
| **Stop-run 回访** | 被扫区域的首次回测 | 回测时卖方消失 | 顺原方向进 | 依赖"车祸现场"未来失衡 |
| **Step 回调（Discretionary Rules 片的完整示例）** | 日内 profile 的合格 step（4-5 分钟、2-5 万手；两小时 30 万手的不算） | 回落至该区 + 参与度在自己一边 | 做多 | 5 个裁量点：今天该不该用/节点合格否/给多少余地/入场后反应（只弹 3-4 tick 反复回来=无参与，走）/相关市场同向否 |

**通用禁令级技术**：不在大挂单前面排队抢跑（"guaranteed losing system"——人家挂单就是为了让你排他前面）；唯一例外是多因素叠加且**别人也在往它前面加单**。

## 5. "不要做"清单（合并全材料）

1. **一条规则的系统永远不成立**（他见过最普遍的失败）："只做吸收"一百万年也不行
2. Fade 所有吸收必败；趋势中的连串冰山应无视；区间中部的量无意义
3. 不追动能末端；不买支撑/卖阻力（他的个人绝对禁令）
4. 不在人人放止损的地方放止损；被扫"don't take it personally"
5. 订单流与位置矛盾 → 不做（"stay out"）
6. 开盘 DOM 前 5-10 分钟只看不做（tune-in）
7. 不为半好机会下单——占着仓位会错过当日真正的单
8. 波动率不匹配时 setup 必须停用（"A setup is not a setup unless it has rules for adjusting for volatility"）
9. 不过度管理持仓；不找完美离场法（"There isn't one"）
10. 不堆指标（"747 驾驶舱"式 footprint；单品种超过一块屏 = 东西太多）
11. 不每周换方法；**"starting over again is the main reason people fail"——已有能用的东西时，订单流应融入而非推倒**
12. 盘感唯一被允许的用途：**让你不进场**，绝不是让你进场
13. "手痒时你会把任何东西看成 setup"——过度想交易是最大的过拟合

## 6. 训练体系（drills，全部 SIM-only）

| Drill | 操作 | 训练目标 |
|---|---|---|
| **Cut & Reverse / Always-In**（最重要） | 1 手建仓后数量设 2，此后每次点击都是反手，永不空仓；60-90 分钟/场，1-2 场/日；**禁止追踪 P&L**（本 drill 设计成无法盈利），只评"这次反手位置是否比上次好"；录屏复盘 | 暴露直觉反向（"多数人恰在跳水前由空翻多，且反复如此"）；强制实时读 flow |
| **One Tick** | 只抓 2 tick 就走，不许拿更多 | 纯入场时机 |
| **Lose Drill** | 故意亏损但须有结构（逻辑反着做仍要挑位置）；10/10 起手，再换荒谬参数（15 损/2 目标）对照 | "如果故意亏钱却开始赚钱，说明了很多问题"；反推策略需要的止损/目标比例 |
| **Momentum Drill** | 在位置挂限价单，动能反向强推时**撤单**（判据是速度不是价位）；被成交且判定被碾 → 立刻平 | "别站在火车前面"；入场后要求买家跟进 |
| **Did the Market Earn It** | 每笔入场后明确"我需要看到什么"→ 看到才移保本/推止损；到反应区没出现预期行为 → 走 | 市场没挣到你继续持有的权利就不给时间 |
| **Follow the Depth** | 用 depth 直方图做"一条规则系统"（spike 方向进），亲手证伪"大单挡价"神话 | "市场并不总是躲开大挂单"——自己亏出来的认知 |
| 观察周（Rule #10） | 选一个事件，**只看不做**跑 10 次，记录假想入场与捕获幅度 | "Observation has no fail" |

时间处方（Rule #6）：理论 25-50 分钟/次、每天 ≤3 小时；技能 45-90 分钟/次、每周 15-25 小时（40 小时后陡降）；睡眠固化记忆。自营盘背景：12 周实习、禁用图表、70-100 笔/日、之后 1-2 手上实盘，"很多人永远上不了实盘"。

**风险升级规律**（对 sim→micro→mini 路径）："每次提升风险等级，表现必然先下降——不是永久的，也不必焦虑。"要求为每级**预先写死**晋级/降级规则（20 天达标才上、实盘回撤到 X 退回 sim）。Micro 的正确用途：练多合约 scaling，"1 手全进全出其实是最难的"。

## 7. 体系弱点与适配性评估

1. **止损无数值体系**：原则丰富（结构位、随波动放大、level-break 离场、"到止损前就该走了"）但从不给公式——他的哲学本就反对（Rule #12"完美离场法不存在"、Rule #13 R:R 是数字幻觉、Rule #20 职业者不看 R:R）。**这是裁量体系，且以此为荣。**
2. **零业绩佐证**：所有规则无分母；"Signal Scope 无法回测"是他的公开立场——即他主动放弃了可证伪性。与 Claim-4 审计对 z说 的批评同构，只是 Davies 诚实地承认了这一点。
3. **素材时效**：核心内容 2011-2015 年录制（低波动 ES）；他自己的 Rule #15/#17 恰好论证了"波动率变了 setup 就要变"——用他的标准审他的旧素材，结论是需重校准。
4. **付费墙后的缺口**：七个具名 Applied Strategies（Volume stop hit and run / Fast flips / Front-run absorption reversal / Delta punch / Order book sweep / Momentum exhaustion reversal / Data pullback continuation）只有名称公开；Kill it or Keep it 专题（止损前识别失败交易）只有预告。

## 8. 与 Contract 体系的映射与隔离

| Davies 概念 | Contract 概念 | 关系 |
|---|---|---|
| ACTUAL / footprint stacked imbalance（他家定义：3 连续、3:1、对角） | MotiveWave L3 5:1 + 100vol + 3-stack | **同一机制同一定义域**，他的比率阈值更松 |
| Anomaly（位置处的成交量异常 → 盈亏比而非胜率） | stacked imbalance reversal **at level** | 完全同构——你的 Contract 就是他的 anomaly 框架的机械化 |
| INTENT（DOM 挂单/冰山/spoof） | Contract 未使用 | 他会说你缺的一半；**30 笔期间只可观察记录，不得作为过滤器** |
| "入场后 2× 参与度 / did it earn it" | Contract 无入场后裁量 | **禁止引入**——Contract 的止损目标是死的，这正是它存在的意义 |
| "Mechanical trading is a myth" / 反 R:R | Contract 的根基 | **定向毒性内容，30 笔前隔离**（见 Jigsaw 调研记忆条目） |

**隔离条款**：本文件在 Contract 30 笔期间仅作背景知识；drills 若要练，全部 SIM、盘后、且不与 Contract 时段混用；任何 DOM/INTENT 观察写 journal 的 notes 字段，不进入进出场决策。30 笔复盘时再评估两件事：① INTENT 侧信息（吸收/冰山确认）是否值得作为下一版合同的候选过滤器（须过 V11 五关）；② 他的入场后participation 判据可否机械化为提前离场规则的候选。

**一个值得记住的对照**：Davies 的"一条规则的系统永远不成立"与你 Contract 的单一 setup 并不矛盾——Contract 从来不是"完整交易系统"，它是 30 笔的**纪律实验**。他自己的话反而支持这个设计："即使最好的机械系统也需要知道何时开关"——你的开关规则（时段、日限、-2R）恰好都写在合同里。
