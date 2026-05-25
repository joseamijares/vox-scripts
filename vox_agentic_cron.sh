#!/bin/bash
# VOX Agentic Cron — Self-updating, self-learning, autonomous system
# Runs every 15 minutes via cron

set -e
SCRIPT_DIR="$HOME/.hermes/scripts"
LOG_FILE="$SCRIPT_DIR/vox_agentic.log"
DASHBOARD_DIR="$HOME/dev/vox-dashboard"

echo "=== VOX Agentic Run $(date) ===" >> "$LOG_FILE"

# 1. Update portfolio data
echo "[1/6] Updating portfolio..." >> "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 vox_portfolio_scan.py 2>> "$LOG_FILE" || true

# 2. Run AI Harness to generate new plays
echo "[2/6] Running AI Harness..." >> "$LOG_FILE"
python3 vox_ai_harness.py --plays --output vox_generated_plays.json 2>> "$LOG_FILE" || true

# 3. Run Signal Enhancer on top positions
echo "[3/6] Enhancing signals..." >> "$LOG_FILE"
python3 vox_signal_enhancer.py --scan --top 20 --output vox_enhanced_signals.json 2>> "$LOG_FILE" || true

# 4. Run Self-Upgrade analysis
echo "[4/6] Self-upgrade analysis..." >> "$LOG_FILE"
python3 vox_self_upgrade.py --report --output vox_upgrade_report.txt 2>> "$LOG_FILE" || true

# 5. Send Telegram alerts for high-confidence plays
echo "[5/6] Sending alerts..." >> "$LOG_FILE"
python3 vox_telegram_alerts.py --plays --min-confidence 50 2>> "$LOG_FILE" || true

# 6. Rebuild and deploy dashboard if plays changed
if [ -f "$SCRIPT_DIR/vox_generated_plays.json" ]; then
    echo "[6/6] Syncing dashboard..." >> "$LOG_FILE"
    cp "$SCRIPT_DIR/vox_generated_plays.json" "$DASHBOARD_DIR/public/"
    cp "$SCRIPT_DIR/vox_enhanced_signals.json" "$DASHBOARD_DIR/public/" 2>/dev/null || true
    cp "$SCRIPT_DIR/vox_daily_brief.json" "$DASHBOARD_DIR/public/" 2>/dev/null || true
    
    cd "$DASHBOARD_DIR"
    npm run build 2>> "$LOG_FILE" && vercel --prod --force 2>> "$LOG_FILE" || true
fi

echo "=== Done $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
