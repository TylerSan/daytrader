#!/bin/bash
# DayTrader Weekly Plan Auto Report (with AI Analysis)
# Runs every Sunday before futures open (17:00 ET / 14:00 PDT)

set -e

cd "/Users/tylersan/Projects/Day trading"

TODAY=$(date +%Y-%m-%d)
LOG_DIR="data/logs"
EXPORT_DIR="data/exports"
OBSIDIAN_WEEKLY="$HOME/Documents/DayTrader Vault/Weekly"
DAYTRADER="$PWD/.venv/bin/daytrader"
CLAUDE="/opt/homebrew/bin/claude"

mkdir -p "$LOG_DIR" "$EXPORT_DIR" "$OBSIDIAN_WEEKLY"

LOG_FILE="$LOG_DIR/weekly-$TODAY.log"

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"; }

log "=== DayTrader Weekly Plan ==="

# Step 1: Generate data report + AI prompt
log "Step 1: Collecting market data..."
"$DAYTRADER" weekly analyze >> "$LOG_FILE" 2>&1

# Step 2: Run AI analysis via Claude Code CLI
log "Step 2: Running AI weekly analysis..."
AI_PROMPT="$EXPORT_DIR/weekly-ai-prompt.md"
AI_OUTPUT="$EXPORT_DIR/weekly-ai-analysis-$TODAY.md"

if [ -f "$AI_PROMPT" ]; then
    "$CLAUDE" -p "$(cat "$AI_PROMPT")" --output-format text > "$AI_OUTPUT" 2>> "$LOG_FILE"
    log "AI weekly analysis saved to $AI_OUTPUT"
else
    log "WARNING: AI prompt file not found, skipping AI analysis"
    echo "*AI analysis unavailable*" > "$AI_OUTPUT"
fi

# Step 3: Merge data report + AI analysis into final report
log "Step 3: Merging final weekly report..."
DATA_REPORT="$EXPORT_DIR/weekly-$TODAY.md"
FINAL_REPORT="$EXPORT_DIR/weekly-final-$TODAY.md"

if [ -f "$DATA_REPORT" ] && [ -f "$AI_OUTPUT" ]; then
    cat "$DATA_REPORT" > "$FINAL_REPORT"
    echo "" >> "$FINAL_REPORT"
    echo "---" >> "$FINAL_REPORT"
    echo "## AI 周度分析 & 交易计划" >> "$FINAL_REPORT"
    echo "" >> "$FINAL_REPORT"
    cat "$AI_OUTPUT" >> "$FINAL_REPORT"

    # Sync final report to Obsidian
    cp "$FINAL_REPORT" "$OBSIDIAN_WEEKLY/weekly-$TODAY.md"
    log "Final weekly report synced to Obsidian"
fi

# Note: Info-card images are generated automatically by 'weekly analyze' in Step 1
# and synced to Obsidian (including images/ subfolder) by the Python code.

log "=== Completed ==="
