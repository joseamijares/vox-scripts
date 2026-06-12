#!/bin/bash
# VOX Daily Digest Pipeline v9.2
# End-of-day intelligence processing
# Run this at 4:30 PM after market close

set -e

echo "🧠 VOX Daily Digest Pipeline"
echo "=============================="
echo "Started: $(date)"
echo ""

cd /Users/jos/.hermes/scripts

# Step 1: Update portfolio snapshot
echo "📊 Step 1: Portfolio Snapshot"
python3 vox_portfolio_scanner.py --output snapshots/snapshot_$(date +%Y%m%d).json

# Step 2: Update grades
echo "📈 Step 2: Grade Update"
python3 vox_grade_system.py --update-all

# Step 3: Generate AI plays
echo "🎯 Step 3: AI Play Generation"
python3 vox_ai_harness.py --plays --output vox_generated_plays.json

# Step 4: Social sentiment
echo "📱 Step 4: Social Sentiment"
python3 vox_social_tracker.py --scan --output vox_social_sentiment.json

# Step 5: Daily brief
echo "📰 Step 5: Daily Brief"
python3 vox_autonomous_agent.py --mode daily

# Step 6: Generate digest
echo "🧠 Step 6: Daily Digest"
python3 vox_daily_digest.py --send-telegram

# Step 7: Generate tomorrow's plan
echo "📋 Step 7: Next-Day Plan"
python3 vox_next_day_planner.py --send-telegram

echo ""
echo "=============================="
echo "✅ Pipeline complete: $(date)"
echo ""
echo "📊 Digest: vox_daily_digest.json"
echo "📋 Plan: vox_next_day_plan.json"
echo "📝 Vault: ~/Documents/Obsidian Vault/Portfolio-Finance/"
echo "📱 Telegram: Sent"
