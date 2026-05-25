#!/bin/bash
# Vox Market Close — Runs M-F 4:30 PM ET
# Day summary, P&L, update monitored plays, journal entry

cd ~/.hermes/scripts

echo "🔮 Vox Market Close — $(date)"
echo "================================"

# Update all monitored plays with closing prices
echo "🔍 Final monitored update..."
python3 vox_monitored_plays.py 2>/dev/null || echo "  ⚠️ Monitored plays failed"

# Options alerts
echo "📜 Options check..."
python3 vox_options_tracker.py 2>/dev/null || echo "  ⚠️ Options tracker failed"

# Generate day summary
echo "📊 Day summary..."
python3 -c "
import json, os
from datetime import datetime

summary = {'date': datetime.now().isoformat(), 'type': 'DAY_CLOSE'}

# Load monitored
if os.path.exists('vox_monitored_plays.json'):
    with open('vox_monitored_plays.json') as f:
        data = json.load(f)
    active = [p for p in data.get('plays', []) if p['status'] in ('WATCHING', 'NEAR_ENTRY')]
    summary['monitored_active'] = len(active)
    summary['monitored_alerts'] = len([p for p in data.get('plays', []) if p['status'] in ('STOP_HIT', 'TARGET_HIT')])

# Load options
if os.path.exists('vox_options_positions.json'):
    with open('vox_options_positions.json') as f:
        data = json.load(f)
    open_opts = [p for p in data.get('positions', []) if p['status'] == 'OPEN']
    summary['options_open'] = len(open_opts)

# Load journal stats
if os.path.exists('vox_play_journal.json'):
    with open('vox_play_journal.json') as f:
        entries = json.load(f)
    today = datetime.now().strftime('%Y-%m-%d')
    today_entries = [e for e in entries if e['date'].startswith(today)]
    summary['today_plays'] = len(today_entries)

with open('vox_day_summary.json', 'w') as f:
    json.dump(summary, f, indent=2)

print(f\"Day summary: {summary}\")
" 2>/dev/null || echo "  ⚠️ Summary failed"

echo "✅ Close done — $(date)"
