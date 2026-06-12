#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# VOX ALERT PIPELINE — Unified: Live Prices → Council → Alerts → Telegram
# Replaces 6 redundant cron jobs with single event-driven flow
# ═══════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$HOME/.hermes/scripts"
LOG_FILE="$SCRIPT_DIR/.vox_pipeline.log"

echo "══════════════════════════════════════════════════════════" >> "$LOG_FILE"
echo "VOX Alert Pipeline — $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
echo "══════════════════════════════════════════════════════════" >> "$LOG_FILE"

# Step 1: Fetch live prices
echo "[1/6] Fetching live prices..." | tee -a "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 vox_live_prices.py >> "$LOG_FILE" 2>&1

# Step 2: Run data collection (volume, X, Reddit, news, sentiment)
echo "[2/6] Collecting market signals..." | tee -a "$LOG_FILE"
python3 vox_volume_scanner.py quick >> "$LOG_FILE" 2>&1 || true
python3 vox_x_momentum.py >> "$LOG_FILE" 2>&1 || true
python3 vox_reddit_tracker.py --scan --limit 20 >> "$LOG_FILE" 2>&1 || true
python3 vox_news_digest.py >> "$LOG_FILE" 2>&1 || true
python3 vox_sentiment_tracker.py >> "$LOG_FILE" 2>&1 || true

# Step 3: Run council voting (feeds real signals into alerts)
echo "[3/6] Running council votes..." | tee -a "$LOG_FILE"
python3 vox_council.py --batch >> "$LOG_FILE" 2>&1

# Step 4: Harness feed (composite scores)
echo "[4/6] Generating harness scores..." | tee -a "$LOG_FILE"
python3 vox_harness_feed.py >> "$LOG_FILE" 2>&1

# Step 5: Intelligence report
echo "[5/6] Generating intelligence report..." | tee -a "$LOG_FILE"
python3 vox_intelligence_report.py >> "$LOG_FILE" 2>&1 || true

# Step 6: Check alerts
echo "[6/6] Checking alerts..." | tee -a "$LOG_FILE"
python3 vox_smart_alerts_v5.py >> "$LOG_FILE" 2>&1

echo "" | tee -a "$LOG_FILE"
echo "✅ PIPELINE COMPLETE: $(date)" | tee -a "$LOG_FILE"
echo "   Log: $LOG_FILE" | tee -a "$LOG_FILE"
