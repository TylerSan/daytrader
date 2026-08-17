# Plan 3 Day 2 — Sensitivity Experiments

**Date:** 2026-04-21
**Scope:** SE-1..SE-4 per parent spec §3.4 (SE-5/SE-6 deferred with S2 per Plan 2c).
**Window:** Pure OOS 2024-04-01 → 2024-12-31 (186 trades), unless noted.

## SE-1 Cost sensitivity

Scan `cost_per_trade ∈ {0.0, 0.5, 1.0}`. Test whether the Day 1 negative result is purely a cost artifact.

| candidate | cost/trade | n | sharpe | max_dd | profit_factor | net_pnl $ |
|---|---:|---:|---:|---:|---:|---:|
| S1a | 0.00 | 186 | **+0.576** | 0.1% | 1.125 | +12.3 |
| S1a | 0.50 | 186 | −3.764 | 0.9% | 0.538 | −80.7 |
| S1a | 1.00 | 186 | −8.105 | 1.8% | 0.307 | −173.7 |
| S1b | 0.00 | 186 | **+0.549** | 0.1% | 1.118 | +11.6 |
| S1b | 0.50 | 186 | −3.828 | 0.9% | 0.534 | −81.4 |
| S1b | 1.00 | 186 | −8.206 | 1.8% | 0.304 | −174.4 |

**Interpretation:** Even at **zero cost**, Sharpe is only ~+0.56 — well below the 1.0 hard gate. The strategy is not "almost there, blocked by costs"; it is "below threshold at any cost level". The +$12 gross PnL on 9 months is within noise for 186 trades.

## SE-2 Signal reversal

Flip direction label on every OOS trade. If reversed is also positive → candidate is earning long-bias β, not α → reject.

| candidate | variant | n | sharpe | sortino | profit_factor | net_pnl $ |
|---|---|---:|---:|---:|---:|---:|
| S1a | original | 186 | −3.764 | −15.383 | 0.538 | −80.7 |
| S1a | reversed | 186 | −4.916 | −18.412 | 0.429 | −105.8 |
| S1b | original | 186 | −3.828 | −15.514 | 0.534 | −81.4 |
| S1b | reversed | 186 | −4.924 | −18.443 | 0.428 | −106.1 |

**Reject flag:** **no** (neither original nor reversed has positive Sharpe for either candidate).

**Interpretation:** The strategy direction sign is "correct" in the weak sense that reversing makes it worse, not better. But both variants lose money after costs. There's no hidden long-bias β to worry about, and no hidden edge either — just a small directional signal swamped by friction.

## SE-3 OOS quarterly stability

Split pure OOS into 2024Q2/Q3/Q4. Flag any quarter with equity change < −3% (spec §3.4 SE-3 rule).

| candidate | quarter | n | net_pnl $ | equity % | fragile |
|---|---|---:|---:|---:|:---:|
| S1a | 2024Q2 | 61 | −32.9 | −0.33% | — |
| S1a | 2024Q3 | 62 | −26.3 | −0.26% | — |
| S1a | 2024Q4 | 63 | −21.4 | −0.21% | — |
| S1b | 2024Q2 | 61 | −32.6 | −0.33% | — |
| S1b | 2024Q3 | 62 | −27.4 | −0.27% | — |
| S1b | 2024Q4 | 63 | −21.4 | −0.21% | — |

**Interpretation:** No fragile quarter flag. But the uniformity is itself diagnostic — **every** quarter of pure OOS is a small loss (−0.2% to −0.3%). This is the opposite of "regime-dependent"; it's "consistently unprofitable". Under no regime did S1 earn back its costs.

## SE-4 OR duration scan (S1a)

`or_minutes ∈ {5, 10, 15, 30}` on pure OOS with canonical $0.50/trade cost.

| or_minutes | n | sharpe | max_dd | profit_factor | net_pnl $ |
|---:|---:|---:|---:|---:|---:|
| 5 (canonical) | 186 | −3.764 | 0.9% | 0.538 | −80.7 |
| 10 | 187 | −3.675 | 0.9% | 0.551 | −87.9 |
| 15 | 189 | −5.282 | 1.1% | 0.449 | −114.3 |
| 30 | 189 | −3.057 | 0.9% | 0.611 | −83.0 |

**Interpretation:** All OR durations fail. No specific overfit to `or_minutes=5`; in fact `or_minutes=30` is marginally less bad (Sharpe −3.06 vs −3.76 at 5). This confirms the failure is structural to the "OR breakout + fixed target" family on unleveraged SPY, not a parameter choice artifact.

## Day 2 summary

| Sensitivity | Outcome |
|---|---|
| SE-1 cost | Even at cost=0, Sharpe < 1.0. Cost is not the binding constraint. |
| SE-2 reversal | No long-bias β reject flag. Both variants lose; direction sign is directionally correct but immaterial. |
| SE-3 quarterly | No fragile quarter flag. Losses are uniform across regimes (consistent bleed, not regime dependence). |
| SE-4 OR duration | Uniform failure across {5, 10, 15, 30} min. Not a parameter-overfit issue. |

**Net:** the Day 1 "both candidates fail 3/5 hard gates" conclusion is robust across all four sensitivity dimensions. No variant of S1 passes hard gates on SPY 2024 pure OOS.

## Next

Day 3: findings doc will read Day 1 + Day 2 together and commit to Plan 3 spec §6 Branch 1 ("No Contract signed"). Retrospective will archive the full bake-off arc.
