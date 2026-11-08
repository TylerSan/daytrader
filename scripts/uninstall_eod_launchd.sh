#!/usr/bin/env bash
# scripts/uninstall_eod_launchd.sh

set -euo pipefail

LABEL="com.daytrader.report.eod.1400pt"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"

if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[uninstall_eod_launchd] booting out $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL"
fi

if [[ -f "$TARGET_PLIST" ]]; then
    rm -f "$TARGET_PLIST"
    echo "[uninstall_eod_launchd] removed $TARGET_PLIST"
fi

echo "[uninstall_eod_launchd] done."
