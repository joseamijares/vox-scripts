#!/bin/bash
# VOX Unified Pipeline v2.0
# Runs all agents in sequence, generates consensus, sends alerts
# Schedule: 9 AM, 12 PM, 3 PM CT weekdays

cd "$HOME/.hermes/scripts"

echo "🤖 VOX UNIFIED PIPELINE v2.0"
echo "=============================="
echo "Started: $(date)"
echo ""

# 1. Live Prices
echo "📈 Step 1: Live Prices"
python3 vox_live_prices.py 2>&1 | tail -5

# 2. Macro Analysis
echo ""
echo "📊 Step 2: Macro Analysis"
python3 vox_macro_agent.py 2>&1 | tail -10

# 3. Sector Analysis
echo ""
echo "🏭 Step 3: Sector Analysis"
python3 vox_sector_agent.py 2>&1 | tail -10

# 4. Volume Scan
echo ""
echo "📊 Step 4: Volume Scan"
python3 vox_volume_scanner.py quick 2>&1 | tail -10

# 5. X Momentum
echo ""
echo "🐦 Step 5: X Momentum"
python3 vox_x_momentum.py 2>&1 | tail -10

# 6. News Digest
echo ""
echo "📰 Step 6: News Digest"
python3 vox_news_digest.py 2>&1 | tail -10

# 7. Sentiment
echo ""
echo "🎭 Step 7: Market Sentiment"
python3 vox_sentiment_tracker.py 2>&1 | tail -10

# 8. Council Votes
echo ""
echo "🏛️  Step 8: Council Votes"
python3 vox_council.py --batch 2>&1 | tail -10

# 9. Agentic Platform (orchestrates all)
echo ""
echo "🤖 Step 9: Agentic Consensus"
python3 vox_agentic_platform.py 2>&1 | tail -20

# 10. Alerts (v6 - quality filtered)
echo ""
echo "🚨 Step 10: Smart Alerts v6"
python3 vox_smart_alerts_v6.py 2>&1 | tail -30

# 11. Sync to Supabase
echo ""
echo "☁️  Step 11: Sync to Supabase"
python3 -c "
from vox_supabase_sync import sync_positions, get_client
import json

# Sync positions
with open('dashboard_positions_live.json') as f:
    data = json.load(f)
    sync_positions(data.get('positions', []))
    print('✅ Positions synced')
" 2>&1

echo ""
echo "=============================="
echo "✅ Pipeline complete: $(date)"
