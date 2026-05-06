#!/usr/bin/env bash
# scripts/install_night_asia_launchd.sh — Phase 5.5 T14
# Installs both night and asia launchd jobs.
# Idempotent: existing jobs are bootout'd first, then re-installed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCHAGENTS"

UID_NUM="$(id -u)"

for cadence in "night.1900pt" "asia.2300pt"; do
    LABEL="com.daytrader.report.${cadence}"
    TEMPLATE="$SCRIPT_DIR/launchd/${LABEL}.plist.template"
    DEST="$LAUNCHAGENTS/${LABEL}.plist"

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "[install_night_asia] missing template: $TEMPLATE" >&2
        exit 1
    fi

    # Bootout existing if loaded (ignore errors — may not be loaded)
    if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
        echo "[install_night_asia] bootout existing $LABEL"
        launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
    fi

    # Render template — substitute {{PROJECT_ROOT}} and {{HOME}}
    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{HOME}}|$HOME|g" \
        "$TEMPLATE" > "$DEST"

    echo "[install_night_asia] bootstrap $LABEL → $DEST"
    launchctl bootstrap "gui/$UID_NUM" "$DEST"
done

echo "[install_night_asia] DONE — verify with: launchctl list | grep -E 'night|asia'"
launchctl list | grep -E "night|asia" || echo "(none loaded — check above for errors)"
