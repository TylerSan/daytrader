#!/bin/bash
# DayTrader Weekly Plan Auto Report (with AI Analysis)
# Runs every Sunday before futures open (17:00 ET / 14:00 PDT)
# Uses 'daytrader weekly run --ai' for the full pipeline:
#   data collection → card generation → news translation → AI analysis → Obsidian sync

set -e

cd "/Users/tylersan/Projects/Day trading"

# Ensure Homebrew binaries (node, claude) are in PATH for cron environment
export PATH="/opt/homebrew/bin:$PATH"

TODAY=$(date +%Y-%m-%d)
LOG_DIR="data/logs"
EXPORT_DIR="data/exports"
OBSIDIAN_WEEKLY="$HOME/Documents/DayTrader Vault/Weekly"
DAYTRADER="$PWD/.venv/bin/daytrader"

mkdir -p "$LOG_DIR" "$EXPORT_DIR" "$OBSIDIAN_WEEKLY"

LOG_FILE="$LOG_DIR/weekly-$TODAY.log"

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"; }

log "=== DayTrader Weekly Plan ==="

# Single-step: data + cards + news translation + AI analysis + Obsidian sync
log "Running full weekly analysis with AI..."
"$DAYTRADER" weekly run --ai >> "$LOG_FILE" 2>&1

log "Weekly report generated and synced to Obsidian"
log "=== Completed ==="
