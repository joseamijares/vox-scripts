#!/bin/bash
# VOX Unified Pipeline v3.1 — Silent unless actionable
# Schedule: 9 AM, 12 PM, 3 PM CT weekdays

cd "$HOME/.hermes/scripts"

OUTPUT=""
HOUR=$(date +%H)

# 1. Live Prices (always run, only show errors)
PRICES=$(python3 vox_live_prices.py 2>&1 | tail -3)
if echo "$PRICES" | grep -qi "error\|fail"; then
    OUTPUT+="📈 Live Prices\n$PRICES\n\n"
fi

# 2. Macro + Sector (9 AM only, only show if warnings)
if [ "$HOUR" == "09" ]; then
    MACRO=$(python3 vox_macro_agent.py 2>&1 | tail -5)
    if echo "$MACRO" | grep -qi "warning\|alert\|critical"; then
        OUTPUT+="📊 Macro\n$MACRO\n\n"
    fi
    
    SECTOR=$(python3 vox_sector_agent.py 2>&1 | tail -5)
    if echo "$SECTOR" | grep -qi "warning\|alert\|critical"; then
        OUTPUT+="🏭 Sector\n$SECTOR\n\n"
    fi
fi

# 3. Volume Scan
VOL=$(python3 vox_volume_scanner.py quick 2>&1 | tail -5)
if echo "$VOL" | grep -q "Alerts:" && ! echo "$VOL" | grep -q "Alerts: 0"; then
    OUTPUT+="📊 Volume\n$VOL\n\n"
fi

# 4. News Digest
NEWS=$(python3 vox_news_digest.py 2>&1 | tail -5)
if echo "$NEWS" | grep -q "portfolio_impact\|relevance"; then
    OUTPUT+="📰 News\n$NEWS\n\n"
fi

# 5. Council + Grades (9 AM only, silent unless errors)
if [ "$HOUR" == "09" ]; then
    COUNCIL=$(python3 vox_council.py --batch 2>&1 | tail -5)
    if echo "$COUNCIL" | grep -qi "error\|fail"; then
        OUTPUT+="🏛️ Council\n$COUNCIL\n\n"
    fi
    
    WGRADES=$(python3 vox_watchlist_grader.py 2>&1 | tail -5)
    if echo "$WGRADES" | grep -qi "error\|fail"; then
        OUTPUT+="🎯 Watchlist\n$WGRADES\n\n"
    fi
    
    PGRADES=$(python3 vox_portfolio_grader.py 2>&1 | tail -5)
    if echo "$PGRADES" | grep -qi "error\|fail"; then
        OUTPUT+="🎯 Portfolio\n$PGRADES\n\n"
    fi
    
    cp vox_watchlist_graded.json ~/dev/vox-dashboard/public/data/ 2>/dev/null
    cp vox_portfolio_graded.json ~/dev/vox-dashboard/public/data/ 2>/dev/null
fi

# 6. SMART ALERTS v8 — ONLY if there are actual alerts
ALERTS=$(python3 vox_smart_alerts_v8.py 2>&1)
if [ -n "$ALERTS" ]; then
    OUTPUT+="🚨 $ALERTS\n\n"
fi

# 7. Supabase sync — only show errors
SUPA=$(python3 -c "
from vox_supabase_sync import sync_positions
import json
with open('dashboard_positions_live.json') as f:
    data = json.load(f)
    sync_positions(data.get('positions', []))
    print('Synced')
" 2>&1)
if echo "$SUPA" | grep -qi "error\|fail"; then
    OUTPUT+="☁️ Supabase\n$SUPA\n\n"
fi

# Only output if there's something to show
if [ -n "$OUTPUT" ]; then
    echo "🤖 VOX UNIFIED — $(date '+%H:%M %Z')"
    echo "=============================="
    echo -e "$OUTPUT"
fi
