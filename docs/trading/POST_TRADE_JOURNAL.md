# Post-Trade Journal

Fill **immediately after exit**, before the next setup tempts you. One entry
per closed trade. The CLI counterpart is `uv run daytrader journal post-trade`
(run from repo root).

Locked setup: **stacked_imbalance_reversal_at_level** (see
[setups/stacked_imbalance_reversal.yaml](setups/stacked_imbalance_reversal.yaml)).

---

## 0. Identifiers

- Date / time of exit (NY local): `__________`
- Trade # in lock-in: `___ / 30`
- `checklist_id` (from pre-trade): `__________`
- `trade_id`: `__________`
- Symbol: `[ ] MES   [ ] MGC`
- Direction: `[ ] long  [ ] short`
- Key level type: `__________`
- For ZONE: TF `____`  edges `____ – ____`  freshness `__________`

## 1. Result

- Entry: `__________`   Stop: `__________`   Target: `__________`
- Exit price: `__________`
- Exit reason: `[ ] stop  [ ] target (all_at_target)  [ ] structure invalidation  [ ] EOD timeout`
- R realized: `_____` R     USD realized: `$_____`
- Held for: `____ min`

## 2. Discipline audit (the part that matters)

Tick "yes" only if the answer is honestly yes.

- [ ] Stop was at the broker the entire time, never widened
- [ ] No averaging down on the loser
- [ ] Did not exit before target unless structure actually invalidated
- [ ] Not a revenge trade after a recent stop
- [ ] Setup matched YAML: 3+ stacked, 5:1 ratio, ≥100 vol, at a valid level,
      level proximity rule satisfied (4 ticks for POINT / inside ZONE edges)
- [ ] No skip filter was active (event today, news ≤15 min, ATR < 0.5,
      OR invalidated)
- [ ] CLI `uv run daytrader journal pre-trade` was run and `PASSED` before entry
- [ ] Pre-trade screenshot saved per Contract §9
- [ ] Post-trade screenshot saved (entry fill, stop/target fill, close timestamp)

**Any unticked box = a discipline break.** Trades that fail the setup-match
check do NOT count toward the 30-trade lock-in and are a §6
`ban_trade_outside_setup_definition` violation.

Discipline breaks this trade: `__________`

## 3. Setup quality (independent of outcome)

A losing trade with a clean setup is fine. A winning trade on a sloppy
setup is a problem.

- Imbalance clarity (1–5): `___`     (5 = unmistakable 3-stack at price)
- Level quality (1–5): `___`         (5 = high-confluence, fresh zone or strong point)
- Was higher-timeframe context with me, against me, or neutral? `__________`
- Would I take this exact signal again? `[ ] yes  [ ] no — because: __________`

## 4. Execution quality

- Slippage on entry (ticks): `___`
- Slippage on stop/target fill (ticks): `___`
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
- Trades today: `___ / 3`
- Cool-off triggered? `[ ] no  [ ] yes — until: __________`
- Circuit `no_trade_flag`? `[ ] no  [ ] yes — reason: __________`

---

## Stop rules reminder (Contract §3, §6, §7)

- 2 consecutive stops → end day (`consecutive_stops_day_end: 2`)
- −2R intraday → 30 min cool-off (`minus_2r_cooloff_minutes: 30`)
- −2R day → done, no exceptions (`daily_loss_limit_r: 2`)
- Any zero-tolerance ban violated (Contract §6) → today's results are
  invalidated for evaluation purposes; log it honestly anyway
- Trade that fails setup-match → does NOT count toward 30-trade lock-in
