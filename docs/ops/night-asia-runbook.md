# Night/Asia Cadences Runbook

**Cadences:** night (19:00 PT) + asia (23:00 PT)
**Auto-fire:** Mon-Fri via launchd
**Spec:** docs/superpowers/specs/2026-05-05-reports-phase5.5-cadences-design.md

## What runs when

| Time | Cadence | Generates |
|---|---|---|
| 19:00 PT (22:00 ET) | night | `Daily/<date>-1900PT-night.md` |
| 23:00 PT (02:00+1 ET) | asia | `Daily/<date>-2300PT-asia.md` |

**Note**: filename uses **PT date** (not ET). For asia at 23:00 PT, the date is the SAME PT day's session — the file is e.g. `2026-05-05-2300PT-asia.md` even though the 23:00 PT clock-time is technically already 2026-05-06 in ET. This is a deliberate Phase 5.5 T10 design decision (PT-anchored archive aligns with how the trader thinks of the "day's overnight" cadence).

## Purpose

D-only learning archive. NO A/B/C sections. AI populates pattern_tags + news_event_tags YAML frontmatter for future programmatic queries (e.g. "all bullish_engulf at support_test in last 30 days").

## Differences from intraday-4h

| Feature | night/asia | intraday-4h |
|---|---|---|
| Sections | metadata + multi-TF + F + news + D archive | A+B+C+F + sentiment + retrospective + trades |
| Multi-TF | 4H + 1H only | D + 4H + 1H |
| Telegram | ❌ off | ✅ on |
| PDF | ❌ off | ❌ off |
| Length | 3.5-5K chars | 5-7K chars |

## Install / uninstall

```bash
./scripts/install_night_asia_launchd.sh
launchctl list | grep -E "night|asia"
./scripts/uninstall_night_asia_launchd.sh
```

## Manual trigger

```bash
daytrader reports run --type night --no-pdf
daytrader reports run --type asia --no-pdf
```

## Troubleshooting

Same as intraday-4h-runbook with these specifics:

1. **TWS at 23:00 PT** — IB Gateway is in cme globex / hkfe boundary; preflight handshake confirms healthy.

2. **D archive frontmatter** — verify report file has YAML at top with pattern_tags + news_event_tags arrays.

3. **Future query** (Phase 6 work, not yet implemented):
   ```bash
   # Future: daytrader research query --pattern bullish_engulf --days 30
   ```

## Logs

- `data/logs/launchd/night-<TS>.log` / `data/logs/launchd/asia-<TS>.log`
- Plus the launchd `.out` / `.err` files. All ignored by `.gitignore`.
