#!/usr/bin/env bash
# scripts/uninstall_weekly_launchd.sh
#
# Counterpart of install_weekly_launchd.sh — boot out the weekly job
# and remove the plist file. Idempotent: safe to run when nothing
# is loaded.

set -euo pipefail

LABEL="com.daytrader.report.weekly.sun1400pt"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"

if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[uninstall_weekly_launchd] booting out $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL"
fi

if [[ -f "$TARGET_PLIST" ]]; then
    rm -f "$TARGET_PLIST"
    echo "[uninstall_weekly_launchd] removed $TARGET_PLIST"
fi

echo "[uninstall_weekly_launchd] done."
