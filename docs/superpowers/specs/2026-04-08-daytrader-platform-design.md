# DayTrader Platform — Design Spec

## Context

An experienced US stock day trader specializing in order flow stacked imbalances scalping (tight stops, high R:R) needs a comprehensive platform to support daily trading. Current workflow uses TradingView for multi-timeframe macro analysis and MotiveWave for footprint chart execution. The platform must be self-evolving (autonomous learning) and designed for eventual commercialization.

## Goals

1. **Pre-market & weekly preparation** — structured daily/weekly prep with multi-channel output
2. **Strategy backtesting & real-time signals** — backtest framework + live signal generation to MotiveWave
3. **Autonomous evolution engine** — system-driven discovery, hypothesis generation, validation, and self-optimization
4. **Trading psychology system** — mental check-in, behavioral guardrails, reflection, analytics
5. **Learning & content curation** — personalized educational content discovery and delivery
6. **Instrument statistical edge** — per-instrument behavioral profiles and exploitable edge discovery
7. **Knowledge base & content publishing** — internal knowledge management + multi-platform publishing pipeline
8. **Trade journal & auto-import** — automated trade record ingestion from multiple sources
9. **Multi-notification system** — Telegram, iMessage, Discord push for signals, reports, and alerts
10. **Prop firm trading module** — rule engine, signal filtering, constrained backtest for multiple prop firms
11. **Commercial-ready architecture** — plugin-based, config-driven, cleanly separated core

---

## Architecture

### Tech Stack

- **Language:** Python 3.12+
- **Package manager:** uv
- **Database:** SQLite (upgradeable to PostgreSQL)
- **CLI:** click
- **Visualization:** plotly
- **HTTP:** httpx
- **Push notifications:** python-telegram-bot
- **AI/Agent:** Claude API (for Research Explorer)
- **Data:** pandas, numpy

### Project Structure

```
Day trading/
├── pyproject.toml
├── config/
│   ├── default.yaml            # Default config (distributable)
│   ├── user.yaml               # User personal config (gitignored)
│   └── prop_firms/             # Prop firm rule profiles
│       ├── ftmo.yaml
│       ├── topstep.yaml
│       └── ...                 # One YAML per prop firm
├── src/daytrader/
│   ├── core/
│   │   ├── models.py           # Domain models (Signal, Trade, Level, Report, Hypothesis)
│   │   ├── registry.py         # Plugin registry
│   │   └── db.py               # Data persistence layer (SQLite)
│   ├── premarket/
│   │   ├── collectors/         # Data collectors (one per source, plugin-style)
│   │   ├── analyzers/          # Analyzers (key levels, sentiment, event calendar)
│   │   ├── renderers/          # Output renderers (markdown, push, platform annotations)
│   │   ├── checklist.py        # Daily pre-market checklist engine
│   │   └── weekly.py           # Weekly plan generator (review + macro + plan)
│   ├── backtest/
│   │   ├── parsers/            # Data parsers (tick/footprint, multi-format)
│   │   ├── signals/            # Signal detectors (stacked imbalance + extensible)
│   │   ├── engine.py           # Backtest engine
│   │   ├── optimizer.py        # Parameter optimizer
│   │   └── report.py           # Backtest report generation
│   ├── evolution/
│   │   ├── observers/
│   │   │   ├── market.py       # Market Observer
│   │   │   ├── performance.py  # Performance Monitor
│   │   │   └── research.py     # Research Explorer (AI-driven)
│   │   ├── hypothesis.py       # Hypothesis generation & management
│   │   ├── validator.py        # Auto-backtest validation
│   │   ├── report.py           # Evolution report generation
│   │   ├── versioning.py       # Parameter version control (rollback support)
│   │   └── scheduler.py        # Evolution task scheduling
│   ├── learning/               # Learning & content curation
│   │   ├── scrapers/           # Content scrapers (YouTube, RSS, Reddit, X, etc.)
│   │   ├── curator.py          # AI-powered relevance ranking & filtering
│   │   ├── digest.py           # Daily/weekly digest generation
│   │   ├── library.py          # Personal knowledge base & spaced repetition
│   │   └── sources.py          # Source subscription management
│   ├── psychology/             # Trading psychology system
│   │   ├── checkin.py          # Pre-session mental check-in
│   │   ├── guardrails.py       # Real-time behavioral circuit breakers
│   │   ├── reflection.py       # Post-session reflection prompts
│   │   └── analytics.py        # Psychology pattern analysis & reports
│   ├── kb/                     # Knowledge base & content publishing
│   │   ├── store.py            # Knowledge entry CRUD, tagging, cross-linking
│   │   ├── generator.py        # AI content generation (Claude) per platform
│   │   ├── publisher.py        # Multi-platform publishing (X, Substack, Discord, etc.)
│   │   ├── sanitizer.py        # Privacy filter — strip proprietary details
│   │   ├── book.py             # Book manuscript builder & chapter organization
│   │   └── analytics.py        # Audience engagement & revenue tracking
│   ├── stats/                  # Instrument statistical edge
│   │   ├── profiler.py         # Build/update instrument profiles
│   │   ├── edges.py            # Edge discovery & significance testing
│   │   ├── calendar.py         # Seasonal/calendar pattern analysis
│   │   └── compare.py          # Cross-instrument comparison
│   ├── journal/                # Trade journal & auto-import
│   │   ├── parsers/            # Source parsers (motivewave, broker, prop firm)
│   │   ├── importer.py         # Import engine (normalize, dedup, enrich)
│   │   ├── watcher.py          # Watch folder daemon
│   │   └── summary.py          # Journal statistics & reporting
│   ├── prop/                   # Prop firm trading module
│   │   ├── rules.py            # Rule engine (load/validate prop profiles)
│   │   ├── gate.py             # Signal filtering gate (risk check before output)
│   │   ├── tracker.py          # Real-time account state vs. rule limits
│   │   └── profiles/           # Prop firm rule profiles (YAML configs)
│   ├── notifications/          # Shared notification system
│   │   ├── telegram.py         # Telegram Bot push
│   │   ├── imessage.py         # iMessage via AppleScript/Shortcuts
│   │   ├── discord.py          # Discord webhook/bot
│   │   └── base.py             # Notifier interface (plugin-style)
│   ├── api/
│   │   └── __init__.py         # Internal API interface definitions
│   └── cli/
│       ├── premarket.py        # `daytrader pre` + `daytrader weekly`
│       ├── backtest.py         # `daytrader bt`
│       ├── evolution.py        # `daytrader evo`
│       ├── prop.py             # `daytrader prop`
│       ├── psychology.py       # `daytrader psych`
│       ├── learning.py         # `daytrader learn`
│       ├── stats.py            # `daytrader stats`
│       ├── kb.py               # `daytrader kb` + `daytrader publish` + `daytrader book`
│       └── journal.py          # `daytrader journal`
├── plugins/                    # External plugin directory
├── motivewave-plugin/          # MotiveWave SDK plugin (Java)
│   ├── src/                    # Plugin source (signal consumer + chart overlay)
│   └── build.gradle            # Build config
├── data/
│   ├── db/                     # SQLite databases
│   ├── tick/                   # Raw tick data
│   ├── imports/                # Watch folder — drop files here for auto-import
│   └── exports/                # Reports, backtest results
├── scripts/                    # Pine Script, MotiveWave scripts
└── tests/
```

