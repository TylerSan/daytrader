# Reports Phase 5.5 — Multi-Cadence Buildout (intraday-4h, night, asia)

**Status**: Approved (2026-05-05) — pending writing-plans phase
**Targets**: intraday-4h-1, intraday-4h-2, night, asia (4 new cadences)
**Builds on**: Phase 4.5 sentiment, Phase 5 EOD, Phase 7 v1 launchd

---

## 1. Goal

Add the four remaining trading-day cadences from master spec §2.2:

- **intraday-4h-1** at 07:00 PT (10:00 ET) — first intraday review (US RTH open + 30min reaction)
- **intraday-4h-2** at 11:00 PT (14:00 ET) — mid-session review (lunch fade window) with full retrospective + sentiment refresh
- **night** at 19:00 PT (22:00 ET) — D-only learning archive (after-hours US session bar)
- **asia** at 23:00 PT (02:00+1 ET) — D-only learning archive (Asian session)

Together with existing premarket (06:00 PT) + EOD (14:00 PT) + weekly (Sun 14:00 PT), this completes 7-cadence coverage for the 30-trade lock-in.

## 2. Why now

The user's 30-trade lock-in is starting (trade 0/30). Phase 5 EOD landed 2026-05-04 with closed-loop Plan Retrospective. Phase 5.5 closes the remaining gaps:

1. **Mid-session feedback** (4h-2 at 11:00 PT) gives "上半场复盘 + 下半场预案" before user makes afternoon decisions. EOD 14:00 PT is too late to influence today's afternoon trades.
2. **Open-bar audit** (4h-1 at 07:00 PT) catches premarket plan vs first 30min reality — gives user a chance to invalidate before the 9:30 ET first push extends past the plan range.
3. **Overnight learning archive** (night + asia) builds the data foundation for future mechanical strategy research. D purpose is not for in-the-moment decisions; it's for "30 days from now, query all bullish_engulf at support_test in last month, how did next-day US session play out?"

Master spec §2.2 was written 2026-04-25 — before Phase 4.5 sentiment + Phase 5 EOD's Plan Retrospective + Trade Archive innovations. This phase integrates those new features into the 4 new cadences via `BaseCadenceGenerator`.

## 3. Out of scope (this phase)

The following are **deferred** and explicitly NOT in Phase 5.5:

1. **Refactoring premarket.py / eod.py to BaseCadenceGenerator** — those work, all 538 tests pass, retrofit is Phase 5.6 post-Trade-#1
2. **Weekly report rewrite** — current weekly (`premarket/weekly.py`) is independent and works; rewrite via BaseCadenceGenerator is Phase 5.7
3. **Mechanical D-only learning queries** — night/asia produce D frontmatter, but querying "all bullish_engulf at support_test" is Phase 6 work (separate research module)
4. **A-1 form (direct buy/sell calls)** — permanently disabled per master spec §2.3
5. **Per-symbol cadence overrides** — all 4 cadences run for all 3 symbols (MES + MNQ + MGC) uniformly
6. **Real-time alerts on level breach** — Phase 8 (push notifications), not this phase
7. **Cross-cadence aggregation views** — "show me MES level X across today's premarket / 4h-1 / 4h-2 / EOD" — Phase 9 (Obsidian dashboard)
8. **Trade Archive full §6/§9 audit in 4h reports** — only EOD has full audit; 4h has light list (per Q3 decision)

## 4. Background

### 4.1 Existing cadences (post-Phase 5)

| Cadence | Time PT | Generator | Purpose | TFs | Auto-fire |
|---|---|---|---|---|---|
| premarket | 06:00 | `PremarketGenerator` | A+B+C | W+D+4H+1H | ✅ Mon-Fri |
| eod | 14:00 | `EODGenerator` | C+D | W+D+4H | ✅ Mon-Fri |
| weekly | Sun 14:00 | `premarket.weekly` (legacy) | A+B | M+W+D+4H | ✅ Sun |

### 4.2 Patterns this phase reuses

- **PremarketGenerator + EODGenerator shape** (multi-symbol fetch → F section → news → AI → validate → write)
- **Phase 4.5 SentimentSection** for D. 情绪面 in 4h-2 (`time_window="past 5h"`)
- **Phase 5 PremarketPlanReader + PremarketPlanParser** for C plan recheck (4h-1 + 4h-2)
- **Phase 5 TodayTradesQuery** for trade archive (4h-1/4h-2 light list; night/asia lock-in count only)
- **Phase 5 PlanRetrospective + simulate_level + plan_retrospective_daily table** for 4h-2 retrospective
- **Phase 7 v1 launchd pattern** (preflight gate, exec tee, plist Mon-Fri 5-Weekday array)
- **C2 fix `_make_intraday_fetcher`** factory pattern — 4h-2 uses identical pattern with end_time = 11:00 PT
- **I1 fix warnings → state.failures** — all new cadences inherit this from BaseCadenceGenerator
- **C1 fix 5m timeframe** — 4h-2 retrospective fetches 5m bars; works because IBClient now supports 5m

### 4.3 Refactor scope guardrail

User explicitly mandated (2026-05-05): "**不要影响到原有已经正确实现的功能，不要修改无关的代码**" — premarket.py and eod.py and their tests must NOT be touched in this phase. BaseCadenceGenerator serves NEW cadences only. Phase 5.6 is the separate refactor decision for retrofit.

