#!/usr/bin/env bash
# scripts/run_intraday_4h_1_launchd.sh — Phase 5.5 T12 (2026-05-05)
#
# launchd wrapper for intraday-4h-1 cadence (07:00 PT Mon-Fri).
# Mirrors run_eod_launchd.sh pattern.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
cd "$PROJECT_ROOT" || {
    echo "[run_intraday_4h_1_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/intraday-4h-1-$TS.log"
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_intraday_4h_1_launchd] start $(date -Iseconds)"
echo "[run_intraday_4h_1_launchd] PATH=$PATH"
echo "[run_intraday_4h_1_launchd] PWD=$PROJECT_ROOT"

if ! uv run python scripts/preflight_check.py --silent; then
    echo "[run_intraday_4h_1_launchd] PREFLIGHT FAILED — notify and exit 0"
    osascript -e 'display notification "intraday-4h-1 preflight failed at 07:00 PT" with title "DayTrader 4H-1" sound name "Submarine"' 2>/dev/null || true
    # Telegram notification (preflight-failure escalation, 2026-05-07)
    uv run python "$PROJECT_ROOT/scripts/notify_preflight_failure.py" "intraday-4h-1" "07:00 PT" 2>/dev/null || true
    exit 0
fi

echo "[run_intraday_4h_1_launchd] preflight ok, invoking reports run --type intraday-4h-1"
uv run daytrader reports run --type intraday-4h-1 --no-pdf
rc=$?
echo "[run_intraday_4h_1_launchd] reports run exit=$rc"
echo "[run_intraday_4h_1_launchd] end $(date -Iseconds)"
exit "$rc"