---

## Module 1: Pre-Market Preparation System

### Daily Checklist

**Phase 1: Macro Environment Scan (T-60 min)**

1. Overnight futures (ES, NQ) — opening direction bias
2. VIX level and change — volatility regime assessment
3. Global markets — Europe/Asia session summary
4. Economic data calendar — key releases with exact times (CPI, FOMC, NFP, etc.)
5. Sector heatmap — capital flow, sector strength ranking

**Phase 2: Stock Focus (T-30 min)**

6. Key level annotation — prior day high/low/close, pre-market high/low, Volume Profile POC/VAH/VAL
7. Earnings/news screening — stocks with earnings today, major news catalysts
8. Watchlist generation — filter by pre-market volume anomalies, volatility
9. Trade plan template — per-stock direction bias, key levels, event time windows

**Phase 3: Platform Prep (T-15 min)**

10. TradingView auto-annotation — generate Pine Script with key levels and event time shading
11. MotiveWave loading — footprint chart presets for watchlist stocks

### Data Collectors (Plugin-style)

| Collector | Source | Data |
|-----------|--------|------|
| `futures_collector` | TradingView MCP | ES, NQ futures |
| `vix_collector` | TradingView MCP / Yahoo | VIX level |
| `news_collector` | Financial news API | Market-moving news |
| `calendar_collector` | Economic calendar API | Data releases, earnings |
| `sector_collector` | TradingView MCP | Sector performance |
| `level_collector` | TradingView MCP | OHLC, volume profile |

### Output Renderers

| Renderer | Format | Timing | Content |
|----------|--------|--------|---------|
| `markdown_renderer` | .md file | T-60 min | Full pre-market report |
| `telegram_renderer` | Push notification | T-30 min | Key events + core levels |
| `tradingview_renderer` | Pine Script | T-15 min | Level lines + event time shading |
| `motivewave_renderer` | Config export | T-15 min | Price level presets |

### CLI (Daily)

```bash
daytrader pre                    # Run full pre-market analysis
daytrader pre --phase macro      # Run only macro scan
daytrader pre --push             # Run and push to all channels
daytrader pre --watchlist        # Generate watchlist only
```

### Weekly Plan (Sunday Evening / Monday Pre-Market)

A higher-level preparation layer that frames the entire trading week. Run before the first session of the week.

**Phase 1: Last Week Review (Auto-generated)**

1. **Performance recap** — weekly P&L, win rate, average R, number of trades, best/worst day
2. **Signal quality report** — which signal types performed well/poorly last week
3. **Rule compliance** — prop firm rule headroom per account (daily loss events, drawdown status)
4. **Evolution digest** — summary of any parameter changes or new hypotheses from the evolution engine
5. **Self-assessment prompts** — generated questions for the trader to reflect on (e.g., "You took 3 trades outside your A+ setup criteria — what triggered that?")

**Phase 2: Week Ahead Macro Context**

6. **Economic calendar** — full week's key events with dates/times (FOMC, CPI, NFP, earnings season status)
7. **Market structure** — weekly chart key levels for major indices (SPY, QQQ, IWM), weekly support/resistance/trend direction
8. **Volatility outlook** — VIX term structure, expected move for the week, options expiry dates (OPEX impact)
9. **Sector rotation** — sector relative strength trends over past 2-4 weeks, emerging leadership/laggards
10. **Correlations & cross-market** — DXY, bonds (TLT/ZB), crude oil — inter-market signals that affect equity flow

**Phase 3: Weekly Trading Plan**

