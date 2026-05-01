# Phase 2 Real-World Acceptance Runbook

After Phase 2 is merged, this runbook walks through the manual end-to-end test
that proves the foundation works against real IB Gateway and real Claude CLI.

## Prerequisites

1. **IB Gateway running locally** — see `docs/ops/ib-gateway-setup.md` (Phase 1).
2. **Claude Code CLI installed and authenticated** — Phase 2 invokes Claude via
   `claude -p` (Pro Max subscription path), NOT the Anthropic API. Verify:

   ```bash
   which claude        # should print a path
   claude --help       # should show usage
   echo "say hi" | claude -p   # quick auth check; should print a response
   ```

   If `claude` is not on PATH, install Claude Code from <https://claude.com/claude-code>
   and sign in with your Pro/Max account before continuing.

3. **Obsidian vault path** — set in `config/user.yaml`:

   ```yaml
   obsidian:
     enabled: true
     vault_path: ~/Path/To/Your/Vault
     daily_folder: Daily
   ```

4. **(Optional) Contract.md** — Phase 2 runs even with empty Contract; it will
   degrade per spec §4.5 state machine. To get the full premarket flow with C
   plan formation tied to your real setup, fill `docs/trading/Contract.md` first.

## Step 1: Smoke test in dry-run mode

```bash
uv run daytrader reports dry-run --type premarket
```

Expected: 6 stub lines, exit 0.

## Step 2: Real end-to-end run

```bash
uv run daytrader reports run --type premarket
```

What it does:
1. Verifies `claude` CLI is on PATH (fails fast if missing)
2. Loads config (no API key needed in Phase 2)
3. Connects to IB Gateway on `127.0.0.1:7496` (or 4002 for IB Gateway)
4. Fetches bars for ALL symbols in `instruments.yaml` (MES + MNQ + MGC by default): 52 weekly + 200 daily + 50 4H + 24 1H per symbol — 12 IB requests per run
5. Loads Contract.md (degrades gracefully if missing)
6. Builds prompt as a flattened `[SYSTEM] / [USER]` text block
7. Invokes `claude -p` subprocess (~5-30 seconds, depends on subscription queue)
8. Validates required sections in the returned markdown
9. Extracts today's plan, saves to SQLite `plans` table
10. Writes markdown to `<vault>/Daily/2026-MM-DD-premarket.md`
11. Records report metadata in SQLite `reports` table (token counts will be 0)
12. Disconnects from IB Gateway

Expected stdout: `Report generated: /path/to/2026-MM-DD-premarket.md`

Expected cost (per run): **$0** — covered by your Claude Pro Max subscription. Subscription
usage counts toward your monthly quota; for Phase 2 dev/testing this is not a concern,
but Phase 7 production cadence (~6 runs/day × 3 instruments) may need re-evaluation.

## Step 3: Inspect the output

1. Open the generated markdown in Obsidian. Check:
   - Lock-in metadata block at top
   - Multi-TF analysis (W / D / 4H / 1H), each with OHLCV + pattern
   - Breaking news section (may say "no news items" if news collector not wired in Phase 2)
   - C section with plan structure
   - B section narrative
   - A section ("no action — execute plan" by default)

2. Check the SQLite plan was extracted:

   ```bash
   uv run python -c "
   from daytrader.core.state import StateDB
   db = StateDB('data/state.db')
   row = db.get_plan_for_date('2026-MM-DD', 'MES')
   print(dict(row) if row else 'no plan')
   "
   ```

3. Check the report record:

   ```bash
   uv run python -c "
   import sqlite3
   conn = sqlite3.connect('data/state.db')
   conn.row_factory = sqlite3.Row
   row = conn.execute('SELECT * FROM reports ORDER BY id DESC LIMIT 1').fetchone()
   print(dict(row))
   "
   ```

## Step 4: Idempotency check

Run again on the same day:

```bash
uv run daytrader reports run --type premarket
```

Expected: `Report already generated today (skipped).` Exit 0. AI not called again.

## Step 5 (Phase 3): Verify multi-instrument coverage

After a successful run, the generated markdown file should contain:

- Three per-instrument multi-TF blocks: MES, MNQ, MGC (each with W/D/4H/1H)
- Two C-block plans: C-MES and C-MGC (NOT C-MNQ — context-only)
- One integrated A-section recommendation

Quick verification:

```bash
grep -c "📊 MES\|📊 MNQ\|📊 MGC" "$HOME/Documents/DayTrader Vault/Daily/$(date +%Y-%m-%d)-premarket.md"
# Expected: 3
```

```bash
uv run python -c "
from daytrader.core.state import StateDB
db = StateDB('data/state.db')
mes = db.get_plan_for_date('$(date +%Y-%m-%d)', 'MES')
mgc = db.get_plan_for_date('$(date +%Y-%m-%d)', 'MGC')
mnq = db.get_plan_for_date('$(date +%Y-%m-%d)', 'MNQ')
print('MES plan:', dict(mes) if mes else 'none')
print('MGC plan:', dict(mgc) if mgc else 'none')
print('MNQ plan:', 'none (context-only) ✓' if mnq is None else 'UNEXPECTED:', dict(mnq) if mnq else 'none')
"
# Expected: MES + MGC plans populated; MNQ none (context-only ✓)
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "claude CLI not found on PATH" | Claude Code not installed or not in shell PATH | Install Claude Code; ensure shell rc sources its bin path |
| "claude -p exit=1: not authenticated" | Claude Code CLI not signed in | Run `claude` interactively once to complete sign-in |
| "claude -p timeout after 180s" | Slow subscription queue or hung CLI | Retry; if persistent, check `claude doctor` for issues |
| "IBClient is not connected" | IB Gateway not running | Start IBC; verify port 4002 |
| `ConnectionError` mid-pipeline | IB Gateway dropped during fetch | The orchestrator marks the report `failed`; manual rerun needed. Phase 2 has no auto-retry. |
| Validation fails: missing C / B / A | Generated structure differs from template expectation | Inspect the report content; adjust `reports/templates/premarket.md` if needed |
| Bars empty for some TF | IB Gateway not receiving market data | Check CME data subscription in IBKR account |
| Subscription rate-limited | Hit Pro Max quota | Wait or temporarily switch to API backend (future Phase 7 work) |

## What this run does NOT yet do (Phase 4+)

- F. 期货结构 (no OI/COT/basis/term/VolumeProfile) → Phase 4
- Anthropic Web Search for breaking news → Phase 4
- Other report types (intraday/EOD/weekly/night) → Phase 5
- Telegram push (only Obsidian today) → Phase 6
- PDF / chart rendering → Phase 6
- Automatic launchd schedule → Phase 7

## Acceptance criteria

Phase 2 is "done" when:
1. ☐ `daytrader reports run --type premarket` succeeds without error
2. ☐ A markdown file is created in your Obsidian Daily folder
3. ☐ The file passes a manual sanity read — sections look correct, numbers are real
4. ☐ The plan extraction populates `state.db.plans` with one row per TRADABLE instrument (MES + MGC; NOT MNQ which is context-only)
5. ☐ Idempotent re-run within the same ET day prints "skipped" and does not call AI
6. ☐ Estimated cost in the `reports` row is 0.0 (claude -p backend)
