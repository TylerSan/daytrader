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
| `stop_hit_rate` | Fraction of trades exited via STOP (not EOD) — key degeneracy driver |
| `long_count / short_count` | Direction balance |
| `avg_mfe_R` | Average Maximum Favorable Excursion from entry, in R units. Diagnostic: is the entry *signal* any good (positive MFE) or is the entry also noise? Separates "entry good, exit bad" from "everything bad". |
| `avg_mae_R` | Average Maximum Adverse Excursion. Used with MFE to characterize the profile of held trades. |

MFE/MAE computed bar-by-bar from entry to actual exit. For a long trade: `MFE = max(high during hold) − entry`; `MAE = entry − min(low during hold)`. Normalized by `risk = |entry − initial_stop|` to get R units.

Plus derived across S2a vs S2b:
- `trade_count_delta`: `len(S2b) − len(S2a)`
- `pnl_delta`: `S2b PnL − S2a PnL`

### 3.4 Regime stratification (per-year)

For each `(atr_multiplier, strategy)` cell, additionally break out by calendar year (2018H2, 2019, 2020, 2021, 2022, 2023) the following:

| Metric | Why |
|---|---|
| `n_trades` per year | Check trading frequency is regime-stable |
| `avg_R` per year | Detect if edge (or anti-edge) is concentrated in one regime |
| `total_pnl_usd` per year | Same for PnL sign |

2020 was a vol shock (COVID), 2022 was a bear, 2023 was a reflation rally — aggregate numbers hide regime-specific behavior. If avg_R is positive only in 2020, that's a vol-regime-dependent edge, not a structural one. Decision framework below uses this breakdown.

### 3.5 Decision framework (findings document)

Pre-committed definitions (evaluated on the full 2018-05 → 2023-12 window):