11. **Bias framework** — weekly directional bias per index with supporting evidence (bullish/bearish/neutral + conditions to invalidate)
12. **Key level map** — weekly-level support/resistance zones for primary instruments (wider than daily levels)
13. **Event risk windows** — time blocks to avoid or be cautious during (e.g., "Wednesday 14:00 FOMC — reduce size or flat")
14. **Focus themes** — 2-3 themes to watch (e.g., "tech earnings week — expect sector-driven moves", "low liquidity holiday-shortened week")
15. **Prop firm weekly targets** — per-account weekly goals aligned with challenge/funded rules (conservative targets preserving drawdown headroom)
16. **Personal focus goals** — based on last week review, 1-2 specific behavioral goals (e.g., "only take A+ setups in first 30 min", "max 3 trades per day this week")

### Output

| Channel | Content | Timing |
|---------|---------|--------|
| Markdown weekly report | Full weekly plan document | Sunday evening |
| Telegram/iMessage push | Key events + weekly bias + personal goals (compact) | Sunday evening |
| TradingView Pine Script | Weekly key levels overlay | Auto-generated |

### CLI (Weekly)

```bash
daytrader weekly                 # Generate full weekly plan
daytrader weekly --review        # Last week review only
daytrader weekly --calendar      # Week ahead calendar only
daytrader weekly --push          # Generate and push to all channels
```

---

## Module 2: Strategy Backtesting System

### Data Pipeline

```
MotiveWave export (tick/footprint)
    → Parser (CSV, custom formats)
    → Standardized models (Tick, FootprintBar, Imbalance)
    → SQLite (incremental import)
```

### Stacked Imbalance Signal Detection

- **Configuration:** consecutive N layers with delta ratio > threshold (e.g., > 300%, ≥ 3 layers)
- **Classification:** buy-side imbalance / sell-side imbalance
- **Context tagging:** market regime (trend/range), volatility level, time-of-day at signal time

### Real-Time Signal Output to MotiveWave

Signal detection is not limited to backtesting — it also serves as a **real-time signal generator** that feeds into MotiveWave for live trading:

- **MotiveWave Plugin Integration:** develop a MotiveWave SDK plugin (Java) that consumes signals from the Python engine
- **Communication:** Python engine publishes signals via local WebSocket or file-based bridge; MotiveWave plugin subscribes and renders in real-time
- **Visual Display:** signals rendered as footprint chart overlays — arrows/markers at imbalance zones, color-coded by signal strength and direction
- **Alert in MotiveWave:** configurable audio/visual alerts when new signal fires

### Signal Notification System

Real-time trading signals are also pushed to external messaging channels for multi-device awareness:

| Channel | Use Case | Format |
|---------|----------|--------|
| Telegram | Mobile push (primary) | Signal summary + key levels |
| iMessage | Apple ecosystem push | Compact alert via AppleScript/Shortcuts |
| Discord | Community/team sharing | Rich embed with chart context |

- **Notification renderer** is plugin-style — same pattern as premarket renderers, easy to add new channels
- **Configurable filters:** user controls which signal types/confidence levels trigger notifications (avoid noise)
- **Latency priority:** notifications fire in parallel with MotiveWave display, not sequentially
- **Signal Metadata:** each signal carries entry zone, suggested stop, target levels, confidence score, and market context

```
Python Signal Engine ──WebSocket/File──→ MotiveWave Plugin
     (detection)                          (real-time display)
```

### Backtest Engine

- **Trade simulation:** entry on imbalance signal, configurable stop-loss and target rules
- **Core metrics:** win rate, average R, max drawdown, profit factor, Sharpe ratio, max consecutive losses
- **Dimensional analysis:** group stats by time-of-day, market regime, signal strength
- **Parameter optimization:** grid search with heatmap visualization for parameter sensitivity

### Backtest Report

- Summary statistics + dimensional breakdown
- Equity curve chart
- Parameter sensitivity heatmap
- Best/worst trade case replay

### CLI

```bash
daytrader bt run --config stacked_imbalance.yaml    # Run backtest
daytrader bt optimize --param imbalance_threshold    # Parameter optimization
daytrader bt report --latest                         # View latest report
daytrader bt import --source motivewave ./data.csv   # Import data
```

---

## Module 3: Autonomous Evolution Engine

### Three Observers

**1. Market Observer (`observers/market.py`)**
- Monitors market regime changes (volatility bands, trend strength, sector rotation)
- Detects regime shifts — when current environment deviates from strategy training conditions
- Trigger: runs daily post-market; real-time on anomaly detection

**2. Performance Monitor (`observers/performance.py`)**
- Tracks rolling signal quality statistics (recent N-day win rate, R-value, decay trends)
- Auto-detects: which signal types are degrading? which sessions underperform? which parameters need recalibration?
- Sources: backtest simulation results + imported trade records

**3. Research Explorer (`observers/research.py`)**
- AI-driven (Claude API) autonomous research:
  - Scans historical data for new effective patterns (imbalance + other indicator combinations)
  - Tests signal variants (different stacking depths, different timeframe imbalances)
  - Analyzes common traits of failed trades, proposes new filter conditions
- Trigger: weekly scheduled exploration tasks

### Hypothesis → Validation → Application Loop

1. Observer detects an anomaly or opportunity
2. **Hypothesis Generator** formulates a specific, testable hypothesis
3. **Auto-Validator** runs targeted backtest against historical data
4. **Evolution Report** documents: discovery → hypothesis → evidence → recommended action
5. **Application** based on confidence level:

| Confidence | Criteria | Action |
|-----------|----------|--------|
| High | Strong statistical significance + large sample | Auto-apply, notify user |
| Medium | Meaningful but limited sample | Push report, await user approval |
| Low | Exploratory finding | Log to research journal, flag for further study |

