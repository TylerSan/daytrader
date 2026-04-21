# Plan 2c — S2 ATR Multiplier Diagnostic

**Date:** 2026-04-21
**Status:** Approved by user (brainstorming session 2026-04-21).
**Parent spec:** [`2026-04-20-strategy-selection-bakeoff-design.md`](2026-04-20-strategy-selection-bakeoff-design.md) §3.3 (S2 rules), §3.4 SE-6 (ATR multiple sensitivity).
**Predecessor merges:** PR #2 (S1 wrong-way guard), PR #3 (ARCX.PILLAR data expansion).

---

## 1. Purpose

Investigate why S2a (max 1 trade/day) and S2b (max 5 trades/day) produce **nearly identical** trade sets on SPY 2018-2023 (1232 vs 1238, only 6 trades diverge across 6.5 years). The canonical 2×ATR_14 stop almost never fires (< 1% of trades) — meaning S2 positions almost always drift to EOD and the per-day cap distinction is vacuous.

**Answer two questions:**
1. **At which `atr_multiplier` does S2a ≠ S2b become meaningful?** I.e., where do stops start firing often enough that intraday re-entries can differentiate S2a's 1-trade cap from S2b's 5-trade cap.
2. **At any scanned multiplier, does S2 have positive gross edge on SPY?** Or is the strategy structurally unprofitable regardless of stop distance?

**Output:** A single decision — keep canonical 2×ATR, change it to X×ATR, or flag S2 rules for deeper redesign in a follow-up.

## 2. Non-Goals

- **Not adding candidates.** Spec §1.4 forbids n_trials inflation for hunting edge. The scan is diagnostic; the canonical S2 rule stays 2×ATR unless findings justify a change.
- **Not touching OOS.** Full 2018-05 → 2023-12 in-sample only. OOS (2024-04+) belongs to Plan 3.
- **Not scanning other S2 parameters.** `avg_intraday_return` lookback (SE-5) and boundary formula stay fixed at spec §3.3 values.
- **Not redesigning exit rules.** If the scan shows 2×ATR is fundamentally wrong, that triggers a separate design cycle (not this plan).

## 3. Scope

### 3.1 Scan grid

`atr_multiplier ∈ {1.0, 1.5, 2.0, 2.5, 3.0}` × `{S2a, S2b}` = 10 runs.

Rationale:
- **1.0** — tight; stops should fire often, S2b should diverge from S2a clearly.
- **2.0** — canonical (spec §3.3). Reproduces current observed behavior.
- **3.0** — very loose; expected to converge S2a ≡ S2b fully (stops never fire).
- 1.5 and 2.5 fill in for monotonicity check.

### 3.2 Window

SPY 1m + daily, **2018-05-01 → 2023-12-31** (paper in-sample). Uses existing Databento cache; zero new data spend.

### 3.3 Metrics per run

For each `(atr_multiplier, strategy)` cell:

| Metric | Why |
|---|---|
| `n_trades` | Primary driver of S2a vs S2b divergence |
| `win_rate` | Shape of per-trade outcome distribution |
| `avg_R` | Per-trade expected value |
| `total_pnl_usd` | Gross edge (on $10k starting capital, $1/point) |
| `stop_hit_rate` | Fraction of trades exited via STOP (not EOD) — the key degeneracy driver |
| `long_count / short_count` | Direction balance |

Plus derived across S2a vs S2b:
- `trade_count_delta`: `len(S2b) − len(S2a)`
- `pnl_delta`: `S2b PnL − S2a PnL`

### 3.4 Decision framework (findings document)

After the scan, the findings doc commits to one of three decisions:

| Condition | Decision |
|---|---|
| At 2.0 multiplier, S2a≡S2b is confirmed AS INTENDED, AND no other multiplier produces positive edge → | **Keep canonical 2×ATR.** Plan 3 proceeds with S2 as-is; S2a/S2b redundancy documented as dataset property not bug. |
| Some multiplier M produces meaningful S2a ≠ S2b AND positive avg_R > +0.05 on full window → | **Change canonical to M×ATR** in a separate spec-revision PR. If multiple multipliers qualify, pick the one with highest avg_R; if tied, pick the smaller M (tighter stop = smaller risk per trade, closer to ensemble of earlier Zarattini conventions). S2 KATs re-calibrate. |
| No multiplier produces positive edge, AND S2a ≈ S2b across all multipliers (stops structurally don't help) → | **Flag S2 rules for redesign.** Separate follow-up to explore different exit mechanisms (MFE-based, time-based, etc.). S2 stays in Plan 3 but with a loud caveat. |

The scan's result, not our prior opinion, picks the branch. If the three conditions don't cleanly partition, the findings doc says so and proposes next steps.

## 4. Implementation

### 4.1 Code changes (minimal, ~15 lines)

**`src/daytrader/research/bakeoff/strategies/_s2_core.py`:**
- `walk_forward_with_trailing(..., atr_multiplier: float = 2.0)` — replace hardcoded `2.0 *` with `atr_multiplier *` in stop-update formulas. Default 2.0 preserves existing behavior.

**`src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py`:**
- `S2a_IntradayMomentum_Max1` and `S2b_IntradayMomentum_Max5`: add `atr_multiplier: float = 2.0` dataclass field.
- `_run_day` and `_generate`: thread `atr_multiplier` through to `walk_forward_with_trailing` and to the `initial_stop = entry ± atr_multiplier * atr_14_d` calculation.

**Tests:**
- New unit test: `test_s2_atr_multiplier_affects_stop_distance` — same bars, three multipliers (1.0, 2.0, 3.0), assert `initial_stop` distance scales linearly.
- Existing tests (default `atr_multiplier=2.0`) stay green.
- Existing S2 KATs stay green.

### 4.2 Scan runner

**`scripts/bakeoff_s2_atr_scan.py`:**

Single-file Python script. Structure:
1. Load cached SPY 1m + daily for 2018-05 → 2023-12.
2. Loop 5 multipliers × 2 strategies → 10 runs.
3. Collect metrics per run.
4. Write markdown table to stdout + CSV to `docs/research/bakeoff/s2_atr_scan_results.csv`.

No new dependencies (pandas already present). Runtime < 2 min.

### 4.3 Findings document

**`docs/research/bakeoff/2026-04-21-s2-atr-scan-findings.md`:**

Structure:
- **TL;DR** — one-sentence decision (filled in after running, per §3.4 framework).
- **Method** — scan params, window, data provenance (commits `26d28c7`, `2c7124f` reproducible).
- **Results** — markdown table with all 10 rows + 2 derived-delta columns.
- **Interpretation** — 2-3 paragraphs reading the table.
- **Decision** — which §3.4 branch, and next action.

## 5. File Structure

```
Create:
  scripts/bakeoff_s2_atr_scan.py
  docs/research/bakeoff/2026-04-21-s2-atr-scan-findings.md
  docs/research/bakeoff/s2_atr_scan_results.csv              (generated by runner)

Modify:
  src/daytrader/research/bakeoff/strategies/_s2_core.py          (add atr_multiplier param)
  src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py  (dataclass field + plumbing)
  tests/research/bakeoff/strategies/test_s2_core.py              (1 new test)
```

No spec revisions in this plan. If the findings doc concludes "change canonical to M×ATR", that triggers a separate spec-revision PR.

## 6. Success Criteria

Plan 2c is done when:

1. Full unit suite green (existing 227 passed + new 1 = 228).
2. Live scan runs to completion on SPY 2018-2023 cache, producing the 10-row table.
3. Findings document committed with explicit **Decision** from §3.4's three branches.
4. If decision = "Keep canonical", Plan 3 proceeds unchanged. If decision = "Change to M×ATR", a follow-up spec-revision PR revises §3.3 and S2 KATs before Plan 3 starts. If decision = "Redesign S2", Plan 3 is gated on that redesign.

## 7. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-2c-1 | Scan results look "cherry-pickable" — some multiplier shows mild positive edge that could be p-hacked into the canonical rule | Decision framework in §3.4 is pre-committed. "Positive edge" threshold is avg_R > +0.05 across full window. No partial-window tuning. |
| R-2c-2 | `atr_multiplier` parameter refactor breaks existing S2 KATs | Default stays 2.0; KATs verify bit-for-bit equivalence. Refactor is TDD'd. |
| R-2c-3 | 2c delays Plan 3 indefinitely if scan suggests redesign | Time-box: if §3.4's third branch triggers, write the redesign spec immediately; don't start Plan 3 on broken rules. This is a feature not a bug. |

## 8. Not in scope

- QQQ replication (paper's primary asset) — would double n_trials, not a diagnostic.
- Boundary-width scan (SE-5) — separate diagnostic if S2 structurally unfit.
- Cost-model integration — Plan 3 territory.
- pybroker adapter — Plan 3 territory.
