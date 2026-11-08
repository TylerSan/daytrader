#!/usr/bin/env bash
# scripts/run_premarket_launchd.sh
#
# Wrapper invoked by launchd at 06:00 PT weekdays. Sources PATH so `claude`
# and `uv` are visible (launchd starts with /usr/bin:/bin only). Runs
# preflight check; on failure sends a notification (best-effort) and
# exits 0 so launchd doesn't keep retrying. On success runs the actual
# report and lets the orchestrator handle delivery.
#
# Preflight degrade (2026-10-29): if preflight fails ONLY on TWS (port /
# API handshake), the report is generated from yfinance instead
# (`reports run --source yfinance`, delayed ~15 min, no OI / contract chain)
# and the notifier is called with --degraded. claude/config/unknown preflight
# failures keep the old path: notify and exit 0.

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
    echo "[run_premarket_launchd] cannot cd to $PROJECT_ROOT" >&2
    exit 0
}

LOG_DIR="$PROJECT_ROOT/data/logs/launchd"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/premarket-$TS.log"

# Tee both stdout and stderr to the run log without using a pipe block —
# this way `exit "$rc"` propagates the actual exit code to launchd.
exec > >(tee "$RUN_LOG") 2>&1

echo "[run_premarket_launchd] start $(date -Iseconds)"
echo "[run_premarket_launchd] PATH=$PATH"
echo "[run_premarket_launchd] PWD=$PROJECT_ROOT"

# Preflight check. stderr is captured so a TWS-only failure (degrade to
# yfinance) can be told apart from a claude/config failure (notify + exit 0);
# it is replayed to stderr so the `[preflight] ✗ ...` lines stay in the run log.
PREFLIGHT_ERR="$(mktemp)"
uv run python scripts/preflight_check.py --silent 2>"$PREFLIGHT_ERR"
prc=$?
cat "$PREFLIGHT_ERR" >&2

if [[ "$prc" -ne 0 ]]; then
    if grep -qE 'claude CLI not found|LLM API|config:' "$PREFLIGHT_ERR"; then
        pf_kind="fatal"
    elif grep -q 'TWS' "$PREFLIGHT_ERR"; then
        pf_kind="tws"
    else
        pf_kind="fatal"
    fi
    rm -f "$PREFLIGHT_ERR"

    if [[ "$pf_kind" == "tws" ]]; then
        echo "[run_premarket_launchd] PREFLIGHT FAILED (TWS only) — degrading to --source yfinance"
        osascript -e 'display notification "premarket at 06:00 PT: TWS unreachable — yfinance fallback report" with title "DayTrader" sound name "Submarine"' 2>/dev/null || true
        uv run python "$PROJECT_ROOT/scripts/notify_preflight_failure.py" "premarket" "06:00 PT" --degraded 2>/dev/null || true
        uv run daytrader reports run --type premarket --no-pdf --source yfinance
        rc=$?
        echo "[run_premarket_launchd] reports run exit=$rc"
        echo "[run_premarket_launchd] end $(date -Iseconds)"
        exit "$rc"
    fi

    echo "[run_premarket_launchd] PREFLIGHT FAILED — send notification and exit"
    # Best-effort macOS notification
    osascript -e 'display notification "Preflight check failed at 06:00 PT — TWS / claude / config issue" with title "DayTrader" sound name "Submarine"' 2>/dev/null || true
    # Telegram notification (preflight-failure escalation, 2026-05-07)
    uv run python "$PROJECT_ROOT/scripts/notify_preflight_failure.py" "premarket" "06:00 PT" 2>/dev/null || true
    exit 0
fi
rm -f "$PREFLIGHT_ERR"

# Run the actual pipeline
echo "[run_premarket_launchd] preflight ok, invoking reports run"
uv run daytrader reports run --type premarket --no-pdf
rc=$?
echo "[run_premarket_launchd] reports run exit=$rc"
echo "[run_premarket_launchd] end $(date -Iseconds)"
exit "$rc"
