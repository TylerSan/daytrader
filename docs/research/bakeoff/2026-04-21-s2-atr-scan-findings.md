# Plan 2c Findings — S2 ATR Multiplier Diagnostic

**Date:** 2026-04-21
**Spec:** [`docs/superpowers/specs/2026-04-21-s2-atr-scan-design.md`](../../superpowers/specs/2026-04-21-s2-atr-scan-design.md)
**Dataset:** SPY 1m + daily from ARCX.PILLAR, 2018-05-01 → 2023-12-31 (cache built in commit `26d28c7`).
**Reproduce:** `.venv/bin/python scripts/bakeoff_s2_atr_scan.py`

---

## TL;DR

**Branch 1 — Flag S2 rules for redesign.** The entry signal on SPY has no follow-through (avg MFE between 0.12-0.35 R, never crosses 1.0 at any multiplier). The stop distance is a second-order detail: changing it from 1× to 3× ATR moves trade count by 0.1-10%, but never produces positive gross edge. A wider stop cannot save an entry signal that doesn't identify meaningful moves.

## Method

Scanned `atr_multiplier ∈ {1.0, 1.5, 2.0, 2.5, 3.0}` × `{S2a, S2b}` on the SPY paper in-sample window (2018-05-01 → 2023-12-31, 1424 trading days). Metrics: spec §3.3 summary + §3.4 per-year stratification + MFE/MAE in R units (entry to actual exit). Decision follows spec §3.5 pre-committed framework, evaluated top-to-bottom (first matching branch wins); no partial-window tuning.

## Results — summary table

| mult | strategy | n | win_rate | avg_R | pnl $ | stop_hit% | L/S | avg_MFE_R | avg_MAE_R |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | S2a | 1232 | 0.511 | −0.002 | −16.0 | 11.9% | 664/568 | +0.35 | +0.33 |
| 1.0 | S2b | 1355 | 0.510 | −0.001 | +3.7 | 11.9% | 711/644 | +0.35 | +0.34 |
| 1.5 | S2a | 1232 | 0.515 | −0.008 | −80.5 | 3.7% | 664/568 | +0.24 | +0.24 |
| 1.5 | S2b | 1267 | 0.517 | −0.008 | −87.7 | 3.8% | 674/593 | +0.24 | +0.24 |
| 2.0 | S2a | 1232 | 0.516 | −0.006 | −83.6 | 0.8% | 664/568 | +0.18 | +0.19 |
| 2.0 | S2b | 1238 | 0.516 | −0.006 | −82.9 | 0.8% | 665/573 | +0.18 | +0.19 |
| 2.5 | S2a | 1232 | 0.516 | −0.006 | −87.8 | 0.2% | 664/568 | +0.14 | +0.15 |
| 2.5 | S2b | 1235 | 0.517 | −0.006 | −87.8 | 0.2% | 664/571 | +0.14 | +0.15 |
| 3.0 | S2a | 1232 | 0.516 | −0.005 | −87.5 | 0.1% | 664/568 | +0.12 | +0.13 |
| 3.0 | S2b | 1233 | 0.517 | −0.005 | −87.4 | 0.1% | 664/569 | +0.12 | +0.13 |

### S2b − S2a deltas

| mult | n_delta | %  | pnl_delta |
|---:|---:|---:|---:|
| 1.0 | +123 | 9.98% | +$19.7 |
| 1.5 | +35 | 2.84% | −$7.2 |
| 2.0 | +6 | 0.49% | +$0.7 |
| 2.5 | +3 | 0.24% | −$0.0 |
| 3.0 | +1 | 0.08% | +$0.1 |

## Results — by-year (S2a avg_R, in percent-of-R)

| mult | 2018H2 | 2019 | 2020 | 2021 | 2022 | 2023 | years>0 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | **+3.40** | **+0.46** | **+0.74** | **+0.32** | −0.70 | −3.30 | 4 of 6 |
| 1.5 | +1.39 | +0.13 | −0.12 | −0.65 | −2.11 | −2.23 | 2 of 6 |
| 2.0 | +0.90 | −0.05 | +0.14 | −0.20 | −1.82 | −1.88 | 2 of 6 |
| 2.5 | +0.55 | −0.06 | +0.09 | −0.22 | −1.49 | −1.49 | 2 of 6 |
| 3.0 | +0.65 | −0.05 | −0.01 | −0.18 | −1.24 | −1.24 | 1 of 6 |

## Predicate evaluation (pre-committed per spec §3.5)

