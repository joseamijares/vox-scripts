#!/bin/bash
# VOX AI Pipeline — Run all AI layers sequentially
# Add to crontab for autonomous operation

set -e

SCRIPT_DIR="$HOME/.hermes/scripts"
LOG_FILE="$SCRIPT_DIR/logs/vox_ai_pipeline.log"

mkdir -p "$SCRIPT_DIR/logs"

echo "=== VOX AI Pipeline Started: $(date) ===" >> "$LOG_FILE"

# 1. Update portfolio data
echo "[1/5] Updating portfolio data..." >> "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 build_portfolio_tracker.py >> "$LOG_FILE" 2>&1 || true

# 2. Run grades on top positions
echo "[2/5] Running grade system..." >> "$LOG_FILE"
python3 grade_system.py NVDA >> "$LOG_FILE" 2>&1 || true
python3 grade_system.py TSLA >> "$LOG_FILE" 2>&1 || true
python3 grade_system.py BTC >> "$LOG_FILE" 2>&1 || true

# 3. Run AI Harness — generate plays
echo "[3/5] Running AI Harness..." >> "$LOG_FILE"
python3 vox_ai_harness.py --plays --output "$SCRIPT_DIR/vox_generated_plays.json" >> "$LOG_FILE" 2>&1 || true

# 4. Run Autonomous Agent — daily brief
echo "[4/5] Generating daily brief..." >> "$LOG_FILE"
python3 vox_autonomous_agent.py --mode daily >> "$LOG_FILE" 2>&1 || true

# 5. Run RAG index update (weekly)
echo "[5/5] Checking RAG index..." >> "$LOG_FILE"
if [ ! -d "$SCRIPT_DIR/vox_chroma_db" ]; then
    echo "Building RAG index..." >> "$LOG_FILE"
    python3 vox_rag_system.py init >> "$LOG_FILE" 2>&1 || true
fi

echo "=== VOX AI Pipeline Complete: $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
