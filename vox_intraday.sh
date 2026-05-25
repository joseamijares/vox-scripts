#!/bin/bash
# Vox Intraday Check — Runs M-F 12:00 PM ET
# Mid-day grade check + alert if changes

cd ~/.hermes/scripts

echo "🔮 Vox Intraday — $(date)"
echo "================================"

# Quick price check on monitored plays
echo "🔍 Updating monitored plays..."
python3 vox_monitored_plays.py 2>/dev/null || echo "  ⚠️ Monitored plays failed"

# Alert check
echo "🚨 Alert check..."
python3 vox_alert_system.py 2>/dev/null || echo "  ⚠️ Alert system failed"

echo "✅ Intraday done — $(date)"
