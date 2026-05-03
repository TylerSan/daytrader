#!/usr/bin/env bash
# scripts/run_weekly_launchd.sh
#
# Wrapper invoked by launchd at 14:00 PT on Sundays. Sources PATH so
# `claude` and `uv` are visible (launchd starts with /usr/bin:/bin only).
# Runs preflight check; on failure sends a notification (best-effort)
# and exits 0 so launchd doesn't keep retrying. On success runs the
# weekly plan generator (old `daytrader weekly run --ai` system, which
# is the live working weekly pipeline; new `reports run --type weekly`
# is a Phase 5 stub).
#
# When Phase 5 lands the new weekly path, swap the invocation to:
#   uv run daytrader reports run --type weekly --no-pdf
# without touching the plist or install scripts.

# NOTE: -e is deliberately NOT set. We want preflight failure to be
# handled (notification + clean exit 0) rather than tripping ERR exit.
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
    echo "[run_weekly_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/weekly-$TS.log"

# Tee both stdout and stderr to the run log without using a pipe block —
# this way `exit "$rc"` propagates the actual exit code to launchd.
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_weekly_launchd] start $(date -Iseconds)"
echo "[run_weekly_launchd] PATH=$PATH"
echo "[run_weekly_launchd] PWD=$PROJECT_ROOT"

# Preflight check (TWS port + claude CLI + config files)
if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_weekly_launchd] PREFLIGHT FAILED — send notification and exit"
    osascript -e 'display notification "Weekly preflight failed at Sunday 14:00 PT — TWS / claude / config issue" with title "DayTrader Weekly" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

# Run the weekly plan generator (old system; ~2-3 min with --ai).
echo "[run_weekly_launchd] preflight ok, invoking weekly run --ai"
uv run daytrader weekly run --ai
rc=$?
echo "[run_weekly_launchd] weekly run exit=$rc"
echo "[run_weekly_launchd] end $(date -Iseconds)"
exit "$rc"