### Parameter Versioning

- Every parameter change is versioned with timestamp, reason, evidence, and before/after values
- Full rollback support to any historical version
- Learning rate controls to prevent overfitting to recent data

### Evolution Report Format

```markdown
## Evolution Report #NNN — YYYY-MM-DD

### Discovery
[What was observed]

### Hypothesis
[Specific, testable claim]

### Validation
[Backtest methodology and results with statistics]

### Recommendation
[Specific parameter/filter change with expected impact]

### Status: [Pending Approval | Auto-Applied | Logged for Research]
```

### CLI

```bash
daytrader evo status              # View evolution system status
daytrader evo report --latest     # Latest evolution report
daytrader evo approve <id>        # Approve a pending recommendation
daytrader evo rollback <version>  # Rollback parameters
daytrader evo explore --run       # Trigger research exploration now
```

---

## Module 4: Notifications System

Shared notification infrastructure used by all modules. See project structure `src/daytrader/notifications/`.

- Plugin-style: each channel implements `base.py` notifier interface
- Channels: Telegram (primary mobile), iMessage (Apple ecosystem), Discord (community/team)
- All modules route through this system — signals, premarket reports, psychology alerts, evolution reports, learning digests, content publishing
- Configurable per-module: which channels receive which message types
- Rate limiting and quiet hours support

---

## Module 5: Trading Psychology System

Trading psychology is the invisible edge. Technical skill gets you to breakeven; mental discipline gets you profitable. This module makes psychological state observable, trackable, and improvable.

### 5.1 Pre-Session Mental Check-in

Before trading begins, a structured self-assessment (integrated into daily pre-market flow):

```
daytrader pre → ... → Phase 0: Mental Check-in (before any market analysis)
```

**Check-in prompts:**
- **Sleep & energy:** rate 1-5 (auto-flags if below threshold — "consider reduced size or sitting out")
- **Emotional state:** calm / anxious / revenge-seeking / overconfident / fatigued
- **Life stress:** any external stressors affecting focus today?
- **Yesterday's carryover:** any unresolved feelings from last session? (big loss, missed trade, FOMO)

**Output:**
- Stored in DB with timestamp — becomes data for pattern analysis
- If red flags detected → automatic risk adjustment suggestion (e.g., "reduce max trades to 2 today", "no trading in first 15 min")
- Check-in is optional but tracked — the system notes when you skip it (skipping often correlates with poor days)

### 5.2 Real-Time Behavioral Guardrails

Rules-based circuit breakers triggered by trading behavior patterns:

| Guardrail | Trigger | Action |
|-----------|---------|--------|
| **Revenge trade detector** | 2+ losses followed by immediate re-entry (<2 min) | Alert: "Possible revenge trade — take a 10-min break" |
| **Overtrading alert** | Exceeds daily trade count limit (configurable) | Alert: "Daily trade limit reached — review before next entry" |
| **Tilt detector** | 3 consecutive losses + increasing position size | Alert: "Tilt pattern detected — mandatory 15-min cooldown" |
| **Win streak overconfidence** | 3+ wins followed by size increase beyond plan | Alert: "Stick to planned size — overconfidence risk" |
| **Fatigue timer** | Continuous screen time > N hours without break | Alert: "Take a break — decision quality degrades after extended sessions" |

- Guardrails are configurable — user sets thresholds and which ones are active
- Alerts push to same notification channels (Telegram, iMessage, Discord)
- All triggers logged for post-session review

### 5.3 Post-Session Reflection

Automated end-of-day psychological debrief:

**Auto-generated prompts based on the day's data:**
- After a losing day: "What was your emotional state during the largest loss? Did you follow your stop?"
- After overtrading: "You took 8 trades today (plan was 4). What drove the extra entries?"
- After a great day: "What did you do differently today? How can you replicate this state?"
- After sitting out: "Good discipline. What kept you patient?"

**Structured journaling:**
- Rate the day: execution quality (1-5), discipline (1-5), emotional control (1-5)
- One thing done well, one thing to improve
- Stored alongside trade data — links psychology scores to actual performance

### 5.4 Psychology Analytics

Long-term pattern discovery from accumulated check-in + reflection data:

- **Correlation analysis:** sleep score vs. daily P&L, emotional state vs. win rate, screen time vs. trade quality
- **Behavioral patterns:** "You lose money 73% of the time when you rate emotional state as 'anxious'"
- **Time patterns:** "Your worst decisions happen between 11:30-12:00 — consider blocking this period"
- **Improvement tracking:** rolling trend of discipline scores, overtrading frequency, revenge trade incidents
- **Monthly psychology report:** auto-generated insights with trends and specific recommendations

### 5.5 Integration with Evolution Engine

The evolution engine's Research Explorer includes psychology as a dimension:

- Hypotheses like: "Filtering out trades taken when mental check-in score < 3 would improve profit factor by 15%"
- Parameter adjustments that factor in psychological state (e.g., auto-reduce position size on low-energy days)
- Recommendations blend technical and psychological: "Your A+ setup works 72% of the time overall, but only 45% when you're in a revenge-trading state"

### CLI

```bash
daytrader psych checkin              # Pre-session mental check-in
daytrader psych reflect              # Post-session reflection
daytrader psych stats                # Psychology analytics dashboard
daytrader psych report --monthly     # Monthly psychology report
daytrader psych guardrails           # View/configure active guardrails
```

---

## Module 6: Learning & Content Curation

