# W2 Setup Gate Bake-off — Retrospective

**Date:** 2026-04-21
**Parent spec:** [`docs/superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md`](../../superpowers/specs/2026-04-20-strategy-selection-bakeoff-design.md)
**Final verdict:** No setup locked (Plan 3 findings branch 1). Track closed.

## Timeline (2026-04-20 → 2026-04-21, single session)

| Phase | Output | Status |
|---|---|---|
| Plan 2a | S1 ORB family implemented + SPY 1m data loader + KAT harness | PR #1 merged |
| Plan 2b | S2 Intraday Momentum implemented + ARCX.PILLAR daily loader + S2 KAT | Merged locally |
| S1 wrong-way fix | Phantom-stop-win bug caught by critical audit | PR #2 merged |
| Data expansion | DBEQ.BASIC (9mo) → ARCX.PILLAR (6.5y); $0.88 one-time | PR #3 merged |
| Plan 2c | S2 ATR multiplier diagnostic; S2 deferred for redesign | Merged locally |
| S2 deferral spec revision | n_trials 4 → 2 per Plan 2c decision | Merged locally |
| Plan 3 | Cost + metrics + main run + 4 SE + findings + this retrospective | This PR |

## What worked

- **TDD + frequent commits** made each step individually bisectable. When the S1 wrong-way bug surfaced in Plan 2b's critical audit, patching was trivial because each strategy + test pair was its own commit. The fix branch touched 2 files and landed without affecting anything else.

