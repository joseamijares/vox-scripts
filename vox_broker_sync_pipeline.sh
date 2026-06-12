#!/bin/bash
# VOX Broker Sync Pipeline v2.1 — Silent unless actionable
# Called by cron at 7 AM and 12 PM CT weekdays

cd "$HOME/.hermes/scripts"

OUTPUT=""

# 1. Broker Sync
SYNC=$(python3 vox_broker_sync.py 2>&1 | tail -40)
if echo "$SYNC" | grep -qi "error\|fail\|warning"; then
    OUTPUT+="📡 Broker Sync\n$SYNC\n\n"
fi

# 2. Stale Broker Detection (only show if stale)
STALE=$(python3 -c "
import json
from datetime import datetime, timezone, timedelta

with open('unified_portfolio_current.json') as f:
    data = json.load(f)

now = datetime.now(timezone.utc)
stale_threshold = timedelta(days=7)
stale_brokers = []

for b, info in data.get('by_broker', {}).items():
    last_updated = info.get('last_updated', '')
    try:
        if isinstance(last_updated, str):
            if 'T' in last_updated:
                if '+' in last_updated or 'Z' in last_updated:
                    last_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                else:
                    last_dt = datetime.fromisoformat(last_updated).replace(tzinfo=timezone.utc)
            else:
                last_dt = datetime.strptime(last_updated, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        
        age = now - last_dt
        if age > stale_threshold:
            stale_brokers.append((b, age.days))
    except:
        stale_brokers.append((b, 'unknown'))

if stale_brokers:
    print('STALE BROKERS:')
    for b, days in stale_brokers:
        print(f'   {b}: {days} days old')
" 2>&1)
if [ -n "$STALE" ]; then
    OUTPUT+="🔍 $STALE\n\n"
fi

# 3. Live Prices (only errors)
PRICES=$(python3 vox_live_prices.py 2>&1 | tail -10)
if echo "$PRICES" | grep -qi "error\|fail"; then
    OUTPUT+="💰 Live Prices\n$PRICES\n\n"
fi

# 4-5. Grading (silent unless errors)
WGRADES=$(python3 vox_watchlist_grader.py 2>&1 | tail -5)
if echo "$WGRADES" | grep -qi "error\|fail"; then
    OUTPUT+="📊 Watchlist Grades\n$WGRADES\n\n"
fi

PGRADES=$(python3 vox_portfolio_grader.py 2>&1 | tail -5)
if echo "$PGRADES" | grep -qi "error\|fail"; then
    OUTPUT+="📈 Portfolio Grades\n$PGRADES\n\n"
fi

# 6. Copy to dashboard (silent)
cp vox_watchlist_graded.json ~/dev/vox-dashboard/public/data/ 2>/dev/null
cp vox_portfolio_graded.json ~/dev/vox-dashboard/public/data/ 2>/dev/null
cp dashboard_positions_live.json ~/dev/vox-dashboard/public/data/ 2>/dev/null
cp unified_portfolio_current.json ~/dev/vox-dashboard/public/data/ 2>/dev/null

# 7. Briefing (only if it has content)
BRIEF=$(python3 vox_premarket_briefing.py 2>&1 | tail -20)
if [ -n "$BRIEF" ] && ! echo "$BRIEF" | grep -q "^$"; then
    OUTPUT+="📋 Briefing\n$BRIEF\n\n"
fi

# Only output if there's something to show
if [ -n "$OUTPUT" ]; then
    echo "🏦 VOX BROKER SYNC — $(date '+%H:%M %Z')"
    echo "=================================================="
    echo -e "$OUTPUT"
fi
