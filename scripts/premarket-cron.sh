#!/bin/bash
# DayTrader Pre-Market Auto Report (with AI Analysis)
# Runs daily Mon-Fri before market open
# Generates data report → AI analysis → merges into final report → syncs to Obsidian

set -e

cd "/Users/tylersan/Projects/Day trading"

TODAY=$(date +%Y-%m-%d)
LOG_DIR="data/logs"
EXPORT_DIR="data/exports"
OBSIDIAN_DAILY="$HOME/Documents/DayTrader Vault/Daily"
OBSIDIAN_WEEKLY="$HOME/Documents/DayTrader Vault/Weekly"
DAYTRADER="$PWD/.venv/bin/daytrader"
CLAUDE="/opt/homebrew/bin/claude"

mkdir -p "$LOG_DIR" "$EXPORT_DIR" "$OBSIDIAN_DAILY"

LOG_FILE="$LOG_DIR/premarket-$TODAY.log"

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"; }

log "=== DayTrader Pre-Market Report ==="

# Step 1: Generate data report + AI prompt
log "Step 1: Collecting market data..."
"$DAYTRADER" pre analyze >> "$LOG_FILE" 2>&1

# Step 2: Run AI analysis via Claude Code CLI
log "Step 2: Running AI analysis..."
AI_PROMPT="$EXPORT_DIR/ai-analysis-prompt.md"
AI_OUTPUT="$EXPORT_DIR/ai-analysis-$TODAY.md"

if [ -f "$AI_PROMPT" ]; then
    "$CLAUDE" -p "$(cat "$AI_PROMPT")" --output-format text > "$AI_OUTPUT" 2>> "$LOG_FILE"
    log "AI analysis saved to $AI_OUTPUT"
else
    log "WARNING: AI prompt file not found, skipping AI analysis"
    echo "*AI analysis unavailable*" > "$AI_OUTPUT"
fi

# Step 3: Merge data report + AI analysis into final report
log "Step 3: Merging final report..."
DATA_REPORT="$EXPORT_DIR/premarket-$TODAY.md"
FINAL_REPORT="$EXPORT_DIR/premarket-final-$TODAY.md"

if [ -f "$DATA_REPORT" ] && [ -f "$AI_OUTPUT" ]; then
    cat "$DATA_REPORT" > "$FINAL_REPORT"
    echo "" >> "$FINAL_REPORT"
    echo "---" >> "$FINAL_REPORT"
    echo "## 五、AI 技术分析 & 操盘建议" >> "$FINAL_REPORT"
    echo "" >> "$FINAL_REPORT"
    cat "$AI_OUTPUT" >> "$FINAL_REPORT"

    # Sync final report to Obsidian
    cp "$FINAL_REPORT" "$OBSIDIAN_DAILY/premarket-$TODAY.md"
    log "Final report synced to Obsidian"
fi

# Step 4: Generate Pine Scripts
log "Step 4: Generating Pine Scripts..."
for sym in SPY QQQ ES=F NQ=F GC=F; do
    "$DAYTRADER" pre pine "$sym" >> "$LOG_FILE" 2>&1
done

log "=== Completed ==="
