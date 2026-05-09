# Reports System — Design Spec

**Date:** 2026-04-25
**Status:** Draft (awaiting user review)
**Scope:** Multi-timeframe, multi-instrument, multi-cadence trading report system with Telegram + Obsidian distribution
**Replaces:** No prior design (extends existing `premarket/` one-shot daily flow)
**Supersedes parts of:** None — `premarket/` and `journal/` modules unchanged

---

## 0. Overview

This spec extends the existing `premarket/` "one daily report" flow into a recurring, multi-cadence reports system covering the full trading week:

- **31 reports per week** (Mon-Thu × 6, Fri × 4, Sun × 3)
- **Multi-timeframe AI analysis** (M / W / D / 4H / 1H, scoped per report type)
- **Three trading instruments**: MES (S&P), MNQ (Nasdaq), MGC (Gold) — full trading focus on all three
- **Futures-specific positioning data**: Open Interest, COT, basis, term structure, volume profile
- **Structured A/B/C/D usage**: decision aid + market narrative + plan recheck + learning archive
- **Dual distribution**: Obsidian (full archive) + Telegram (multi-message + PDF attachment)
- **Contract.md integration**: lock-in progress visible in every report; plan re-check anchored to user's own plan

The system is designed for the user's **30-trade discretionary lock-in** phase following W2 bake-off closure (S1 family closed 2026-04-22).

---

## 1. Goals & Scope

### 1.1 Goals

- Automate generation of 31 reports/week with zero manual intervention
- Each report serves a defined purpose (A/B/C/D mix, see §2.2)
- Multi-TF analysis scoped per report type (no boilerplate dilution)
- Multi-instrument coverage (MES + MNQ + MGC) with futures-specific positioning data
- Telegram + Obsidian distribution, both consistent and observable
- Contract.md and journal integration (read-only)
- Total monthly cost ~$140-170 (full Opus 4.7, all 3 instruments)

### 1.2 Non-Goals

| Out of scope | Reason |
|---|---|
| Mechanical trade signal generation | W2 closed S1 family; this is discretionary aid, not strategy |
| Automatic order execution | No IBKR trade endpoint integration; market data only |
| Tick-by-tick or sub-minute alerts | Discrete triggers (4H bar close + session anchors) |
| Modifications to `journal/` subsystem | Read-only integration via existing journal API |
| New mechanical strategy bake-off | W2 closed; not opening new mechanical track |
| Lock-in mode push-side guardrails | User explicitly declined (see §7 risk record) |
| Renaming or restructuring `premarket/` | Avoids regression in shipped code |

### 1.3 Success Criteria

The system is "done" when all of the following hold:

1. **Automation**: 6 daily report times run end-to-end without human intervention; IB Gateway + launchd long-run stable
2. **Content correctness**: Each report follows its defined template (per §3); multi-TF scope correct per type
3. **Distribution reliability**: Telegram push and Obsidian write are 100% consistent; no silent failures
4. **Contract integration**: Every report shows lock-in progress (X/30); C section quotes Contract.md verbatim
5. **Observability**: Failures produce Telegram alerts; logs are queryable; weekly health digest auto-generated
6. **Reversibility**: `premarket/` and `journal/` are unchanged; new code can be removed cleanly

### 1.4 Constraints

- **No interface changes** to `premarket/`, `journal/`, `core/config.py`
- **AI**: Claude Opus 4.7 for all reports (no model tiering), with prompt caching
- **Time zones**: internal UTC, market logic ET, display ET+PT dual-label
- **Scheduling**: launchd with fixed PT clock times (US/Canada DST synchronized between PT and ET)
- **Data source**: IBKR API + ib_insync + user's existing CME real-time subscription

---

## 2. Schedule & Purpose Matrix

### 2.1 Weekly Calendar

| Day | 06:00 | 07:00 | 11:00 | 14:00 | 19:00 | 23:00 | Total |
|---|---|---|---|---|---|---|---|
| Mon | premarket | 4H#1 | 4H#2 | EOD | night | asia | 6 |
| Tue | premarket | 4H#1 | 4H#2 | EOD | night | asia | 6 |
| Wed | premarket | 4H#1 | 4H#2 | EOD | night | asia | 6 |
| Thu | premarket | 4H#1 | 4H#2 | EOD | night | asia | 6 |
| Fri | premarket | 4H#1 | 4H#2 | EOD | — | — | 4 |
| Sat | — | — | — | — | — | — | 0 |
| Sun | — | — | — | **weekly** | night | asia | 3 |
| | | | | | | **Total** | **31** |

All times Pacific Time (PT). PT/ET both observe US DST (synchronized since 2007), so PT clock is stable year-round relative to ET (always +3h ET).

### 2.2 Per-Report Definition

| Report | PT | ET | Trigger | Purpose | A form | Multi-TF | Length | Telegram | Filename |
|---|---|---|---|---|---|---|---|---|---|
| premarket | 06:00 | 09:00 | session anchor (30min before US open) | A+B+C | A-2+A-3 | W+D+4H+1H | 9-12K chars | ✅ | `YYYY-MM-DD-premarket.md` |
| intraday-4h-1 | 07:00 | 10:00 | 4H bar close | A+B+C | A-2+A-3 | D+4H+1H | 5-7K | ✅ | `YYYY-MM-DD-0700PT-4H1.md` |
| intraday-4h-2 | 11:00 | 14:00 | 4H bar close | A+B+C | A-2+A-3 | D+4H+1H | 5-7K | ✅ | `YYYY-MM-DD-1100PT-4H2.md` |
| eod | 14:00 | 17:00 | futures session close | C+D | — | W+D+4H | 6.5-9K | ✅ | `YYYY-MM-DD-eod.md` |
| night | 19:00 | 22:00 | 4H bar close (new session bar 1) | D | — | 4H+1H | 3.5-5K | ❌ | `YYYY-MM-DD-night-1900PT.md` |
| asia | 23:00 | 02:00+1 | 4H bar close (new session bar 2) | D | — | 4H+1H | 3.5-5K | ❌ | `YYYY-MM-DD-night-2300PT.md` |
| weekly | 14:00 (Sun) | 17:00 (Sun) | session anchor (futures Sun open -1h) | A+B | A-2+A-3 | M+W+D+4H | 12-18K | ✅ | `YYYY-WW-weekly.md` |