- **"Meaningful S2a ≠ S2b"**: `trade_count_delta / len(S2a) ≥ 0.10` (i.e. S2b generates at least 10% more trades than S2a). Current 2×ATR canonical is 0.5%, clearly fails this.
- **"Positive gross edge"**: `avg_R > 0` AND `total_pnl_usd > 0`. This is a diagnostic floor, not a hard-gate bar. avg_R of +0.05 (≈ S1a's level) produces ~0.1%/year gross, which is noise after transaction costs — Plan 3's spec §2.4 hard gates do the real screening. Here we only want to know "does any multiplier escape negative territory".
- **"Regime-stable edge"**: `avg_R > 0` in at least 4 of the 6 calendar-year buckets. Catches 2020-only vol-regime flukes.
- **"Entry signal quality"**: `avg_mfe_R` consistently ≥ 1.0 across multipliers (MFE exceeds 1R on average). If true, entries touch meaningful favorable moves — exit is the degeneracy driver. If false across all multipliers, the boundary trigger itself is noise.

Decision table (check in order — first matching row wins):

| # | Condition | Decision |
|---|---|---|
| 1 | NO multiplier produces positive gross edge AND `avg_mfe_R < 1.0` universally | **Flag S2 rules for redesign.** Entry signal has no reach; exit fix won't save it. Separate follow-up spec. S2 stays in Plan 3 only with a loud caveat. |
| 2 | Some multiplier M produces meaningful S2a ≠ S2b AND positive gross edge AND regime-stable edge | **Change canonical to M×ATR** in a separate spec-revision PR. Tie-break: highest avg_R; if still tied, smaller M (tighter risk). S2 KATs re-calibrate. |
| 3 | Positive edge at some M but S2a ≡ S2b at all scanned multipliers (entry has edge; stop does not differentiate) | **Keep canonical 2×ATR BUT merge S2a and S2b into one candidate in Plan 3** (per-day cap has no effect on this dataset). Plan 3's n_trials drops from 4 to 3. Document as dataset property. |
| 4 | S2a ≡ S2b at 2.0 AND no multiplier produces positive edge | **Keep canonical 2×ATR as-is, mark S2 as likely R1/R2 failure.** Plan 3 runs the 4 candidates, fully expects S2 to fail hard gates, proceeds to spec §2.5 failure conclusion if appropriate. |
| 5 | None of the above (e.g., mixed signals, partial fits) | **Findings doc enumerates the ambiguity, proposes next diagnostic**, does NOT silently pick a branch. |

The framework is evaluated **once** after running, following the table from top to bottom. No partial-window cherry-picking.

## 4. Implementation

### 4.1 Code changes (minimal, ~15 lines)

**`src/daytrader/research/bakeoff/strategies/_s2_core.py`:**
- `walk_forward_with_trailing(..., atr_multiplier: float = 2.0)` — replace hardcoded `2.0 *` with `atr_multiplier *` in stop-update formulas. Default 2.0 preserves existing behavior.

**`src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py`:**
- `S2a_IntradayMomentum_Max1` and `S2b_IntradayMomentum_Max5`: add `atr_multiplier: float = 2.0` dataclass field.
- `_run_day` and `_generate`: thread `atr_multiplier` through to `walk_forward_with_trailing` and to the `initial_stop = entry ± atr_multiplier * atr_14_d` calculation.

**Tests:**
- New unit test: `test_s2_atr_multiplier_affects_stop_distance` — same bars, three multipliers (1.0, 2.0, 3.0), assert `initial_stop` distance scales linearly.
- New unit test: `test_compute_mfe_mae` — fixture with a known intraday path, assert MFE/MAE numbers match hand-computed expectations.
- Existing tests (default `atr_multiplier=2.0`) stay green.
- Existing S2 KATs stay green.

### 4.2 Scan runner

**`scripts/bakeoff_s2_atr_scan.py`:**

Single-file Python script. Structure:
1. Load cached SPY 1m + daily for 2018-05 → 2023-12.
2. Loop 5 multipliers × 2 strategies → 10 runs.
3. For each run, collect §3.3 summary metrics AND §3.4 per-year breakdown AND MFE/MAE (computed post-hoc by looking up each trade's held 1m bars in the cache — no strategy-class changes needed for this).
4. Write markdown summary table to stdout; CSV with full metrics (one row per `(multiplier, strategy)` for summary and one per `(multiplier, strategy, year)` for stratification) to `docs/research/bakeoff/s2_atr_scan_results.csv` + `_by_year.csv`.

MFE/MAE helper function lives in the script (not the strategy package) since it's scan-specific and doesn't belong in the strategy's wire format. Unit-tested alongside.

No new dependencies (pandas already present). Runtime < 2 min.

### 4.3 Findings document

**`docs/research/bakeoff/2026-04-21-s2-atr-scan-findings.md`:**

Structure:
- **TL;DR** — one-sentence decision (filled in after running, per §3.5 framework).
- **Method** — scan params, window, data provenance (commits `26d28c7`, `2c7124f` reproducible).
- **Results** — markdown table with 10 summary rows + per-year stratification block + MFE/MAE columns.
- **Interpretation** — 2-3 paragraphs reading the tables.
- **Decision** — which §3.5 branch, and next action.

## 5. File Structure

```
Create:
  scripts/bakeoff_s2_atr_scan.py
  scripts/_s2_scan_mfe_mae.py                                (helper, importable by runner + tests)
  tests/scripts/test_s2_scan_mfe_mae.py                      (unit test for MFE/MAE helper)
  docs/research/bakeoff/2026-04-21-s2-atr-scan-findings.md
  docs/research/bakeoff/s2_atr_scan_results.csv              (generated by runner — committed for review)
  docs/research/bakeoff/s2_atr_scan_results_by_year.csv      (generated by runner — committed for review)

Modify:
  src/daytrader/research/bakeoff/strategies/_s2_core.py          (add atr_multiplier param)
  src/daytrader/research/bakeoff/strategies/s2_intraday_momentum.py  (dataclass field + plumbing)
  tests/research/bakeoff/strategies/test_s2_core.py              (1 new test)
```

Generated CSVs are committed to the repo (not gitignored) so the findings doc is self-contained and reproducible from git history alone.

No spec revisions in this plan. If the findings doc concludes "change canonical to M×ATR", that triggers a separate spec-revision PR.

## 6. Success Criteria

Plan 2c is done when:

1. Full unit suite green: existing 227 passed + 2 new tests (atr_multiplier, MFE/MAE helper) = 229 passed.
2. Live scan runs to completion on SPY 2018-05 → 2023-12 cache, producing both summary and by-year CSVs.
3. Findings document committed with explicit **Decision** from §3.5's five branches (including branch 5 "enumerate ambiguity" if the scan doesn't cleanly partition).
4. Next action clearly stated in the findings doc:
   - Branch 1 (redesign) → separate design spec before Plan 3 starts; Plan 3 gated.
   - Branch 2 (change M) → separate spec-revision PR revises spec §3.3 + re-calibrates S2 KATs; then Plan 3.
   - Branch 3 (merge S2a/S2b) → separate spec-revision PR drops one of S2a/S2b; Plan 3 starts with 3 candidates, n_trials=3.
   - Branch 4 (keep as-is, expect failure) → Plan 3 starts unchanged; S2 expected to fail hard gates.
   - Branch 5 (ambiguous) → followup diagnostic plan; Plan 3 gated.

## 7. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-2c-1 | Scan results look "cherry-pickable" — some multiplier shows mild positive edge that could be p-hacked into the canonical rule | Decision framework in §3.5 is pre-committed and this spec is committed *before* the scan runs. "Positive edge" is `avg_R > 0` AND `total_pnl_usd > 0` AND regime-stable (4 of 6 years). No partial-window tuning. Plan 3's hard-gate bar is the real selection filter, not this diagnostic. |
| R-2c-2 | `atr_multiplier` parameter refactor breaks existing S2 KATs | Default stays 2.0; KATs verify bit-for-bit equivalence. Refactor is TDD'd. |
| R-2c-3 | 2c delays Plan 3 if scan suggests redesign (branch 1 or 5) | Time-box to 3 calendar days of work after the scan runs. If a full redesign is needed and can't be scoped in 3 days, Plan 3 starts with 4 candidates as-is and an explicit "S2 under review" caveat in its findings. |
| R-2c-4 | Train-on-test concern if branch 2 fires and M is chosen from the same window it's later evaluated on | Mitigated by: (a) decision framework requires regime-stable edge across 6 years, not overall average; (b) Plan 3's pure OOS (2024-04+) is the independent check; (c) if branch 2 fires we commit to the M before running Plan 3, no re-tuning. |

## 8. Not in scope

- QQQ replication (paper's primary asset) — would double n_trials, not a diagnostic.
- Boundary-width scan (SE-5) — separate diagnostic if S2 structurally unfit.
- Cost-model integration — Plan 3 territory.
- pybroker adapter — Plan 3 territory.
