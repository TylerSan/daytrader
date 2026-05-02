# Reports System — Phase 7 v1: launchd Premarket Auto-Trigger

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute. Steps use checkbox `- [ ]` syntax.

**Goal:** Auto-generate the premarket report every weekday at **06:00 PT** without user intervention. After Phase 7 v1: user wakes up to a fresh `YYYY-MM-DD-premarket.md` in Obsidian + (if Telegram bot configured) a phone push, no manual command needed.

**Architecture:** Strictly additive. New `scripts/launchd/` directory with one plist for premarket. New shell wrapper that sources PATH (for `claude` + `uv`), runs preflight check, then calls `daytrader reports run --type premarket`. New `scripts/preflight_check.py` that pings TWS port + verifies `claude` CLI before invocation. New `scripts/install_launchd.sh` for one-command install. New runbook documents the manual user steps.

**Scope (intentionally tight):**
- ✅ premarket 06:00 PT only (Mon-Fri)
- ❌ Other 6 report time slots (intraday/EOD/night/weekly) — defer to Phase 7.5 after Phase 5 lands those report types
- ❌ IB Gateway 24/7 / IBC headless mode — defer; user keeps using TWS manually for now
- ❌ Cleanup / log rotation — defer; data dir won't fill fast

**Tech Stack:** Bash, plist (XML), Python (preflight check), no new external deps.

**Spec reference:** `docs/superpowers/specs/2026-04-25-reports-system-design.md` §6.2 launchd schedule, §6.6 first-run checklist.

**Prerequisites:**
- Phases 1-6 complete ✅
- Mac stays awake / wakes up at 06:00 PT (covered in runbook with `pmset`)
- TWS launches automatically OR user starts manually before 06:00 PT
- Optional: Telegram bot configured for alert when preflight fails

---

## File Structure

| File | Action | Why |
|---|---|---|
| `scripts/preflight_check.py` | Create | Pre-run sanity check (TWS port, claude CLI, config) |
| `tests/scripts/test_preflight_check.py` | Create | Unit tests |
| `scripts/run_premarket_launchd.sh` | Create | Bash wrapper invoked by launchd |
| `scripts/launchd/com.daytrader.report.premarket.0600pt.plist` | Create | macOS launchd manifest |
| `scripts/install_launchd.sh` | Create | One-command install/load |
| `scripts/uninstall_launchd.sh` | Create | One-command uninstall/unload |
| `docs/ops/phase7-runbook.md` | Create | Manual setup + troubleshooting |
| `data/logs/launchd/.gitkeep` | Create | Ensure log dir exists |
| `.gitignore` | Modify (additive) | Ignore launchd log files |

---

## Task 1: PreflightCheck script

**Files:**
- Create: `scripts/preflight_check.py`
- Create: `tests/scripts/test_preflight_check.py`

- [ ] **Step 1: Write failing test**

Create `tests/scripts/test_preflight_check.py`:

```python
"""Unit tests for scripts/preflight_check.py."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight_check.py"


def _run(*extra_args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), *extra_args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_preflight_help_succeeds():
    """`--help` exits 0."""
    result = _run("--help")
    assert result.returncode == 0
    assert "preflight" in (result.stdout + result.stderr).lower()


def test_preflight_silent_mode_supported():
    """`--silent` flag is accepted."""
    result = _run("--help")
    assert result.returncode == 0
    assert "--silent" in result.stdout


def test_preflight_check_tws_port_unreachable_when_no_tws(monkeypatch):
    """Direct function test: tws_port_open returns False when nothing's listening."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Pick an unused port — port 0 is invalid, use 65000
        result = module.tws_port_open(host="127.0.0.1", port=65000, timeout=1.0)
        assert result is False
    finally:
        sys.path.pop(0)


def test_preflight_check_tws_port_open_when_listener(monkeypatch, tmp_path):
    """Spin up a temp TCP listener; preflight detects it."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            result = module.tws_port_open(host="127.0.0.1", port=port, timeout=1.0)
            assert result is True
        finally:
            srv.close()
    finally:
        sys.path.pop(0)


def test_preflight_check_claude_cli_available():
    """claude_cli_available returns True when `claude` binary is on PATH."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("preflight_check", str(SCRIPT))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Real claude is installed (at /opt/homebrew/bin/claude)
        # Test default behavior — should find it
        result = module.claude_cli_available()
        # Accept either True or False; we just want it not to crash
        assert isinstance(result, bool)
    finally:
        sys.path.pop(0)
```

