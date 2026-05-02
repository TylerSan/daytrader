# Phase 7 v1: launchd Auto-Trigger Runbook

After Phase 7 v1 install, the premarket report generates **automatically every weekday at 06:00 PT** (Mon-Fri). User wakes up to a fresh report in Obsidian + Telegram (if bot configured), no manual command needed.

## Scope

✅ Premarket 06:00 PT only (Mon-Fri)
❌ Other report types (intraday/EOD/night/weekly) — Phase 7.5 after Phase 5 lands those
❌ IB Gateway 24/7 — TWS still needs to be running (manually or via separate automation)

## Prerequisites

1. **Mac stays awake at 06:00 PT.** Either:
   - Mac mini that doesn't sleep (best: leave power-on, screen-saver OK)
   - Or: configure power schedule to wake at 05:55 PT:
     ```bash
     # Wake every weekday at 05:55 PT
     sudo pmset repeat wakeorpoweron MTWRF 05:55:00
     ```
   - Verify: `pmset -g sched`
2. **TWS is running by 06:00 PT.** Two options:
   - Manual: open TWS each morning when you get up (5:50-6:00 PT)
   - Auto: use TWS's "Auto-restart" config + macOS Login Items so TWS launches at boot, then keep Mac awake overnight
3. **claude CLI logged in** (verified once; persists)
4. **All Phase 1-6 work merged / present** in the project worktree

## Install

```bash
cd "/Users/tylersan/Projects/Day trading/.claude/worktrees/nice-varahamihira-9d6142"
./scripts/install_launchd.sh
```

Output should end with "Next firing: next weekday at 06:00 PT".

## Verify

```bash
# Job is loaded
launchctl print "gui/$(id -u)/com.daytrader.report.premarket.0600pt" | head -30
```

Look for `state = waiting` and the `StartCalendarInterval` entries.

## Test fire NOW (without waiting for 06:00 PT)

⚠️ This invokes the real pipeline (TWS + claude + Obsidian + optional Telegram). Make sure TWS is running.

```bash
launchctl kickstart "gui/$(id -u)/com.daytrader.report.premarket.0600pt"
# Wait ~2.5 minutes
ls -la "$HOME/Documents/DayTrader Vault/Daily/" | grep premarket
tail -50 data/logs/launchd/premarket-*.log | tail -50
```

If everything wired correctly: a fresh `YYYY-MM-DD-premarket.md` appears in Obsidian.

## What happens if TWS isn't running at 06:00 PT?

`scripts/preflight_check.py` detects the unreachable port → wrapper exits 0 (no retry storm) → macOS sends a notification ("Preflight check failed at 06:00 PT — TWS / claude / config issue") → user gets the alert and starts TWS manually.

⚠️ **The notification only shows if Mac is awake AND not in Do Not Disturb mode.** For a phone alert (more reliable), wire Telegram bot per `docs/ops/phase2-runbook.md` step "Telegram bot setup".

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No file generated at 06:00 PT, no log | Mac was asleep; launchd didn't fire | `pmset -g sched` to confirm wake schedule; test with `kickstart` |
| Log shows "TWS unreachable" | TWS not running at 06:00 PT | Open TWS by 05:55; or auto-launch TWS via Login Items |
| Log shows "claude CLI not found" | launchd PATH doesn't include /opt/homebrew/bin | Already handled in plist `EnvironmentVariables.PATH`; verify by `launchctl print` |
| Log shows AI timeout | claude -p > 180s | Increase `AIAnalyst.timeout_seconds` in code; or accept retry |
| Log shows "Telegram disabled: Secrets file not found" | bot not configured | OK — only Obsidian write happens; configure bot per phase2-runbook if you want phone push |
| Job fires but NO log file at all | Wrapper didn't even start; permission issue on shell script | `ls -la scripts/run_premarket_launchd.sh` — must be executable; re-`chmod +x` if not |

## Uninstall

```bash
./scripts/uninstall_launchd.sh
```

Removes plist and unloads job. Pipeline files (markdown, charts, etc.) are NOT deleted.

## Logs

Each run writes to `data/logs/launchd/premarket-YYYY-MM-DD-HHMMSS.log` (the wrapper's tee output). launchd's own stdout/stderr also go to `data/logs/launchd/premarket.0600pt.{out,err}`.

Both are gitignored. Manual rotation for now — `ls data/logs/launchd | wc -l` shouldn't grow past ~30 unless you run many test fires.

## What about the other 6 report time slots?

Spec §6.2.1 lists 7 plists total. Phase 7 v1 only installs the premarket one because Phase 5 (other report types) hasn't been built. When Phase 5 lands:
- Same plist template pattern, just different time slots
- Phase 7.5 plan will write/install all 7
