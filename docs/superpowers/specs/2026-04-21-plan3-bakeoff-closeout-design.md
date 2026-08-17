# Plan 3 — W2 Bake-off Closeout (Lean, Time-boxed)

**Date:** 2026-04-21
**Status:** Approved by user in chat (2026-04-21, time-boxed scope decision).
**Parent spec:** [`2026-04-20-strategy-selection-bakeoff-design.md`](2026-04-20-strategy-selection-bakeoff-design.md) §2 (evaluation protocol), §5.3 milestones M2/M5/M6/M7/M8.
**Predecessor:** Plan 2c S2 deferral (commit `2f9d982`) → `n_trials = 2` (S1a + S1b only).

---

## 1. Purpose

Execute W2 Setup Gate bake-off evaluation on SPY 2018-05 → 2024-12 for the two active candidates (S1a, S1b), produce a formal pass/fail report against spec §2.4 hard gates, and close out the bake-off track. Expected outcome: "no Contract signed" per spec §2.5 failure branch (predicted by pre-cost gross PnL +$58/6.5y for S1a — clearly below any plausible hard-gate threshold after costs).

**Objective is not to find edge.** It is to **rigorously document the absence of edge** and preserve the research infrastructure for future strategy work.

## 2. Non-Goals

- **No pybroker.** S1 strategies already return `list[Trade]`; metrics can be computed directly in pandas. Spec §1.2 lists pybroker as the engine; this scope decision deviates deliberately to save ~1 day of integration.
- **No MES extension.** Parent spec's original MES framing is a known drift; Plan 3 stays on SPY. If the user wants MES later, it's a separate plan.
- **No new candidates or S2 re-test.** Plan 2c ruled S2 out.
- **No `promote` CLI / YAML v2 / Contract.md filler.** Predicted decision is "don't sign"; these features are only needed if a candidate passes. If one does, a trivial follow-up PR adds them.
- **No QQQ replication.** Would double `n_trials` and shift scope.

## 3. Scope

### 3.1 Cost model (locked for Plan 3)

SPY retail round-trip cost = **$0.50 per trade** (fixed). Rationale:
- IBKR Pro tiered: $0.0035/share; SPY at $450 × 1 unit = $0.0035 commission/side.
- Half-spread on SPY is typically $0.005 = $0.005/share at 1 unit = $0.005/side.
- Conservative "retail realistic" = ~$0.01 total/side × 2 sides = $0.02 round-trip at 1 share.
- But the strategies don't specify position size; using a unit-normalized model `$0.50/trade` approximates a more realistic position (~50 shares, not the toy 1-share) and gives SE-1 room to scan.

Applied as point-value subtraction: `net_pnl = gross_pnl - 0.50` per trade. Sensitivity experiment SE-1 scans `{0.0, 0.50, 1.00}` (i.e., × {0, 1, 2}).

### 3.2 Data split (from parent spec §2.2, adjusted to actual window)

| Window | Dates | Trading days | Purpose |
|---|---|---|---|
| Replication | 2018-05-01 → 2024-03-31 | ~1489 | In-sample; spec §2.2 "paper window + tail" |
| **Pure OOS** | **2024-04-01 → 2024-12-31** | **~189** | **Main decision window per spec §2.4** |

Already-cached SPY ARCX.PILLAR data covers both.

### 3.3 Metrics (from parent spec §2.4)

Compute for each (candidate, window) cell — 2 candidates × 2 windows = 4 cells, plus SE variants:

| Metric | Hard gate | Formula |
|---|---|---|
| Annualized Sharpe (net) | **≥ 1.0** | `mean(daily_return) / std(daily_return) × sqrt(252)` |
| Annualized Sortino | ≥ 1.5 | Same but denominator = downside deviation |
| Calmar ratio | ≥ 1.0 | `annualized_return / max_drawdown` |
| Max drawdown | **≤ 15%** | Peak-to-trough on cumulative equity |
| Longest DD duration | ≤ 60 trading days | Bars to recover peak |
| Profit factor | **≥ 1.3** | `sum(wins) / abs(sum(losses))` |
| Expectancy (R) | ≥ 0.2 | `avg(r_multiple)` |
| n_trades (pure OOS) | **≥ 100** | count |
| DSR p-value | **< 0.10** | López de Prado DSR with `n_trials=2` |
| Bootstrap 95% CI of Sharpe | lower bound > 0 | 10k resample |
| Excess Sharpe vs SPY buy-hold | > 0.3 | Difference vs baseline |

**Bold = 5 hard gates.** Any miss = not recommended. Evaluated on pure OOS.

### 3.4 Sensitivity experiments (all 4 done)

| Experiment | Scan | Diagnostic signal |
|---|---|---|
| SE-1 Cost | `cost_per_trade ∈ {0.0, 0.5, 1.0}` | If `cost=0` is the only positive → edge is paper-thin vs slippage |
| SE-2 Signal reversal | S1a/S1b flipped long↔short | If reversed also profits → long-bias β, not α → **reject** |
| SE-3 OOS quarterly | 2024 Q2/Q3/Q4 separately | Any quarter < −3% equity → regime fragility |
| SE-4 OR duration | `or_minutes ∈ {5, 10, 15, 30}` (S1a target logic) | Only `5` works → overfit to indicator |