Continuous self-improvement through curated, personalized learning content. The system acts as a personal trading education assistant — finding the right content at the right time based on your actual trading weaknesses and interests.

### 6.1 Content Sources

| Source Type | Examples | Method |
|-------------|----------|--------|
| Articles & blogs | Medium, Substack, trading blogs, research papers | Web scraping + RSS |
| Videos | YouTube (trading channels), webinar replays | YouTube API + channel subscriptions |
| Books | New releases, classic recommendations | Goodreads API / curated lists |
| Twitter/X threads | Order flow traders, market structure analysts | X API / curated account list |
| Reddit | r/orderflow, r/daytrading, r/futurestrading | Reddit API |
| Podcasts | Chat with Traders, Order Flow Online, etc. | Podcast RSS feeds |

### 6.2 Intelligent Curation

Content is not just aggregated — it's **filtered and ranked by relevance to you:**

**Keyword & topic matching:**
- Core topics: order flow, footprint charts, stacked imbalances, delta, volume profile, auction market theory
- Extended topics: market microstructure, prop firm strategies, trading psychology, risk management

**Personalized ranking based on your data:**
- Psychology module flags "revenge trading" as a weakness → system surfaces articles/videos on emotional discipline
- Backtest shows poor performance in choppy markets → system finds content on range-bound strategies and order flow in low-volatility
- Evolution engine detects signal degradation in opening 15 min → system searches for opening range tactics

**Quality scoring:**
- Engagement metrics (views, likes, shares)
- Source reputation (known quality authors/channels get higher weight)
- Recency (prefer fresh content, but surface timeless classics when relevant)
- AI summary + relevance score (Claude evaluates if content is genuinely valuable vs. clickbait)

### 6.3 Content Delivery

| Format | Content | Timing |
|--------|---------|--------|
| **Daily digest** | 3-5 curated articles/videos, matched to recent trading issues | Post-market or evening |
| **Weekly deep dive** | 1 long-form recommendation (book chapter, research paper, workshop video) | Weekend |
| **Contextual suggestion** | Specific content triggered by events (bad day → psychology article) | Real-time |
| **Learning queue** | Bookmarked/saved items for later consumption | On-demand |

- All content pushed via notification channels (Telegram, iMessage, Discord)
- Each item includes: title, source, AI-generated summary (2-3 sentences), relevance reason ("Recommended because your tilt incidents increased this week")

### 6.4 Knowledge Base

Consumed content is stored and organized:

- **Personal library:** all curated content with read/watched status, personal notes, rating
- **Key takeaways extraction:** AI extracts actionable insights from content you've consumed
- **Spaced repetition:** important concepts resurface periodically to reinforce learning
- **Topic graph:** tracks which areas you've studied deeply vs. gaps in your knowledge

### 6.5 Integration with Other Modules

- **Psychology module** → learning content responds to psychological patterns
- **Evolution engine** → technical weaknesses drive technical content curation
- **Weekly plan** → "Learning focus this week" section auto-populated based on last week's data
- **Post-session reflection** → after journaling, suggest one relevant short read/video

### CLI

```bash
daytrader learn digest               # Today's curated content digest
daytrader learn weekly               # Weekly deep dive recommendation
daytrader learn queue                # View learning queue
daytrader learn search "order flow"  # Search curated content library
daytrader learn sources              # Manage content sources / subscriptions
daytrader learn stats                # Learning activity stats
```

---

## Module 7: Instrument Statistical Edge

Beyond strategy backtesting, each tradable instrument has its own behavioral fingerprint — recurring patterns in price action, volume, volatility, and microstructure that create exploitable edges. This module builds and maintains a statistical profile for every instrument you trade.

### 7.1 Instrument Profile

For each symbol (SPY, QQQ, ES, NQ, individual stocks, etc.), the system builds a comprehensive statistical profile:

**Time-of-Day Behavior:**
- Average range by 30-min session block (e.g., 9:30-10:00 = highest range)
- Directional bias by time block (e.g., "ES tends to reverse 10:00-10:30 on FOMC days")
- Volume distribution by time block — when does liquidity peak/dry up
- Spread & slippage patterns — when execution cost is lowest

**Volatility Profile:**
- Average daily range (ADR) — rolling 5/10/20 day
- ATR by timeframe
- Volatility clustering patterns — how often does a big day follow a big day
- Expected move vs. actual move (options-implied vs. realized)

**Key Level Behavior:**
- How often does price respect prior day high/low/close — bounce rate, breakout rate
- Volume Profile level reliability — POC, VAH, VAL as support/resistance hit rates
- Round number magnetism — tendency to gravitate toward .00, .50 levels
- Opening range breakout statistics — ORB success rate by timeframe (5/15/30 min)

**Order Flow Characteristics:**
- Typical imbalance thresholds for this instrument (stacked imbalance on ES behaves differently than on AAPL)
- Delta divergence patterns — how often does delta divergence precede reversal
- Absorption patterns — frequency and reliability of absorption signals at key levels
- Iceberg detection statistics — how common and how predictive

**Event Response:**
- Average move on earnings day (for stocks)
- Response to FOMC/CPI/NFP by instrument
- Post-event drift — tendency to continue or reverse after initial event reaction
- Pre-event contraction — how much does range compress before known events

**Correlation & Relative Behavior:**
- Correlation with SPY/ES (beta)
- Lead/lag relationships — does this instrument lead or follow the index
- Sector relative strength impact — how sector moves affect this name
- Cross-instrument signals — when ES breaks out, how does NQ typically respond

### 7.2 Statistical Edge Discovery

