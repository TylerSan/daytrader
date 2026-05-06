# Post-Trade Journal

Fill **immediately after exit**, before the next setup tempts you. One entry
per closed trade. The CLI counterpart is `daytrader journal post-trade`.

---

## 0. Identifiers

- Date / time of exit (local): `__________`
- Trade # in lock-in: `___ / 30`
- `checklist_id` (from pre-trade): `__________`
- `trade_id`: `__________`
- Symbol: `[ ] MES   [ ] MGC`
- Direction: `[ ] long  [ ] short`

## 1. Result

- Entry: `__________`   Stop: `__________`   T1: `__________`
- Exit price: `__________`
- Exit reason: `[ ] stop  [ ] target/T1  [ ] trail  [ ] structure invalidation  [ ] discretionary`
- R realized: `_____` R     USD realized: `$_____`
- Held for: `____ min`

## 2. Discipline audit (the part that matters)

Tick "yes" only if the answer is honestly yes.

- [ ] Stop was at the broker the entire time, never widened
- [ ] No averaging down on the loser
- [ ] Did not cut a winner before 1R unless structure actually invalidated
- [ ] Not a revenge trade after a recent stop
- [ ] Setup was a true stacked imbalance reversal (5:1 + 100 vol, structural location)
- [ ] CLI `pre-trade` was run and `PASSED` before entry
- [ ] Screenshots saved (signal + order ticket + exit)

**Any unticked box = a discipline break.** Note which and why below — the
breaks are the data, not the PnL.

Discipline breaks this trade: `__________`

## 3. Setup quality (independent of outcome)

A losing trade with a clean setup is fine. A winning trade on a sloppy
setup is a problem.

- Signal clarity (1–5): `___`
- Location quality (1–5): `___`
- Was higher-timeframe context with me, against me, or neutral? `__________`
- Would I take this exact signal again? `[ ] yes  [ ] no — because: __________`

## 4. Execution quality

- Slippage on entry (ticks): `___`
- Slippage on stop/exit (ticks): `___`
- Did I hesitate? `[ ] no  [ ] yes — `: `__________`
- Did I act on a non-signal impulse at any point? `[ ] no  [ ] yes — `: `__________`

## 5. One-sentence reflection (required by CLI `--notes`)

> __________________________________________________

## 6. Lesson / pattern note

If this trade reinforced or contradicted a prior pattern, name it:

- Pattern observed: `__________`
- Repeats prior trade #: `__________`
- Action for next session: `__________`

## 7. Circuit / day state after this trade

- Realized R today: `_____`
- Trades today: `___ / 5`
- Cool-off triggered? `[ ] no  [ ] yes — until: __________`
- Circuit `no_trade_flag`? `[ ] no  [ ] yes — reason: __________`

---

## Stop rules reminder

- 2 consecutive stops → end day
- −2R intraday → 30 min cool-off
- −3R day → done, no exceptions
- Any zero-tolerance ban violated (Contract §6) → today's results are
  invalidated for evaluation purposes; log it honestly anyway
