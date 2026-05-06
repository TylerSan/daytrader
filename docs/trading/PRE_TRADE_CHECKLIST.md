# Pre-Trade Checklist

Fill this **before** clicking buy/sell. If any item is ✗, do not trade.

The 5 hard gates (sections 3–5 below) are also enforced by
`daytrader journal pre-trade` — this Markdown form is the human-readable
companion for screenshot/audit purposes. Per Contract.md §5,
`entry_via_cli_only: true` — you must still run the CLI.

---

## 0. Trade header

- Date / time (local): `__________`
- Trade # in lock-in: `___ / 30`
- Symbol: `[ ] MES   [ ] MGC`
- Direction: `[ ] long  [ ] short`
- Setup: `stacked imbalance reversal`

## 1. Contract status

- [ ] Contract.md `Active: true` and within current lock-in
- [ ] Today's trade count `<` `max_trades_per_day` (5)
- [ ] Today's realized R `>` `-daily_loss_limit_r` (−3R)
- [ ] Not inside a cool-off window (last stop ≥ 30 min ago; not after 2 consecutive stops)

## 2. Signal validation (Stacked Imbalance Reversal)

- [ ] MotiveWave Level 3 shows **stacked** imbalances (≥ 2 adjacent prints)
- [ ] Each qualifying print: ratio **≥ 5:1** AND volume **≥ 100**
- [ ] Reversal location is structural (prior HH/LL, VWAP, HVN/LVN) — not mid-range
- [ ] Higher-timeframe context does not contradict (not fading a strong trend bar with no exhaustion)

## 3. Risk parameters (preset BEFORE entry)

- [ ] Entry price written: `__________`
- [ ] Stop price written: `__________` (this is non-negotiable, will not be widened)
- [ ] Target ≥ 1R written: `__________`
- [ ] Size computed so risk ≤ 1R = $50
  - MES: $5/pt × size × |entry−stop| ≤ $50
  - MGC: $10/pt × size × |entry−stop| ≤ $50
- [ ] Size ≤ `max_contracts` (2)

## 4. Order ticket (IBKR)

- [ ] Entry + stop + target submitted as a **bracket / OCO** order
- [ ] Stop is at the broker (not mental, not a "watch" level)
- [ ] Scale plan: 50% off at T1, trail remainder (per Contract §5)

## 5. Bans — confirm none are about to be violated

- [ ] No averaging down planned if it goes against me
- [ ] Will not move stop away from entry under any circumstance
- [ ] Will not exit at < 1R unless structure invalidates (this is not a "scared out" license)
- [ ] Not a revenge trade after a recent stop

## 6. Environment

- [ ] No high-impact news in the next 15 min (CPI, FOMC, NFP, EIA for MGC)
- [ ] Liquid session (RTH or active overnight window for the instrument)

## 7. Audit artifacts

- [ ] Screenshot saved: MotiveWave chart with signal annotated
- [ ] Screenshot saved: IBKR order ticket showing bracket attached
- [ ] Ran `daytrader journal pre-trade ...` and got `PASSED checklist_id=...`
- [ ] `checklist_id` recorded: `__________`

---

## If any box is ✗

Do **not** size down and trade anyway. Skip the trade. Note the reason in the
journal. Pattern-tracking the skips is part of the audit gate.

## After fill

Move to the post-trade journal entry; reference `checklist_id` above.
