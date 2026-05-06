#!/usr/bin/env bash
# scripts/run_asia_launchd.sh — Phase 5.5 T12 (2026-05-05)
#
# launchd wrapper for asia cadence (23:00 PT Mon-Fri).
# Mirrors run_eod_launchd.sh pattern.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_asia_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/asia-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_asia_launchd] start $(date -Iseconds)"
echo "[run_asia_launchd] PATH=$PATH"
echo "[run_asia_launchd] PWD=$PROJECT_ROOT"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_asia_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "asia preflight failed at 23:00 PT" with title "DayTrader Asia" sound name "Submarine"' 2>/dev/null || true
    exit 0
fi

echo "[run_asia_launchd] preflight ok, invoking reports run --type asia"
uv run daytrader reports run --type asia --no-pdf
rc=$?
echo "[run_asia_launchd] reports run exit=$rc"
echo "[run_asia_launchd] end $(date -Iseconds)"
exit "$rc"