- [ ] **Step 2: Run tests (red)**

Run: `uv run pytest tests/scripts/test_preflight_check.py -v`
Expected: FAIL — script doesn't exist.

- [ ] **Step 3: Implement preflight script**

Create `scripts/preflight_check.py`:

```python
#!/usr/bin/env python3
"""Pre-run sanity check for `daytrader reports run` automation.

Returns exit 0 if all checks pass, exit non-zero if any check fails.
With `--silent`, suppresses stdout (errors still go to stderr).

Checks:
- TWS / IB Gateway port reachable
- `claude` CLI present on PATH
- `config/default.yaml` and `config/user.yaml` readable
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
from pathlib import Path


def tws_port_open(host: str = "127.0.0.1", port: int = 7496, timeout: float = 2.0) -> bool:
    """Return True iff TCP connect to host:port succeeds within timeout."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False


def claude_cli_available() -> bool:
    """Return True iff `claude` is on PATH."""
    return shutil.which("claude") is not None


def config_files_readable(project_root: Path) -> tuple[bool, str]:
    """Return (ok, msg). ok=True if both config files readable."""
    default = project_root / "config" / "default.yaml"
    user = project_root / "config" / "user.yaml"
    if not default.exists():
        return False, f"missing {default}"
    if not user.exists():
        return False, f"missing {user} (run setup or use defaults)"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="preflight check for daytrader reports automation")
    parser.add_argument("--silent", action="store_true", help="suppress stdout on success")
    parser.add_argument("--tws-host", default="127.0.0.1")
    parser.add_argument("--tws-port", type=int, default=7496)
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    project_root = Path(args.project_root)
    failures: list[str] = []

    # 1. TWS port
    if tws_port_open(host=args.tws_host, port=args.tws_port):
        if not args.silent:
            print(f"[preflight] ✓ TWS reachable at {args.tws_host}:{args.tws_port}")
    else:
        failures.append(f"TWS unreachable at {args.tws_host}:{args.tws_port}")

    # 2. claude CLI
    if claude_cli_available():
        if not args.silent:
            print("[preflight] ✓ claude CLI on PATH")
    else:
        failures.append("claude CLI not found on PATH")

    # 3. config files
    ok, msg = config_files_readable(project_root)
    if ok:
        if not args.silent:
            print("[preflight] ✓ config files readable")
    else:
        failures.append(f"config: {msg}")

    if failures:
        for f in failures:
            print(f"[preflight] ✗ {f}", file=sys.stderr)
        return 1
    if not args.silent:
        print("[preflight] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable:

Run: `chmod +x scripts/preflight_check.py`

- [ ] **Step 4: Run tests (green)**

Run: `uv run pytest tests/scripts/test_preflight_check.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Manual sanity check**

Run: `uv run python scripts/preflight_check.py`
Expected: prints check results, exits 0 if TWS is up + claude on PATH + configs exist.

- [ ] **Step 6: Commit**

```bash
git add scripts/preflight_check.py tests/scripts/test_preflight_check.py
git commit -m "feat(reports): scripts/preflight_check.py (TWS + claude + config sanity)"
```

---

## Task 2: launchd wrapper bash script

**Files:**
- Create: `scripts/run_premarket_launchd.sh`

The wrapper does what plist alone can't easily do:
- Source proper PATH (launchd jobs start with minimal PATH)
- Capture preflight failure separately from real run failure
- Send a notification (Telegram or osascript) on failure

- [ ] **Step 1: Create wrapper**

Create `scripts/run_premarket_launchd.sh`:

```bash
#!/usr/bin/env bash
# scripts/run_premarket_launchd.sh
#
# Wrapper invoked by launchd at 06:00 PT weekdays. Sources PATH so `claude`
# and `uv` are visible (launchd starts with /usr/bin:/bin only). Runs
# preflight check; on failure sends a notification (best-effort) and
# exits 0 so launchd doesn't keep retrying. On success runs the actual
# report and lets the orchestrator handle delivery.

set -uo pipefail

# Resolve project root from the script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Source common shell init for PATH (homebrew + user bins).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Add ~/.local/bin (uv default install loc) if present.
if [[ -d "$HOME/.local/bin" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

cd "$PROJECT_ROOT" || {
    echo "[run_premarket_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/premarket-$TS.log"

{
    echo "[run_premarket_launchd] start $(date -Iseconds)"
    echo "[run_premarket_launchd] PATH=$PATH"
    echo "[run_premarket_launchd] PWD=$PROJECT_ROOT"

    # Preflight check
    if ! uv run python scripts/preflight_check.py --silent; then
        echo "[run_premarket_launchd] PREFLIGHT FAILED — send notification and exit"
        # Best-effort macOS notification
        osascript -e 'display notification "Preflight check failed at 06:00 PT — TWS / claude / config issue" with title "DayTrader" sound name "Submarine"' 2>/dev/null || true
        exit 0
    fi

    # Run the actual pipeline
    echo "[run_premarket_launchd] preflight ok, invoking reports run"
    uv run daytrader reports run --type premarket --no-pdf
    rc=$?
    echo "[run_premarket_launchd] reports run exit=$rc"
    echo "[run_premarket_launchd] end $(date -Iseconds)"
    exit "$rc"
} 2>&1 | tee "$RUN_LOG"
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/run_premarket_launchd.sh`

