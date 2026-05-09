#!/usr/bin/env bash
# scripts/install_eod_launchd.sh
#
# One-command install: substitutes path placeholders in the plist template,
# copies result to ~/Library/LaunchAgents/, and bootstraps via launchctl.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_ROOT/scripts/launchd/com.daytrader.report.eod.1400pt.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/com.daytrader.report.eod.1400pt.plist"

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

echo "[install_eod_launchd] wrote $TARGET_PLIST"

# Defensively chmod +x the wrapper
chmod +x "$PROJECT_ROOT/scripts/run_eod_launchd.sh"

# Bootstrap (load) the job. `bootstrap` is the modern equivalent of `load`.
# Use `gui/$UID` domain for user-level agents.
GUI_DOMAIN="gui/$(id -u)"
LABEL="com.daytrader.report.eod.1400pt"

# If already loaded, unload first so we pick up the new plist.
if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "[install_eod_launchd] removing existing job $LABEL"
    launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
fi

echo "[install_eod_launchd] bootstrapping $LABEL"
launchctl bootstrap "$GUI_DOMAIN" "$TARGET_PLIST"

echo "[install_eod_launchd] done. Next firing: next weekday at 14:00 PT."
echo "Test fire: launchctl kickstart $GUI_DOMAIN/$LABEL"
