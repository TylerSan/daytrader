#!/usr/bin/env bash
# scripts/install_intraday_4h_launchd.sh — Phase 5.5 T14
# Installs both intraday-4h-1 and intraday-4h-2 launchd jobs.
# Idempotent: existing jobs are bootout'd first, then re-installed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCHAGENTS"

UID_NUM="$(id -u)"

for cadence in "intraday-4h-1.0700pt" "intraday-4h-2.1100pt"; do
    LABEL="com.daytrader.report.${cadence}"
    TEMPLATE="$SCRIPT_DIR/launchd/${LABEL}.plist.template"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "[install_intraday_4h] missing template: $TEMPLATE" >&2
        exit 1
    fi

    # Bootout existing if loaded (ignore errors — may not be loaded)
    if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
        echo "[install_intraday_4h] bootout existing $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    fi

    # Render template — substitute {{PROJECT_ROOT}} and {{HOME}}
    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{HOME}}|$HOME|g" \
        "$TEMPLATE" > "$DEST"

    echo "[install_intraday_4h] bootstrap $LABEL → $DEST"
    launchctl bootstrap "gui/$UID_NUM" "$DEST"
done

echo "[install_intraday_4h] DONE — verify with: launchctl list | grep intraday-4h"
launchctl list | grep -E "intraday-4h" || echo "(none loaded — check above for errors)"
