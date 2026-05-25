#!/bin/bash
# VOX Agentic Cron — Silent background operations
# Runs every 15 minutes but ONLY alerts on actionable events

set -e
SCRIPT_DIR="$HOME/.hermes/scripts"
LOG_FILE="$SCRIPT_DIR/vox_agentic.log"
DASHBOARD_DIR="$HOME/dev/vox-dashboard"

# Timestamp
echo "=== $(date) ===" >> "$LOG_FILE"

# 1. Update portfolio data (silent)
python3 "$SCRIPT_DIR/vox_portfolio_scanner.py" --output "$SCRIPT_DIR/dashboard_positions.json" >> "$LOG_FILE" 2>&1 || true

# 2. Run AI harness (silent)
python3 "$SCRIPT_DIR/vox_ai_harness.py" --scan >> "$LOG_FILE" 2>&1 || true

# 3. Run signal enhancer (silent)
python3 "$SCRIPT_DIR/vox_signal_enhancer.py" --scan --output "$SCRIPT_DIR/vox_enhanced_signals.json" >> "$LOG_FILE" 2>&1 || true

# 4. Self-upgrade analysis (silent)
python3 "$SCRIPT_DIR/vox_self_upgrade.py" --report >> "$LOG_FILE" 2>&1 || true

# 5. Check for HIGH-CONFIDENCE plays only (>70%)
python3 "$SCRIPT_DIR/vox_telegram_alerts.py" --plays --min-confidence 70 >> "$LOG_FILE" 2>&1 || true

# 6. Check for grade changes (significant only)
python3 "$SCRIPT_DIR/vox_telegram_alerts.py" --grades --min-change 15 >> "$LOG_FILE" 2>&1 || true

# 7. Only redeploy if plays changed AND it's high confidence
if [ -f "$SCRIPT_DIR/vox_generated_plays.json" ]; then
    # Check if any play has confidence >= 70
    HAS_HIGH_CONF=$(python3 -c "import json; d=json.load(open('$SCRIPT_DIR/vox_generated_plays.json')); print('YES' if any(p.get('confidence',0)>=70 for p in d) else 'NO')" 2>/dev/null || echo "NO")
    
    if [ "$HAS_HIGH_CONF" = "YES" ]; then
        echo "High-confidence plays detected — redeploying dashboard" >> "$LOG_FILE"
        cd "$DASHBOARD_DIR" && npm run build >> "$LOG_FILE" 2>&1 && vercel --prod --force >> "$LOG_FILE" 2>&1 || true
        
        # Send ONE alert about the deployment
        python3 "$SCRIPT_DIR/vox_telegram_alerts.py" --alert "INFO" "🚀 Dashboard redeployed with new high-confidence plays" >> "$LOG_FILE" 2>&1 || true
    fi
fi

echo "Done" >> "$LOG_FILE"
