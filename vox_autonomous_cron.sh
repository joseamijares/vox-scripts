#!/bin/bash
# VOX Autonomous Cron - Runs every 30 min during market hours
# Makes VOX truly agentic: proactive, continuous, autonomous

cd /Users/jos/.hermes/scripts

# Log
LOG_FILE="/tmp/vox_autonomous.log"
echo "[$(date)] VOX Autonomous Cycle" >> "$LOG_FILE"

# 1. Update market data
python3 vox_live_prices.py >> "$LOG_FILE" 2>&1

# 2. Run agent council on portfolio
python3 vox_council.py --batch >> "$LOG_FILE" 2>&1

# 3. Generate insights
python3 vox_insights_generator.py dashboard >> "$LOG_FILE" 2>&1

# 4. Run orchestrator
python3 vox_orchestrator.py run >> "$LOG_FILE" 2>&1

# 5. Update dashboard data
cp vox_insights.json ~/dev/vox-dashboard/public/ 2>/dev/null
cp vox_council_votes.json ~/dev/vox-dashboard/public/ 2>/dev/null
cp vox_technical_analysis.json ~/dev/vox-dashboard/public/ 2>/dev/null
cp vox_market_regime.json ~/dev/vox-dashboard/public/ 2>/dev/null

echo "[$(date)] Cycle complete" >> "$LOG_FILE"
