# Phase 5: EOD Daily Report — Plan Retrospective + Tomorrow Preliminary Plan

**Date:** 2026-05-04
**Status:** Implemented (HEAD commit 49693d2)
**Owner:** Tyler San
**Parent spec:** [`2026-04-25-reports-system-design.md`](./2026-04-25-reports-system-design.md) §2.2 / §2.3 / §6
**Sibling spec (sentiment):** [`2026-05-02-reports-phase4.5-sentiment-design.md`](./2026-05-02-reports-phase4.5-sentiment-design.md)

---

## 1. Goal

Implement the **EOD (End-Of-Day) report** as the second cadence in the new reports system, fired automatically at **14:00 PT (Mon-Fri)** by macOS launchd. EOD delivers three jobs:

1. **Today's market recap** — multi-TF (W/D/4H) update post-RTH-close, F. 期货结构 with today's basis/term/VP, D. 情绪面 8h-window sentiment, today's narrative.
2. **Today's trade audit** — journal-DB-sourced trade ledger + §6 ban / §9 screenshot compliance, lock-in counter update.
3. **Plan-vs-PA closed loop** — retrospective evaluation of today's premarket plan against actual price action (per-level trigger + simulated outcome + execution-gap analysis), plus tomorrow's preliminary plan as a data-driven first draft.

The third job is the **structural innovation** — it turns every trading day (including 0-trade days) into a data point for plan quality, building the substrate for future statistical iteration on setup parameters and key-level selection rules.

## 2. Why This, Why Now

The user starts the 30-trade lock-in this week. Without EOD:

- Every "no trade today" day disappears with no audit trail. Was it discipline (no setup matched) or absence (no screen time)? You don't know.
- Every traded day's after-action review depends on memory + manual journaling. The §9 audit requirement is partial.
- Plan quality has no data feedback loop. After 30 trades you'll know your execution PnL but not whether the plan ITSELF was sound.
- Tomorrow's premarket has no structured handoff from today's data — every morning starts from a cold state.

EOD with retrospective closes all four gaps in a single cadence.

## 3. Non-Goals (Explicitly Out of Scope)

- **Multi-day aggregate stats / dashboards** — defer to Phase 5.5 after lock-in completes; v1 stores per-day rows in a new `plan_retrospective_daily` table but doesn't render aggregates.
- **AI-driven plan iteration suggestions** — the v2 vision is "AI suggests the plan rule should change because data shows X"; v1 only generates the data, not suggestions.
- **Footprint imbalance verification post-hoc** — the simulator assumes any plan-listed level "would have triggered the setup" if price touched it. Real verification requires Level 3 / 5:1 / volume-100 footprint data from MotiveWave; v1 explicitly notes this assumption.
- **Reverse-causation analysis** — "your 7 worst days were all 4H POC fades" — needs N≥30 data; v2.
- **A section** — spec §6 explicitly forbids; A is premarket-only, A-1 is permanently disabled.
- **Direct "tomorrow plan" as a final plan source** — premarket 06:00 PT remains the canonical plan; EOD's tomorrow section is preliminary, will be refined overnight.
- **Other 4 cadences** (intraday-4h-1, intraday-4h-2, night, asia) — Phase 5.5+ work.

## 4. Background

### 4.1 What exists today

