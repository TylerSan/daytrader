# Pre-Trade Checklist

Fill this **before** clicking buy/sell. If any item is ✗, do not trade.

The 5 hard gates (sections 3–5 below) are also enforced by
`uv run daytrader journal pre-trade` — this Markdown form is the
human-readable companion for screenshot/audit purposes. Per Contract.md §5,
`entry_via_cli_only: true` — you must still run the CLI from the repo root.

Locked setup: **stacked_imbalance_reversal_at_level** (see
[setups/stacked_imbalance_reversal.yaml](setups/stacked_imbalance_reversal.yaml)).

---

## 0. Trade header

- Date / time (local, NY): `__________`
- Trade # in lock-in: `___ / 30`
- Symbol: `[ ] MES   [ ] MGC`     (MNQ is reports-only, NOT tradable)
- Direction: `[ ] long  [ ] short`
- Footprint instrument watched: `[ ] ES (for MES)   [ ] GC (for MGC)`

## 1. Contract status

- [ ] Contract `Active: true` and within current 30-trade lock-in
- [ ] Today's trade count `<` `max_trades_per_day` (**3**)
- [ ] Today's realized R `>` `-daily_loss_limit_r` (**−2R**)
- [ ] Not inside a cool-off window: last stop ≥ 30 min ago
- [ ] Not at `consecutive_stops_day_end` (2 stops today → no more trades)
- [ ] If realized today is at −2R already → **stop, no more trades**

## 2. Session window (per setup YAML)

- [ ] Now is within the instrument's window (NY local):
  - MES: `09:30 – 11:30`
  - MGC: `08:20 – 10:30`
- [ ] No high-impact event today: FOMC, CPI, NFP, opex_friday → if yes, skip
- [ ] No news within next 15 min
- [ ] Opening Range NOT already invalidated

## 3. Setup validation (mechanical — every box must be ✓)

### Key level (must match one in setup YAML)

- [ ] Level type identified (write below):
  - POINT: prior_day_high / prior_day_low / prior_day_close / day_vwap /
    weekly_high / weekly_low / psychological_round / hvn_value_area_high /
    lvn_value_area_low
  - ZONE (HTF supply/demand, ≥ 4H TF): htf_demand_zone / htf_supply_zone
- Level type recorded: `__________`
- For ZONE only — record:
  - Zone TF: `__________` (4H / Daily / Weekly / Monthly)
  - Zone low: `__________`   Zone high: `__________`
  - Freshness: `[ ] fresh  [ ] tested_once  [ ] multiple_taps`
- [ ] Price ≥ 0.5 ATR away from level

### Level proximity rule

- [ ] POINT level: entry within **4 ticks** of the point price, OR
- [ ] ZONE level: entry price **inside [zone_low, zone_high]**

### Stacked imbalance (MotiveWave Level 3 / footprint)

- [ ] **≥ 3 consecutive prices**, same direction
- [ ] Each qualifying price: ratio **≥ 5:1** (MotiveWave Imbalance 3 = 500%)
- [ ] Each qualifying price: volume **≥ 100 contracts** (Delta Filter 3)
- [ ] Direction: I am entering **against** the imbalance (fade aggression)
- [ ] Timing: entering immediately on the 3rd stacked print (mid-bar OK)

## 4. Risk parameters (preset BEFORE entry)

- [ ] Entry price written: `__________`
- [ ] Stop price written: `__________` (will not be widened, full stop)
- [ ] Stop placement matches YAML rule:
  - POINT level: 2 ticks beyond the point (opposite side)
  - ZONE level: 2 ticks beyond the far edge of the zone
- [ ] Target price written: `__________`
  - Rule: **closer of (2R, next key level)** — `target = max_2R_or_next_key_level`
- [ ] R USD computed: `$_____` ≤ **$50** (1R)
  - MES: $5/pt × size × |entry−stop| ≤ $50
  - MGC: $10/pt × size × |entry−stop| ≤ $50
- [ ] Size = **1** (Contract `max_contracts: 1`)

## 5. Order ticket (IBKR)

- [ ] Entry + stop + target submitted as **bracket / OCO**
- [ ] Stop is **at the broker** (not mental, not a "watch" level)
- [ ] Exit structure: **all_at_target** (1 contract closes at one target — no scaling)

## 6. Bans — confirm none are about to be violated

- [ ] No averaging down planned if it goes against me
- [ ] Will not move stop away from entry, ever
- [ ] Will not exit at < target unless structure invalidates
- [ ] Not a revenge trade after a recent stop
- [ ] Setup matches the YAML — if it doesn't, this trade does NOT count toward
      lock-in AND is a §6 violation (`ban_trade_outside_setup_definition`)

## 7. §9 audit screenshots (mandatory for lock-in count)

- [ ] **Pre-trade MotiveWave screenshot** showing:
  - The key level being faded (matches a `key_level_types` entry)
  - For ZONE levels: TF, zone edges, freshness annotated
  - The 3+ stacked imbalances (5:1 + ≥100 contracts visible)
  - Footprint instrument: ES (for MES) or GC (for MGC)
  - Filter conditions: no event, ATR proximity OK, OR not invalidated
- Screenshot saved to: `__________`

## 8. CLI gate — must PASS

- [ ] Ran `uv run daytrader journal pre-trade ...` and got `PASSED checklist_id=...`
- `checklist_id` recorded: `__________`
- `trade_id` recorded: `__________`

---

## If any box is ✗

Do **not** size down and trade anyway. Skip the trade. Note the reason in the
journal. Skips are part of the audit data.

## After fill

Move to the post-trade journal entry; reference `checklist_id` and `trade_id`.
Capture the §9 post-trade screenshot (entry fill, stop/target fill, close
timestamp) before running `post-trade`.
