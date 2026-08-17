# Phase 2 Dry-Run Walkthrough

Use this once per week to verify the system end-to-end. All commands run from
project root.

1. Sign contract (manual):
   - Edit `docs/trading/Contract.md` — fill in real values, set Active: true

2. Run sanity on a candidate setup:
   ```bash
   daytrader journal sanity run docs/trading/setups/opening_range_breakout.yaml
   ```
   Record verdict status.

3. Simulate a dry-run:
   ```bash
   # checklist + hypothetical record:
   daytrader journal pre-trade --symbol MES --direction long \
       --setup orb --entry 5000 --stop 4995 --target 5010 \
       --size 1 --stop-at-broker --dry-run
   # note checklist_id from output

   daytrader journal dry-run start --checklist-id <id> --symbol MES \
       --direction long --setup orb --entry 5000 --stop 4995 \
       --target 5010 --size 1
   # later:
   daytrader journal dry-run end <dry_run_id> \
       --outcome target_hit --outcome-price 5010 \
       --notes "clean break, held to target"
   ```

4. Check circuit + audit + gate:
   ```bash
   daytrader journal circuit status
   daytrader journal audit
   daytrader journal resume-gate check
   ```

5. Verify Obsidian vault has new files under DayTrader/Trades and DayTrader/DryRuns.