- **Premarket cadence** (06:00 PT Mon-Fri) — fully implemented through Phase 4.5 + futures-positioning fix. Generates `Daily/{YYYY-MM-DD}-premarket.md` with W/D/4H multi-TF, F. 期货结构 (basis/term/VP), D. 情绪面 (Sentiment via WebSearch), C. 计划复核 (per-tradable plan blocks), B. 市场叙事, A. 建议, 数据快照.
- **Weekly cadence** (Sun 14:00 PT) — bridge implementation via OLD `daytrader weekly run --ai` (post-yesterday's data-quality fix).
- **Journal subsystem** — Pydantic v2 models (`JournalTrade`, `Checklist`, `ChecklistItems`, `TradeMode`, `TradeSide`), CLI (`pre-trade`, `post-trade`, `audit`, `circuit`, `resume-gate`, `sanity`), DB at `data/db/journal.db`. Restricted to MES/MNQ/MGC. Currently empty (lock-in starts this week).
- **Reusable modules**:
  - `IBClient` (10 methods including `get_bars`, `get_daily_close`, `get_contract_chain`, `get_active_front_expiry`)
  - `FuturesSection` + `UnderlyingPriceFetcher` + `TermPricesFetcher` (Phase 4 + yesterday's fix)
  - `SentimentSection` / `SentimentCollector` / parser (Phase 4.5)
  - `AIAnalyst` (claude -p, 300s timeout)
  - `PromptBuilder.build_premarket(...)` (with sentiment_md hook)
  - `OutputValidator` (REQUIRED_SECTIONS schema)
  - `ObsidianWriter`, `ChartRenderer`, `PDFRenderer`, `TelegramPusher`
  - `Orchestrator.run_premarket(...)` (template for EOD's `run_eod`)
  - launchd plist + wrapper template (Phase 7 v1)
  - `preflight_check.py` (with API handshake check landed today)

### 4.2 What changed during brainstorm

| Initial framing | Resolution |
|---|---|
| "EOD is just an audit report" (my first take) | Wrong. EOD per spec §6 is full TA + audit + tomorrow prep. Cannot strip away technical analysis. |
| Section list per spec §6 | `["W", "D", "4H", "F", "今日交易档案", "C", "B"]` + Lock-in metadata + tomorrow prep + 数据快照 |
| Plan retrospective | User-driven addition — turn premarket plan + today's bars into per-level trigger + sim outcome + execution gap. This is the structural innovation. |
| Tomorrow plan formation | Spec said "raw, not plan"; user wants "明天预案". Resolution: EOD outputs **preliminary** tomorrow plan, premarket 06:00 PT next day **finalizes** with overnight + Asia + EU PA. Honors spec intent. |
| A section | Removed (spec §6 explicit). |
| v1 audit depth | User confirmed: existence + violations + screenshots fields only. Deeper compliance (Level 3 ratio, key-level proximity, stop placement rule) defer to v2. |

## 5. Architecture

### 5.1 Pipeline (mirrors `Orchestrator.run_premarket`)

```
Orchestrator.run_eod(run_at)
  │
  ├── Idempotency check (state.db: report_type='eod', date=today_et)
  │
  ├── ContextLoader (existing) — fetch W/D/4H bars per symbol
  │     · IBClient.get_bars('MES', timeframe='1W', bars=8) etc.
  │     · Snapshot post-cash-close (close-of-bar)
  │
  ├── FuturesSection (existing, Phase 4 fix) — basis + term + VP
  │     · UnderlyingPriceFetcher (SPX/NDX/GLD)
  │     · TermPricesFetcher (front/next/far via active_expiry)
  │     · Volume profile from today's RTH bars
  │
  ├── SentimentSection (existing, Phase 4.5)
  │     · SentimentCollector(symbols, time_window="past 8h")  ← shorter window than premarket
  │
  ├── PremarketPlanReader (NEW)
  │     · Read $OBSIDIAN_VAULT/Daily/{TODAY}-premarket.md
  │     · Extract `### C-MES` and `### C-MGC` blocks (regex)
  │     · Return raw markdown for verbatim quote in C section
  │
  ├── PremarketPlanParser (NEW)
  │     · Parse raw C blocks into structured Plan(levels=[PlanLevel...], stop_rule, target_rule, invalidation)
  │     · Each PlanLevel: price, type (POINT/ZONE), source ("4H POC", "W high"), direction (short_fade/long_fade)
  │     · Tolerance for AI-format variance: regex with multiple alternatives (similar to sentiment parser)
  │
  ├── TodayTradesQuery (NEW)
  │     · Query journal DB: SELECT * FROM trades WHERE date = today_et AND mode = 'real'
  │     · Return list[JournalTrade]
  │     · Compute audit fields: §6 ban triggers (from violations array), §9 screenshot status
  │
  ├── PlanRetrospective (NEW) — the heart of EOD's value
  │     · Input: structured Plan + intraday bars (5m, 06:30-13:00 PT) + today's actual trades
  │     · For each PlanLevel, run TradeSimulator → SimOutcome
  │     · Compute aggregate stats: trigger rate, sim total R, actual total R, gap
  │     · Persist row to new state.db table `plan_retrospective_daily`
  │
  ├── TradeSimulator (NEW)
  │     · Per (level_price, direction) + intraday_bars → SimOutcome
  │     · Algorithm: detect first touch, then walk-forward to determine stop/target/open outcome
  │     · Honors plan's stop_rule (POINT: level±2 ticks; ZONE: zone_far_edge±2 ticks)
  │     · Honors plan's target_rule (MIN(2R, next_key_level))
  │
  ├── TomorrowPreliminaryPlan (NEW)
  │     · Input: today's W/D/4H bars + retrospective insights + sentiment shift
  │     · Output: preliminary key levels + setup preference + invalidation triggers
  │     · Marked "preliminary — premarket finalizes" so user (and tomorrow's premarket prompt) treat as draft
  │
  ├── EODPromptBuilder (extend PromptBuilder.build_eod)
  │     · Compose all the above into a single AI prompt
  │     · Section list per spec §6: Lock-in metadata → W/D/4H multi-TF → F → D 情绪面 → 今日交易档案 → 🔄 Plan Retrospective → C 计划复核 → B 市场叙事 → 📅 Tomorrow Preliminary Plan → 数据快照
  │     · A section explicitly excluded
  │
  ├── AIAnalyst (existing) — claude -p, 300s timeout
  │     · 1 call (no second sentiment call needed since SentimentSection already ran)
  │
  ├── OutputValidator (extended)
  │     · REQUIRED_SECTIONS["eod"] added
  │     · Slots: ["Lock-in", "W", "D", "4H", "F", "情绪面", "今日交易档案", "Plan Retrospective", "计划复核", "市场叙事", "Tomorrow Preliminary"]
  │
  ├── ObsidianWriter (existing) — `Daily/{TODAY}-eod.md`
  │     · Filename per spec §2.2: ET date
  │
  └── delivery: ChartRenderer + Telegram (existing) ✅
```

### 5.2 Two AI calls vs one

Premarket: SentimentSection (claude -p call #1) + AIAnalyst main (call #2) = 2 claude -p calls.

EOD: same pattern — SentimentSection (call #1, time_window="past 8h") + AIAnalyst main (call #2). Same 2-call architecture; the structural code is identical. Wall time impact: ~7 min total.

### 5.3 Why mirror PremarketGenerator instead of refactor-first

Phase 7 v1 + Phase 4.5 + futures fix all converged on `PremarketGenerator` as the working precedent. EODGenerator runs in parallel — same shape, different content. The 5+ remaining cadences (intraday-4h-1, etc.) will likewise mirror; after we have N=3 cadences a refactor pass will extract a `BaseCadenceGenerator` cleanly. Premature abstraction pre-N=3 is YAGNI.

## 6. Components

### 6.1 New module: `src/daytrader/reports/eod/`

```
src/daytrader/reports/eod/
  ├── __init__.py
  ├── plan_reader.py            # Read premarket .md, extract C-MES/C-MGC raw blocks
  ├── plan_parser.py            # Raw block → structured Plan(levels, rules, invalidation)
  ├── plan_dataclasses.py       # PlanLevel, Plan, SimOutcome, RetrospectiveRow
  ├── trades_query.py           # Journal DB query → list[JournalTrade] + audit
  ├── trade_simulator.py        # SimOutcome per (level, intraday_bars)
  ├── retrospective.py          # Compose plan + sim outcomes + actual trades → retrospective table
  └── tomorrow_plan.py          # Compose preliminary tomorrow plan
```

### 6.2 New EOD generator: `src/daytrader/reports/types/eod.py`

Mirrors `src/daytrader/reports/types/premarket.py` (`PremarketGenerator`):

```python
class EODGenerator:
    def __init__(
        self,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher=None,
        term_price_fetcher=None,
        tick_sizes: dict[str, float] | None = None,
        sentiment_section: SentimentSection | None = None,
        plan_reader: PremarketPlanReader | None = None,
        plan_parser: PremarketPlanParser | None = None,
        trades_query: TodayTradesQuery | None = None,
        retrospective: PlanRetrospective | None = None,
        tomorrow_planner: TomorrowPreliminaryPlan | None = None,
    ) -> None: ...

    def generate(
        self,
        context: ContextData,
        run_timestamp_pt: str,
        run_timestamp_et: str,
        sentiment_md: str = "",
    ) -> EODOutcome: ...
```

### 6.3 Plan dataclasses (frozen)

```python
@dataclass(frozen=True)
class PlanLevel:
    price: float
    level_type: Literal["POINT", "ZONE"]
    source: str                    # e.g. "4H POC", "W high", "D low"
    direction: Literal["short_fade", "long_fade"]
    zone_low: float | None = None  # ZONE only
    zone_high: float | None = None # ZONE only

@dataclass(frozen=True)
class Plan:
    symbol: str
    levels: list[PlanLevel]
    stop_offset_ticks: int = 2
    target_r_multiple: float = 2.0
    raw_block_md: str = ""         # for verbatim quote in C section

@dataclass(frozen=True)
class SimOutcome:
    triggered: bool
    touch_time_pt: str | None       # "06:53" or None
    touch_bar_high: float | None
    touch_bar_low: float | None
    sim_entry: float | None
    sim_stop: float | None
    sim_target: float | None
    outcome: Literal["target", "stop", "open", "untriggered"]
    sim_r: float                    # 0 if untriggered, +N if target, -1 if stop, partial if open
    mfe_r: float | None             # max favorable excursion
    mae_r: float | None             # max adverse excursion

@dataclass(frozen=True)
class RetrospectiveRow:
    symbol: str
    date_et: str
    total_levels: int
    triggered_count: int
    sim_total_r: float
    actual_total_r: float
    gap_r: float
    per_level_outcomes: list[tuple[PlanLevel, SimOutcome]]
```

### 6.4 PremarketPlanReader

```python
class PremarketPlanReader:
    """Read today's premarket .md from Obsidian, extract C-MES / C-MGC blocks."""

    def __init__(self, vault_path: Path, daily_folder: str = "Daily") -> None: ...

    def read_today_plan(self, date_et: str) -> dict[str, str]:
        """Return {"MES": raw_C_block_md, "MGC": raw_C_block_md} or empty dict if file missing."""
```

Filename pattern: `{vault_path}/{daily_folder}/{date_et}-premarket.md`. Falls back to empty dict if file doesn't exist (e.g., premarket failed) — EOD still runs but C section reflects "no plan available today".

### 6.5 PremarketPlanParser

```python
class PremarketPlanParser:
    """Parse raw C-MES / C-MGC markdown block into structured Plan."""

    def parse(self, raw_block_md: str, symbol: str) -> Plan:
        """Extract levels, stop_offset_ticks, target_r_multiple from free-text plan.

        Tolerates AI-format variance via regex with alternatives. If parsing
        fails completely (e.g., empty block), returns Plan with levels=[].
        """
```

Regex patterns target the format the AI produced in 2026-05-02 / 2026-05-04 premarket reports:

```
- 上方 R1 = 7272.75 (4H POC) → short fade
- 上方 R2 = 7300.75 (W 高) → short fade
- 下方 S1 = 7240.75 (D 低) → long fade
- 下方 S2 = 7220 (前 4H demand zone) → long fade
```

Parse:
- Float prices: `(\d+\.?\d*)` after `R\d` / `S\d`
- Source: paren content
- Direction: `short fade` / `long fade` keywords

If AI outputs differently next week (which is plausible), parser falls back to "best effort — list levels detected, mark unparseable parts in retrospective as 'plan format ambiguous'". Defensive over strict.

### 6.6 TodayTradesQuery

```python
class TodayTradesQuery:
    def __init__(self, journal_db_path: Path) -> None: ...

    def trades_for_date(self, date_et: str, mode: TradeMode = TradeMode.REAL) -> list[JournalTrade]:
        ...

    def audit_summary(self, trades: list[JournalTrade]) -> TradesAudit:
        """Return:
        - count
        - violations triggered (from each trade's `violations: list[str]` field)
        - screenshot status (placeholder for v1 — checks `notes` field for keyword
          'screenshots: yes' until JournalTrade model adds explicit fields)
        - daily R total
        - week-to-date R
        """
```

### 6.7 TradeSimulator

```python
def simulate_level(
    level: PlanLevel,
    intraday_bars: list[OHLCV],     # 5m bars in chronological order
    next_key_level: float | None,
    tick_size: float,
    stop_offset_ticks: int = 2,
    target_r_multiple: float = 2.0,
) -> SimOutcome:
```

Algorithm:

```
1. Detect first touch:
   - For short_fade: first bar where bar.high >= level.price (within 1 tick tolerance)
   - For long_fade: first bar where bar.low <= level.price
   - If never touches → SimOutcome(triggered=False, ...)

2. Compute sim entry / stop / target at touch:
   - sim_entry = level.price (assume limit order at level)
   - For short_fade:
       sim_stop = level.price + stop_offset_ticks * tick_size
       r_distance = sim_stop - sim_entry
       target_2r = sim_entry - target_r_multiple * r_distance
       sim_target = max(target_2r, next_key_level) if next_key_level else target_2r
   - For long_fade: mirror
   - For ZONE: stop = zone_far_edge + offset; entry = level.price (assume mid-zone)

3. Walk forward from touch bar onward, find which fires first:
   - target → SimOutcome(outcome="target", sim_r=+target_r_multiple)
   - stop → SimOutcome(outcome="stop", sim_r=-1.0)
   - end of session bars (13:00 PT) → SimOutcome(outcome="open", sim_r=mid-bar partial)

4. Compute MFE / MAE during the trade for diagnostic:
   - MFE = max profitable excursion in R units
   - MAE = max adverse excursion in R units

5. Return SimOutcome with all fields populated.
```

**Caveat for v1**: this assumes any plan-listed level "would have triggered the stacked-imbalance setup if price touched it". Real verification requires footprint Level 3 / 5:1 / volume-100 data which is not yet in our pipeline. v2 enhancement: integrate MotiveWave footprint replay or live data subscription.

The retrospective output explicitly notes this assumption next to each row.

### 6.8 PlanRetrospective composition

```python
class PlanRetrospective:
    def __init__(
        self,
        plan_parser: PremarketPlanParser,
        trade_simulator: Callable,        # the simulate_level function
        intraday_bar_fetcher: Callable,   # IBClient.get_bars(timeframe='5m', ...)
        trades_query: TodayTradesQuery,
        retrospective_db_path: Path,
    ) -> None: ...

    def compose(
        self,
        plans: dict[str, str],            # raw blocks from PremarketPlanReader
        symbols: list[str],
        date_et: str,
        tick_sizes: dict[str, float],
    ) -> dict[str, RetrospectiveRow]:
        """Per symbol: parse plan → fetch intraday bars → simulate each level →
        compose RetrospectiveRow with per-level outcomes + aggregate stats."""

    def persist(self, rows: dict[str, RetrospectiveRow]) -> None:
        """Append per-symbol rows to data/state.db's `plan_retrospective_daily`
        table. Schema:
          date | symbol | total_levels | triggered_count
              | sim_total_r | actual_total_r | gap_r
              | retrospective_json (full per-level outcomes)
        """
```

### 6.9 TomorrowPreliminaryPlan

```python
class TomorrowPreliminaryPlan:
    """Compose preliminary tomorrow plan from today's data + retrospective."""

    def __init__(self, retrospective: PlanRetrospective) -> None: ...

    def build_input_data(
        self,
        today_bars: dict[str, dict[str, list[OHLCV]]],   # per symbol per TF
        today_retrospective: dict[str, RetrospectiveRow],
        sentiment_md: str,
    ) -> str:
        """Return markdown to inject into AI prompt's tomorrow section.

        Includes:
        - Today's W/D/4H formed levels (PriorDay High/Low, today's POC/VAH/VAL,
          new swing high/low)
        - Sentiment shift indicator (today's combined score)
        - Retrospective insight ("today plan triggered at X — tomorrow same
          level area is Y due to structure shift")
        - Pending econ events (web search; same as premarket)
        - Invalidation triggers (overnight breakouts that kill preliminary)
        """
```

The AI then renders this into the `📅 Tomorrow Preliminary Plan` section of the EOD output, per the prompt's instructions.

### 6.10 PromptBuilder.build_eod

Extend `src/daytrader/reports/core/prompt_builder.py`:

```python
def build_eod(
    self,
    instruments_data: dict[str, dict[str, list[OHLCV]]],
    futures_data: FuturesSection | None = None,
    sentiment_md: str = "",
    today_plan_blocks: dict[str, str] = None,           # raw C blocks for verbatim quote
    retrospective_md: str = "",                          # rendered retrospective table + summary
    today_trades_md: str = "",                           # rendered trade ledger + audit
    tomorrow_preliminary_md: str = "",                   # rendered tomorrow prep
    contract_meta: dict = None,
    journal_meta: dict = None,
    report_date: str = "",
) -> str:
    """Build EOD prompt. Section order per spec §6 + brainstorm decisions:
    Lock-in → W/D/4H per symbol → F. → D. 情绪面 → 今日交易档案 →
    🔄 Plan Retrospective → C. 计划复核 → B. 市场叙事 →
    📅 Tomorrow Preliminary → 数据快照. A section explicitly excluded.
    """
```

### 6.11 Modifications to existing files

| File | Change |
|---|---|
| `src/daytrader/cli/reports.py` | `if report_type == "eod": orchestrator.run_eod(...)` (no longer exits 2) |
| `src/daytrader/reports/core/orchestrator.py` | New `run_eod()` method mirrors `run_premarket()` |
| `src/daytrader/reports/core/output_validator.py` | Add `REQUIRED_SECTIONS["eod"]` |
| `src/daytrader/reports/templates/eod.md` | NEW — prompt instructions for AI |
| `src/daytrader/core/state.py` | Add `plan_retrospective_daily` table init |

## 7. EOD Output Template (Section List)

```markdown
# 📋 EOD Daily Report — YYYY-MM-DD

## 🔒 Lock-in Metadata (today's update)
- trades_done: today=N (cumulative=M/30)
- daily R: today=±X, week-to-date=±Y
- cool-off entering tomorrow: yes/no + reason
- §6 ban audit: 任何 ban 触发？

## 📊 MES — Multi-TF (W / D / 4H, today's close updates)
## 📊 MNQ — Multi-TF (context only)
## 📊 MGC — Multi-TF

## 🌐 Cross-Asset Narrative (今日过去时, NO predictions)

## 📰 Breaking News (今日 + 收盘后)

## F. 期货结构 / Futures Positioning (post-cash-close)
- F-MES: settle, basis, term structure, RTH-formed POC/VAH/VAL
- F-MNQ
- F-MGC

## D. 情绪面 / Sentiment Index (today 8h window)
- 同 Phase 4.5 SentimentSection 输出格式

## 今日交易档案 / Today's Trade Archive
| # | symbol | side | entry | exit | R | setup match | §6 violations | §9 screenshots |
- 0 trade 模式: "今天没交易. 原因: [no setup matched / no screen time]"
- §6 ban audit
- §9 screenshot status

## 🔄 Plan Retrospective / 计划复盘
### MES
| # | Planned level | 类型 | 方向 | 触及? | Touch 时间 | Sim entry | Sim stop | Sim target | Sim outcome | 实际 trade? |
### MGC
[same structure]

### 📊 Plan Accuracy 评估
- Plan levels 触及率, sim 总收益, 实际收益, gap

### 💡 Iteration insight (AI 综合)
- Plan 质量 vs Execution gap

### 🎯 Lock-in 期间累计表
| Date | Plan levels | 触发率 | Sim R | Actual R | Gap |
- 从 plan_retrospective_daily 表 join 出来过去 N 天

## C. 计划复核 / Plan Adherence Assessment
- **VERBATIM quote** of today's premarket C-MES / C-MGC blocks
- Plan vs actual:
  - For each entered trade: did entry/stop/target match plan?
  - For each non-entered plan level: was setup truly absent, or was it skipped?
- Invalidation status
- R progress

## B. 市场叙事 / Today's Narrative (past)
- 今天怎么走、为什么、关键事件
- **Forbidden**: forward-looking predictions

## 📅 Tomorrow Preliminary Plan
> 注：preliminary，premarket 06:00 PT 会用亚欧盘 PA finalize

### Per-symbol 明天初步关键位
- R1, R2, S1, S2 (今日 W/D/4H 形成)

### 明天 setup 偏好（基于今日 retrospective + sentiment shift）
### 失效条件 (overnight breakouts)
### 风险事件 (econ events from web search)

## 📑 数据快照 / Data Snapshot
```

**A 段：完全不出现** (spec §6 forbidden).

## 8. Data Flow Detail

```
T+0    Orchestrator.run_eod() invoked at ~14:00 PT
T+1s   Idempotency check: already_generated_today('eod', date_et)?
T+2s   StateDB.insert_report(report_type='eod', status='pending')
T+5s   ContextLoader: bars W/D/4H per symbol (~5s)
T+10s  FuturesSection: basis + term + VP (~5s) — uses today's RTH bars
T+15s  SentimentSection.collect(time_window="past 8h"): claude -p (~80s)
T+95s  PremarketPlanReader: read Obsidian file (~ms)
T+95s  PremarketPlanParser: parse C-MES + C-MGC into Plans (~ms)
T+95s  TodayTradesQuery: query journal DB (~ms)
T+96s  PlanRetrospective.compose:
       └── For each symbol, for each level, simulate against today's 5m bars
           (all in-memory, ~2s)
T+98s  PlanRetrospective.persist: append rows to plan_retrospective_daily
T+98s  TomorrowPreliminaryPlan.build_input_data: ~ms
T+98s  PromptBuilder.build_eod: compose mega prompt (~ms)
T+99s  AIAnalyst.call: claude -p (~150-180s with retrospective + tomorrow content)
T+280s OutputValidator.validate: check sections (~ms)
T+281s ObsidianWriter writes Daily/{TODAY}-eod.md
T+285s Delivery: chart + Telegram (~5s)
T+~5min Done
```

Net: ~7-8 min total for EOD pipeline (similar to premarket post-Phase-4.5).

## 9. Error Handling

Same principle as Phase 4.5: **per-component failures degrade gracefully; main pipeline never blocked**.

| Failure mode | Detection | Behavior |
|---|---|---|
| Premarket file missing | `PremarketPlanReader.read_today_plan` returns empty | Plan Retrospective renders "today's plan unavailable (premarket failed?)" + Plan Adherence renders "no plan to compare" |
| Plan parsing fails | `PremarketPlanParser` returns Plan(levels=[]) | Retrospective renders "plan format unparseable" + skips per-level table |
| Journal DB empty / no trades | `TodayTradesQuery` returns [] | Trade archive renders "0 trades today" |
| Intraday 5m bars missing | `IBClient.get_bars(timeframe='5m')` returns < N | Simulator returns SimOutcome(triggered=False, reason="insufficient bars") for affected levels |
| Sentiment timeout | (existing Phase 4.5 graceful degrade) | D. 情绪面 renders unavailable block |
| `claude -p` main timeout | RuntimeError | Pipeline fails, status='failed' in state DB; user sees Telegram notification (existing) |

## 10. Testing Strategy

### 10.1 Unit tests (mocked, ~50 tests)

- `tests/reports/eod/test_plan_reader.py` — given fake Obsidian file → returns C-MES/C-MGC blocks
- `tests/reports/eod/test_plan_parser.py` — parse 5+ AI-format variants from real Phase 4.5 reports
- `tests/reports/eod/test_trades_query.py` — mock journal DB → returns + audits trades
- `tests/reports/eod/test_trade_simulator.py` — 10+ scenarios (target hit / stop hit / never triggered / open at end / ZONE level / next-level cap reduces target / MFE/MAE math)
- `tests/reports/eod/test_retrospective.py` — compose end-to-end with mocks
- `tests/reports/eod/test_tomorrow_plan.py` — input data composition
- `tests/reports/eod/test_eod_generator.py` — EODGenerator integration with all mocks
- `tests/reports/test_prompt_builder.py` — extend; assert build_eod produces all required sections
- `tests/reports/test_orchestrator.py` — extend; mock all EOD-specific deps; assert run_eod calls them in order
- `tests/reports/test_output_validator.py` — extend; REQUIRED_SECTIONS["eod"] enforced

### 10.2 Live integration test (slow-marked)

`tests/reports/eod/test_integration_live.py` (`@pytest.mark.slow`):
- Real claude -p call via SentimentSection
- Real claude -p call via AIAnalyst
- Real journal DB (empty for v1)
- Real Obsidian file read (today's premarket)
- Verifies EOD report markdown contains all required section markers

### 10.3 End-to-end test fire

After implementation:
1. `uv run daytrader reports run --type eod --no-pdf`
2. Verify `Daily/{TODAY}-eod.md` exists with all sections
3. Verify Plan Retrospective table populated (assuming today's premarket exists)
4. Verify trade archive renders "0 trades" (assuming user didn't trade today)
5. Failure-path: temporarily rename today's premarket file → re-run EOD → confirm graceful "plan unavailable" rendering

## 11. launchd Integration (Phase 7.5 light)

New plist + wrapper + install pair (mirrors premarket / weekly):

| File | Action |
|---|---|
| `scripts/run_eod_launchd.sh` | NEW (mirrors `run_premarket_launchd.sh`, calls `daytrader reports run --type eod --no-pdf`) |
| `scripts/launchd/com.daytrader.report.eod.1400pt.plist.template` | NEW (StartCalendarInterval Hour=14 Minute=0 Weekday=1..5) |
| `scripts/install_eod_launchd.sh` | NEW (mirrors install_weekly_launchd.sh) |
| `scripts/uninstall_eod_launchd.sh` | NEW |
| `.gitignore` | Add `data/logs/launchd/eod-*.log` |

Phase 7's preflight handshake (landed today as commit `daa0d75`) automatically applies to EOD's wrapper too — the wrapper invokes the same `preflight_check.py` script.

## 12. Files Inventory

| File | Action | Estimated LOC |
|---|---|---|
| `src/daytrader/reports/eod/__init__.py` | Create | ~15 |
| `src/daytrader/reports/eod/plan_dataclasses.py` | Create | ~80 |
| `src/daytrader/reports/eod/plan_reader.py` | Create | ~60 |
| `src/daytrader/reports/eod/plan_parser.py` | Create | ~150 (regex-heavy) |
| `src/daytrader/reports/eod/trades_query.py` | Create | ~120 |
| `src/daytrader/reports/eod/trade_simulator.py` | Create | ~200 |
| `src/daytrader/reports/eod/retrospective.py` | Create | ~180 |
| `src/daytrader/reports/eod/tomorrow_plan.py` | Create | ~100 |
| `src/daytrader/reports/types/eod.py` | Create | ~250 (mirrors premarket.py) |
| `src/daytrader/reports/templates/eod.md` | Create | ~80 (template) |
| `src/daytrader/reports/core/prompt_builder.py` | Modify | +120 (build_eod method) |
| `src/daytrader/reports/core/orchestrator.py` | Modify | +80 (run_eod method) |
| `src/daytrader/reports/core/output_validator.py` | Modify | +20 (REQUIRED_SECTIONS[eod]) |
| `src/daytrader/cli/reports.py` | Modify | +30 (eod dispatch) |
| `src/daytrader/core/state.py` | Modify | +30 (plan_retrospective_daily table) |
| `scripts/run_eod_launchd.sh` | Create | ~60 |
| `scripts/launchd/...eod.1400pt.plist.template` | Create | ~40 |
| `scripts/install_eod_launchd.sh` | Create | ~50 |
| `scripts/uninstall_eod_launchd.sh` | Create | ~25 |
| `.gitignore` | Modify | +1 |
| Tests (10 new files + extensions) | Create / Modify | ~900 |
| **Total estimated** | | **~2,650 LOC** |

## 13. Acceptance Criteria

A Phase 5 EOD implementation is complete when ALL of these hold:

- [ ] `uv run pytest tests/reports/eod/ -v` passes (excluding slow live test)
- [ ] `uv run pytest tests/ --ignore=tests/research -q` still passes (no regressions; total now ~400+)
- [ ] Live test fire of `daytrader reports run --type eod --no-pdf` succeeds, producing `Daily/{TODAY}-eod.md` containing:
  - Lock-in metadata block with today's trade count
  - W/D/4H multi-TF section per tradable symbol (and MNQ context)
  - F. 期货结构 with today's basis + term + RTH-formed VP
  - D. 情绪面 with sentiment from past 8h window
  - 今日交易档案 (0-trade case correctly rendered)
  - 🔄 Plan Retrospective with per-level table (or "plan unavailable" graceful fallback)
  - C. 计划复核 with verbatim quote of today's premarket plan
  - B. 市场叙事 (past-tense)
  - 📅 Tomorrow Preliminary Plan section
  - **NO A. section**
- [ ] Failure-path test: temporarily move `Daily/{TODAY}-premarket.md` → EOD generates with graceful "plan unavailable" messaging in C and Retrospective sections
- [ ] launchd job loaded successfully via `install_eod_launchd.sh`; `launchctl print` shows Hour=14 Minute=0 Weekday=1..5
- [ ] Total pipeline wall time ≤ 10 min (target ~7-8 min)
- [ ] `plan_retrospective_daily` table populated with at least one row after live fire

## 14. Decision Records

**DR-1: Mirror PremarketGenerator pattern (don't refactor first)** — Premature abstraction with N=1. After Phase 5.5 lands intraday cadences (N=3+) extract `BaseCadenceGenerator`.

**DR-2: 2 claude -p calls (sentiment + main)** — Same pattern as premarket. Total wall ~7-8 min.

**DR-3: PremarketPlanParser tolerates AI-format variance** — Regex with multiple alternatives. If parsing fails completely → empty plan with "plan format ambiguous" message. Defensive over strict.

**DR-4: Trade simulator assumes plan-level "would have triggered setup" if price touches** — Real Level 3 / 5:1 / vol-100 footprint verification deferred to v2 (requires MotiveWave integration).

**DR-5: Tomorrow plan is "preliminary"** — Honors spec §6 "raw, not plan" by labeling explicitly. Premarket 06:00 PT next day finalizes.

**DR-6: A section completely omitted** — spec §6 forbidden.

**DR-7: New `plan_retrospective_daily` table in state.db** — Daily aggregate row per symbol. Foundation for v2 multi-day stats.

**DR-8: Retrospective on intraday 5m bars** — Granularity sufficient for ±1 tick touch detection. 1m bars too noisy (false touches), 15m too coarse (miss touches between bars).

**DR-9: §9 screenshot audit uses `notes` field placeholder for v1** — `JournalTrade` model doesn't have explicit `pre_screenshot_path` / `post_screenshot_path` fields yet. v1 checks `notes` for keyword `screenshots: yes`; v1.5 will extend the model.

**DR-10: launchd plist follows Phase 7 v1 pattern** — Same wrapper + preflight + install/uninstall pattern. Preflight's API handshake (landed today) applies automatically.

## 15. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Plan parser fragile to AI format drift | Med | Med | Multiple regex alternatives + graceful fallback to "ambiguous"; integration test against 3+ real premarket files |
| Trade simulator assumes "level touched = setup triggered" — overestimates sim PnL | High | Low | Document explicitly in retrospective output; v2 fixes with footprint integration |
| 5m bar IB request rate limits during EOD pipeline | Low | Low | We already fetch W/D/4H/1H per symbol; 5m for 6.5 hours = 78 bars × 3 symbols = 234 bars in <2s, well under IB throttle |
| `plan_retrospective_daily` table grows unbounded | Low (1 row/day) | Low | Document quarterly truncate in runbook; 30 days × 3 symbols × ~1KB = trivial |
| User's premarket file path varies (e.g., custom vault) | Low | Low | PremarketPlanReader takes `vault_path` from `config/user.yaml`; fallback messaging |
| EOD fires while user is reviewing 14:00 ET CME settle data manually | Low | Low | EOD doesn't disrupt user workflow; report appears as Obsidian + Telegram |
| Footprint setup truth value drift (Level 3 / 5:1 / 100 vol assumption) | Med over 30 days | Med over 30 days | Retrospective explicitly disclaims; lock-in trade journal screenshots remain ground truth |

## 16. Future Enhancements (v2+)

- **Multi-day aggregate dashboard** — render `plan_retrospective_daily` past-30-days table with rolling stats
- **Footprint integration** — MotiveWave data export → verify Level 3 / 5:1 / vol-100 at touch time → simulator uses real setup truth value
- **AI plan iteration suggestions** — "Past 30 days W-extreme levels triggered 12% of time → suggest dropping from plan list"
- **Reverse causation analysis** — "Your -2R days correlate with X setup type"
- **Phase 5.5 — other cadences** — intraday-4h-1, intraday-4h-2, night, asia
- **Phase 7.5 — full launchd inventory** — install all 6 remaining plists per spec §6.2.1

## 17. Migration Path to Phase 5.5

The 4 remaining cadences (intraday-4h-1, intraday-4h-2, night, asia) reuse most EOD infrastructure:

- `IBClient` — same
- `FuturesSection` / `SentimentSection` — same
- `PromptBuilder` — extend with `build_intraday_4h_1` / `build_eod` / etc.
- `OutputValidator.REQUIRED_SECTIONS` — add per-cadence section list
- `Orchestrator` — add per-cadence `run_X` method
- `Generator` classes — one per cadence; refactor pass extracts `BaseCadenceGenerator` after EOD lands

Plan/trade specific machinery (PremarketPlanReader, TradeSimulator, PlanRetrospective) is EOD-specific and not reused by intraday/night/asia cadences (those are forward-looking, not retrospective).

---

**End of spec. Next step: write implementation plan via `superpowers:writing-plans` skill.**
