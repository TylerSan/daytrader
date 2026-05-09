#!/usr/bin/env bash
# scripts/uninstall_night_asia_launchd.sh — Phase 5.5 T14

set -euo pipefail

LAUNCHAGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

for cadence in "night.1900pt" "asia.2300pt"; do
    LABEL="com.daytrader.report.${cadence}"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ -f "$DEST" ]]; then
        echo "[uninstall_night_asia] bootout + rm $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
        rm -v "$DEST"
    else
        echo "[uninstall_night_asia] $LABEL plist not found, skipping"
    fi
done

echo "[uninstall_night_asia] DONE"
