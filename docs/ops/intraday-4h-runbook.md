# Intraday 4H Cadences Runbook

**Cadences:** intraday-4h-1 (07:00 PT) + intraday-4h-2 (11:00 PT)
**Auto-fire:** Mon-Fri via launchd
**Spec:** docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md

## What runs when

| Time | Cadence | Trigger | Generates |
|---|---|---|---|
| 07:00 PT (10:00 ET) | intraday-4h-1 | launchd `com.daytrader.report.intraday-4h-1.0700pt` | `Daily/<date>-0700PT-4H1.md` |
| 11:00 PT (14:00 ET) | intraday-4h-2 | launchd `com.daytrader.report.intraday-4h-2.1100pt` | `Daily/<date>-1100PT-4H2.md` |

## Differences between 4h-1 and 4h-2

| Feature | 4h-1 | 4h-2 |
|---|---|---|
| Plan Retrospective | ❌ skip (placeholder text) | ✅ full retrospective + persist to `plan_retrospective_daily` |
| Sentiment refresh | ❌ reuse premarket cache | ✅ refresh with `time_window="past 5h"` |
| News window | past 1h | past 5h |
| Trade archive | light list | light list |
| Telegram | ✅ | ✅ |
| PDF render | ❌ skipped (--no-pdf flag) | ❌ skipped |
| Length target | 5-7K chars | 5-7K chars |

## Install / uninstall

```bash
./scripts/install_intraday_4h_launchd.sh
launchctl list | grep intraday-4h
./scripts/uninstall_intraday_4h_launchd.sh
```

## Manual trigger

```bash
daytrader reports run --type intraday-4h-1 --no-pdf
daytrader reports run --type intraday-4h-2 --no-pdf
```

## Troubleshooting

### Report not generated at 07:00 PT or 11:00 PT

1. Check launchd log: `tail -50 $(ls -t data/logs/launchd/intraday-4h-1-*.log | head -1)`
2. Check preflight passed (TWS healthy, claude on PATH, config files present)
3. Check state.db: `sqlite3 data/state.db "SELECT * FROM reports WHERE report_type LIKE 'intraday-4h%' ORDER BY id DESC LIMIT 5;"`
4. Check warnings (I1 fix): `sqlite3 data/state.db "SELECT * FROM failures WHERE report_type LIKE 'intraday-4h%' ORDER BY id DESC LIMIT 10;"`

### 4h-2 retrospective is empty / failed

1. Verify premarket plan exists: `ls -la <obsidian-vault>/Daily/$(date +%Y-%m-%d)-premarket.md`
2. Check `plan_retrospective_daily` table for today's row
3. Verify 5m bar fetch (depends on Phase 5.5 hot-fix C1, commit b04b151)

### Report missing required sections

Validator marks report `failed`. Check `state.failures` for `failure_stage="validation"`.

## Logs

- `data/logs/launchd/intraday-4h-1-<TS>.log` — wrapper stdout/stderr
- `data/logs/launchd/intraday-4h-1.0700pt.out` — launchd stdout
- `data/logs/launchd/intraday-4h-1.0700pt.err` — launchd stderr (should be 0 byte if healthy)
- Same for 4h-2. All ignored by `.gitignore`.
