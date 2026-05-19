# IBKR Behavioral Review — 2023 → 2026-YTD

**Purpose.** Convert ~4 years of real IBKR fills into a quantified behavioral
diagnosis, validate the signed Contract's discipline rules against the user's
own money, and propose concrete refinement *candidates* for the **next**
Contract review.

**Boundary (read first).** This document is behavioral diagnosis + Contract-review
input. It does **not** redesign or relitigate the locked setup
(`stacked_imbalance_reversal_at_level`) or instruments (MES/MGC). The 30-trade
lock-in stands as-is; every proposed change in §5 is for the **next scheduled
Contract review, not mid-lock-in**. No historical data was used to fit a new
strategy (that is the user's named failure pattern — strategy hopping).

**Source of truth caveat.** Written from the public companion docs
(`PRE_TRADE_CHECKLIST.md`) + project memory. The signed `Contract.md` is
git-ignored and per-worktree; it was **not** read for this review. Where this
doc says "current Contract," verify against the actual `Contract.md` §refs.

**Data scope.** Account `U11548070`, IBKR Activity Statements (Flex v2):
`2023`, `2024`, `2025`, `2026-01-01 → 2026-05-15`. 6,065 order rows;
3,035 closed trades reconstructed.

**Method & honesty limits.** Pure-stdlib parse of the multi-section CSVs;
FIFO round-trip reconstruction for hold-time / direction / episodes. Caveats
carried throughout:
- CAD P/L converted at a flat **0.73** (magnitude only; IBKR base-currency
  totals are the hard anchor).
- Counterfactuals are **rule-overlays on actual fills at historical sizing**;
  later same-day trades are the ones dropped (selection caveat) — directionally
  robust given the magnitudes, not a strategy backtest.
- MAE/MFE (how far trades ran in your favor/against) is **not** measured —
  unreliable from statement data. Not claimed anywhere.
- Time-of-day is statement-local time (assumed ≈ US/Eastern); treat as relative.

---

## 1. Bottom line

**IBKR-reported Total P/L (hard anchor, not reconstructed):**

| Year | Total P/L | Median trades/day | Max/day |
|---|---:|---:|---:|
| 2023 | **+$9,035** | 2 | 13 |
| 2024 | **+$1,690** | 2 | 40 |
| 2025 | **−$34,331** | **12** | **117** |
| 2026 YTD (4.5 mo) | **−$12,474** | 6 | 71 |
| **Net** | **≈ −$36,080** | | |

**Thesis.** The entry edge is *not* the problem. Win rate is 58–61%; MES is
net-positive and +EV; long-futures is +EV; 2023 was profitable. The account
was destroyed by a small, now-quantified set of **behavioral leaks**, all on
the management/discipline side. Proof: replaying the user's *own signed rules*
on the user's *own fills* flips realized P/L from **−$24,232 to +$18k–+$48k**.

**The single unifying root cause — independently re-derived from a different
instrument.** An options autopsy (he will *not* trade options under the
Contract; this is cross-validation, not advice) shows the identical disease:
the −$58k options loss was ~100% long-*bought* premium, almost all long calls,
58% win-rate yet −$60/trade. The cleanest natural experiment in the entire
dataset: 0DTE options (the instrument **forces** an exit) bled only
**−$17/trade**, while 31–90DTE options (the instrument **lets him hold and
hope**) bled **−$98/trade** — 6× worse, the same shape as the futures
multi-day bagholding in L1. Conclusion: **enforced exit is the master
variable.** His P/L is governed by whether *something* forces him out — not by
instrument, direction, or entry skill. This is why the enforced-exit rules
outrank everything else in §5.

---

## 2. The counterfactual — your own rules on your own fills

Rule-overlay on real fills, historical sizing (caveat §0):

| Rule stack | Kept | Sim. realized | vs actual −$24,232 |
|---|---:|---:|---:|
| Actual (no rules) | 3035 | −$24,232 | — |
| ≤3 trades/day only | 1127 | −$9,592 | **+$14,640** |
| + no trade ≤10 min after a loss | 1080 | **+$18,340** | **+$42,572** |
| + halt day after −2× median-loss | 957 | **+$47,703** | **+$71,934** |

**The single most valuable rule is the post-loss cool-off** — it alone moves
the result ~+$28k (−$9.6k → +$18.3k). The Contract already encodes the top-value
defenses (≤3/day, −2R/day, 30-min cool-off, 2-stops-end). **This table is the
strongest possible validation that the signed Contract is pointed correctly.**

---

## 3. Leaks ranked by dollar impact

Each maps to a current Contract rule (✓ already covered / ✚ refinement proposed, see §5).

| # | Leak | Hard evidence | Contract coverage |
|---|---|---|---|
| L1 | **Hold losers past the day** | ≤1 day held = **+$70k** (intraday +$44.0k / overnight +$26.5k); >1 day held = **−$96k** (multi-day −$41.4k / >1wk −$54.9k). 100% of destruction is in trades carried past the day. | ✓ day-trading discipline / flat EOD ✚ R-07 |
| L2 | **No preset stop (fat left tail)** | Median loss $120 (2.4R) but **max loss $7,713 = 154R**; max/median = **64×**. 205 trades > 10R bled −$274,787. | ✓ preset stop + fixed 1 contract |
| L3 | **Strangled winners (0.5R-grab)** | Winner median collapsed **2.88R (2023) → 0.79R (2025)**; 37% of 2025 wins < 0.5R. Letting winners run pays **monotonically** ($103 <30min → $601 >1wk). Top 10% of winners = **45%** of all gross profit. | ✚ **R-03 (gap: profit side)** |
| L4 | **Post-loss tilt** | Trade ≤10 min after a loss: avg **−$108**, win 40%. All other trades: avg **+$12**, win 62%. | ✓ 30-min cool-off after stop ✚ R-06 |
| L5 | **First-trade-of-day spiral** | First trade loses → day red **72%**, avg day **−$726**. Stopping after a losing first trade = **+$65,667** over 208 days. | ✚ **R-01 (tighten stop-count)** |
| L6 | **Short-MGC graveyard** | Short MGC alone = **−$17,892** (n378). MES net **+$7,672** both directions; MGC long ≈ flat (+$453). Futures LONG +$12,952 / SHORT −$11,519 at near-equal win rate. | ✚ **R-04 (calibration, your call)** |
| L7 | **Multi-session (next-day) tilt** | Day **after** a −2×median-loss day: avg **−$408**, red 51%. After any other day: avg **+$87**, red 38%. Intraday −2R stop does not span sessions. | ✚ **R-05 (gap)** |
| L8 | **Oversize / martingale** | Futures at exactly 1 contract: **+$21.24/trade (+$22.9k)**. 2–3: −$10. 4–9: −$100. 10+: **−$549/trade**. Size after a loss ×1.49 vs after a win ×1.24. | ✓ **fixed 1 contract (bulletproof-validated)** |
| L9 | **Overtrading / machine-gun** | 2025: 81% of days > 3 trades, median 12/day. Trade #4+ of day: 1,908 trades, −$14,640. 40% of trades re-fired within 5 min of the prior. | ✓ ≤3/day ✚ R-06 |
| L10 | **Green-day giveback** | 57 solidly-green days gave back >50% of peak = **−$94,153**; 40 green days closed red (−$78,005 swing). No upside circuit-breaker. | ✚ **R-07 (gap)** |
| L11 | **Averaging down** | 1,079 add-to-loser events across 266 symbol-legs. | ✓ fixed 1 contract |
| L12 | **Options = largest single asset-class loss** | **−$58,235** (n975, 58% win, −$60/trade), ~100% long-*bought* premium; **long calls alone −$53.9k**. 31–90DTE "held & hoped" = −$36.2k; 0DTE (forced exit) only −$17/trade. Worst 5 underlyings = 57% (ADBE/WDC = 0% win). 2025 was the blow-up vehicle (−$48.5k). | ✓ futures-only Contract amputates it; behavior itself cured only by the enforced-exit cluster |

Pain concentration (validates the daily stop): worst 5 days = 18%, worst 20
days = **49%** of all losing-day losses, over 466 trading days. Max drawdown on
cumulative realized = **−$68,892**; longest losing streak 12 trades.

**The enforced-exit natural experiment (the review's strongest causal
evidence).** Within options, the *only* thing that changed across the DTE
buckets is how long the instrument permitted a losing position to be held:
0DTE = **−$17/trade**, 1–7d = −$60, 8–30d = −$74, 31–90d = **−$98**, >90d =
−$104 — monotonic in "how long it lets him hold." The same monotonic pattern
appears in futures by hold-time (L1: ≤1 day +$70k, >1 day −$96k) and in the
counterfactual (§2: the post-loss cool-off alone ≈ +$28k). Three independent
slices, one conclusion: **his loss is a function of enforced exit, not of
instrument, direction, or entry quality.**

---

## 4. What is working — preserve, do not "fix"

- **Entry edge is fine.** 58–61% win rate. Do **not** chase a higher win rate —
  2025 had the *higher* win rate (61%) and blew up; 2023 won only 45% and made
  money. The lever is payoff, not hit-rate.
- **MES is +EV** (+$13.39/trade over 573 trades, both directions positive).
- **Long-futures is +EV** (+$21.20/trade, n=611).
- **No euphoria leak.** After ≥3 straight wins: avg **+$60**, win 68% — *better*,
  not worse. The leak is purely loss-side. Keep the Contract lean: do **not**
  add win-streak rules.
- **2023 is your own profitable template:** few, selective (26 symbols, 2/day),
  winners allowed to reach ~3R. The Contract's "do less, fixed R" forces you
  back toward 2023-you.

---

## 5. Proposed Contract refinement candidates — for the NEXT review

Lock-in stands. These are **proposals you decide at the next review**, not
changes I make. Priority = expected $ impact × evidence strength.

**Top tier — the enforced-exit cluster.** The strongest causal evidence in
this review (options 0DTE −$17 vs 31–90DTE −$98/trade; futures ≤1d vs >1d;
counterfactual post-loss cool-off ≈ +$28k) all says the rules that *force him
out* dominate everything else. Treat the preset stop, flat-by-EOD, daily −2R,
**R-01**, and **R-03** as one inviolable cluster ranked above R-04…R-07 — they
attack the master variable; the rest are refinements.

| ID | Proposed delta | Data rationale | Priority | Status vs current |
|---|---|---|---|---|
| **R-01** | **First trade of the day is a loss → day is done** (tighten the existing 2-stops-end circuit-breaker; one losing first trade ≠ two stops today). | First-loss day: 72% red, −$726 avg; stop-after-first-loss = +$65,667 / 208 days. | **P0** | Tightens existing rule |
| **R-02** | **Keep fixed 1 contract inviolable**; make any size > 1 an automatic Contract breach, not a judgment call. | 1 contract +$21/trade; 10+ = −$549/trade, monotonic. | **P0** | Validates / hardens |
| **R-03** | **Add a preset profit rule** mirroring the preset stop: target defined by setup structure, **floor ≥ 2R**, no discretionary exit < 1R. | Winner median 2.88R→0.79R is the blowup mechanism; >5R wins fell 33%→5%. | **P0** | **Gap (profit side)** |
| **R-04** | **Short-MGC gate**: either MES-first start to the lock-in, or an extra confirmation gate for short-MGC entries. *Calibration of locked instruments — explicitly your call.* | Short MGC = −$17,892 single largest sink; MES +$7,672. | P1 | **Gap (your decision)** |
| **R-05** | **Multi-session cool-off**: a −2R day → next session is reduced-size or no-trade. | Day after a big-loss day: −$408 avg vs +$87. | P1 | **Gap** |
| **R-06** | **Minimum gap between any two trades** (not only after a stop), e.g. ≥ N min. | 40% of trades re-fired < 5 min; tilt trade = −$108. | P1 | Extends cool-off |
| **R-07** | **Green-day protection** (upside mirror of −2R): after +Xr, lock the day / stop adding. | $94,153 given back on 57 green days; 40 green→red. | P2 | **Gap (upside)** |

**Mindset rule for the lock-in itself.** Historical non-overlapping 30-trade
blocks (undisciplined baseline): 65% green, but **p10 −$6,192 / p90 +$3,796,
worst −$26,562**. A single 30-trade block is statistically near-meaningless.
**Judge these 30 trades on process adherence, not on the 30-trade P/L** — or
you will kill a correct system on noise, or trust a broken one on luck.

---

## 6. Methodology & reproducibility

Five standalone pure-stdlib scripts (no project deps; read-only on
`~/Downloads`; the daytrader package was **not** modified):

| Script | Covers |
|---|---|
| `/tmp/ibkr_snapshot.py` | Overtrading, no-stop tail, win/loss asymmetry, averaging-down, tilt, 2026, Contract reality check |
| `/tmp/ibkr_deep.py` | Counterfactual replay, 2023-vs-2025, asset class, pain concentration, holding segment, time-of-day, euphoria, sizing |
| `/tmp/ibkr_profit.py` | Winner R-multiple, profit concentration, green-day giveback, let-run payoff, scale-out, commission recalibration |
| `/tmp/ibkr_next30.py` | MES/MGC profile, long/short, first-trade-of-day, next-day tilt, inter-trade gap, size buckets, 30-trade variance |
| `/tmp/ibkr_options.py` | Options autopsy: long-vs-short premium, DTE buckets, calls/puts, underlying concentration, by-year |

The validated logic from these throwaway `/tmp` scripts has been consolidated
into a reusable command:

```
uv run daytrader journal review-history <statement.csv|dir> [--r 50] [--out report.md]
```

Engine: `src/daytrader/journal/review_history.py` (pure-stdlib parse + FIFO
reconstruction; no new dependencies — there is no existing IBKR-Activity-
Statement parser in the project or in maintained libraries that covers the
multi-section CSV + the bespoke behavioral metrics here, so a custom, tested
module is justified per the project dependency policy). The user's statement
CSVs are private and **never committed** (kept under the git-ignored
`data/imports/`).

**Honest recalibration.** An earlier framing said "commission = 44.8% of net
realized." On the fairer gross basis, commission is only **3% of gross
winnings** ($10,867 / $385,156). Commissions are *not* a primary leak — the
money was lost to L1–L5/L12, not fees. This correction supersedes the earlier
statement.

**Honest hypothesis correction.** A working hypothesis that the options loss
was *short* premium ("picking up pennies in front of a steamroller") was
**refuted** by FIFO reconstruction: it was ~100% *long*-bought premium. A
round-1 raw-row read that treated `qty −12` as "short" was an artifact of
reading closing fills without round-trip reconstruction; the FIFO episode
logic supersedes it. Recorded here rather than silently fixed.