| # | Predicate | Pass? | Detail |
|---|---|:---:|---|
| 1 | Meaningful S2a ≠ S2b (`n_delta/n_S2a ≥ 10%`) | ❌ none | Best is mult=1.0 at **9.98%** (just under threshold). 1.5 drops to 2.8%, 2.0 to 0.5%. |
| 2 | Positive gross edge (S2a `avg_R > 0 AND pnl > 0`) | ❌ none | **Every** multiplier produces negative S2a avg_R and negative pnl. S2b at mult=1.0 is breakeven (+$3.7) but the canonical reference is S2a. |
| 3 | Regime-stable edge (S2a avg_R > 0 in ≥ 4 of 6 years) | Partial | Only mult=1.0 reaches 4/6; 2018-2021 positive then 2022-2023 negative. Full-window avg_R still negative. |
| 4 | Universally good entry (`avg_MFE_R ≥ 1.0` at every multiplier) | ❌ fail | Max observed avg_MFE = **0.35** at mult=1.0. Min = 0.12 at mult=3.0. Universally below 1.0. |

## Decision

**Branch 1 — Flag S2 rules for redesign.**

Condition per spec §3.5 branch 1: *"NO multiplier produces positive gross edge AND `avg_mfe_R < 1.0` universally."* Both sub-conditions hold:

- Predicate 2 fails at every scanned multiplier (S2a gross PnL is negative at 1.0, 1.5, 2.0, 2.5, 3.0).
- Predicate 4 fails universally — the highest observed avg_MFE_R is 0.35 (mult=1.0). That means S2's "best" trades on average only capture about one-third of 1R of favorable price movement before reverting. The noise-boundary breakout does not identify trades with meaningful directional reach.

Branch 2 is ruled out (no multiplier has positive edge → predicate 2 fails universally, short-circuiting branch 2's conjunction). Branch 3 is ruled out for the same reason. Branch 4 overlaps with branch 1's territory but is superseded because predicate 4 explicitly fails and we reached branch 1 first. Branch 5 would apply only if the scan had produced mixed signals; here the signal is unambiguous.

### Why the stop distance is a second-order concern

The MFE/MAE columns tell the real story. At every multiplier, `avg_MFE_R ≈ avg_MAE_R` (0.35/0.33 at mult=1.0; 0.12/0.13 at mult=3.0). A trade's favorable and adverse excursions are approximately symmetric — the classic signature of noise around entry, not signal. No stop placement can extract edge from an entry signal whose forward distribution has no directional drift.

The additional regime-stratified view (2018-2021 slightly positive, 2022-2023 clearly negative at mult=1.0) suggests S2 may have worked during the quieter trending years 2018-2021 but degraded once the market entered higher-noise regimes. That is consistent with a strategy that piggybacks on momentum persistence — which SPY provided 2018-2021 and largely did not in 2022-2023.

## Next action

**Plan 3 is blocked on S2 redesign.** Concrete follow-up:

1. Do NOT open a PR on `feat/plan2c-s2-atr-scan` to main immediately. Plan 3 cannot start on the current canonical S2 rules because branch 1 fired.
2. Open a new brainstorming session on "S2 redesign" covering at minimum:
   - Is a boundary-breakout entry fundamentally the wrong primitive on SPY? (Paper's edge is QQQ/TQQQ; SPY was always a mention.)
   - Alternative entry formulations: volume-weighted breakout, regime-filtered breakout (only trade when VIX regime matches), or abandon the family.
   - Alternative risk model: MFE-targeted profit-take (e.g., take 0.5R profit), time-stop (e.g., 30-min max hold), or move to a completely different family.
3. **Alternative path** — if the user chooses instead to drop S2 entirely: Plan 3 proceeds with only S1a + S1b as candidates (n_trials=2, much friendlier DSR threshold). S2 is parked indefinitely as "unprofitable on SPY per Plan 2c evidence".
4. The Plan 2c branch may still be merged to main to lock in (a) the atr_multiplier parameter refactor, (b) the MFE/MAE helper, and (c) this findings document. These are reusable for any redesign path. The merge is safe — it does not pre-commit S2 to stay in Plan 3's candidate matrix.

## Limitations

- **Paper in-sample only.** 2024-04+ pure OOS (Plan 3 territory) is the independent confirmation; these findings are not an OOS claim.
- **MFE/MAE computed from 1m bars.** Intra-minute excursions are invisible; true MFE could be slightly higher than reported.
- **Scan holds other S2 parameters constant** per spec §2 non-goals: `avg_intraday_return` lookback = 14 days, 12 check times, noise boundary formula, direction rule. A different lookback or boundary formula might change the conclusion, but that's a larger diagnostic than this plan's scope.
- **S2a is the canonical reference for predicate 2.** S2b at mult=1.0 is breakeven gross (+$3.7 over 5.7 years, essentially zero). If the future redesign chooses to shift the canonical to S2b with tight stops, predicate 2 becomes borderline — but that's a redesign decision, not a conclusion of this scan.
