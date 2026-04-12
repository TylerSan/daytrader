#!/bin/bash
# DayTrader Pre-Market Auto Report (with AI Analysis)
# Runs daily Mon-Fri before market open
# Uses 'daytrader pre run --ai' for the full pipeline:
#   data collection → card generation → news translation → AI analysis → Obsidian sync

set -e

cd "/Users/tylersan/Projects/Day trading"

# Ensure Homebrew binaries (node, claude) are in PATH for cron environment
export PATH="/opt/homebrew/bin:$PATH"

TODAY=$(date +%Y-%m-%d)
LOG_DIR="data/logs"
EXPORT_DIR="data/exports"
DAYTRADER="$PWD/.venv/bin/daytrader"

mkdir -p "$LOG_DIR" "$EXPORT_DIR"

LOG_FILE="$LOG_DIR/premarket-$TODAY.log"

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"; }

log "=== DayTrader Pre-Market Report ==="

# Step 1: Full pipeline — data + cards + news translation + AI analysis + Obsidian sync
log "Running full pre-market analysis with AI..."
"$DAYTRADER" pre run --ai >> "$LOG_FILE" 2>&1

log "Pre-market report generated and synced to Obsidian"

# Step 2: Generate Pine Scripts for TradingView
log "Generating Pine Scripts..."
for sym in SPY QQQ ES=F NQ=F GC=F; do
    "$DAYTRADER" pre pine "$sym" >> "$LOG_FILE" 2>&1
done

log "=== Completed ==="
