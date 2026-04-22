# Plan 3 Findings — W2 Bake-off Closeout

**Date:** 2026-04-21
**Spec:** [`docs/superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md`](../../superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md)
**Parent spec:** [`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../../superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md)

---

## TL;DR

**Plan 3 spec §6 Branch 1 — "No Contract signed."** Both S1a and S1b fail three of five hard gates on SPY pure OOS (2024-04 → 2024-12). Sensitivity experiments confirm the failure is structural to the strategy family on this dataset, not an artifact of cost / direction / regime / OR duration. W2 bake-off track formally closes.

## Evidence summary

### Day 1 (main run, pure OOS 2024-04 → 2024-12, cost $0.50/trade)

Hard-gate pass/fail:

| Candidate | Sharpe ≥ 1.0 | Max DD ≤ 15% | PF ≥ 1.3 | n ≥ 100 | DSR p < 0.10 | Overall |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| S1a | ❌ (−3.76) | ✅ (0.9%) | ❌ (0.54) | ✅ (186) | ❌ (0.999) | **FAIL** |
| S1b | ❌ (−3.83) | ✅ (0.9%) | ❌ (0.53) | ✅ (186) | ❌ (0.999) | **FAIL** |

3 of 5 gates fail for each candidate. Detail + full 13-column metrics table in [`2026-04-21-plan3-main-report.md`](2026-04-21-plan3-main-report.md). Source: [`plan3_main_report.csv`](plan3_main_report.csv).

### Day 2 (sensitivity)

| Sensitivity | Outcome |
|---|---|
| SE-1 cost `∈ {0.0, 0.5, 1.0}` | **cost=0 Sharpe is +0.58, still below 1.0 gate.** Cost is not the binding constraint. |
| SE-2 signal reversal | Reversed Sharpe is more negative than original (−4.92 vs −3.76). No long-bias β reject flag; also no hidden edge. |
| SE-3 OOS quarterly (Q2/Q3/Q4) | All three quarters between −0.21% and −0.33% equity. No fragile-quarter flag, but uniform losses → not regime-dependent, just consistent bleed. |
| SE-4 OR duration `∈ {5, 10, 15, 30}` | All four durations produce Sharpe between −3.06 and −5.28. No overfit to 5-min specifically. |

Detail: [`2026-04-21-plan3-sensitivity.md`](2026-04-21-plan3-sensitivity.md).

## Decision (per Plan 3 spec §6)

Walking the pre-committed decision table from top to bottom:

| Row | Condition | Match? |
|---|---|:---:|
| 1 | Both S1a and S1b fail ≥ 1 hard gate on pure OOS | **✅ MATCH** |
| 2 | Exactly one candidate passes all 5 + survives SE-2 + SE-3 | n/a |
| 3 | Both pass | n/a |

**Branch 1 fires.** Decision is final: **no candidate is recommended for locking; W2 Setup Gate bake-off ends with zero setups chosen.**

Rationale in plain language:
- **S1 has no defensible edge on SPY.** Even gross of costs, Sharpe is 0.58 — well below the 1.0 quality bar required to justify mechanical execution.
- **Costs cement the verdict.** With a conservative $0.50/trade retail assumption, net Sharpe is deeply negative (−3.8). The failure is not "close but not quite"; it is structural.
- **Sensitivity experiments remove all obvious escape hatches.** No OR-window size rescues it, no cost assumption rescues it, no regime rescues it, no flip-direction rescues it.
- **S2 was already deferred** per Plan 2c; no candidate remains.

## Next action

W2 bake-off track **formally closes**. The user decides among:

**(a) Explore new strategy families via fresh brainstorm.** Likely candidates (user's call):
- Mean-reversion on SPY intraday (opposite shape: high win rate, small avg R)
- Multi-instrument (QQQ, /ES, /NQ) to see if the family works elsewhere
- Regime-gated ORB (only trade when VIX is in specific band)
- Completely different rule families (e.g., overnight-gap fills, opening-drive continuation)

**(b) Pause mechanical research, start live discretionary trading** with the journal subsystem (already shipped in Phase 2) as the discipline guardrail. No pre-selected setup; each trade manually journaled with pre-commit R, stop, target. This takes the W2 bake-off's null result at face value and moves to empirical discretionary work.

**(c) Pause entirely.** Use the infrastructure and bake-off artifacts as a reference, revisit later.

The infrastructure built over Plans 2a-3 is preserved for future use; see [`2026-04-21-bakeoff-retrospective.md`](2026-04-21-bakeoff-retrospective.md) (Task 12).

## Limitations (stated honestly)

- **SPY only, not MES.** The original spec framed MES as the target instrument; we switched to SPY because Zarattini's paper uses SPY/QQQ and the data is cheaper. If the user wants to rule out MES specifically, a re-run on MES 1m data (with rollover handling) is required. Current evidence suggests the family is unlikely to work there either (MES has similar diurnal structure, higher nominal costs).
- **Single time window.** Pure OOS is 9 months of 2024; 2025 and beyond are not available. A persistent post-2024 edge can't be ruled out by this window alone, but the in-sample 2018-2023 also failed, so the argument that "2024 was an unusually bad year" has to overcome 5.8 prior years of failure too.
- **DSR `n_trials = 2` is the most favorable setting.** Including S2a/S2b (deferred) would have made DSR p-values even less favorable, pushing Branch 1 harder.
- **Cost model is coarse.** $0.50/trade is one conservative number; SE-1 partially addresses this by scanning × {0, 1, 2}. A more nuanced tier-based model is possible but unnecessary given cost=0 also fails.
- **KAT methodology circularity.** KAT thresholds were calibrated against observed values on the same dataset (spec §3.5 S1a wr band widened to observed; Plan 2b S2a n_trades widened after observation). "KAT pass" mostly means "code is internally consistent", not "code matches paper". This does not affect the negative result — we are closing on failure-to-pass, not claiming replication.