The system actively identifies **exploitable edges** from the data:

```
Raw Data → Statistical Analysis → Edge Candidates → Significance Testing → Confirmed Edges
```

**Edge examples:**
- "ES reverses at prior day high 67% of the time when VIX > 20 — average R of 2.1"
- "AAPL opening range breakout (15 min) has 72% continuation rate on earnings week"
- "NQ stacked sell imbalance at VWAP has 3.2x higher success rate than at random levels"
- "SPY tends to fill overnight gap within first 30 min 61% of the time when gap < 0.5%"

**Significance requirements:**
- Minimum sample size (configurable, default ≥ 30 occurrences)
- Statistical significance (p < 0.05)
- Out-of-sample validation (split test)
- Edge must persist across multiple time periods (not regime-dependent unless labeled as such)

### 7.3 Edge Integration

Discovered edges feed directly into other modules:

| Module | Integration |
|--------|-------------|
| **Premarket** | "Today's statistical edge notes" section — relevant edges for today's watchlist |
| **Signal detection** | Boost/filter signal confidence based on instrument-specific edge data |
| **Backtest** | Test strategies with instrument-specific parameters (not one-size-fits-all) |
| **Evolution** | Edges are continuously validated; decaying edges trigger re-evaluation |
| **Prop firm** | Edge strength informs position sizing under risk constraints |

### 7.4 Reports

- **Instrument profile card:** one-page statistical summary for any symbol
- **Edge catalog:** all confirmed edges with current status (active/decaying/invalidated)
- **Comparative analysis:** side-by-side instrument comparison (e.g., ES vs NQ for your strategy)
- **Seasonal/calendar patterns:** monthly/weekly/day-of-week tendencies

### CLI

```bash
daytrader stats profile ES                   # Full statistical profile for ES
daytrader stats profile AAPL --timeframe 5m  # Profile at specific timeframe
daytrader stats edges                        # List all confirmed edges
daytrader stats edges --instrument SPY       # Edges for specific instrument
daytrader stats compare ES NQ                # Side-by-side comparison
daytrader stats update                       # Refresh all profiles with latest data
daytrader stats calendar ES                  # Seasonal/calendar patterns
```

---

## Module 8: Knowledge Base & Content Publishing

Trading knowledge decays if not captured, and compounds if shared. This module serves dual purposes: an internal knowledge management system for continuous improvement, and an automated content publishing pipeline for external audience building and revenue generation.

### 8.1 Internal Knowledge Base

**Knowledge Capture (Automatic + Manual):**

Sources automatically feeding into the knowledge base:
- Evolution reports → distilled into strategy insights
- Backtest findings → validated patterns become knowledge entries
- Instrument edge discoveries → statistical facts
- Psychology reflections → behavioral insights
- Learning module takeaways → extracted concepts from consumed content
- Weekly/daily reviews → recurring observations

Manual capture:
- Quick notes during trading: `daytrader kb add "Noticed ES respects VWAP more cleanly on low VIX days"`
- Tag-based organization: #orderflow, #psychology, #ES, #propfirm, #setup, etc.

**Knowledge Structure:**

```
Knowledge Base
├── Strategies/          # Validated strategy descriptions & rules
├── Setups/              # Specific trade setup playbooks with examples
├── Market Insights/     # Market structure observations & statistical findings
├── Psychology/          # Mental models, behavioral rules, emotional patterns
├── Prop Firm/           # Platform-specific rules, tips, gotchas
├── Lessons Learned/     # Mistakes & corrections (linked to actual trades)
└── Research/            # Ongoing hypotheses & explorations
```

**Knowledge Evolution:**
- Entries have confidence levels that update over time (hypothesis → tested → validated / invalidated)
- Cross-linking: related entries auto-linked (e.g., a setup links to its backtest results, instrument edge, and psychology notes)
- Periodic review prompts: "You haven't revisited your 'Opening Range Breakout' setup notes in 60 days — still valid?"

### 8.2 Content Publishing Pipeline

Transform internal knowledge into publishable content across multiple platforms:

**Content Generation Flow:**

```
Knowledge Base Entries
        ↓
  AI Content Generator (Claude)
    - Selects publishable material
    - Adapts tone/format per platform
    - Sanitizes proprietary details (configurable: what to share vs. keep private)
        ↓
  Content Queue (draft review)
        ↓
  User Review & Approve / Auto-publish (per confidence level)
        ↓
  Multi-Platform Publishing
```

**Platform Support:**

| Platform | Content Type | Format | Frequency |
|----------|-------------|--------|-----------|
| Twitter/X | Short insights, trade lessons, statistical facts | Thread / single tweet | Daily (1-3 posts) |
| Substack / Blog | Deep dives, strategy breakdowns, weekly market reviews | Long-form article | Weekly |
| YouTube / TikTok | Trade recaps, setup explanations, educational content | Script + outline (video production manual) | Weekly |
| Discord / Telegram channel | Real-time insights, community discussion starters | Short posts | As generated |
| Book manuscript | Accumulated knowledge organized by theme | Book chapters (Markdown → export) | Ongoing accumulation |

**Content Categories:**

1. **Trade recaps** — anonymized breakdowns of interesting trades with lessons (auto-generated from journal data)
2. **Statistical insights** — "Did you know ES reverses at prior day high 67% of the time?" (from stats module)
3. **Strategy education** — order flow concepts, footprint reading, imbalance interpretation (from knowledge base)
4. **Psychology posts** — emotional discipline, tilt management, routine building (from psychology module)
5. **Market commentary** — weekly/daily market outlook (from premarket/weekly modules)
6. **Prop firm guides** — challenge strategies, rule navigation, platform comparisons (from prop module)

