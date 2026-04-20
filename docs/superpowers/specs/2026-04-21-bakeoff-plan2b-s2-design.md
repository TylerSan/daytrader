# Bake-off Plan 2b — S2 Intraday Momentum Design

**Date:** 2026-04-21
**Status:** Approved by user (brainstorming session 2026-04-21).
**Parent spec:** [`2026-04-20-strategy-selection-bakeoff-design.md`](2026-04-20-strategy-selection-bakeoff-design.md) §3.3 (S2 rules), §5.1 (KAT protocol), M4.
**Predecessor plan:** Plan 2a (merged to main via [PR #1](https://github.com/TylerSan/daytrader/pull/1), commit `3d24636`) — S1 ORB family, SPY 1m loader, KAT harness.

---

## 1. Scope

Mechanize S2 Intraday Momentum (Zarattini-Aziz-Barbon 2024 "Beat the Market", Swiss Finance Institute RP 24-97) as two strategy classes, structurally parallel to Plan 2a's S1 family:

- **S2a**: Intraday Momentum, **max 1 trade per day** (conservative — our choice).
- **S2b**: Intraday Momentum, **max 5 trades per day** (matches Contract's `max_trades_per_day` ceiling, close to paper intent).

Both use the same entry/exit rules from spec §3.3; they differ only in an intraday-throttle counter. Strategy classes stay plain Python (no pybroker), continuing Plan 2a's pattern.

**Out of scope for Plan 2b:** pybroker adapter (Plan 3), walk-forward / sensitivity experiments (Plan 3), MES loader changes, anything touching `src/daytrader/journal/`.

---

## 2. Architecture

### 2.1 New files

```
src/daytrader/research/bakeoff/
├── data_spy_daily.py                             # NEW: ARCX.PILLAR daily SPY loader
└── strategies/
    ├── _s2_core.py                               # NEW: S2 mechanical helpers
    └── s2_intraday_momentum.py                   # NEW: S2a + S2b classes

tests/research/bakeoff/
├── test_data_spy_daily.py                        # NEW
├── test_integration_spy_daily.py                 # NEW (skipped by default)
└── strategies/
    ├── test_s2_core.py                           # NEW
    ├── test_s2_intraday_momentum.py              # NEW
    └── test_s2_kat_spy.py                        # NEW (skipped by default)
```

### 2.2 Reused modules (unchanged)

- `_trade.py` — `Trade`, `TradeOutcome` (wire format).
- `_known_answer.py` — `summary_stats`, `compare_to_paper`, `KnownAnswerResult`.
- `data_spy.py` — DBEQ.BASIC 1m loader (`load_spy_1m`) + `_consolidate_publishers`.

### 2.3 Data sources

| Data | Dataset | Schema | Window needed | Notes |
|---|---|---|---|---|
| SPY 1-minute bars | DBEQ.BASIC | `ohlcv-1m` | 2023-03-28 → 2023-12-29 | Already cached from Plan 2a KAT. |
| SPY daily bars | **ARCX.PILLAR** | `ohlcv-1d` | 2023-03-01 → 2023-12-29 | NEW purchase. NYSE Arca is SPY's primary listing venue → authoritative daily OHLC. ~$1-3. |

### 2.4 Strategy method signature change

S2 needs both 1m and daily bars:

```python
def generate_trades(
    self, bars_1m: pd.DataFrame, bars_1d: pd.DataFrame
) -> list[Trade]: ...
```

S1 classes keep their existing single-arg signature. No common base class; the two families deliberately diverge because S1 is single-data-source and introducing an abstraction now would be premature. Plan 3's pybroker adapter will normalize both into the same runner.

---

## 3. Mechanical rules (per spec §3.3, minor clarifications)

### 3.1 Per-day variables

```
daily_open[d]      = open of the 09:30 ET 1-min bar on day d
prev_close[d]      = close of the 15:59 ET 1-min bar on day d-1
                     (spec says "16:00" but that's the session end; last RTH
                     bar is 15:59. Use 15:59 close = prev_close.)
overnight_gap[d]   = daily_open[d] - prev_close[d]
atr_14[d]          = 14-day SMA of daily True Range, computed from daily bars
                     ending on day d-1 (uses daily CLOSE-to-CLOSE, not
                     intraday high/low; see §3.4). Updated once per day.
```

### 3.2 Per-minute-of-day pattern

For each minute-of-day `t ∈ {10:00, 10:30, …, 15:30}` (12 check times):

```
avg_intraday_return[t] =
    mean over last 14 trading days (ending on day d-1) of:
    (close[t,k] - daily_open[k]) / daily_open[k]
```

where `close[t,k]` is the close of the 1-min bar at clock time `t` on day `k`. This is a rolling 14-day average of the intraday return *at that clock minute*.

### 3.3 Noise boundary

```
raw_upper[t, d] = daily_open[d] × (1 + |avg_intraday_return[t]|)
raw_lower[t, d] = daily_open[d] × (1 - |avg_intraday_return[t]|)

if overnight_gap[d] > 0:     # up-gap
    lower[t, d] = raw_lower[t, d] - overnight_gap[d]
    upper[t, d] = raw_upper[t, d]
elif overnight_gap[d] < 0:   # down-gap
    upper[t, d] = raw_upper[t, d] + abs(overnight_gap[d])
    lower[t, d] = raw_lower[t, d]
else:
    upper, lower = raw_upper, raw_lower
```

### 3.4 ATR definition

Daily True Range for day `d`:
```
TR[d] = max(high[d] - low[d],
            abs(high[d] - close[d-1]),
            abs(low[d] - close[d-1]))
ATR_14[d] = SMA(TR, 14) over days d-13..d
```

Strategy uses `atr_14` computed from daily bars *ending at day d-1* (i.e., the most recent fully-closed daily bar before the trading day). This avoids look-ahead.

### 3.5 Entry

At each check time `t` (10:00, 10:30, …, 15:30 ET):

- If `price[t] > upper[t,d]` and no position is currently open: enter **long** at `close[t] + 1 tick slippage`.
- If `price[t] < lower[t,d]` and no position is currently open: enter **short** at `close[t] - 1 tick slippage`.
- If a position is already open: **ignore** subsequent triggers until flat (no adding, no reversing). After a position closes, subsequent triggers in the same day are eligible again, subject to the daily cap (§3.6).

`price[t]` = close of the 1-min bar at time `t`. Entry fill timestamp = `t`'s bar close.

### 3.6 Daily trade cap

- **S2a**: after any trade is closed, no further entries this day.
- **S2b**: up to 5 trades per day. Counter resets at next session open.

### 3.7 Exit

Three ways out, earliest wins:

1. **Initial stop**: `entry ∓ 2 × ATR_14[d]` (long: minus; short: plus). Checked bar-by-bar.
2. **Chandelier trailing** (ratchets toward price, never away):
   - long: `stop = max(prev_stop, highest_high_since_entry − 2 × ATR_14[d])`
   - short: `stop = min(prev_stop, lowest_low_since_entry + 2 × ATR_14[d])`
   Updated at every 1-min bar close after entry.
3. **Forced flat** at 15:55 ET (5 minutes before session close). Exit at close of 15:55 bar.

**Intra-bar order of operations** (no look-ahead): on each 1-min bar after entry, (a) evaluate stop exit against the *previous* bar's trailing stop using the current bar's high/low, then (b) if still open, update the trailing stop using the current bar's high/low for the *next* bar's check. Initial stop applies to the first post-entry bar; trailing starts updating from there.

### 3.8 Position sizing

Fixed 1 unit (matches S1). Cost model layered on in Plan 3 metrics, not here.

---

## 4. Warmup chain

| Source | Earliest available | First valid signal day | Reason |
|---|---|---|---|
| ARCX.PILLAR daily | 2023-03-01 | 2023-03-22 | ATR_14 needs 14 closed daily bars. |
| DBEQ.BASIC 1m | 2023-03-28 | ~2023-04-20 | `avg_intraday_return[t]` needs 14 trading days of per-minute-of-day history. |

**First day S2 can signal: 2023-04-20.**
**Effective KAT window: 2023-04-20 → 2023-12-29 ≈ 170 trading days.**

Strategy code must skip days before both warmups are ready. Implementation: return `[]` for any day `d` where either `atr_14[d]` is `NaN` or `avg_intraday_return` cannot be computed (insufficient history). This is a silent skip, not an error.

---

## 5. KAT protocol

**Paper**: Zarattini, Aziz, Barbon (2024), "Beat the Market: An Effective Intraday Momentum Strategy", Swiss Finance Institute Research Paper 24-97.

**Why SPY not QQQ**: spec §5.1 says paper replication runs on SPY. Paper's headline figures are QQQ/TQQQ (leveraged), which is aspirational for mechanical validation. We only need to prove rules are implemented correctly — mechanical anchors do that.

**Anchors (parallel to Plan 2a, same 15% tolerance structure):**

| # | Metric | Paper value / band | Tolerance | Purpose |
|---|---|---|---|---|
| 1 | S2a n_trades on SPY 2023-04-20 → 2023-12-29 | 75 (≈ 170 days × 0.44 hit-rate guess) | ±15% | Entry + daily-cap logic |
| 2 | S2a win rate | band `[0.30, 0.65]` | n/a (hard band) | Rule-level sanity |
| 3 | `len(s2b_trades) >= len(s2a_trades)` | strict inequality | n/a | S2b must not under-count S2a |
| 4 | S2a vs S2b average R per trade: `abs(avg_r_b - avg_r_a) / avg_r_a < 0.30` | same entries, same exit logic → similar | n/a | No phantom cap leakage |

**Calibration policy (learned from Plan 2a):** Anchor #1 and #2's numeric values are best-guess bands, not exact paper figures. On first live KAT run, if results fall wildly outside → treat as a bug signal and debug rules. If results are "near but outside" → document and widen band once, like we did for S1a (band [0.25, 0.50] → [0.15, 0.50] with rationale note). Never re-tighten a band to force a PASS on unchanged code.

**Live-test gating**: exactly like Plan 2a — `RUN_LIVE_TESTS=1 + DATABENTO_API_KEY + SPY_HISTORY_YEARS=2023` env vars. Default `pytest` run skips all 4 KAT tests.

---

## 6. Task breakdown (Plan 2b implementation plan)

Target ~7 tasks, aligned with spec M4 ("S1b / S2a / S2b + 各自 known-answer"). Plan 2a's Trade class and KAT harness are reused; no re-implementation needed.

1. **`_s2_core.py`** — mechanical helpers: `overnight_gap`, `daily_true_range`, `atr_14`, `avg_intraday_return_14d`, `compute_noise_boundary`, `walk_forward_with_trailing`. Pure functions, no I/O. Unit tests with synthetic fixtures.
2. **`s2_intraday_momentum.py`** — `S2a_IntradayMomentum_Max1` and `S2b_IntradayMomentum_Max5` classes. Unit tests: entry-trigger correctness (up-gap, down-gap, no-gap days), trailing stop ratchet, 15:55 EOD force-flat, daily trade cap.
3. **Multi-day integration test** — 5-day synthetic fixture (gap up / gap down / flat / no-signal / multi-trigger) covering both S2a and S2b, verifying day-grouping, cap behavior, warmup skip.
4. **`data_spy_daily.py`** — ARCX.PILLAR daily loader. Parallel to `data_spy.py` but simpler: no RTH filter (daily bars are already EOD), no publisher consolidation (daily is consolidated at source). Mock-based unit tests.
5. **Live daily smoke test** (skipped by default) — fetch 1 week of SPY daily from ARCX.PILLAR, verify schema + bar count.
6. **S2 KAT test** (skipped by default) — 4 tests per §5 above.
7. **Final verification** — full suite green, commit history review, directory structure check, journal untouched, pybroker not imported.

---

## 7. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-2b-1 | ARCX.PILLAR not in user's Databento plan | Daily smoke test runs first; clear error on permission failure; fallback docs point to XNAS.BASIC. |
| R-2b-2 | Paper's "dynamic trailing stop" formula is under-specified | Spec §3.3 already locks Chandelier 2×ATR_14 (daily TR). KAT anchor #3 (S2b count ≥ S2a) catches gross misinterpretation. |
| R-2b-3 | `avg_intraday_return[t]` warmup consumes 14 days of KAT window → anchor #1's 75 paper_value may be high | Band-widen policy per §5 covers this. |
| R-2b-4 | Session-calendar quirks (half-days, holidays) around 2023-07-04, 2023-11-24, 2023-12-26 | 1m RTH filter already handles these (Plan 2a). Daily loader inherits same calendar via ARCX.PILLAR's own trading-day output. |
| R-2b-5 | Plan 3 (pybroker adapter) may want a common `generate_trades` signature — S1 single-arg vs S2 two-arg | Plan 3's adapter can wrap S2 with a closure that curries the daily frame. Not a blocker; defer to Plan 3. |

---

## 8. Success criteria (Plan 2b done)

- Full unit suite: 200 (baseline) + ~25 new Plan 2b unit tests passing.
- 4 skipped KAT tests + 1 skipped daily smoke, runnable via `RUN_LIVE_TESTS=1 + ...`.
- Live daily smoke PASS.
- S2 KAT 4/4 PASS on SPY 2023-04-20 → 2023-12-29.
- `src/daytrader/journal/` and `tests/journal/` untouched across branch.
- No `pybroker` imports under `src/daytrader/research/`.

**If KAT anchors #1 or #2 fail outside calibration-policy forgiveness, STOP and debug rules before merging to main.** Plan 3 does not start until Plan 2b KAT passes.