## 5. Architecture

### 5.1 Module layout

```
src/daytrader/reports/types/
├── base.py                NEW — BaseCadenceGenerator + CadenceOutcome + default hooks
├── premarket.py           UNCHANGED ✋ — Phase 2-4 implementation
├── eod.py                 UNCHANGED ✋ — Phase 5 implementation
├── intraday_4h.py         NEW — IntradayFourHGenerator(Base) + IntradayFourHConfig
└── night_asia.py          NEW — NightAsiaGenerator(Base) + NightAsiaConfig

src/daytrader/reports/templates/
├── premarket.md           UNCHANGED ✋
├── eod.md                 UNCHANGED ✋
├── intraday_4h.md         NEW — 8-section A+B+C+F template
└── night_asia.md          NEW — 5-section D-only template

scripts/
├── run_intraday_4h_1_launchd.sh        NEW
├── run_intraday_4h_2_launchd.sh        NEW
├── run_night_launchd.sh                NEW
├── run_asia_launchd.sh                 NEW
├── install_intraday_4h_launchd.sh      NEW
├── install_night_asia_launchd.sh       NEW
├── uninstall_intraday_4h_launchd.sh    NEW
├── uninstall_night_asia_launchd.sh     NEW
└── launchd/
    ├── com.daytrader.report.intraday-4h-1.0700pt.plist.template  NEW
    ├── com.daytrader.report.intraday-4h-2.1100pt.plist.template  NEW
    ├── com.daytrader.report.night.1900pt.plist.template          NEW
    └── com.daytrader.report.asia.2300pt.plist.template           NEW
```

### 5.2 BaseCadenceGenerator (template method pattern)

```python
class BaseCadenceGenerator(ABC):
    """Common cadence generation pipeline. Subclasses override hooks."""

    def __init__(self, ib_client, ai_analyst, symbols, tradable_symbols,
                 prompt_builder=None, validator=None, ...): ...

    @property
    @abstractmethod
    def report_type(self) -> str: ...

    @property
    @abstractmethod
    def tfs(self) -> tuple[str, ...]: ...

    @property
    @abstractmethod
    def bars_per_tf(self) -> dict[str, int]: ...

    @abstractmethod
    def _build_prompt(self, **inputs) -> list[dict[str, Any]]: ...

    # Default-skip hooks — override in subclass to enable:
    def _maybe_fetch_sentiment(self) -> str:
        return ""

    def _maybe_read_plan(self, date_et: str) -> dict[str, str]:
        return {}

    def _maybe_fetch_trades(self, date_et: str) -> list[dict]:
        return []

    def _maybe_compose_retrospective(self, plans, trades, date_et) -> str:
        return ""

    def _maybe_compose_tomorrow(self, ...) -> str:
        return ""

    def generate(self, context, date_et, run_timestamp_pt, run_timestamp_et,
                 news_items=None, sentiment_md="") -> CadenceOutcome:
        warnings_list: list[str] = []

        bars = self._fetch_bars()
        f_data = self._fetch_f_section(warnings_list)
        news = self._fetch_news(warnings_list) if news_items is None else news_items
        sentiment = sentiment_md or self._maybe_fetch_sentiment()
        plans = self._maybe_read_plan(date_et)
        trades = self._maybe_fetch_trades(date_et)
        retrospective = self._maybe_compose_retrospective(plans, trades, date_et)
        tomorrow = self._maybe_compose_tomorrow(...)

        prompt = self._build_prompt(
            context=context, bars=bars, f_data=f_data, news=news,
            sentiment_md=sentiment, plans=plans, trades=trades,
            retrospective_md=retrospective, tomorrow_md=tomorrow,
            run_timestamp_pt=run_timestamp_pt,
            run_timestamp_et=run_timestamp_et,
        )
        ai_result = self.ai_analyst.call(messages=prompt, max_tokens=12288)
        validation = self.validator.validate(ai_result.text,
                                             report_type=self.report_type)
        return CadenceOutcome(
            report_text=ai_result.text,
            ai_result=ai_result,
            validation=validation,
            bars_by_symbol_and_tf=bars,
            warnings=tuple(warnings_list),
        )
```

`CadenceOutcome` is a frozen dataclass — same shape as Phase 5's `EODOutcome` (this lets Orchestrator use the same warnings → state.failures pipeline).

### 5.3 IntradayFourHGenerator config-parameterized

