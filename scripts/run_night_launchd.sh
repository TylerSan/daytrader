#!/usr/bin/env bash
# scripts/run_night_launchd.sh — Phase 5.5 T12 (2026-05-05)
#
# launchd wrapper for night cadence (19:00 PT Mon-Fri).
# Mirrors run_eod_launchd.sh pattern.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_night_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/night-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_night_launchd] start $(date -Iseconds)"
echo "[run_night_launchd] PATH=$PATH"
echo "[run_night_launchd] PWD=$PROJECT_ROOT"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_night_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "night preflight failed at 19:00 PT" with title "DayTrader Night" sound name "Submarine"' 2>/dev/null || true
    # Telegram notification (preflight-failure escalation, 2026-05-07)
    uv run python "$PROJECT_ROOT/scripts/notify_preflight_failure.py" "night" "19:00 PT" 2>/dev/null || true
    exit 0
fi

echo "[run_night_launchd] preflight ok, invoking reports run --type night"
uv run daytrader reports run --type night --no-pdf
rc=$?
echo "[run_night_launchd] reports run exit=$rc"
echo "[run_night_launchd] end $(date -Iseconds)"
exit "$rc"