Each SE is a scan runner similar to Plan 2c's; output as table in findings doc.

## 4. Architecture

### 4.1 New modules

```
src/daytrader/research/bakeoff/
├── costs.py                                 # cost subtraction + SE-1 helpers
└── metrics.py                               # Sharpe/Sortino/Calmar/MDD/PF/DSR/bootstrap

scripts/
├── bakeoff_plan3_main_run.py                # § 3.3 main report
├── bakeoff_plan3_se1_cost.py                # SE-1
├── bakeoff_plan3_se2_reversal.py            # SE-2
├── bakeoff_plan3_se3_quarterly.py           # SE-3
└── bakeoff_plan3_se4_or_duration.py         # SE-4

docs/research/bakeoff/
├── 2026-04-21-plan3-main-report.md          # Day 1 output
├── 2026-04-21-plan3-sensitivity.md          # Day 2 output
├── 2026-04-21-plan3-findings.md             # Day 3: decision + pass/fail table
└── 2026-04-21-bakeoff-retrospective.md      # Day 3: lessons learned, what's preserved
```

### 4.2 Reused

- `data_spy.py` / `data_spy_daily.py` (ARCX.PILLAR loaders)
- `strategies/s1_orb.py` (S1a / S1b unchanged)
- `strategies/_trade.py`, `_orb_core.py`, `_known_answer.py`
- `_s2_scan_mfe_mae.py` pattern (template for SE scan runners)

### 4.3 Boundaries

- `costs.py` is pure-pandas, no pybroker.
- `metrics.py` consumes a `list[Trade]` + a point-value cost, returns a dict of metric values. No side effects.
- Each scan runner is a single file, follows Plan 2c's pattern (load cache → loop params → collect metrics → write CSV + markdown to stdout).
- Reports under `docs/research/bakeoff/` are markdown files committed to the repo; CSVs alongside are the machine-readable source.

## 5. Timebox (3 working days)

| Day | Deliverable | Hard stop |
|---|---|---|
| 1 | costs + metrics + main run report | If metrics module takes > 6 hours, simplify and move on |
| 2 | 4 sensitivity scans | If any scan takes > 1 hour wall-clock, cut its grid |
| 3 | findings doc + retrospective + merge PR | Default outcome = "0 passing → no Contract" |

If day 3 slips because a candidate unexpectedly passes hard gates, add 1 more day for a follow-up scope discussion (not auto-proceed to signing).

## 6. Decision framework (pre-committed)

Evaluated after Day 1 main report, reaffirmed after Day 2 sensitivity:

| Condition | Decision |
|---|---|
| Both S1a and S1b fail ≥ 1 hard gate on pure OOS | **"No Contract signed."** Spec §2.5 failure branch. Close bake-off. |
| Exactly one candidate passes all 5 hard gates + survives SE-2 (reversal is negative) + SE-3 (no quarter < −3%) | **Lock as `locked_setup`** (requires a brainstorm session to add `promote` CLI + YAML v2 — Plan 3 stops; user decides next) |
| Both pass | Pick higher Sharpe; runner-up → `backup_setup`. Same caveat as above. |

Predicted outcome based on current evidence: **first row** (neither passes). This pre-commit prevents the "one barely passed, let's tweak" failure mode.

## 7. Success Criteria

Plan 3 done when:
1. Unit tests green (baseline 232 + new costs/metrics tests = ~240 expected).
2. All 4 scan scripts run end-to-end on the cached dataset.
3. Four docs exist in `docs/research/bakeoff/` (main report, sensitivity, findings, retrospective).
4. Findings doc commits to a §6 branch explicitly.
5. Retrospective doc lists what infrastructure is preserved for future work and what known gaps remain (MES untested, KAT-on-own-data, cost model coarse).
6. All merged to main in a single closing PR titled "W2 bake-off closeout".

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-3-1 | Metric implementations have bugs (Sharpe, DSR) | TDD each metric against a known-answer synthetic series before using on real trades |
| R-3-2 | "One barely passed" ambiguity | Pre-committed §6 table; the decision is read out, not debated |
| R-3-3 | Runtime blows past 3 days | Hard stops per Day in §5. Default assumption: outcome is "no Contract" anyway; spending more time won't change it |
| R-3-4 | Retrospective ignored, lessons lost | Retrospective is a merge-blocking deliverable, not optional |

## 9. Handoff after Plan 3

If "no Contract signed" (expected):
- Bake-off track formally closes.
- User decides: (a) explore new strategy families via fresh brainstorm (likely different from ORB/momentum), (b) start live discretionary trading with journal discipline guardrails and no pre-selected setup, (c) pause.
- Infrastructure (data loaders, Trade type, metrics, KAT harness, MFE/MAE helper) is available for any future bake-off.

If a candidate passes (unexpected):
- Follow-up spec for `promote` + YAML v2 + Contract.md filling.
- Hold on live trading until that infrastructure is in.
