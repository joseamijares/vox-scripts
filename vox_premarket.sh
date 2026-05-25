#!/bin/bash
# Vox Pre-Market Routine — Runs M-F 8:00 AM ET
# 1. Trump tracker scan
# 2. Grade refresh on watchlist
# 3. Alert if any grade crosses 80+ or drops below 50
# 4. Telegram brief

cd ~/.hermes/scripts

echo "🔮 Vox Pre-Market — $(date)"
echo "================================"

# 1. Trump Tracker
echo "🇺🇸 Trump scan..."
python3 trump_tracker.py 2>/dev/null || echo "  ⚠️ Trump tracker failed"

# 2. Refresh watchlist grades
echo "📊 Watchlist refresh..."
python3 vox_watchlist.py 2>/dev/null || echo "  ⚠️ Watchlist failed"

# 3. Check for alerts
echo "🚨 Alert check..."
python3 vox_alert_system.py 2>/dev/null || echo "  ⚠️ Alert system failed"

# 4. Update monitored plays
echo "🔍 Monitored plays..."
python3 vox_monitored_plays.py 2>/dev/null || echo "  ⚠️ Monitored plays failed"

echo "✅ Pre-market done — $(date)"