```python
@dataclass(frozen=True)
class IntradayFourHConfig:
    cadence_label: str           # "intraday-4h-1" | "intraday-4h-2"
    do_retrospective: bool       # False | True
    sentiment_refresh: bool      # False | True
    sentiment_time_window: str   # ""(no refresh) | "past 5h"
    news_time_window: str        # "past 1h" | "past 5h"
    intraday_end_time_et: str    # "10:00" (4h-1) | "14:00" (4h-2) → used by retrospective fetcher

class IntradayFourHGenerator(BaseCadenceGenerator):
    def __init__(self, config: IntradayFourHConfig, ...): ...

    @property
    def report_type(self) -> str:
        return "intraday-4h"  # validator uses this single key for both

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("1D", "4H", "1H")

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"1D": 10, "4H": 12, "1H": 24}

    def _maybe_fetch_sentiment(self) -> str:
        if not self._config.sentiment_refresh:
            return ""  # caller passes premarket sentiment via sentiment_md
        # Phase 4.5 SentimentSection with custom time_window
        section = SentimentSection(symbols=self.symbols,
                                   time_window=self._config.sentiment_time_window)
        result = section.collect()
        return section.render(result)

    def _maybe_read_plan(self, date_et: str) -> dict[str, str]:
        # Always read for both 4h-1 and 4h-2 — needed for C section
        return self.plan_reader.read_today_plan(date_et)

    def _maybe_fetch_trades(self, date_et: str) -> list[dict]:
        # Light list (no §6/§9 audit, just trades_for_date)
        return self.trades_query.trades_for_date(date_et)

    def _maybe_compose_retrospective(self, plans, trades, date_et) -> str:
        if not self._config.do_retrospective:
            return ""
        # Reuse Phase 5 PlanRetrospective with intraday_end_time_et override
        rows = self.retrospective.compose(plans, self.symbols, date_et,
                                          self.tick_sizes)
        self.retrospective.persist(rows)  # persist to plan_retrospective_daily
        return self._render_retrospective_block(rows)

    def _build_prompt(self, **inputs) -> list[dict]:
        return self.prompt_builder.build_intraday_4h(
            cadence_label=self._config.cadence_label, **inputs
        )
```

### 5.4 NightAsiaGenerator (D-only)

```python
@dataclass(frozen=True)
class NightAsiaConfig:
    cadence_label: str           # "night" | "asia"
    trigger_time_pt: str         # "19:00" | "23:00"
    news_time_window: str        # "past 4h" both

class NightAsiaGenerator(BaseCadenceGenerator):
    @property
    def report_type(self) -> str:
        return self._config.cadence_label  # "night" or "asia"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("4H", "1H")  # No D — overnight bars

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"4H": 12, "1H": 24}

    # NO override of _maybe_fetch_sentiment / _maybe_read_plan /
    # _maybe_fetch_trades / _maybe_compose_retrospective — defaults return
    # empty so D-only template doesn't render those sections.

    def _build_prompt(self, **inputs) -> list[dict]:
        return self.prompt_builder.build_night_asia(
            cadence_label=self._config.cadence_label, **inputs
        )
```

### 5.5 Orchestrator dispatch

```python
class Orchestrator:
    # ... existing run_premarket / run_eod UNCHANGED ...

    def run_intraday_4h_1(self, run_at: datetime) -> PipelineResult:
        config = IntradayFourHConfig(
            cadence_label="intraday-4h-1",
            do_retrospective=False,
            sentiment_refresh=False,
            sentiment_time_window="",
            news_time_window="past 1h",
            intraday_end_time_et="10:00",
        )
        return self._run_cadence(config, run_at, IntradayFourHGenerator)

    def run_intraday_4h_2(self, run_at: datetime) -> PipelineResult:
        config = IntradayFourHConfig(
            cadence_label="intraday-4h-2",
            do_retrospective=True,
            sentiment_refresh=True,
            sentiment_time_window="past 5h",
            news_time_window="past 5h",
            intraday_end_time_et="14:00",
        )
        return self._run_cadence(config, run_at, IntradayFourHGenerator)

    def run_night(self, run_at: datetime) -> PipelineResult:
        config = NightAsiaConfig(cadence_label="night",
                                 trigger_time_pt="19:00",
                                 news_time_window="past 4h")
        return self._run_cadence(config, run_at, NightAsiaGenerator,
                                 telegram=False)

    def run_asia(self, run_at: datetime) -> PipelineResult:
        config = NightAsiaConfig(cadence_label="asia",
                                 trigger_time_pt="23:00",
                                 news_time_window="past 4h")
        return self._run_cadence(config, run_at, NightAsiaGenerator,
                                 telegram=False)

    def _run_cadence(self, config, run_at, generator_cls, telegram=True):
        """Common pipeline: idempotency → pending row → generator.generate()
        → warnings to state.failures → write Obsidian → success/fail."""
        # ... shared logic, ~150 LOC ...
```

## 6. Output template

### 6.1 intraday-4h template (4h-1 + 4h-2 share, AI fills cadence-specific sections)

```markdown
---
type: intraday-4h
cadence_label: {{cadence_label}}        # "intraday-4h-1" | "intraday-4h-2"
date: {{date_et}}
time_pt: "{{run_timestamp_pt}}"
time_et: "{{run_timestamp_et}}"
trigger: 4h_bar_close
tf_coverage: [D, 4H, 1H]
sections: [A, B, C, F]
instruments: [MES, MNQ, MGC]
---

# Intraday 4H Report ({{cadence_number}}) · {{date_et}} {{run_timestamp_pt}} PT

## 📋 Contract.md status
{{lock_in_metadata}}

## 📊 MES (S&P) — Multi-TF
#### D / 4H / 1H

## 📊 MNQ (Nasdaq) — Multi-TF
#### D / 4H / 1H

## 📊 MGC (Gold) — Multi-TF
#### D / 4H / 1H

## F. 期货结构 / Futures Positioning
### F-MES: OI Δ + Basis + Term + RTH-Volume Profile + AI signal
### F-MNQ: same
### F-MGC: same

## 📰 Breaking News (past {{news_window}})
- ...

## D. 情绪面 / Sentiment Index
{{sentiment_md_VERBATIM_FROM_INPUT}}

## 今日交易档案 / Today's Trade Archive (since 06:30 PT)
| # | Time PT | Symbol | Side | Entry | Exit | R |
| --- | --- | --- | --- | --- | --- | --- |
{{trades_light_list}}

## 🔄 Plan Retrospective / 计划复盘 [4h-2 ONLY; 4h-1 omits this whole section]
{{retrospective_md_VERBATIM}}

## C. 计划复核 / Plan Adherence Assessment
### C-MES (verbatim quote from premarket plan)
{{premarket_C_MES_VERBATIM}}
### C-MGC (verbatim from premarket plan)
{{premarket_C_MGC_VERBATIM}}
[Plan vs actual delta + invalidation triggers fired so far]

## B. 市场叙事 / Today's Narrative (so far)
[Past-tense for the period 06:30 PT → now; FORBIDDEN: forward predictions for rest of session — that's A's job]

## A. 建议 / Recommendation (rest-of-session)
[A-3 default; A-2 escalation if conditions met. Mixed form A.3: each instrument has mini-A inside F section; main A is cross-instrument integration. NO A-1 (direct buy/sell calls)]

## 📑 数据快照 / Data Snapshot
- IBKR connection: ✓ healthy
- Bars fetched: D / 4H / 1H ✓ (3 instruments)
- News source: ✓ {{N}} items
- Sentiment: {{ "refreshed" if 4h-2 else "from premarket cache" }}
```