### 8.3 Privacy & Sanitization

Critical for protecting your actual edge while still sharing valuable content:

- **Privacy levels per knowledge entry:**
  - `public` — safe to share as-is
  - `sanitized` — share concept but obscure specific parameters/thresholds
  - `private` — never publish, internal only
- **Auto-sanitization rules:** strip exact parameter values, replace with ranges ("imbalance threshold between 200-400%" instead of exact value)
- **Review gate:** all content passes through approval queue before publishing (unless explicitly set to auto-publish)

### 8.4 Audience & Revenue Tracking

- **Analytics integration:** track followers, engagement, click-through per platform
- **Content performance:** which topics/formats drive the most engagement
- **Revenue tracking:** subscription revenue (Substack), ad revenue, affiliate links
- **Feedback loop:** high-engagement topics get prioritized for future content generation

### 8.5 Book Manuscript Builder

Long-term book project support:

- Knowledge base entries tagged as `book-worthy` accumulate over time
- AI organizes into thematic chapters: "Part 1: Order Flow Fundamentals", "Part 2: Psychology of Scalping", etc.
- Each chapter drafts from validated knowledge entries + real (anonymized) trade examples
- Export to Markdown → convertible to PDF, ePub, or publisher-ready format
- Progress tracking: word count, chapter completion, gaps to fill

### CLI

```bash
daytrader kb add "insight text" --tags orderflow,ES   # Quick knowledge capture
daytrader kb search "VWAP"                            # Search knowledge base
daytrader kb review                                   # Review entries due for validation

daytrader publish queue                               # View content queue (drafts)
daytrader publish approve <id>                        # Approve draft for publishing
daytrader publish now <id> --platform twitter          # Publish immediately
daytrader publish schedule <id> --time "2026-04-10 09:00"  # Schedule publication
daytrader publish stats                               # Audience & revenue analytics

daytrader book status                                 # Book manuscript progress
daytrader book generate --chapter 3                   # Generate/update chapter draft
daytrader book export --format pdf                    # Export manuscript
```

---

## Module 9: Trade Journal & Auto-Import

### Pain Point

Manual trade logging is tedious and error-prone. The system should automatically ingest trade records from multiple sources with minimal user effort.

### Auto-Import Pipeline

```
Data Sources                    Import Engine                   Database
─────────────                   ─────────────                   ────────
MotiveWave export (CSV)    ─┐
                            ├→  Parser (per-source)  →  Normalizer  →  Dedup  →  SQLite
Broker/Prop firm reports   ─┘       ↑                      ↑
  (CSV, PDF, API)                   │                      │
                              Source plugins          Match by symbol +
                              (one per format)        time + price + size
```

### Import Sources (Plugin-style)

| Source | Method | Format |
|--------|--------|--------|
| MotiveWave | File export | CSV |
| Broker statements | File upload | CSV / PDF parse |
| Prop firm platforms | File upload or API | CSV / Platform-specific |

- Each source has a dedicated **parser plugin** — same registry pattern as other modules
- New brokers/platforms can be added by implementing the parser interface

### Auto-Import Modes

| Mode | Trigger | Use Case |
|------|---------|----------|
| **Watch folder** | File dropped into `data/imports/` | Set MotiveWave/broker export path → auto-detect and import |
| **CLI import** | `daytrader journal import ./file.csv` | Manual one-off import |
| **Scheduled pull** | Cron/scheduler | Future: API-based auto-pull from platforms that support it |

### Normalization & Dedup

- All trades normalized to a standard model: `symbol, side, entry_time, entry_price, exit_time, exit_price, size, pnl, fees, source`
- **Dedup logic:** match by symbol + entry_time (±tolerance) + price + size to prevent duplicates across sources
- **Conflict resolution:** if two sources disagree on a field (e.g., slightly different fill price), prefer broker data (authoritative) over MotiveWave

### Trade Enrichment

After import, trades are automatically enriched with context:

- **Signal linkage:** match trade to the signal that triggered it (by time + price proximity)
- **Market context:** tag with regime, volatility, session at trade time
- **Prop firm tagging:** associate with active prop firm account and rule profile
- **P&L in R-multiples:** calculate R based on actual stop distance

### Journal Outputs

- Per-trade detail view with linked signal and market context
- Daily/weekly/monthly summary statistics
- Performance by signal type, time-of-day, prop firm account
- Feeds into evolution engine's Performance Monitor

### CLI

```bash
daytrader journal import ./trades.csv --source motivewave    # Import from file
daytrader journal import ./statement.csv --source broker     # Import broker statement
daytrader journal watch                                      # Start watch folder daemon
daytrader journal summary --period weekly                    # Weekly summary
daytrader journal list --date 2026-04-08                     # View day's trades
```

---

## Data Model (Core)

### Key Entities

- **Signal** — detected imbalance signal with location, strength, context
- **Trade** — simulated or real trade with entry/exit/result
- **Level** — key price level with source and type
- **MarketContext** — regime snapshot (volatility, trend, sector data)
- **Hypothesis** — generated hypothesis with status and evidence
- **EvolutionLog** — parameter change record with version, reason, evidence
- **PremarketReport** — daily pre-market analysis output

### Database

SQLite with well-defined schema. Abstraction layer (repository pattern) for future PostgreSQL migration.

---

## Data Flow

