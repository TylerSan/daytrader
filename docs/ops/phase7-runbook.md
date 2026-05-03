# Phase 7: launchd Auto-Trigger Runbook (premarket + weekly)

After install, two reports generate automatically without user intervention:

| Job | Schedule | Command | Output |
|---|---|---|---|
| **premarket** | **Mon-Fri 06:00 PT** | `daytrader reports run --type premarket --no-pdf` (new system, multi-instrument) | `~/Documents/DayTrader Vault/Daily/YYYY-MM-DD-premarket.md` |
| **weekly** | **Sunday 14:00 PT** | `daytrader weekly run --ai` (old system; new `reports --type weekly` is a Phase 5 stub) | `~/Documents/DayTrader Vault/Weekly/weekly-YYYY-MM-DD.md` |

User wakes up to a fresh report in Obsidian + Telegram (if bot configured), no manual command needed.

## Scope

✅ Premarket 06:00 PT (Mon-Fri) — new multi-instrument pipeline
✅ Weekly 14:00 PT (Sun) — old `daytrader weekly` pipeline (Phase 5 will route this to new system; only the wrapper's invoked command will change, plist + schedule stay the same)
❌ Other report types (intraday/EOD/night/asia) — Phase 7.5 after Phase 5 lands those
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
# From the project root (e.g., ~/Projects/Day trading)
cd "$(git rev-parse --show-toplevel)"

# Premarket job (Mon-Fri 06:00 PT)
./scripts/install_launchd.sh

# Weekly job (Sun 14:00 PT)
./scripts/install_weekly_launchd.sh
```

Each install ends with "Next firing: ..." line. Run them independently — neither depends on the other.

## Verify

```bash
# Premarket job is loaded
launchctl print "gui/$(id -u)/com.daytrader.report.premarket.0600pt" | head -30

# Weekly job is loaded
launchctl print "gui/$(id -u)/com.daytrader.report.weekly.sun1400pt" | head -30
```

Look for `state = not running` (= idle/armed) and the calendar interval descriptor (Hour/Minute/Weekday).

## Test fire NOW (without waiting for the schedule)

⚠️ Both invocations exercise the real pipeline (TWS + claude + Obsidian). Make sure TWS is running before testing premarket; weekly only needs claude + config.

```bash
# Premarket (~2.5 min, writes to Daily/)
launchctl kickstart "gui/$(id -u)/com.daytrader.report.premarket.0600pt"
ls -la "$HOME/Documents/DayTrader Vault/Daily/" | grep premarket
tail -50 data/logs/launchd/premarket-*.log

# Weekly (~2.5 min, writes to Weekly/)
launchctl kickstart "gui/$(id -u)/com.daytrader.report.weekly.sun1400pt"
ls -la "$HOME/Documents/DayTrader Vault/Weekly/" | grep weekly
tail -80 data/logs/launchd/weekly-*.log
```

If everything wired correctly: fresh markdown files appear in Obsidian.

## What happens if TWS isn't running at 06:00 PT?

`scripts/preflight_check.py` detects the unreachable port → wrapper exits 0 (no retry storm) → macOS sends a notification ("Preflight check failed at 06:00 PT — TWS / claude / config issue") → user gets the alert and starts TWS manually.

⚠️ **The notification only shows if Mac is awake AND not in Do Not Disturb mode.** For a phone alert (more reliable), wire Telegram bot per `docs/ops/phase2-runbook.md` Prerequisites step 5 (Telegram bot setup).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No file generated at 06:00 PT, no log | Mac was asleep; launchd didn't fire | `pmset -g sched` to confirm wake schedule; test with `kickstart` |
| Log shows "TWS unreachable" | TWS not running at 06:00 PT | Open TWS by 05:55; or auto-launch TWS via Login Items |
| Log shows "claude CLI not found" | launchd PATH doesn't include /opt/homebrew/bin | Already handled in plist `EnvironmentVariables.PATH`; verify by `launchctl print` |
| Log shows AI timeout | claude -p > 180s | Increase `AIAnalyst.timeout_seconds` in code; or accept retry |
| Log shows "Telegram disabled: Secrets file not found" | bot not configured | OK — only Obsidian write happens; see Telegram bot setup steps in `docs/ops/phase2-runbook.md` Prerequisites step 5 |
| Job fires but NO log file at all | Wrapper didn't even start; permission issue on shell script | `ls -la scripts/run_premarket_launchd.sh` — must be executable; re-`chmod +x` if not |

## Uninstall

```bash
./scripts/uninstall_launchd.sh           # premarket
./scripts/uninstall_weekly_launchd.sh    # weekly
```

Removes plist and unloads job. Pipeline files (markdown, charts, etc.) are NOT deleted.

## Logs

Each run writes a timestamped wrapper log:
- Premarket: `data/logs/launchd/premarket-YYYYMMDD-HHMMSS.log`
- Weekly: `data/logs/launchd/weekly-YYYYMMDD-HHMMSS.log`

launchd's own stdout/stderr also go to `data/logs/launchd/premarket.0600pt.{out,err}` and `data/logs/launchd/weekly.sun1400pt.{out,err}`.

All gitignored. Manual rotation for now — `ls data/logs/launchd | wc -l` shouldn't grow past ~50 unless you run many test fires. Quarterly truncate launchd's own .out/.err if they grow:

```bash
: > data/logs/launchd/premarket.0600pt.out
: > data/logs/launchd/premarket.0600pt.err
: > data/logs/launchd/weekly.sun1400pt.out
: > data/logs/launchd/weekly.sun1400pt.err
```

## Troubleshooting (additions for weekly)

| Symptom | Likely cause | Fix |
|---|---|---|
| Weekly fires Sunday but writes to wrong vault folder | `weekly_folder` config drift | Check `config/user.yaml` `obsidian.weekly_folder` (default: `Weekly`) |
| Weekly log shows "Phase 2 implements premarket only" | The wrapper accidentally calls `daytrader reports run --type weekly` instead of `daytrader weekly run --ai` | Inspect `scripts/run_weekly_launchd.sh` line ~57; should be `uv run daytrader weekly run --ai` until Phase 5 lands |
| Weekly fires twice on the same Sunday | Both `Weekday=0` and `Weekday=7` defined (both = Sunday); only have ONE of them in the plist | `plutil -p` the plist to confirm only one Weekday entry |

## What about the other 5 report time slots?

Spec §6.2.1 lists 7 cadences total. Phase 7 currently installs 2 (premarket + weekly). The remaining 5 (intraday-4h-1, intraday-4h-2, eod, night, asia) wait for Phase 5 to build out their content generation. When Phase 5 lands:
- Same plist template pattern, just different time slots
- Phase 7.5 plan will write/install all remaining plists

## Migration note (Phase 5)

When Phase 5 implements `daytrader reports run --type weekly` properly, swap the wrapper's invocation from `uv run daytrader weekly run --ai` to `uv run daytrader reports run --type weekly --no-pdf`. Plist + schedule + install scripts stay unchanged.
