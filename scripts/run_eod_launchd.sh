#!/usr/bin/env bash
# scripts/run_eod_launchd.sh
#
# Wrapper invoked by launchd at 14:00 PT weekdays. Mirrors run_premarket_launchd.sh
# pattern: source PATH → run preflight (real API handshake) → daytrader reports
# run --type eod --no-pdf.

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
    echo "[run_eod_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/eod-$TS.log"

# Tee both stdout and stderr to the run log without using a pipe block —
# this way `exit "$rc"` propagates the actual exit code to launchd.
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_eod_launchd] start $(date -Iseconds)"
echo "[run_eod_launchd] PATH=$PATH"
echo "[run_eod_launchd] PWD=$PROJECT_ROOT"

# Preflight check
if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_eod_launchd] PREFLIGHT FAILED — send notification and exit"
    # Best-effort macOS notification
    osascript -e 'display notification "EOD preflight failed at 14:00 PT — TWS / claude / config issue" with title "DayTrader EOD" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

# Run the actual pipeline
echo "[run_eod_launchd] preflight ok, invoking reports run --type eod"
uv run daytrader reports run --type eod --no-pdf
rc=$?
echo "[run_eod_launchd] reports run exit=$rc"
echo "[run_eod_launchd] end $(date -Iseconds)"
exit "$rc"