```
                    ┌─────────────┐
                    │ External     │
                    │ TradingView  │
                    │ News APIs    │
                    │ MotiveWave   │
                    └──────┬──────┘
                           ▼
┌──────────────────────────────────────────────┐
│         Data Collection & Persistence         │
│     SQLite (tick, signals, trades,            │
│      market context, evolution log)           │
└───────┬──────────────┬───────────────┬───────┘
        ▼              ▼               ▼
  ┌──────────┐  ┌───────────┐  ┌────────────┐
  │ Premarket │  │ Backtest  │  │ Evolution  │
  │ System    │  │ System    │  │ Engine     │
  │           │  │           │  │            │
  │ Collect → │  │ Parse →   │  │ Observe →  │
  │ Analyze → │  │ Detect →  │  │ Hypothesize│
  │ Render    │  │ Simulate →│  │ → Validate │
  │ → Push    │  │ Report    │  │ → Apply    │
  └──────────┘  └───────────┘  └────────────┘
        │              │               │
        └──────────────┴───────────────┘
                       ▼
              ┌────────────────┐
              │  Unified CLI    │
              │ daytrader pre   │
              │ daytrader bt    │
              │ daytrader evo   │
              └────────────────┘
```

---

## Module 10: Prop Firm Trading Module

User trades multiple prop firm accounts simultaneously, each with unique rule constraints. This module ensures strategies, signals, and evolution all operate within prop-specific boundaries.

### Rule Engine

Each prop firm is defined as a **rule profile** in config:

```yaml
# config/prop_firms/ftmo.yaml
name: FTMO
account_size: 100000
rules:
  max_daily_loss_pct: 5          # Daily loss limit
  max_total_drawdown_pct: 10     # Max trailing/absolute drawdown
  min_trading_days: 10           # Minimum active trading days
  max_position_size: 10          # Max lots/contracts
  weekend_holding: false         # No weekend positions
  news_trading: restricted       # Some firms restrict news trading
  scaling_plan: true             # Funded account scaling rules
  profit_target_pct: 10          # Challenge profit target
  time_limit_days: 30            # Challenge time limit
```

- **Multi-profile support:** each prop firm has its own rule profile, user can switch or run in parallel
- **Rule validator:** before any trade signal fires, validate against active prop firm rules (position size, daily loss remaining, drawdown headroom)
- **Real-time risk dashboard:** track current account state vs. rule limits

### Prop-Aware Signal Filtering

Signals pass through a **prop rule gate** before output:

```
Signal Detector → Prop Rule Gate → Approved Signal → MotiveWave / Notifications
                       ↓
                  Blocked (with reason: "daily loss limit 80% consumed")
```

- Dynamically adjusts position sizing based on remaining daily loss budget
- Blocks signals when risk limits are near breach
- Annotates approved signals with prop-adjusted stop/target (tighter if headroom is low)

### Prop-Specific Backtest Mode

The backtest engine supports **prop-constrained simulation:**

- Simulate entire challenge periods (e.g., 30-day FTMO challenge)
- Enforce daily loss resets, drawdown tracking, minimum trading day requirements
- Report: challenge pass rate, average days to target, risk of ruin, worst drawdown path
- Compare strategy performance across different prop firm rule sets

### Prop-Specific Evolution

The evolution engine includes prop firm awareness:

- **Performance Monitor** tracks per-prop-firm metrics (not just overall)
- **Hypothesis generation** considers prop constraints (e.g., "reducing trade frequency on day 25+ improves challenge pass rate")
- **Parameter optimization** under prop constraints — optimize not just profit factor but **challenge pass rate**

### CLI

```bash
daytrader prop status                        # Current account states vs. rules
daytrader prop switch ftmo                   # Activate FTMO rule profile
daytrader bt run --prop ftmo                 # Backtest under FTMO rules
daytrader bt run --prop topstep              # Compare under Topstep rules
daytrader evo report --prop ftmo             # Prop-specific evolution insights
```

---

## Commercialization Design

- **Core/config separation:** `daytrader` package is the product; `config/user.yaml` is personalization
- **Plugin registry:** new signal detectors, data sources, renderers register as plugins without modifying core
- **API layer:** internal function calls with clean interfaces; wrappable as REST/WebSocket API later
- **SQLite → PostgreSQL:** zero-config dev; smooth migration path for production
- **Multi-user ready:** config-driven, no hardcoded user assumptions in core engine

---

## Verification Plan

1. **Core & DB:** create all tables, verify CRUD operations on each entity model
2. **Pre-market (daily):** run `daytrader pre`, verify markdown report + Telegram push + Pine Script output
3. **Pre-market (weekly):** run `daytrader weekly`, verify review + macro + plan sections
4. **Backtest:** import sample tick data, run backtest, verify statistics match manual calculation
5. **Real-time signals:** trigger signal detection, verify MotiveWave plugin receives and displays
6. **Notifications:** send test message to each channel (Telegram, iMessage, Discord)
7. **Evolution:** seed historical data, trigger observers, verify hypothesis → validation → report flow
8. **Psychology:** complete check-in → trade session → reflection cycle, verify data stored and analytics work
9. **Learning:** trigger content scrape, verify curation ranking and digest generation
10. **Stats:** build instrument profile from sample data, verify edge discovery with known patterns
11. **Knowledge base:** add entries, generate content drafts, verify sanitization rules
12. **Journal:** import from MotiveWave + broker, verify dedup and enrichment
13. **Prop firm:** configure rule profile, run constrained backtest, verify signal gate blocks correctly
14. **Integration:** full daily cycle (pre-market → signals → journal import → reflection → evolution) end-to-end
