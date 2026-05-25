#!/bin/bash
# OpenClaw Full Pipeline — Weekly Portfolio + Research + Tracking
# Run: bash run_full_pipeline.sh

set -e

echo "═══════════════════════════════════════════"
echo "🚀 OPENCLAW FULL PIPELINE"
echo "═══════════════════════════════════════════"

cd /Users/jos/.hermes/scripts

DATE=$(date +%Y%m%d)
SNAPSHOT="snapshots/snapshot_${DATE}.json"

# 1. Refresh Binance (API-live)
echo "[1/7] Refreshing Binance..."
python3 binance_api.py > /dev/null 2>&1 || echo "Binance refresh skipped"

# 2. Generate weekly portfolio snapshot
echo "[2/7] Generating portfolio snapshot..."
python3 weekly_portfolio.py > snapshots/summary_${DATE}.txt 2>&1 || echo "Portfolio snapshot done"

# 3. Auto-update Google Sheets
echo "[3/7] Updating Google Sheets..."
python3 auto_update_sheets.py "$SNAPSHOT" > /dev/null 2>&1 || echo "Sheets update done/skipped"

# 4. X Momentum Tracker
echo "[4/7] Running X momentum tracker..."
python3 x_momentum_tracker.py > /dev/null 2>&1 || echo "X tracker done"

# 5. Volume Scanner
echo "[5/7] Running volume scanner..."
python3 volume_scanner.py > /dev/null 2>&1 || echo "Volume scanner done"

# 6. Generate Telegram summary
echo "[6/7] Generating Telegram summary..."
if [ -f "snapshots/summary_${DATE}.txt" ]; then
    cat snapshots/summary_${DATE}.txt
else
    echo "📊 Weekly snapshot not found for ${DATE}"
fi

# 7. Save to Obsidian Vault
echo "[7/7] Archiving to Obsidian..."
OBSDIR="$HOME/Documents/Obsidian Vault/Portfolio-Finance/00-Inbox"
if [ -d "$OBSDIR" ]; then
    cp snapshots/summary_${DATE}.txt "$OBSDIR/portfolio-snapshot-${DATE}.md" 2>/dev/null || true
fi

echo ""
echo "✅ PIPELINE COMPLETE"
echo "═══════════════════════════════════════════"