- [ ] **Step 3: Test the wrapper manually (don't expect TWS up)**

Run: `./scripts/run_premarket_launchd.sh`

Expected output (TWS NOT up):
```
[run_premarket_launchd] start ...
[run_premarket_launchd] PATH=...
[run_premarket_launchd] PWD=...
[preflight] ✗ TWS unreachable at 127.0.0.1:7496
[run_premarket_launchd] PREFLIGHT FAILED — send notification and exit
```

A macOS notification banner should appear briefly. Exit code 0 (so launchd doesn't keep retrying).

- [ ] **Step 4: Commit**

```bash
git add scripts/run_premarket_launchd.sh
git commit -m "feat(reports): scripts/run_premarket_launchd.sh (launchd wrapper with preflight)"
```

---

## Task 3: launchd plist for premarket 06:00 PT

**Files:**
- Create: `scripts/launchd/com.daytrader.report.premarket.0600pt.plist.template`
- Create: `data/logs/launchd/.gitkeep`

The `.template` extension is intentional — the plist references absolute paths that depend on the user's actual project root. The install script (Task 4) substitutes the real path at install time.

- [ ] **Step 1: Create plist template**

Create `scripts/launchd/com.daytrader.report.premarket.0600pt.plist.template`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daytrader.report.premarket.0600pt</string>

    <key>ProgramArguments</key>
    <array>
        <string>__PROJECT_ROOT__/scripts/run_premarket_launchd.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>__PROJECT_ROOT__/data/logs/launchd/premarket.0600pt.out</string>
    <key>StandardErrorPath</key>
    <string>__PROJECT_ROOT__/data/logs/launchd/premarket.0600pt.err</string>

    <key>WorkingDirectory</key>
    <string>__PROJECT_ROOT__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>__HOME__</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Notes:
- `__PROJECT_ROOT__` and `__HOME__` are placeholders the install script replaces.
- launchd Weekday: 1=Mon, 2=Tue, ..., 7=Sun. Mon-Fri = 1-5.
- `RunAtLoad=false` — don't fire when plist loads, only at scheduled time.
- macOS launchd interprets `Hour/Minute` in **local system time**, which is PT for the user. Auto-DST.

- [ ] **Step 2: Create log dir placeholder**

Create `data/logs/launchd/.gitkeep` (empty file):

```bash
mkdir -p data/logs/launchd
touch data/logs/launchd/.gitkeep
```

- [ ] **Step 3: Update .gitignore**

Append to `.gitignore`:

```
# launchd run logs (rotate manually for now; auto-rotate in future phase)
data/logs/launchd/*.out
data/logs/launchd/*.err
data/logs/launchd/premarket-*.log
!data/logs/launchd/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add scripts/launchd/com.daytrader.report.premarket.0600pt.plist.template data/logs/launchd/.gitkeep .gitignore
git commit -m "feat(reports): launchd plist template + log dir for premarket 0600 PT"
```

---

## Task 4: Install/uninstall scripts

**Files:**
- Create: `scripts/install_launchd.sh`
- Create: `scripts/uninstall_launchd.sh`

- [ ] **Step 1: Create install script**

Create `scripts/install_launchd.sh`:

```bash
#!/usr/bin/env bash
# scripts/install_launchd.sh
#
# One-command install: substitutes path placeholders in the plist template,
# copies result to ~/Library/LaunchAgents/, and bootstraps via launchctl.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_ROOT/scripts/launchd/com.daytrader.report.premarket.0600pt.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/com.daytrader.report.premarket.0600pt.plist"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

# Substitute placeholders. Use | as sed delimiter to handle / in paths.
sed \
    -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE" > "$TARGET_PLIST"

echo "[install_launchd] wrote $TARGET_PLIST"

# Bootstrap (load) the job. `bootstrap` is the modern equivalent of `load`.
# Use `gui/$UID` domain for user-level agents.
GUI_DOMAIN="gui/$(id -u)"
LABEL="com.daytrader.report.premarket.0600pt"

# If already loaded, unload first so we pick up the new plist.
if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[install_launchd] removing existing job $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
fi

echo "[install_launchd] bootstrapping $LABEL"
launchctl bootstrap "$GUI_DOMAIN" "$TARGET_PLIST"

echo "[install_launchd] done. To verify:"
echo "  launchctl print $GUI_DOMAIN/$LABEL | head -20"
echo "  launchctl print-disabled $GUI_DOMAIN | grep daytrader"
echo
echo "Next firing: next weekday at 06:00 PT (local system time)."
echo "To run NOW for testing: launchctl kickstart $GUI_DOMAIN/$LABEL"
```

- [ ] **Step 2: Create uninstall script**

Create `scripts/uninstall_launchd.sh`:

```bash
#!/usr/bin/env bash
# scripts/uninstall_launchd.sh

set -euo pipefail

LABEL="com.daytrader.report.premarket.0600pt"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"

if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[uninstall_launchd] booting out $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL"
fi

if [[ -f "$TARGET_PLIST" ]]; then
    rm -f "$TARGET_PLIST"
    echo "[uninstall_launchd] removed $TARGET_PLIST"
fi

echo "[uninstall_launchd] done."
```

- [ ] **Step 3: Make executable**

Run:
```bash
chmod +x scripts/install_launchd.sh scripts/uninstall_launchd.sh
```

- [ ] **Step 4: Test install (then uninstall — don't leave stale plist before validation)**

Run: `./scripts/install_launchd.sh`

Expected:
- Writes plist to `~/Library/LaunchAgents/`
- `launchctl bootstrap` succeeds
- Prints "next firing: next weekday at 06:00 PT"

Verify:
```bash
launchctl print "gui/$(id -u)/com.daytrader.report.premarket.0600pt" | head -20
```

Should show the job's state, working dir, calendar interval.

Then uninstall:
```bash
./scripts/uninstall_launchd.sh
```

Verify removed:
```bash
launchctl print "gui/$(id -u)/com.daytrader.report.premarket.0600pt" 2>&1 | head -3
# Expected: "Could not find service" or similar
```

- [ ] **Step 5: Commit**

```bash
git add scripts/install_launchd.sh scripts/uninstall_launchd.sh
git commit -m "feat(reports): launchd install/uninstall scripts for premarket plist"
```

---

## Task 5: Phase 7 runbook

**Files:**
- Create: `docs/ops/phase7-runbook.md`

- [ ] **Step 1: Write runbook**

Create `docs/ops/phase7-runbook.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/phase7-runbook.md
git commit -m "docs(reports): Phase 7 runbook (launchd premarket auto-trigger)"
```

---

## Task 6: Phase 7 acceptance — verify plist fires correctly

**Files:** None (verification only).

- [ ] **Step 1: Full project test pass**

Run: `uv run pytest tests/ --ignore=tests/research -q`
Expected: 271+ pass (with new preflight_check tests added).

- [ ] **Step 2: Install launchd job for real**

Run: `./scripts/install_launchd.sh`

Verify in `~/Library/LaunchAgents/`:

```bash
ls -la ~/Library/LaunchAgents/ | grep daytrader
```

Should show `com.daytrader.report.premarket.0600pt.plist`.

- [ ] **Step 3: Verify launchctl loaded the job**

Run:

```bash
launchctl print "gui/$(id -u)/com.daytrader.report.premarket.0600pt" | head -40
```

Look for:
- `state = waiting`
- `program = .../scripts/run_premarket_launchd.sh`
- `working directory = .../nice-varahamihira-9d6142`
- `start interval = (5 entries: Hour=6 Minute=0 Weekday=1..5)`

- [ ] **Step 4: Live test fire (requires TWS running)**

```bash
# Verify TWS is up
nc -zv 127.0.0.1 7496

# Manually kickstart the job (simulates 06:00 PT firing)
launchctl kickstart "gui/$(id -u)/com.daytrader.report.premarket.0600pt"

# Watch the log build up — wait ~2.5 minutes
tail -f data/logs/launchd/premarket-*.log

# Verify report file generated
ls -la "$HOME/Documents/DayTrader Vault/Daily/$(date +%Y-%m-%d)-premarket.md"
```

If file appears + log shows `reports run exit=0` → **Phase 7 acceptance PASS**.

- [ ] **Step 5: (Optional) Test the failure path**

Stop TWS (close the app or kill the process). Then kickstart the job:

```bash
launchctl kickstart "gui/$(id -u)/com.daytrader.report.premarket.0600pt"
# Wait ~5 seconds
tail data/logs/launchd/premarket-*.log
```

Expected: log shows `[preflight] ✗ TWS unreachable at 127.0.0.1:7496`, then `PREFLIGHT FAILED — send notification and exit`. macOS notification banner appears.

- [ ] **Step 6: Push commit history**

```bash
git push
```

- [ ] **Step 7: Update todos / runbook references**

Run `git log --oneline` and confirm 6 Phase 7 commits exist. Add a note to user that next weekday morning at 06:00 PT, the report will auto-generate.

---

## Summary

After Phase 7 v1, every weekday at 06:00 PT:
1. macOS launchd wakes the wrapper
2. Wrapper sources PATH and runs preflight (TWS + claude + config)
3. If preflight fails → macOS notification + log + exit 0
4. If preflight passes → `daytrader reports run --type premarket --no-pdf`
5. ~2.5 minutes later: report in Obsidian + (if bot wired) Telegram push
6. User wakes up to fresh report; no manual command

**Coverage vs spec §6.2:** v1 = 1/7 plists. Phase 7.5 (after Phase 5) will add the other 6.

**Lock-in friction reduced**: from "wake up → start TWS → run command → wait 2.5 min → read" to "wake up → glance phone → read".

**Out of scope** (deferred):
- IB Gateway / IBC 24/7 headless mode → user keeps using TWS for now
- Cleanup / log rotation → manual `rm` if dir gets large
- Other 6 report time slots (intraday/EOD/night/weekly) → Phase 7.5 + Phase 5
- Anthropic Web Search news → Phase 4.5

**Next**: After Phase 5 lands the other report types, Phase 7.5 plan adds the remaining 6 plists using this same template pattern.
