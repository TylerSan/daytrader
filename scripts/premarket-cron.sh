#!/bin/bash
# DayTrader Pre-Market Auto Report
# Runs daily before market open, generates report and syncs to Obsidian

cd "/Users/tylersan/Projects/Day trading"

LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/premarket-$(date +%Y-%m-%d).log"

echo "=== DayTrader Pre-Market Report ===" >> "$LOG_FILE"
echo "Started at: $(date)" >> "$LOG_FILE"

# Generate pre-market report (auto-saves to exports + Obsidian)
/Users/tylersan/Projects/Day\ trading/.venv/bin/daytrader pre run >> "$LOG_FILE" 2>&1

# Generate AI analysis prompt
/Users/tylersan/Projects/Day\ trading/.venv/bin/daytrader pre analyze >> "$LOG_FILE" 2>&1

# Generate Pine Scripts for key instruments
for sym in SPY QQQ ES=F NQ=F GC=F; do
    /Users/tylersan/Projects/Day\ trading/.venv/bin/daytrader pre pine "$sym" >> "$LOG_FILE" 2>&1
done

echo "Completed at: $(date)" >> "$LOG_FILE"
echo "==================================" >> "$LOG_FILE"