**Filename time zone**: ET date (the market's "today"). Aligns with existing Obsidian daily-folder convention.

### 2.3 Purpose Templates (Content Obligations)

| Purpose | Must include | Forbidden |
|---|---|---|
| A (decision aid) | Current price vs key levels; trigger conditions; scenario matrix when A-2 escalates | Direct "buy now / sell now" calls (A-1 form is permanently disabled) |
| B (market narrative) | Past period events; pattern description; news; sectors; VIX | Forward-looking directional predictions |
| C (plan recheck) | Verbatim quote of today/this-week's plan; invalidation status; R progress | New plan formulation; restating the plan |
| D (learning archive) | Pattern classification tags; news event tags; data archive in frontmatter | Direct signals to reader |

### 2.4 Lock-In Progress Metadata Block

Every report begins with a metadata block **regardless of A/B/C/D mix**:

```
─────────────────────────────────
📋 Contract.md status
   Setup: [setup name from Contract]
   R-unit: $[X] per R
   Lock-in: [N] / 30 trades complete
   Per-instrument: MES [n1], MNQ [n2], MGC [n3]
   Last trade: 2026-04-23 (-0.5R)
   Streak: 2L1W in last 5
─────────────────────────────────
```

This is the minimal-form guardrail. The user explicitly declined "suppress A in lock-in" but every report shows their lock-in position. If they see "Streak: 5L0W", the report doesn't block the next trade, but the data is in front of them.

### 2.5 Trigger Semantics

Triggers fire on real market events, not wall-clock alone:

| Type | Condition | Latency tolerance | Failure fallback |
|---|---|---|---|
| 4H bar close (07/11/19/23 PT) | IB receives final tick of bar + bar marked closed | 0-30s | Wait up to 5 min, else use most recent available bar with warning |
| Session anchor (06/14 PT, Sun 14 PT) | wall-clock hit | <1s | Retry 3× then alert |

**Why this matters**: 4H bar close occasionally arrives 10-30 seconds late from CME via IB. Waiting on `bar.closed=True` ensures pattern analysis sees the complete bar.

### 2.6 DST Handling

- launchd plists use fixed PT clock times
- US/Canada DST: PT and ET switch on the same dates → ET offset always = PT + 3h
- IB Gateway timestamps are UTC internally, so no DST confusion in stored data

### 2.7 Failure Matrix

| Failure | Action |
|---|---|
| IB Gateway connection fails | Wait up to 5 min for reconnect; if still fails, Telegram alert + skip report + log failure |
| News source down | Mark "news data unavailable" section; other sections proceed normally |
| Anthropic API timeout | Retry 3× exponential backoff; final failure → Telegram alert; **never degrade to truncated report** |
| Telegram push fails | Retry 3×; final failure → write Obsidian error log + queue for retry on next launch |
| Obsidian write fails | Retry 3× → fallback to `data/exports/` + Telegram alert |
| PDF render fails | Push markdown messages without PDF + alert noting PDF missing |

**Core principle**: "Better no report than wrong report." A is the most dangerous content; a malformed A is worse than a missing one.

---

## 3. Multi-TF Content + A/B/C Templates

### 3.1 Per-TF Analysis Block (reusable building block)

Every TF in every report uses this structure:

```markdown
### {TF} {bar end time ET / PT}

**OHLCV**: O 5240.00 | H 5252.50 | L 5238.25 | C 5246.75 | V 142,830 | Range 14.25 (1.7×ATR-20)
**Pattern**: bullish engulf swallowing prior down-shadow
**Position**: uptrend; above day VWAP; above weekly 200-EMA
**Key levels (this TF)**: R 5252.50 (today high) / S 5238.25 (today low)
**HTF consistency**: 4H trend aligned ✓ / D trend aligned ✓
**Source**: IBKR MES1! continuous, last close 2026-04-25 14:00 ET
```

Same fields filled the same way every report → user develops scanning habit, cross-day comparison fast.

### 3.2 A Template (Decision Aid, A-2 + A-3 mixed)

A defaults to **A-3 (conservative)**. **Escalates to A-2 (scenario matrix)** only when ANY of:

- An invalidation condition for the day's plan is triggered
- Current price within 0.25R of any key level
- Breaking news with material market-moving impact (FOMC / CPI / major earnings / geopolitical)
- Most recent 4H bar shows a high-confidence pattern (engulfing / pin bar / breakout)

**A-3 form (default)**:

```markdown
### A. Recommendation

No action recommended — continue executing your 06:00 PT plan.

Reasoning:
- All invalidation conditions remain inactive
- Price > 0.25R from all key levels
- No market-moving news
- 4H pattern aligned with premarket thesis
```

**A-2 form (escalated)**:

```markdown
### A. Recommendation

⚠️ Plan assumption status: partially changed (4H showing bearish engulf)

Scenario matrix:
- IF price holds above 5238 + 1H turns up → 4H is a fakeout, original plan still valid; continue holding
- IF price breaks 5238 + volume expands → trend may reverse; execute stop at 5232 per plan
- IF 5240-5246 chops → wait, no add no trim

Do not: adjust position before any of the above conditions confirm.
```

**A-1 (direct "buy now / sell now" call) is permanently disabled.**

### 3.3 B Template (Market Narrative)

```markdown
### B. Past 4-hour Market Narrative

**Price**: MES from 5240 up to 5246, did not test today's high 5252. SPY +0.32%, QQQ +0.45% (risk-on).
**Sectors**: Tech +0.6% leading, financials +0.3%, energy -0.2% (rotation into risk).
**Risk**: VIX 14.2 (below 20-day avg 15.8), credit spreads stable.
**Events**: 10:00 ET PMI 49.8 (consensus 49.5), modestly above.
**Asia/Europe spillover**: European stocks closed up (DAX +0.5%), Asia mixed, DXY 104.2.

**Narrative synthesis**: risk-on continuation, no catalyst changing direction, ranging into afternoon.
```

**Hard constraint**: B describes the past only. AI saying "market may..." → fails validation, retry.

### 3.4 C Template (Plan Recheck)

```markdown
### C. Plan Recheck

**Today's plan (from 06:00 PT premarket report)**:
> Long setup: MES at 5240, stop 5232 (-1R = -$8/contract = -$8 R-unit), target 5256 (+2R)

**Current state**:
- Current price: 5246.75 (+0.84R unrealized)
- Distance to stop: 14.75 pt (far)
- Distance to target: 9.25 pt
- Time in position: 03:12 (entered 11:00 PT)

**Invalidation checks**:
- ① Break below 5232 → ❌ not triggered (current 5246.75)
- ② SPY break below 580 → ❌ not triggered (current 581.40)
- ③ VIX above 18 → ❌ not triggered (current 14.2)

**Conclusion**: Plan remains fully valid. Continue per plan.

**Lock-in progress**: 7 / 30 trades, +1.5R cumulative this week
```

**Hard constraint**: C must **verbatim quote** today's plan parameters. AI may not paraphrase.

### 3.5 D Template (Learning Archive)

D writes structured tags into Obsidian frontmatter + brief body. Not for "now"-reading; for future retrieval.

```yaml
---
type: night-report
date: 2026-04-25
session: asia
tf_primary: 4H
patterns:
  - name: bullish_engulf
    tf: 4H
    location: support_test
    confidence: medium
news_events:
  - tag: jp_yen_intervention
    impact: minor
    timestamp: 2026-04-25T22:30:00Z
key_levels:
  R: [5252.50, 5260.00]
  S: [5238.25, 5230.00]
---
```

D body is brief: bar data + pattern description + news summary. **No A or C section**.

**Future use**: 30 days later, query "all bullish_engulf at support_test in last month, how did next-day US session play out?" — this is the data foundation for any future mechanical strategy research, not current decision input.

### 3.6 Standard Report Skeleton (intraday-4h-1 example)

```markdown
---
type: intraday-4h
date: 2026-04-25
time_pt: "07:00"
time_et: "10:00"
trigger: 4h_bar_close
tf_coverage: [D, 4H, 1H]
sections: [A, B, C, F]
instruments: [MES, MNQ, MGC]
---

# Intraday 4H Report #1 · 2026-04-25 07:00 PT (10:00 ET)

## 📋 Contract.md status
[Lock-in metadata block per §2.4]

## Multi-TF Analysis

### 📊 MES (S&P)
#### D / 4H / 1H [each per §3.1 template]

### 📊 MNQ (Nasdaq)
#### D / 4H / 1H

### 📊 MGC (Gold)
#### D / 4H / 1H

## F. Futures Structure (Positioning)
### MES: OI Δ + Basis + Term + Volume Profile + AI long/short interpretation
### MNQ: same
### MGC: same

## News (past 4h)
- [news 1 + impact assessment]
- [news 2 + impact assessment]

## C. Plan Recheck
[per §3.4, one C block per instrument]

## B. Market Narrative
[per §3.3]

## A. Recommendation
[per §3.2; A-3 default; A-2 escalation if triggered]
[Mixed form A.3: each instrument has mini-A inside F section; main A is cross-instrument integration]

## Data Snapshot
- IBKR connection: ✓ healthy
- Bars fetched: D / 4H / 1H ✓ (all 3 instruments)
- News source: ✓ N items
- Anthropic web search: ✓ M items
```

**Section order is fixed**: metadata → multi-TF (facts) → futures structure → news → C (your old plan) → B (narrative) → A (recommendation) → data snapshot.

**Why this order**: user reads "my own plan status" (C) before seeing "AI's new recommendation" (A). Structurally enforces self-anchored thinking.

### 3.7 Per-Type Skeleton Diffs

| Report | Diff from §3.6 skeleton |
|---|---|
| premarket 06:00 | Adds W section; adds economic calendar; C section is **plan formation** (no prior daily plan to recheck, but references prior weekly thesis) |
| intraday-4h-1/2 | Uses §3.6 as-is |
| eod 14:00 | Removes A section; C is "today's plan adherence assessment"; adds D section (today's trade archive); adds tomorrow setup prep (raw, not plan) |
| weekly Sun | Adds M section; removes 1H; removes per-day C (no daily plan recheck); D section is full week archive; A is "next week scenario map" |
| night/asia D | Removes A, B, C; only multi-TF + news + D frontmatter |

### 3.8 F. Futures Structure (Positioning) per Instrument

Every non-D report includes the F section:

```markdown
### MES (S&P)
- Settlement: 5246.75 (yesterday 5240.50, +6.25 / +0.12%)
- OI: 2,143,820 (Δ +12,430 vs yesterday, +0.6%)
- OI signal: price up + OI up → genuine new long inflow ✓
- Basis (MES − SPX): +0.5 pt (normal range −2 to +3) → neutral
- Term structure: Jun 5246.75 / Sep 5252.00 / Dec 5258.50 → mild contango, normal carry
- Volume Profile (today, RTH): POC 5244 | VAH 5249 | VAL 5240
  - current 5246.75 above POC, below VAH → "upper edge of fair value"

**AI long/short interpretation**:
Price +0.3% + OI +0.6% + neutral basis + price above POC = **new long capital genuinely inflowing, trend continuation probability moderately high**.
COT (week ending [Tue release date], latest CFTC publication): non-commercial net long +5% vs prior week, third consecutive weekly increase, institutional sentiment bullish.
Term structure: mild contango, no stress signal.
**Synthesis**: bullish positioning (strength: medium).
```

Same template for MNQ and MGC. AI interpretation is one short paragraph synthesizing all positioning data.

**COT data freshness note**: CFTC publishes the COT report Friday afternoon ET (covering positions through Tuesday close of the same week). Reports must always cite the **publication date** of the COT data being referenced, not "today's" COT. Across the trading week, the same COT snapshot is referenced from Friday's release through the following Friday's release. Sunday weekly report is the natural place for COT delta narrative; intraday reports cite the same snapshot more briefly.

### 3.9 Output Language

All reports in **Chinese (user's first language)**, with:
- Technical terms preserved in English (VWAP, EMA, ATR, OI, POC, etc.)
- Numbers in ASCII (5246.75, not 五千二百四十六点七五)
- Section labels A/B/C/D/F preserved in English (already in user's mental model)

### 3.10 Length Limits

Each report has hard upper limit; AI compression behavior on overflow:

| Report | Limit (chars) | Compression on overflow |
|---|---|---|
| premarket | 12,000 | Compress B (bullets); preserve A/C/multi-TF/F |
| intraday-4h | 7,000 | Compress 1H section; preserve 4H + A/B/C/F |
| eod | 9,000 | Compress W; preserve D + today |
| weekly | 18,000 | Compress 4H section; preserve M/W/D main thread |
| night/asia D | 5,000 | No compression — overflow indicates data anomaly |

Overflow triggers a flag in the SQLite `reports` table for prompt review.

---

## 4. Data Layer + AI Layer

### 4.1 IBKR Data Layer

#### 4.1.1 Runtime Architecture

```
┌─────────────────────────────────────────────┐
│  User's Mac (24/7 always on)                │
│                                              │
│  ┌──────────────┐    ┌─────────────────┐    │
│  │ IB Gateway   │ ←→ │ ib_insync       │    │
│  │ (long-run    │    │ (Python client) │    │
│  │  via IBC)    │    └─────────────────┘    │
│  └──────────────┘             ↓              │
│         ↓               core/ib_client.py   │
│   CME GLBX feed         (singleton +        │
│   (user's CME           reconnect)          │
│    real-time sub)                           │
└─────────────────────────────────────────────┘
```

- **IB Gateway** (not TWS): headless, lightweight, designed for long-running API
- Managed by **IBC (IB Controller)**: open-source auto-login wrapper, handles daily logout/reconnect
- launchd plist `com.daytrader.ibgateway` keeps it alive (KeepAlive=true)
- Weekend behavior: futures pause Fri 14:00 PT — Sun 15:00 PT, IB Gateway can idle; report scripts reconnect on Sunday before weekly report

#### 4.1.2 `core/ib_client.py` Interface

`IBClient` is the **minimal core** — only generic market-data methods. Futures-specific extensions (OI, term structure, settlement) live in `reports/futures_data/ib_extensions.py` as module-level functions that accept an `IBClient` instance.

```python
class IBClient:
    """Singleton ib_insync wrapper, reused across reports.
    Generic market-data only; futures-specific helpers in
    reports/futures_data/ib_extensions.py."""

    def get_bars(
        self,
        symbol: str,                                # MES | MNQ | MGC
        contract: str = "continuous",               # MES1!/MNQ1!/MGC1! front-month auto-roll
        timeframe: Literal["1M","1W","1D","4H","1H","15m","1m"] = "4H",
        bars: int = 50,                             # how many historical bars
        end_time: datetime | None = None,
    ) -> list[OHLCV]:
        """Blocking call, 30s timeout."""

    def get_snapshot(self, symbol: str) -> Snapshot:
        """Current bid/ask/last, sub-second."""

    def is_healthy(self) -> bool:
        """Connection state check; called at start of every report."""

    def reconnect(self) -> None:
        """Idempotent explicit reconnect."""
```

`reports/futures_data/ib_extensions.py` adds (depend on `IBClient`):

```python
def get_open_interest(client: IBClient, symbol: str,
                      end_time: datetime | None = None) -> tuple[int, int]:
    """Returns (today_OI, yesterday_OI). Uses genericTickList=100 on the
    front-month contract."""

def get_term_structure(client: IBClient, symbol: str,
                       n_months: int = 3) -> list[ContractPrice]:
    """Front month + n-1 back months."""

def get_settlement(client: IBClient, symbol: str, date: date) -> float:
    """Daily official settlement price."""
```

This keeps `core/ib_client.py` minimal and confined to generic IB plumbing; futures-specific extensions are isolated in the `reports/futures_data/` module so they can be added/changed without touching core.

#### 4.1.3 Multi-TF Bar Fetch Strategy

| TF | Bars needed | Use case |
|---|---|---|
| M (monthly) | 24 (2y) | Monthly trend context |
| W (weekly) | 52 (1y) | Weekly swing structure |
| D (daily) | 200 (~1y) | 200-EMA, long swings |
| 4H | 50 (~8 days) | Pattern recognition left-context |
| 1H | 24 (yesterday + today) | 4H bar internal texture |
| 15m | 8 (intraday 2h) | EOD report review |

**Caching**:
- D / W / M bars: SQLite cache, refreshed at first daily report (06:00 PT)
- 4H / 1H bars: live fetch every report (IB calls cheap)
- IB calls per report: ≤ 6 per instrument × 3 instruments = 18 max per report

### 4.2 News Layer

#### 4.2.1 Dual Source

**Source 1 (existing)**: `premarket/collectors/news.py` — preserved as-is, called from new pipeline.

**Source 2 (new)**: Anthropic Web Search via Claude SDK tool use:

```python
tools = [{
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}]
```

AI auto-decides queries:
- premarket / 4H / EOD: "ES futures news last 4 hours", "FOMC statement today", etc.
- weekly: "S&P 500 weekly outlook" + economic calendar
- night/asia D: Asia macro news (FX, central banks)

#### 4.2.2 Time Windows (No Overlap)

| Report | News window |
|---|---|
| premarket 06:00 PT | Since prior 23:00 PT report (overnight Asia + Europe) |
| intraday-4h-1 07:00 PT | 06:00 → 07:00 PT (open + first 30min) |
| intraday-4h-2 11:00 PT | 07:00 → 11:00 PT |
| eod 14:00 PT | 11:00 → 14:00 PT |
| night 19:00 PT | 14:00 → 19:00 PT |
| asia 23:00 PT | 19:00 → 23:00 PT |
| weekly Sun 14:00 PT | Prior Fri 14:00 PT → Sun 14:00 PT (full weekend) |

#### 4.2.3 Deduplication

`news_seen` SQLite table, primary key `(source, external_id)`. Same news from multiple sources appears once.

### 4.3 AI Layer

#### 4.3.1 Call Stack

```
core/ai_analyst.py
├── load_context()           # Contract.md + today's plan + last report + lock-in stats
├── build_prompt()           # Per-report-type template assembly
├── call_claude()            # anthropic SDK, Opus 4.7
│   ├── prompt caching       # System prompt + Contract.md + template
│   ├── tool: web_search     # Anthropic native
│   └── retry × 3 (exponential backoff: 1s, 4s, 16s)
├── validate_output()        # Required sections check
└── return ReportContent
```

#### 4.3.2 Prompt Structure with Caching

```python
messages = [
    {
        "role": "system",
        "content": [
            {"type": "text", "text": SYSTEM_PROMPT,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": REPORT_TEMPLATE_FOR_TYPE,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": contract_md_content,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic_context},  # not cached: bars + news + plan
        ]
    },
    {"role": "user", "content": "Generate the {report_type} report for {timestamp}."}
]
```

5-minute cache TTL; same report-type retries within 5 min hit cache.

#### 4.3.3 Token Budget

Per report (3 instruments full coverage):

| Component | Tokens | Cached |
|---|---|---|
| SYSTEM_PROMPT | ~2,000 | ✅ |
| REPORT_TEMPLATE | ~3,000 | ✅ |
| Contract.md | ~3,000 | ✅ |
| Dynamic context (bars + news + plan + futures data, 3 instruments) | ~25,000-30,000 | ❌ |
| Output | ~10,000-12,000 | — |
| **Total** | ~33-38K in + 10-12K out | |

#### 4.3.4 Monthly Cost (full Opus 4.7, all 3 instruments)

124 reports/month × estimated tokens:

| Item | Estimate |
|---|---|
| Cache write (first call per type per 5 min) | ~$25/month |
| Cache read | <$2 |
| Fresh input | ~$50 |
| Output | ~$70 |
| Anthropic Web Search | ~$10-15 |
| **AI total** | **~$140-170/month** |
| IBKR API + ib_insync (lib free) | $0 |
| CME real-time (user already has) | (existing expense) |
| Telegram bot | $0 |
| **Incremental total** | **~$140-170/month** |

#### 4.3.5 Output Validation

```python
REQUIRED_SECTIONS = {
    "premarket":   ["W", "D", "4H", "1H", "F", "新闻", "C", "B", "A"],
    "intraday-4h": ["D", "4H", "1H", "F", "新闻", "C", "B", "A"],
    "eod":         ["W", "D", "4H", "F", "今日交易档案", "C", "B"],
    "night-d":     ["4H", "1H", "新闻", "F"],   # plus frontmatter:tags
    "weekly":      ["M", "W", "D", "4H", "F", "新闻", "B", "A"],
}
```

Missing required section → validate fails → retry. After 3 retries → Telegram alert, no degraded output.

### 4.4 SQLite State (`data/state.db`)

```sql
-- 4.4.1 Today's plan extracted from 06:00 PT report
CREATE TABLE plans (
    date TEXT,                       -- ET date
    instrument TEXT,                 -- MES | MNQ | MGC
    setup_name TEXT,
    direction TEXT,                  -- long | short | neutral
    entry REAL,
    stop REAL,
    target REAL,
    r_unit_dollars REAL,
    invalidations TEXT,              -- JSON list
    raw_plan_text TEXT,
    created_at TEXT,
    source_report_path TEXT,
    PRIMARY KEY (date, instrument)
);

-- 4.4.2 Report generation history
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT,
    date TEXT,                       -- ET date
    time_pt TEXT,
    time_et TEXT,
    obsidian_path TEXT,
    pdf_path TEXT,
    telegram_msg_ids TEXT,           -- JSON list
    status TEXT,                     -- success | failed | partial
    failure_reason TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cache_hit_rate REAL,
    duration_seconds REAL,
    estimated_cost_usd REAL,
    created_at TEXT
);

-- 4.4.3 News deduplication
CREATE TABLE news_seen (
    source TEXT,
    external_id TEXT,
    url TEXT,
    title TEXT,
    published_at TEXT,
    first_seen_at TEXT,
    impact_tag TEXT,
    PRIMARY KEY (source, external_id)
);

-- 4.4.4 Failure log
CREATE TABLE failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT,
    scheduled_at TEXT,
    failure_stage TEXT,              -- ib | news | ai | obsidian | pdf | telegram
    failure_reason TEXT,
    retry_count INTEGER,
    resolved_at TEXT
);

-- 4.4.5 Lock-in snapshot (synced from journal/)
CREATE TABLE lock_in_status (
    snapshot_at TEXT PRIMARY KEY,
    trades_done INTEGER,
    trades_target INTEGER,           -- 30
    cumulative_r REAL,
    last_trade_date TEXT,
    last_trade_r REAL,
    streak TEXT,                     -- e.g. "2L1W" last 5 trades
    breakdown_mes INTEGER,
    breakdown_mnq INTEGER,
    breakdown_mgc INTEGER
);

-- 4.4.6 D-bar cache
CREATE TABLE bar_cache (
    instrument TEXT,
    timeframe TEXT,                  -- M | W | D
    bar_time TEXT,                   -- ISO UTC
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (instrument, timeframe, bar_time)
);
```

**Relationship to `journal/`**: this system **read-only** with respect to journal. `lock_in_status` is an aggregate snapshot, not the source of truth.

### 4.5 Contract.md State Machine

```
Contract.md missing or empty
   ↓
   metadata: "Contract.md: not yet created"
   C section: degrades to "form today's thesis" (no prior plan)
   A section: A-3 only, never escalates A-2 (no anchor for invalidation)

Contract.md present, lock-in count = 0
   ↓
   metadata: "Lock-in: 0/30 (not started)"
   Other sections normal

Contract.md present, lock-in active (1 ≤ count < 30)
   ↓
   Full functionality (designed flow)

Lock-in complete (count ≥ 30)
   ↓
   metadata: "Lock-in: ✅ complete (30+ trades)"
   Content unchanged; awaits user's next-phase decision
```

### 4.6 Multi-Instrument Configuration (`config/instruments.yaml`)

```yaml
instruments:
  MES:
    full_name: "Micro E-mini S&P 500"
    underlying_index: SPX
    cme_symbol: MES
    typical_atr_pts: 14
    typical_stop_pts: 8
    typical_target_pts: 16
    cot_commodity: "S&P 500 STOCK INDEX"
  MNQ:
    full_name: "Micro E-mini Nasdaq 100"
    underlying_index: NDX
    cme_symbol: MNQ
    typical_atr_pts: 60
    typical_stop_pts: 30
    typical_target_pts: 60
    cot_commodity: "NASDAQ MINI"
  MGC:
    full_name: "Micro Gold"
    underlying_index: null            # COMEX, no equity index
    cme_symbol: MGC
    typical_atr_pts: 8
    typical_stop_pts: 5
    typical_target_pts: 10
    cot_commodity: "GOLD"
```

`Contract.md` extends to per-instrument setup definitions:

```yaml
instruments:
  MES:
    setup_name: "ORB long"           # user's chosen setup
    r_unit_dollars: 25
  MNQ:
    setup_name: "..."
    r_unit_dollars: 20
  MGC:
    setup_name: "..."
    r_unit_dollars: 15

lock_in:
  trades_target: 30                  # 30 total across all instruments
  trades_done: 0
  per_instrument_breakdown:
    MES: 0
    MNQ: 0
    MGC: 0
```

---

## 5. Distribution Layer (Obsidian + PDF + Telegram)

### 5.1 Output Pipeline

```
ReportContent (AI output, validated)
        │
        ├──→ §5.2  Obsidian Writer  →  vault/<folder>/<file>.md
        ├──→ §5.3  Chart Renderer    →  data/charts/<id>-<tf>.png
        ├──→ §5.4  PDF Renderer      →  data/pdfs/<id>.pdf
        └──→ §5.5  Telegram Pusher   →  multi-message + charts + PDF
                  │
                  └─ on success → SQLite reports.status = 'success'
```

Order: Obsidian first (most important archive) → render artifacts → push Telegram. Failures of later steps do not roll back earlier ones; Obsidian is the canonical archive.

### 5.2 Obsidian Writer

#### 5.2.1 Directory Structure (Additive)

```yaml
# config/default.yaml — additive new fields
obsidian:
  enabled: true
  vault_path: ~/Obsidian/Trading
  daily_folder: Daily               # existing, preserved
  weekly_folder: Weekly             # existing, preserved
  # New:
  intraday_folder: Daily/Intraday
  eod_folder: Daily/EOD
  night_folder: Daily/Night
```

```
~/Obsidian/Trading/
├── Daily/                          # existing
│   ├── 2026-04-25-premarket.md     # premarket reports stay here (existing convention)
│   ├── Intraday/                   # NEW
│   │   ├── 2026-04-25-0700PT-4H1.md
│   │   └── 2026-04-25-1100PT-4H2.md
│   ├── EOD/                        # NEW
│   │   └── 2026-04-25-eod.md
│   └── Night/                      # NEW
│       ├── 2026-04-25-night-1900PT.md
│       └── 2026-04-25-night-2300PT.md
└── Weekly/                          # existing
    └── 2026-W17-weekly.md
```

#### 5.2.2 Frontmatter Standard

Every report has full frontmatter for Dataview / Bases queries (sample shown in §3.6).

#### 5.2.3 Journal Backlinks

Reports add Obsidian backlink to the day's journal entry at body footer:

```markdown
---
Related: [[2026-04-25-journal]]
```

`journal/` itself unchanged; backlinks are Obsidian-native bidirectional.

#### 5.2.4 Write Failure Handling

```python
def write_obsidian(content: str, path: Path) -> Result:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return Result.ok()
    except (OSError, PermissionError) as e:
        fallback = Path("data/exports") / path.name
        fallback.write_text(content)
        alert_telegram(f"Obsidian write failed: {e}. Fallback: {fallback}")
        return Result.fallback(fallback)
```

### 5.3 Chart Renderer (matplotlib)

#### 5.3.1 Required Charts

Per non-D report: 2 PNGs.
Per D report: 1 PNG.

| Chart | Content |
|---|---|
| `<id>-tf-stack.png` | Multi-TF price stack: W / D / 4H / 1H subplots, shared Y range markers, per instrument |
| `<id>-context.png` | Current price + key levels + invalidation lines (visual plan recheck) |
| `<id>-pattern.png` (D only) | 4H + 1H subplots with pattern annotations |

#### 5.3.2 Library Choice

**matplotlib** — stable, static PNG output, fast (<2s/chart), no browser dependency. Plotly rejected because Telegram doesn't render HTML.

#### 5.3.3 Output Path

```
data/charts/
├── 2026-04-25-0700PT-4H1-tf-stack.png
└── 2026-04-25-0700PT-4H1-context.png
```

References:
- Obsidian: `![[2026-04-25-0700PT-4H1-tf-stack.png]]`
- PDF: embedded base64
- Telegram: separate photo message

### 5.4 PDF Renderer (weasyprint)

#### 5.4.1 Pipeline

```
markdown content
   │
   ├─→ markdown-it-py (parse to HTML)
   │
   ├─→ Jinja2 template (apply CSS theme + header/footer)
   │
   └─→ weasyprint (HTML + CSS → PDF)
```

#### 5.4.2 Visual Spec

- Page: A4 portrait
- Body: Inter or Source Sans; mono: JetBrains Mono
- Section labels colored: A=blue, B=gray, C=green, D=purple, F=orange
- Header: report type + ET/PT timestamp
- Footer: page number + Contract.md status summary + generation timestamp

#### 5.4.3 Library Comparison

| Candidate | Pro | Con |
|---|---|---|
| **weasyprint** ⭐ | Pure Python, HTML+CSS support, good table rendering | Slow-ish (~3-5s/PDF) |
| pandoc | Universal compatibility | Heavy dep (binary required) |
| wkhtmltopdf | Fast | Discontinued |
| reportlab | Full control | No HTML input, layout from scratch |
| mdpdf | Simple | Poor table / CSS support |

#### 5.4.4 Output

```
data/pdfs/
└── 2026-04-25-0700PT-4H1.pdf
```

Same stem as the markdown file.

### 5.5 Telegram Pusher (python-telegram-bot)

#### 5.5.1 Setup

```yaml
# config/secrets.yaml (gitignored)
telegram:
  bot_token: "..."          # Created via @BotFather
  chat_id: "..."            # User's personal chat ID
```

Library: `python-telegram-bot` v21+ (async, actively maintained).

#### 5.5.2 Message Splitting

```python
MAX_MSG_CHARS = 4000        # < 4096, leave buffer for prefixes

def split_report_to_messages(content: str) -> list[str]:
    """Split at markdown ## headers, each chunk ≤ 4000 chars."""
    sections = split_by_h2_headers(content)
    chunks, current = [], ""
    for section in sections:
        if len(current) + len(section) > MAX_MSG_CHARS:
            chunks.append(current)
            current = section
        else:
            current += section
    if current:
        chunks.append(current)
    return chunks
```

Each message prefixed `[N/M]` for progress visibility.

Typical premarket split (3 instruments, full multi-TF, ~12K chars total per §3.10):

| # | Content | Chars |
|---|---|---|
| 1 | metadata + Lock-in + multi-TF MES | ~3000 |
| 2 | multi-TF MNQ + MGC | ~3000 |
| 3 | F. futures structure (all 3) | ~2500 |
| 4 | news + C (3 plans) | ~2500 |
| 5 | B + A + data snapshot | ~1000 |
| photo 1 | tf-stack.png | — |
| photo 2 | context.png | — |
| document | full PDF | — |

Total: ~5 text messages + 2 photos + 1 PDF = **8 Telegram messages per premarket report**.

Intraday 4H (~7K chars total per §3.10): ~2-3 text + 2 photos + 1 PDF = 5-6 messages.

EOD (~9K chars): ~3 text + 2 photos + 1 PDF = 6 messages.

Weekly (~18K chars): ~5 text + 2 photos + 1 PDF = 8 messages.

#### 5.5.3 MarkdownV2 Escaping

Special chars require `\` escape: `_*[]()~`>#+-=|{}.!`

Use `python-telegram-bot`'s built-in `escape_markdown(text, version=2)`. Never hand-write escaping.

#### 5.5.4 Tables → Code Block

```python
def table_to_codeblock(md_table: str) -> str:
    """Align columns to widest cell, wrap in ```...```"""
```

Example output (Telegram view):

```
TF    | Pattern        | Key levels
1D    | uptrend        | 5210/5260
4H    | bullish engulf | 5240/5252
1H    | range          | 5246-5250
```

#### 5.5.5 Push Order

```
[1/N] metadata header
[2/N] multi-TF section
...
[N/N] A recommendation section
🖼 chart: tf-stack
🖼 chart: context
📎 PDF: <filename>.pdf
```

PDF last as the "full-fidelity archive version".

#### 5.5.6 Failure Handling

```python
async def push_with_retry(messages, charts, pdf):
    for attempt in range(3):
        try:
            for msg in messages:
                await bot.send_message(chat_id, msg, parse_mode="MarkdownV2")
            for chart in charts:
                await bot.send_photo(chat_id, chart)
            await bot.send_document(chat_id, pdf)
            return Result.ok()
        except TelegramError as e:
            if attempt == 2:
                queue_for_retry(report_id, messages, charts, pdf)
                return Result.failed(e)
            await asyncio.sleep(2 ** attempt)
```

### 5.6 Failure Rollback Matrix

| Step fails | Action | User experience |
|---|---|---|
| Obsidian write | Fallback to `data/exports/`, continue PDF + Telegram | Telegram alert added |
| Chart render | Skip charts, text proceeds | PDF has no images |
| PDF render | Push text + charts only | Telegram alert about PDF missing |
| Telegram all 3 retries fail | Obsidian + PDF archived; queue for retry on next launch | Visible in Obsidian; auto-retry later |
| All steps fail | SQLite failure log; next-launch retry | Should never happen; if it does, system fault |

---

## 6. Architecture, Module Structure, Scheduling

### 6.1 Final Module Structure

```
src/daytrader/
├── premarket/                              # ⚠️ unchanged
│   └── (all existing files)
│
├── journal/                                 # ⚠️ unchanged
│   └── (all existing files)
│
├── core/                                    # additions only
│   ├── config.py                           # existing
│   ├── ib_client.py                        # NEW: ib_insync wrapper
│   └── state.py                            # NEW: SQLite state manager
│
├── reports/                                 # NEW module (everything additive lives here)
│   ├── __init__.py
│   ├── core/
│   │   ├── ai_analyst.py
│   │   ├── context_loader.py
│   │   ├── prompt_builder.py
│   │   ├── output_validator.py
│   │   └── orchestrator.py
│   ├── futures_data/
│   │   ├── ib_extensions.py
│   │   ├── cot_collector.py
│   │   ├── basis_calculator.py
│   │   ├── volume_profile.py
│   │   └── positioning_interpreter.py
│   ├── instruments/
│   │   ├── definitions.py
│   │   └── multi_fetcher.py
│   ├── types/
│   │   ├── premarket.py
│   │   ├── intraday_4h.py
│   │   ├── eod.py
│   │   ├── night.py
│   │   └── weekly.py
│   ├── delivery/
│   │   ├── obsidian_writer.py
│   │   ├── chart_renderer.py
│   │   ├── pdf_renderer.py
│   │   └── telegram_pusher.py
│   └── templates/
│       ├── premarket.md
│       ├── intraday_4h.md
│       ├── eod.md
│       ├── night.md
│       └── weekly.md
│
└── cli/
    ├── premarket.py                        # existing, preserved
    ├── weekly_cmd.py                       # existing, preserved
    ├── journal_cmd.py                      # existing, preserved
    └── reports.py                          # NEW: daytrader reports {...} command group

scripts/
├── run_report.py                            # NEW: launchd entry point
├── ib_gateway_watchdog.py                  # NEW
└── launchd/
    ├── com.daytrader.report.0600pt.plist
    ├── com.daytrader.report.0700pt.plist
    ├── com.daytrader.report.1100pt.plist
    ├── com.daytrader.report.1400pt.plist
    ├── com.daytrader.report.1900pt.plist   # Sun-Thu
    ├── com.daytrader.report.2300pt.plist   # Sun-Thu
    ├── com.daytrader.weekly.sun1400pt.plist
    ├── com.daytrader.ibgateway.plist
    └── com.daytrader.cleanup.weekly.plist

config/
├── default.yaml                             # existing, additive extension only
├── user.yaml                                # existing
├── secrets.yaml                             # NEW: gitignored
└── instruments.yaml                         # NEW: MES/MNQ/MGC params

data/
├── state.db                                 # NEW
├── charts/                                  # NEW
├── pdfs/                                    # NEW
├── logs/                                    # NEW
│   └── reports/<YYYY-MM-DD>/
└── exports/                                 # existing, preserved
```

**Backward compatibility**: `daytrader pre run` and `daytrader weekly run` commands work unchanged. New functionality lives under `daytrader reports` subcommand group.

### 6.2 Scheduler (launchd)

#### 6.2.1 Plist Inventory

| Plist | PT time | Days | Job |
|---|---|---|---|
| `report.0600pt` | 06:00 | Mon-Fri | premarket |
| `report.0700pt` | 07:00 | Mon-Fri | intraday-4h-1 |
| `report.1100pt` | 11:00 | Mon-Fri | intraday-4h-2 |
| `report.1400pt` | 14:00 | Mon-Fri | eod |
| `report.1900pt` | 19:00 | Sun-Thu | night |
| `report.2300pt` | 23:00 | Sun-Thu | asia |
| `weekly.sun1400pt` | 14:00 Sun | Sun | weekly |
| `ibgateway` | boot + KeepAlive | always | IB Gateway long-run |
| `cleanup.weekly` | 02:00 Sun | Sun | rotate old PDFs, charts, logs |

PT clock fixed year-round (US/Canada DST sync between PT and ET).

#### 6.2.2 Plist Template

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.0600pt</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/uv</string>
        <string>run</string>
        <string>scripts/run_report.py</string>
        <string>--type</string>
        <string>premarket</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/tylersan/Projects/Day trading</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>/.../data/logs/launchd/report.0600pt.out</string>
    <key>StandardErrorPath</key>
    <string>/.../data/logs/launchd/report.0600pt.err</string>
</dict>
</plist>
```

(launchd Weekday convention: 1=Mon, 7=Sun.)

### 6.3 Per-Report Pipeline (`scripts/run_report.py`)

```
launchd fires
   ↓
1.  Acquire lock (data/locks/<type>.lock) — prevent concurrent runs
2.  Read SQLite: was today's report of this type already generated? (idempotency check)
3.  Verify IB Gateway healthy → reconnect if needed
4.  Wait for 4H bar close (if applicable, max 5 min)
5.  Fetch bars (parallel: 3 instruments × multi-TF)
6.  Fetch futures-specific data (OI / basis / term / VP)
7.  Fetch news (premarket-collector + Anthropic web search via tool use)
8.  (Sunday weekly only) Fetch COT
9.  Load context: Contract.md + today's plan + prior report + journal trade stats
10. Build AI prompt (per report-type template)
11. Call Claude Opus 4.7 (retry × 3, exponential backoff)
12. Validate output (required sections check)
13. Write Obsidian
14. Render charts (matplotlib → PNG)
15. Render PDF (markdown → HTML → weasyprint)
16. Push Telegram (multi-message + charts + PDF)
17. Update SQLite reports.status = 'success' + record tokens / duration / cost
18. Release lock
```

Each step: log to `data/logs/reports/<date>/<report-id>.log` + try/except + fallback per §5.6.

### 6.4 IB Gateway Long-Run Management

- **IBC (IB Controller)**: open-source auto-login wrapper for IB Gateway, handles daily logout / 2FA / reconnection
- **launchd plist `ibgateway`**: launches at boot, KeepAlive=true (auto-restart on crash)
- **Watchdog script**: `scripts/ib_gateway_watchdog.py` runs every 5 min, pings IB socket, kills + restarts if unresponsive
- **Weekend behavior**: Fri 14:00 PT — Sun 15:00 PT, Gateway can idle (no reports scheduled); reconnect on Sun before weekly report

### 6.5 Logging + Observability

#### 6.5.1 Log Hierarchy

```
data/logs/
├── launchd/                       # launchd's own stdout/stderr per plist
│   ├── report.0600pt.out
│   └── ...
├── reports/<YYYY-MM-DD>/          # per-day, per-report detailed pipeline logs
│   ├── 06-00-PT-premarket.log
│   └── ...
├── ib_gateway/                    # connection events
└── system.log                     # rotated central log
```

#### 6.5.2 SQLite Metrics

Per report (`reports` table):
- duration_seconds, tokens_input, tokens_output, cache_hit_rate
- estimated_cost_usd
- bars_fetched_count, news_count, web_search_count
- delivery step statuses

#### 6.5.3 Weekly Health Section

Sunday weekly report auto-includes:

```markdown
## System Health (last 7 days)
- Total reports: 31 / 31 (100% success)
- Avg generation time: 18.4s (premarket 25s / 4H 12s / EOD 22s / night 15s)
- AI total cost: $32.40
- IB Gateway restarts: 0
- Failed retries: 2 (4H#1 Tue — Telegram timeout; EOD Thu — IB reconnect)
```

User's weekly system check-up; no need to read logs for routine status.

### 6.6 First-Run Deployment Checklist

1. **IBKR**
   - [ ] Install IB Gateway (latest stable)
   - [ ] Install IBC (auto-login wrapper)
   - [ ] Confirm CME Real-time data subscription active
   - [ ] Test ib_insync connection

2. **Anthropic / Claude**
   - [ ] API key in `config/secrets.yaml`
   - [ ] Confirm Web Search tool permission for organization
   - [ ] Test Opus 4.7 + caching call

3. **Telegram**
   - [ ] @BotFather create bot, get token
   - [ ] DM bot to obtain chat_id
   - [ ] Test send_message + send_photo + send_document

4. **Obsidian**
   - [ ] vault_path configured
   - [ ] Create subfolders: `Daily/Intraday`, `Daily/EOD`, `Daily/Night`
   - [ ] Install Dataview / Bases plugin (for frontmatter queries)

5. **Contract.md**
   - [ ] Fill `config/instruments.yaml` (MES/MNQ/MGC: setup_name, r_unit, typical_stop)
   - [ ] Fill `Contract.md` (lock-in target=30, instruments breakdown)

6. **System**
   - [ ] Install launchd plists (`launchctl bootstrap`)
   - [ ] Initialize `data/state.db`
   - [ ] Create log directories
   - [ ] First dry-run for each report type

7. **Validation**
   - [ ] First Monday 06:00 PT premarket → check Obsidian + Telegram
   - [ ] Monitor first 3 days; tune AI prompt templates
   - [ ] First Sunday weekly: verify Health section

### 6.7 Testing Strategy

- **Unit tests**: every new module under `tests/reports/...`
- **Integration tests**: end-to-end pipeline in dry-run mode (writes to `data/test_outputs/`, no Obsidian/Telegram side effects)
- **Mocked IB**: use `ib_insync.IB.connectAsync` mock for offline test
- **Mocked Anthropic**: cassette-style fixtures for prompt → response pairs
- **CLI**: `daytrader reports dry-run --type intraday-4h` runs full pipeline with all side effects disabled

### 6.8 Rollback Procedure

If the system needs to be removed:

1. `launchctl bootout` for all `com.daytrader.*` plists (except premarket-related, if any)
2. Delete `src/daytrader/reports/` directory
3. Delete `src/daytrader/core/ib_client.py`, `src/daytrader/core/state.py`
4. Remove new fields from `config/default.yaml` (intraday_folder, eod_folder, night_folder)
5. Remove new CLI registration in `cli/main.py`
6. Optionally archive `data/state.db`, `data/charts/`, `data/pdfs/`

`premarket/`, `journal/`, existing CLI commands, existing Obsidian content unaffected.

---

## 7. Risk & Decision Record

For audit by user 1-3 months from now: distinguishing "design error" from "user-knowingly-chose tradeoff".

| Decision | User choice | Push back rounds | User reasoning |
|---|---|---|---|
| Intraday reports during lock-in | Keep | 1 | Wants real-time intraday input |
| 1H → 4H frequency | Adopted 4H | 1 | Accepted noise argument |
| Intraday A (decision aid) retained | A-2 + A-3 mixed | 2 | Decision aid is core value |
| Lock-in push guardrail (`suppress_a_section`) | Declined | 1 | Wants full content always pushed |
| AI model tiering vs all-Opus | All Opus 4.7 | 1 | Analysis quality is highest priority |
| Three-instrument trading (MES + MNQ + MGC) | All 3 traded | 0 (accepted directly) | Full futures coverage |
| Lock-in counting for 3 instruments | 30 total (not per-instrument) | 0 | Accepted recommendation |
| A.3 form for 3 instruments | Mini-A per instrument + integrated overview | 0 | Accepted recommendation |
| Cost ceiling | ~$140-170/month accepted | 0 | Quality > cost |
| Phase 2+ build order vs Contract.md fill | Build Phase 2-8 first; Contract.md and lock-in deferred | 1 (after Phase 1 merge milestone) | User prefers tooling momentum over decision work |

**Key implication**: this system's outputs during the 30-trade lock-in include AI decision-aid content (A sections) for each of 3 instruments at every report time. PnL data from the 30 trades will reflect a mixture of (a) user's discretionary skill, (b) Contract.md's setup definitions, and (c) AI input influence. After lock-in, the user can decide whether (c) is signal or noise based on observed performance.

**Build-order trade-off**: At Phase 1 merge (2026-04-25), I flagged that the actual stated next step (per project memory) was Contract.md fill + 30-trade lock-in start, not more reports infrastructure. User chose to continue Phase 2-8 build. Implication: Phase 2's C-section (plan-recheck) and Contract.md state machine (§4.5) will run against an empty/skeletal Contract.md initially; the spec's degraded-mode paths cover this, but the system will not deliver its full value until Contract.md is filled regardless of how many phases are coded.

---

## 8. Open Questions / Deferred Decisions

| Question | Defer to |
|---|---|
| Chart style/colors detailed visual spec | Implementation phase, iterate after first week |
| Specific COT data file format and parser | Implementation (CFTC public CSV format is documented) |
| Volume Profile calculation params (bins, lookback) | Implementation, default to 30-bin RTH session |
| Telegram group vs private chat | First-run setup (private chat assumed) |
| PDF cover page design | Implementation (skip if time pressure) |

---

## 9. Migration Plan (Summary)

1. **Phase 0**: Spec review + plan writing (this doc → writing-plans skill)
2. **Phase 1**: Foundation (`core/ib_client.py`, `core/state.py`, IB Gateway + IBC setup, dry-run scaffolding)
3. **Phase 2**: Single-instrument single-report-type proof-of-concept (MES premarket, full pipeline)
4. **Phase 3**: Multi-TF + multi-instrument (MES + MNQ + MGC)
5. **Phase 4**: F. futures structure + positioning interpretation
6. **Phase 5**: All 6 report types
7. **Phase 6**: Telegram + PDF + chart delivery
8. **Phase 7**: launchd integration + production deployment
9. **Phase 8**: First week monitoring + tuning

Each phase has its own implementation plan (TDD task breakdown, see writing-plans output).

---

## 10. Dependencies

### 10.1 Third-Party Libraries (per CLAUDE.md "prefer proven over building from scratch")

| Library | Purpose | License | Maintenance | Justification |
|---|---|---|---|---|
| `ib_insync` | IBKR API wrapper | BSD | Active | De facto standard for ib_insync; better than raw `ibapi` |
| `IBC` (IB Controller) | IB Gateway auto-login | GPL | Active | Standard solution for headless IB Gateway operation |
| `python-telegram-bot` | Telegram Bot API | LGPL | Active | Mature, async, full Bot API coverage |
| `weasyprint` | HTML → PDF | BSD | Active | Pure Python, good CSS support |
| `markdown-it-py` | Markdown → HTML | MIT | Active | CommonMark-compliant |
| `matplotlib` | Chart rendering | PSF-based | Active | Python standard for static charts |
| `anthropic` (SDK) | Claude API | MIT | Anthropic-maintained | Official |
| `Jinja2` | PDF templating | BSD | Active | Python standard templating |
| `pyyaml` | Config parsing | MIT | Active | Already a project dep (likely) |

### 10.2 System Requirements

- macOS (launchd)
- Python 3.11+
- IB Gateway (Java, x64 stable)
- 24/7 always-on Mac (or VPS, but Mac is simpler given existing setup)
- ~5 GB free disk for first-year logs / charts / PDFs

---

## End of Spec
