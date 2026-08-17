# Plan 3 Day 1 — Main Run Report

**Date:** 2026-04-21
**Spec:** [`docs/superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md`](../../superpowers/specs/2026-04-21-plan3-bakeoff-closeout-design.md)
**Config:** SPY 2018-05 → 2024-12 ARCX.PILLAR cache; starting capital $10,000; cost $0.50/trade; `n_trials = 2`.
**Reproduce:** `.venv/bin/python scripts/bakeoff_plan3_main_run.py`

## Results

| candidate | window | n | sharpe | sortino | calmar | max_dd | longest_dd_days | profit_factor | expectancy_r | dsr_p | ci95 (Sharpe) | net_pnl $ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| S1a | replication | 1414 | −4.115 | −13.618 | −0.183 | 6.6% | 1413 | 0.487 | +0.063 | 1.000 | [−5.50, −3.01] | −661.66 |
| S1a | **pure OOS** | 186 | **−3.764** | −15.383 | −1.202 | 0.9% | 176 | **0.538** | −0.015 | **0.999** | [−7.69, −1.13] | −80.68 |
| S1b | replication | 1414 | −4.168 | −13.690 | −0.183 | 6.6% | 1413 | 0.484 | +0.060 | 1.000 | [−5.55, −3.06] | −665.22 |
| S1b | **pure OOS** | 186 | **−3.828** | −15.514 | −1.198 | 0.9% | 176 | **0.534** | −0.019 | **0.999** | [−7.78, −1.18] | −81.37 |

## Hard gates on pure OOS (spec §2.4)

Required to pass (all five bold-threshold metrics):
1. Sharpe (net) ≥ 1.0
2. Max drawdown ≤ 15%
3. Profit factor ≥ 1.3
4. n_trades ≥ 100
5. DSR p-value < 0.10 (n_trials = 2)

### S1a pure OOS — **FAIL**
| Gate | Result |
|---|---|
| Sharpe ≥ 1.0 (observed: **−3.76**) | ❌ FAIL |
| Max DD ≤ 15% (observed: 0.9%) | ✅ PASS |
| Profit factor ≥ 1.3 (observed: **0.54**) | ❌ FAIL |
| n_trades ≥ 100 (observed: 186) | ✅ PASS |
| DSR p < 0.10 (observed: **0.999**) | ❌ FAIL |

### S1b pure OOS — **FAIL**
| Gate | Result |
|---|---|
| Sharpe ≥ 1.0 (observed: **−3.83**) | ❌ FAIL |
| Max DD ≤ 15% (observed: 0.9%) | ✅ PASS |
| Profit factor ≥ 1.3 (observed: **0.53**) | ❌ FAIL |
| n_trades ≥ 100 (observed: 186) | ✅ PASS |
| DSR p < 0.10 (observed: **0.999**) | ❌ FAIL |

Both candidates fail three of five hard gates on the pure OOS window.

## Interpretation

The Sharpe ratio is not just below the 1.0 bar — it is **strongly negative** (−3.76 and −3.83). This is what a cost-dominated strategy looks like: small gross edge + per-trade friction that is larger than the edge per trade.

Quick decomposition of the replication window for S1a:
- Gross PnL ≈ +$58 over 6.5 years (per earlier audit, before cost)
- Trades × cost = 1414 × $0.50 = $707
- Net PnL ≈ $58 − $707 = **−$649**, matching the observed −$661.66 (minor difference from rounding + the window being 2018-05 → 2024-03 not 2018-05 → 2024-12)

The strategy is structurally unprofitable after cost.

The DSR p-value of 0.999 means: even at the favorable `n_trials = 2` setting, we cannot reject the null of zero edge. No amount of multiple-testing penalty relief would help here.

Max DD is trivially low (0.9% on pure OOS) only because the strategy bleeds slowly — 186 small losers add up to $81 over 9 months, but no single drawdown event. This is not a "low DD = good" signal; it's a "consistent decay" signal.

## Next

Day 2: run SE-1..SE-4 to check whether any sensitivity variant rescues the result. SE-1 in particular will show whether `cost = 0` flips the sign, which would tell us the edge is purely cost-blocked; if `cost = 0` is also negative, the strategy has no edge at any level.

Based on Day 1 alone, **Plan 3 spec §6 Branch 1** is the near-certain decision: "No Contract signed — both candidates fail ≥ 1 hard gate on pure OOS."
