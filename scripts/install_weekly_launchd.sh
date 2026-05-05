#!/usr/bin/env bash
# scripts/install_weekly_launchd.sh
#
# One-command install for the WEEKLY plist (Sunday 14:00 PT).
# Substitutes path placeholders in the plist template, copies result
# to ~/Library/LaunchAgents/, and bootstraps via launchctl.
#
# This is the weekly counterpart of scripts/install_launchd.sh
# (which handles the premarket plist). Same wrapper/plist pattern,
# different label + schedule + invoked command.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_ROOT/scripts/launchd/com.daytrader.report.weekly.sun1400pt.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/com.daytrader.report.weekly.sun1400pt.plist"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

# Substitute placeholders. Use | as sed delimiter to handle / in paths.
sed \
    -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE" > "$TARGET_PLIST"

echo "[install_weekly_launchd] wrote $TARGET_PLIST"

# Bootstrap (load) the job. `bootstrap` is the modern equivalent of `load`.
GUI_DOMAIN="gui/$(id -u)"
LABEL="com.daytrader.report.weekly.sun1400pt"

# If already loaded, unload first so we pick up the new plist.
if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[install_weekly_launchd] removing existing job $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
fi

echo "[install_weekly_launchd] bootstrapping $LABEL"
launchctl bootstrap "$GUI_DOMAIN" "$TARGET_PLIST"

echo "[install_weekly_launchd] done. To verify:"
echo "  launchctl print $GUI_DOMAIN/$LABEL | head -20"
echo "  launchctl print-disabled $GUI_DOMAIN | grep daytrader"
echo
echo "Next firing: next Sunday at 14:00 PT (local system time)."
echo "To run NOW for testing: launchctl kickstart $GUI_DOMAIN/$LABEL"