**Section order is FIXED** (master spec §3.6): metadata → multi-TF → F → news → sentiment → trades → [retrospective in 4h-2] → **C → B → A** → snapshot. C before A is structural for self-anchored thinking (user reads "my own plan status" before AI's new recommendation).

### 6.2 night/asia template (D-only)

```markdown
---
type: {{cadence_label}}                  # "night" | "asia"
date: {{date_et}}
time_pt: "{{run_timestamp_pt}}"
time_et: "{{run_timestamp_et}}"
trigger: 4h_bar_close
tf_coverage: [4H, 1H]
sections: [F, D]
pattern_tags: []                         # AI populates
news_event_tags: []                      # AI populates
instruments: [MES, MNQ, MGC]
---

# {{cadence_title}} D-Archive · {{date_et}} {{run_timestamp_pt}} PT

## 📋 Contract.md status (compact)
[Lock-in count + last trade summary; no analysis]

## 📊 MES — Multi-TF (4H / 1H, overnight session)
## 📊 MNQ — same
## 📊 MGC — same

## F. 期货结构 / Futures Positioning (compact)
### F-MES / F-MNQ / F-MGC: settlement + OI Δ + basis (if cash open)

## 📰 Breaking News (past 4h)
- ...

## D. Pattern Archive
[Bar-by-bar pattern description per symbol; pattern_tags populated for future query]
[NO recommendation, NO narrative beyond fact statement]

## 📑 数据快照
- IBKR: ✓ ; Bars: ✓ ; News: ✓ N items
```

**Section order**: metadata → multi-TF → F → news → D archive → snapshot. **NO A, B, C** — pure description for the learning index.

## 7. Data flow timeline

### 7.1 Daily 06:00 PT → 23:00 PT timeline

```
06:00 PT  premarket auto-fire           [existing — UNCHANGED]
07:00 PT  intraday-4h-1 auto-fire       [NEW: read premarket plan, no retrospective]
11:00 PT  intraday-4h-2 auto-fire       [NEW: read premarket plan + full retrospective + sentiment refresh]
14:00 PT  eod auto-fire                  [existing — UNCHANGED]
19:00 PT  night auto-fire                [NEW: D-only archive, no Telegram]
23:00 PT  asia auto-fire                 [NEW: D-only archive, no Telegram]
```

### 7.2 4h-2 retrospective end-to-end (most complex new flow)

```
[orchestrator.run_intraday_4h_2(run_at)]
    │
    ▼
  idempotency check: already_generated_today("intraday-4h-2", date_et) ?
    │
    ▼
  StateDB insert pending row (report_type="intraday-4h-2")
    │
    ▼
  IBClient.connect() (clientId=1)
    │
    ▼
  IntradayFourHGenerator(config_4h_2).generate(context, date_et, ...)
    │
    ├─ _fetch_bars()                                  # 3 symbols × 3 TFs
    ├─ _fetch_f_section()                             # OI + basis + term + VP
    ├─ _fetch_news("past 5h")
    ├─ _maybe_fetch_sentiment()
    │   └─ SentimentSection(symbols, time_window="past 5h").collect()
    │       └─ subprocess(["claude", "-p", ...], timeout=240)  # I5
    ├─ _maybe_read_plan(date_et)
    │   └─ PremarketPlanReader.read_today_plan(date_et) → {C-MES: "...", C-MGC: "..."}
    ├─ _maybe_fetch_trades(date_et)
    │   └─ TodayTradesQuery.trades_for_date(date_et) → [trade1, trade2, ...]
    ├─ _maybe_compose_retrospective(plans, trades, date_et)
    │   ├─ retrospective.compose(plans, symbols, date_et, tick_sizes)
    │   │   └─ for each symbol → simulate_level(level, intraday_bars_5m, ...)
    │   │       └─ intraday_bar_fetcher = orchestrator._make_intraday_fetcher_4h_2()
    │   │           └─ closure: get_bars(timeframe="5m", bars=78,
    │   │                                end_time=date_et + 11:00 PT)  # C2-style
    │   ├─ retrospective.persist(rows)              # write plan_retrospective_daily
    │   └─ render markdown block
    ├─ _build_prompt(intraday-4h, ...)              # all inputs assembled
    ├─ ai_analyst.call(messages=prompt, max_tokens=12288)
    └─ validator.validate(text, report_type="intraday-4h")
    │
    ▼
  for w in outcome.warnings:
      state_db.log_failure(report_type="intraday-4h-2", stage=..., reason=..., 0)
    │
    ▼
  if validation.ok:
      ObsidianWriter.write_intraday_4h(date_et, "1100PT-4H2", text)
      ChartRenderer.render_all(...)        # best-effort
      PDFRenderer.render_to_pdf(...)       # best-effort
      TelegramPusher.push(text, charts, pdf)  # best-effort
      state_db.update_report_status(report_id, "success", ...)
      return PipelineResult(success=True, ...)
  else:
      state_db.update_report_status(report_id, "failed",
                                    failure_reason=f"validation: missing {missing}")
      return PipelineResult(success=False, ...)
```

### 7.3 night flow (simplest)

```
[orchestrator.run_night(run_at)]
    ├─ idempotency check
    ├─ insert pending
    ├─ IBClient.connect()
    ├─ NightAsiaGenerator(night_config).generate(...)
    │   ├─ _fetch_bars()           # 3 symbols × 2 TFs (4H, 1H)
    │   ├─ _fetch_f_section()
    │   ├─ _fetch_news("past 4h")
    │   ├─ (no sentiment / no plan read / no trades / no retrospective)
    │   ├─ _build_prompt(night_asia, ...)
    │   └─ AI call + validator
    ├─ warnings → state.failures
    ├─ ObsidianWriter.write_night_asia(date_et, "1900PT-night", text)
    │   (NO PDF, NO Telegram for night/asia)
    └─ update report status
```

## 8. Error handling

### 8.1 Failure modes

| # | Failure | Trigger | Handling | state.failures stage |
|---|---|---|---|---|
| F1 | TWS unavailable | preflight (port + handshake) catches | exit 0, macOS notify | (preflight logs) |
| F2 | Partial bars (<70%) | IBClient.get_bars warning | render with warning, continue | `bars_partial:<sym><tf>` |
| F3 | F section partial fail | basis/term/VP throws | "⚠️ data unavailable" inline, continue | `f_section:<type>:<msg>` |
| F4 | News fetch fail | webfetch/parse exception | "(no news)" inline, continue | `news:<type>:<msg>` |
| F5 | Sentiment fail (4h-2) | claude -p timeout | "⚠️ unavailable" inline + raw dump, continue | `sentiment:<type>:<msg>` |
| F6 | Plan missing (4h-1, 4h-2) | premarket file not found | "⚠️ premarket plan 未找到" in C section; 4h-2 retrospective also skipped | `plan_missing:<date>` |
| F7 | Retrospective fail (4h-2) | simulator/parser exception | "⚠️ retrospective failed: {exc}" inline, continue | `retrospective:<type>:<msg>` |
| F8 | AI call fail | claude -p timeout / non-zero exit | hard fail: report row failed, exit 1 | (reports.failure_reason) |
| F9 | Validator fail | required sections missing | hard fail: report row failed, exit 1 | (reports.failure_reason) |
| F10 | Obsidian write fail | vault path missing / perm | fallback to data/exports/, warn | `obsidian:fallback:<path>` |
| F11 | Telegram push fail (4h only) | bot token / network | warn, **no impact on report status** | `telegram:<type>:<msg>` |

**Hard failures** (F8/F9): launchd exit non-zero → macOS error notification → user must investigate.
**Soft degradations** (F1-F7, F10, F11): launchd exit 0, report still ships, warnings persisted to state.failures for later audit.

### 8.2 night/asia specific notes

- Telegram OFF — F11 N/A
- No sentiment / plan read / retrospective — F5/F6/F7 N/A
- D-only template — fewer required sections in validator → less F9 risk

## 9. Testing strategy

### 9.1 Test layers (~80 new tests)

| Layer | Module | Pattern | New tests |
|---|---|---|---|
| L1 | base.py | unit + dummy subclass | ~12 |
| L2 | intraday_4h.py | unit + mock IBClient/AI | ~14 |
| L3 | night_asia.py | unit + mock | ~10 |
| L4 | prompt_builder.py | unit + golden text | +6 (extend) |
| L5 | output_validator.py | unit | +6 (extend) |
| L6 | obsidian_writer.py | unit + tmp_path | +6 (extend) |
| L7 | orchestrator.py | integration + full mock stack | +16 (extend) |
| L8 | cli/reports.py | E2E subprocess | +4 (extend) |
| L9 | scripts/run_*_launchd.sh | shell + plist parse | ~6 |

### 9.2 Mock fixtures (reuse Phase 5 pattern)

```python
fake_ib = MagicMock()
fake_ib.get_bars.return_value = [_ohlcv(...)]
fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

fake_ai = MagicMock()
fake_ai.call.return_value = _ai_result(text=VALID_INTRADAY_4H_REPORT)

# Reuse from tests/reports/test_orchestrator.py:
@pytest.fixture(autouse=True)
def _mock_sentiment_section():
    with patch("daytrader.reports.core.orchestrator.SentimentSection") as m:
        m.return_value.collect.return_value = SentimentResult.unavailable_due_to("test")
        m.return_value.render.return_value = "## D. 情绪面\n⚠️ test mock\n"
        yield m
```

### 9.3 Golden text fixtures

- `VALID_INTRADAY_4H_REPORT` — 8-section text passing intraday-4h validator
- `VALID_NIGHT_ASIA_REPORT` — 5-section text passing night/asia validator
- For each, `_MISSING_<SECTION>` variants to test validator catches absence

### 9.4 Live e2e (slow-marked, opt-in)

```python
# tests/reports/integration/test_intraday_4h_live.py
@pytest.mark.slow
def test_intraday_4h_2_live_e2e_runs_to_obsidian():
    """Requires TWS + claude CLI + Pro Max sub. Manual run before ship."""
    ...
```

### 9.5 Regression invariants

- Every commit: `pytest tests/ -q --tb=line` ≥ 538 green
- After all tasks: `pytest tests/` ≥ 620 green
- Pre-commit: `git diff --name-only HEAD | grep -E "premarket\.py|eod\.py" && exit 1`
  to block accidental writes to UNCHANGED files

## 10. launchd integration

### 10.1 Final 6-cadence schedule

| Label | Time | Weekday | Wrapper | Telegram |
|---|---|---|---|---|
| `com.daytrader.report.premarket.0600pt` | 06:00 PT | 1-5 | run_premarket_launchd.sh | ✅ |
| `com.daytrader.report.intraday-4h-1.0700pt` | 07:00 PT | 1-5 | **run_intraday_4h_1_launchd.sh** | ✅ |
| `com.daytrader.report.intraday-4h-2.1100pt` | 11:00 PT | 1-5 | **run_intraday_4h_2_launchd.sh** | ✅ |
| `com.daytrader.report.eod.1400pt` | 14:00 PT | 1-5 | run_eod_launchd.sh | ✅ |
| `com.daytrader.report.night.1900pt` | 19:00 PT | 1-5 | **run_night_launchd.sh** | ❌ |
| `com.daytrader.report.asia.2300pt` | 23:00 PT | 1-5 | **run_asia_launchd.sh** | ❌ |

(plus `com.daytrader.report.weekly.sun1400pt` Sunday-only)

### 10.2 Wrapper script template

```bash
#!/usr/bin/env bash
# scripts/run_<cadence>_launchd.sh — sourced from EOD pattern (49693d2)
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || exit 0

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/<cadence>-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_<cadence>_launchd] start $(date -Iseconds)"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_<cadence>_launchd] PREFLIGHT FAILED"
    osascript -e 'display notification "<cadence> preflight failed" with title "DayTrader" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

uv run daytrader reports run --type <cadence> --no-pdf
rc=$?
echo "[run_<cadence>_launchd] reports run exit=$rc"
exit "$rc"
```

### 10.3 Install / uninstall scripts

`install_intraday_4h_launchd.sh` installs both 4h-1 and 4h-2 plists in one call.
`install_night_asia_launchd.sh` installs both night and asia.
Symmetric uninstall scripts.

All sourced from `scripts/install_launchd.sh` (Phase 7 v1) + `scripts/install_eod_launchd.sh` (Phase 5 T11) patterns. Idempotent: bootout existing first → cp template → bootstrap.

### 10.4 .gitignore

```
data/logs/launchd/intraday-4h-1-*.log
data/logs/launchd/intraday-4h-2-*.log
data/logs/launchd/night-*.log
data/logs/launchd/asia-*.log
```

## 11. Files inventory (~3500 LOC total)

### 11.1 New source files (~1700 LOC)

| File | LOC |
|---|---|
| src/daytrader/reports/types/base.py | 350 |
| src/daytrader/reports/types/intraday_4h.py | 400 |
| src/daytrader/reports/types/night_asia.py | 250 |
| src/daytrader/reports/templates/intraday_4h.md | 80 |
| src/daytrader/reports/templates/night_asia.md | 50 |

### 11.2 Modified existing files (additive only, ~650 LOC)

| File | Diff type | LOC added |
|---|---|---|
| src/daytrader/reports/core/prompt_builder.py | +build_intraday_4h, +build_night_asia | +200 |
| src/daytrader/reports/core/output_validator.py | +REQUIRED_SECTIONS["intraday-4h"], ["night"], ["asia"] | +50 |
| src/daytrader/reports/core/orchestrator.py | +run_intraday_4h_1, +run_intraday_4h_2, +run_night, +run_asia, +_run_cadence | +340 |
| src/daytrader/reports/delivery/obsidian_writer.py | +write_intraday_4h, +write_night_asia | +60 |
| src/daytrader/cli/reports.py | extend run_cmd dispatch | +30 |

### 11.3 New tests (~1500 LOC, ~80 tests)

| File | tests |
|---|---|
| tests/reports/types/test_base_generator.py | ~12 |
| tests/reports/types/test_intraday_4h_generator.py | ~14 |
| tests/reports/types/test_night_asia_generator.py | ~10 |
| tests/reports/test_prompt_builder.py | +6 |
| tests/reports/test_output_validator.py | +6 |
| tests/reports/test_obsidian_writer.py | +6 |
| tests/reports/test_orchestrator.py | +16 |
| tests/cli/test_reports_cli.py | +4 |
| tests/scripts/test_intraday_4h_launchd.py | ~3 |
| tests/scripts/test_night_asia_launchd.py | ~3 |

### 11.4 Launchd files (~400 LOC)

| File | LOC |
|---|---|
| scripts/run_intraday_4h_1_launchd.sh | 50 |
| scripts/run_intraday_4h_2_launchd.sh | 50 |
| scripts/run_night_launchd.sh | 50 |
| scripts/run_asia_launchd.sh | 50 |
| scripts/launchd/com.daytrader.report.intraday-4h-1.0700pt.plist.template | 40 |
| scripts/launchd/com.daytrader.report.intraday-4h-2.1100pt.plist.template | 40 |
| scripts/launchd/com.daytrader.report.night.1900pt.plist.template | 40 |
| scripts/launchd/com.daytrader.report.asia.2300pt.plist.template | 40 |
| scripts/install_intraday_4h_launchd.sh | 50 |
| scripts/install_night_asia_launchd.sh | 50 |
| scripts/uninstall_intraday_4h_launchd.sh | 30 |
| scripts/uninstall_night_asia_launchd.sh | 30 |

### 11.5 Docs

- docs/ops/intraday-4h-runbook.md (NEW, ~300 LOC)
- docs/ops/night-asia-runbook.md (NEW, ~250 LOC)
- This spec doc

### 11.6 ABSOLUTE NO-TOUCH list

- src/daytrader/reports/types/premarket.py
- src/daytrader/reports/types/eod.py
- src/daytrader/reports/templates/premarket.md
- src/daytrader/reports/templates/eod.md
- src/daytrader/reports/core/prompt_builder.py `build_premarket()` / `build_eod()` methods
- src/daytrader/reports/core/output_validator.py existing REQUIRED_SECTIONS["premarket"] / ["eod"]
- src/daytrader/reports/core/orchestrator.py existing run_premarket / run_eod methods
- src/daytrader/reports/delivery/obsidian_writer.py existing write_premarket / write_eod
- scripts/preflight_check.py
- scripts/run_premarket_launchd.sh
- scripts/run_eod_launchd.sh
- All existing tests under tests/premarket/, tests/reports/eod/

## 12. Acceptance criteria

### A. Functional correctness

- [ ] A1. `daytrader reports dry-run --type intraday-4h-1` / `intraday-4h-2` / `night` / `asia` exit 0
- [ ] A2. `daytrader reports run --type intraday-4h-1` writes Obsidian `Daily/<date>-0700PT-4H1.md`
- [ ] A3. Same for 4h-2 (`<date>-1100PT-4H2.md`), night (`<date>-1900PT-night.md`), asia (`<date>-2300PT-asia.md`)
- [ ] A4. Same-day repeat returns `skipped_idempotent=True`
- [ ] A5. 4h-2 contains `## 🔄 Plan Retrospective`, persists row to `plan_retrospective_daily`
- [ ] A6. 4h-1 does NOT contain retrospective section (shows "下次复盘 4h-2")
- [ ] A7. 4h-2 D段 sentiment refreshed (time_window="past 5h"); 4h-1 reuses premarket sentiment text
- [ ] A8. night/asia have NO A/B/C/sentiment sections — only metadata + multi-TF + F + news + D archive

### B. Validation

- [ ] B1. OutputValidator on full intraday-4h report → ok=True; missing any required → ok=False
- [ ] B2. Same for night, asia
- [ ] B3. Length: intraday-4h 5-7K chars; night/asia 3.5-5K
- [ ] B4. C section before A section in intraday-4h template (master spec §3.6 fixed order)

### C. Error handling

- [ ] C1. 4h-1 with missing premarket plan → graceful "⚠️ plan 未找到", continues
- [ ] C2. 4h-2 retrospective ValueError → markdown degraded + state.failures row (I1 pattern)
- [ ] C3. F section partial fail → degraded inline, warnings persisted
- [ ] C4. Validator fail → report row status="failed", failure_reason has missing sections
- [ ] C5. Obsidian vault unavailable → fallback to data/exports/

### D. Test coverage

- [ ] D1. `pytest tests/` ≥ 620 passed (538 base + ~80 new + buffer)
- [ ] D2. **0 existing tests broken** — 538 base all green
- [ ] D3. Each new generator: ≥ 10 unit tests
- [ ] D4. Orchestrator integration tests cover all 4 new cadences × idempotency / validation-fail / Telegram-disabled paths

### E. System integration

- [ ] E1. After install scripts run: `launchctl list | grep daytrader` shows 7 jobs
- [ ] E2. Install/uninstall scripts idempotent
- [ ] E3. All 4 wrappers match EOD wrapper pattern (PATH / cd / preflight / tee)
- [ ] E4. launchd fires produce log files under `data/logs/launchd/<cadence>-<TS>.log`, 0-byte stderr on success
- [ ] E5. preflight failure → macOS notification + exit 0

### F. Documentation

- [ ] F1. Spec doc updated to status=Implemented at completion
- [ ] F2. Plan doc each task ✅
- [ ] F3. `docs/ops/intraday-4h-runbook.md` complete
- [ ] F4. `docs/ops/night-asia-runbook.md` complete
- [ ] F5. README/master spec cadence table shows 6 implemented + 1 pending (weekly)

### G. Regression boundary (NO-TOUCH)

- [ ] G1. `git diff src/daytrader/reports/types/premarket.py` empty
- [ ] G2. `git diff src/daytrader/reports/types/eod.py` empty
- [ ] G3. `tests/reports/eod/` only additive (no existing test modified)
- [ ] G4. `git diff tests/premarket/` empty
- [ ] G5. `git diff scripts/preflight_check.py` empty
- [ ] G6. `prompt_builder.build_premarket` / `build_eod` unchanged
- [ ] G7. `output_validator.REQUIRED_SECTIONS["premarket"]` / `["eod"]` unchanged
- [ ] G8. `orchestrator.run_premarket` / `run_eod` unchanged

## 13. Decision Records

Decisions made via brainstorming Q&A 2026-05-05:

| # | Question | Decision | Rationale |
|---|---|---|---|
| DR-1 | Plan Retrospective scope | **B**: 4h-2 only (skip 4h-1, defer to EOD too) | 4h-1 at 07:00 PT only 30min into RTH — too few level touches; 4h-2 at 11:00 PT has 4.5h of data, retrospective is meaningful |
| DR-2 | Sentiment refresh scope | **B**: 4h-2 only refresh, 4h-1 reuses premarket | Saves ~120s subprocess cost on 4h-1 (low value); 4h-2 covers post-open intraday news |
| DR-3 | Trade Archive in 4h | **B**: light list both, full audit only EOD | A段 needs to know "已成交几笔"; full §6/§9 audit is EOD's differentiator |
| DR-4 | launchd auto-fire | **A**: all 4 auto-fire Mon-Fri | Master spec default; user explicitly chose over manual-only |
| DR-5 | Phase scope | **B**: all 4 cadences (4h + night + asia) together | One refactor pass, one base class, one phase — better than splitting |
| DR-6 | Architecture | **B**: refactor BaseCadenceGenerator + 4 new cadences only | At N=3 trigger per Phase 5 spec; deduped scaffolding |
| DR-7 | Refactor scope guard | UNCHANGED premarket/EOD | User constraint "不要影响已实现的功能" — Phase 5.6 retrofits |

## 14. Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | BaseCadenceGenerator abstraction wrong, can't fit night/asia D-only | Medium | Hooks default to empty/skip; subclass override only what differs. Verified by Q3 (D-only ≠ A+B+C strictly subtractive) |
| R2 | 4h-1 / 4h-2 config divergence grows beyond 4 booleans → IntradayFourHConfig becomes messy | Medium | YAGNI — start with current 4 fields; refactor to subclass split if N=8+ flags |
| R3 | TWS client_id=1 conflict with user's manual ib_insync usage during 4h triggers | Low | preflight uses 999 sentinel; user's TWS UI doesn't use API; document warning in runbook |
| R4 | Sentiment subprocess at 11:00 PT hits subscription rate limit (multiple Pro Max calls per day) | Low | Pro Max is unlimited; observed ≤ 6 daily calls (premarket + 4h-2 + EOD + future cadences); budget OK |
| R5 | BaseCadenceGenerator abstract class makes orchestrator code less greppable | Low | Type hints + clear method names; runbook documents which cadence uses which generator |
| R6 | night/asia auto-fire at 19:00 / 23:00 wakes user (TWS notification, terminal output) | Low | No Telegram for night/asia; tee log goes to file not stdout; macOS notify only on preflight fail |
| R7 | Plan retrospective end_time fixture (11:00 PT) wrong on DST transitions | Low | Use ET 14:00 directly via zoneinfo, not PT clock; same as C2 fix pattern |

## 15. Future enhancements (post-Phase 5.5)

- **Phase 5.6**: retrofit premarket / EOD to BaseCadenceGenerator (post-Trade-#1)
- **Phase 5.7**: weekly cadence rewrite via base class (current weekly is independent legacy code)
- **Phase 6**: D-only learning index queries (the entire reason night/asia exist — pattern_tags + news_event_tags become the data foundation for "all bullish_engulf at support_test in last 30 days")
- **Phase 7**: cross-cadence aggregation Obsidian dashboard
- **Phase 8**: real-time level-breach push notifications

## 16. Migration path

This phase is **purely additive** — no migration concerns:

- Existing premarket / EOD / weekly cadences keep firing unchanged
- Existing reports/ table accommodates new report_types ("intraday-4h-1", "intraday-4h-2", "night", "asia") — no schema change
- `plan_retrospective_daily` table accepts 4h-2 rows alongside EOD rows — no schema change (UNIQUE(date, symbol) — but 4h-2 and EOD use different report_type? wait — need ON CONFLICT design)

**ON CONFLICT design check**: `plan_retrospective_daily` has UNIQUE(date, symbol). EOD writes one row per (date, symbol). 4h-2 also writes one row per (date, symbol). If 4h-2 fires at 11:00 PT and EOD at 14:00 PT same day, EOD's row will OVERWRITE 4h-2's via ON CONFLICT DO UPDATE.

This is **intentional** — EOD has the more complete picture (full RTH session) so its data should win. Implementation must preserve this: don't add a `cadence` discriminator to the UNIQUE constraint.

Trace path: 4h-2 11:00 PT writes row → user sees it in 4h-2 report → EOD 14:00 PT overwrites with newer/more-complete data → EOD report shows updated row → user sees latest in EOD. The transient 4h-2 row is captured in the 4h-2 report's markdown, not lost.

## 17. Status

- 2026-05-05: Spec drafted, brainstorming complete (Q1-Q5 + 8 design sections + DR-1 through DR-7).
- Pending: writing-plans.

---

**End of spec.**
