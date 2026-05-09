#!/usr/bin/env bash
# scripts/uninstall_intraday_4h_launchd.sh — Phase 5.5 T14

set -euo pipefail

LAUNCHAGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

for cadence in "intraday-4h-1.0700pt" "intraday-4h-2.1100pt"; do
    LABEL="com.daytrader.report.${cadence}"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ -f "$DEST" ]]; then
        echo "[uninstall_intraday_4h] bootout + rm $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
        rm -v "$DEST"
    else
        echo "[uninstall_intraday_4h] $LABEL plist not found, skipping"
    fi
done

echo "[uninstall_intraday_4h] DONE"