- **Critical audits between plans** (at user's request) caught two real issues that happy-path TDD did not:
  - S1 wrong-way entry bug (4 phantom-win trades inflating win rate from 0.197 → 0.218).
  - S2a ≡ S2b degeneracy (only 6/1232 trade difference over 6.5y).
  Both required Plan 2c-style follow-up work to resolve. Build this audit habit into future projects.

- **Databento pre-flight cost API** (`client.metadata.get_cost`) gave exact $ estimates before pulling. Pre-pull extrapolations from DBEQ.BASIC were 10-20× too high; the API was accurate to the cent. Enabled the jump from 3-year ($0.42) to 6.5-year ($0.88) scope without fear.

- **Pre-committed decision frameworks** (Plan 2c §3.5 five branches, Plan 3 §6 three rows) prevented "move the bar" temptation when results were ambiguous. Plan 3 findings read mechanically off the Day 1 hard-gate table into Branch 1; no narrative massaging.

- **Strategy layer kept plain Python** (no pybroker dependency) through Plans 2a-3. Made auditing easy and made Plan 3 trivially skip pybroker without architectural pain. Spec §1.2 called for pybroker; Plan 3 opted out with a 1-paragraph rationale and saved an entire day.

- **Time-boxed Plan 3.** Given the predicted null-result, a 3-day box avoided over-investment. Actual execution came in under the box (~half a day thanks to warm cache + predictable result).

## What didn't

- **Spec drift (MES → SPY).** Parent spec was written for MES futures; we switched to SPY for data accessibility. The drift was only patched cosmetically (§0, §3.3 footnote). The cost model (§2.3) still contains MES-specific numbers in the retired Plan 1 helpers (`costs.py` top), and §1.3/§5.2 R1 rollover language is stale. Not harmful but noisy for readers. **MES remains untested** — if the user wants MES specifically, this whole pipeline needs a second pass.

- **KAT methodology was circular.** Every KAT threshold was calibrated against observed values on the same dataset we were "validating":
  - Plan 2a S1a win rate band widened to match observed (0.25 → 0.15).
  - Plan 2b S2 KAT n_trades widened after observation (75 → 130).
  - Plan 2c decision framework predicates were pinned *after* the diagnostic audit revealed the shape of the data.
  KAT passing therefore mostly means "code matches itself", not "code matches paper". True independent validation would have needed paper's SPY numbers (unavailable from text) or a second instrument (QQQ, rejected for DSR penalty cost).

- **Negative-space testing gap.** 14 happy-path S1 unit tests missed the wrong-way entry edge case entirely. Every fixture used a well-behaved post-OR bar. Future plans should deliberately include "ways the rule could be misinterpreted" tests alongside the "ways the rule normally fires" tests — e.g., price gaps past OR, same-bar entry-and-stop, zero-range OR.

- **Premature refactoring for S2.** S2 code + S2 KAT + MFE/MAE helper were built before we knew S2 wouldn't survive Plan 2c. Not wasted — the infrastructure is reusable and the `atr_multiplier` parameterization retroactively turned out to be the right shape. But shipping S2 as a full Plan 2b was heavier than needed; a lighter "prototype + scan" would have reached the same deferral decision faster.

- **"One bad day = rerun" implicit mode.** Plan 2a KAT, Plan 2b KAT, and Plan 2c all had an initial failure that triggered "widen the band / fix the bug / run again". In each case the fix was real (phantom-win bug, dataset difference). But the cycle risks normalizing "first failure is a calibration issue" rather than "first failure is evidence against the hypothesis". Plan 3 pre-commit via §6 decision table was the countermeasure.

## Preserved infrastructure (reusable for any future bake-off)

- **Data loaders** — `data_spy.py` (1m ARCX.PILLAR) and `data_spy_daily.py` (daily ARCX.PILLAR). Caching built in. Extensible to other instruments by swapping the dataset string.

- **`Trade` wire format** + `TradeOutcome` enum. Strategy-agnostic; any new candidate can emit `list[Trade]`.

- **Known-answer harness** (`strategies/_known_answer.py`) — `summary_stats` + `compare_to_paper`. Applies to any future paper replication.

- **ORB mechanical core** (`strategies/_orb_core.py`) — reusable for other opening-range variants.

- **S2 mechanical core** (`strategies/_s2_core.py`) — noise boundary + ATR + Chandelier trailing, parameterized. If momentum families get revisited, this is ready.

- **MFE/MAE helper** (`scripts/_s2_scan_mfe_mae.py`) — diagnostic for any entry-signal quality question, not just S2.

- **Cost model** (`costs.py`) — both MES tick-based (Plan 1 legacy) and SPY per-trade (Plan 3) helpers. Extensible.

- **Metrics module** (`metrics.py`) — Sharpe/Sortino/Calmar/MDD/longest-DD/PF/expectancy/DSR/bootstrap CI. Paper-referenced DSR formula.

- **Trade utilities** (`scripts/_plan3_trade_utils.py`) — filter_trades_by_window, flip_trades_direction, equity_curve_from_pnl, daily_returns_from_pnl.

- **Scan runner pattern** — Plan 2c + Plan 3 SE scripts all follow "load cache → loop params → CSV + markdown to stdout". Template for future sensitivity work.

## Known gaps (if bake-off track reopens)

- **MES instrument support** — needs rollover handling, continuous-contract schema, different session calendar, different tick/point multiplier, different cost tier.
- **Walk-forward with rolling windows** — we used a single train/OOS split; true walk-forward would re-fit parameters in expanding windows.
- **Multi-asset** — currently one symbol at a time.
- **pybroker adapter** — deferred from Plan 3; needed only if a future candidate requires richer portfolio accounting than per-trade PnL.
- **`promote` CLI + YAML v2 + Contract.md filling** — deferred from Plan 3; needed only if a future bake-off yields a passing candidate.
- **Real transaction cost integration** — fixed $0.50/trade is a start; queue position, tier pricing, and spread adaptation are out of scope.

## Decision log (key choices and why)

| Decision | Why | Where |
|---|---|---|
| Strategies as plain Python, no pybroker | Spec §1.4 R5 insulates correctness from engine lifecycle risk | Plan 2a onwards |
| SPY instead of MES | Zarattini papers use SPY/QQQ; MES rollover complexity avoided | Plan 2a |
| DBEQ.BASIC → ARCX.PILLAR | NYSE Arca is SPY primary listing; single publisher; 6.5y history | PR #3 |
| S2 deferred | Plan 2c: no multiplier produces positive edge; avg_MFE universally < 1R | Plan 2c findings |
| No pybroker in Plan 3 | Only 2 active candidates; direct pandas is simpler and faster | Plan 3 spec §2 |
| No `promote` CLI | Predicted "no Contract" outcome; trivial to add if wrong | Plan 3 spec §2 |
| Cost $0.50/trade fixed | Retail-realistic IBKR estimate; SE-1 scans sensitivity | Plan 3 spec §3.1 |
| Branch 1 closure | Both candidates fail 3/5 hard gates; SEs confirm structural | Plan 3 findings |

## Final status

- All bake-off plans merged to `main`.
- All tests green (pre-Plan 3 baseline + Plan 3 new additions).
- W2 Setup Gate bake-off track **closed**. No setup recommended for live trading via this research.
- Data purchased: ~$0.88 one-time from Databento.
- Time invested: ~1-2 sessions across Plans 2a-3.
- **Handoff**: user picks among (a) new strategy families brainstorm, (b) live discretionary with journal guardrails, (c) pause. See [`2026-04-21-plan3-findings.md`](2026-04-21-plan3-findings.md) §"Next action".
