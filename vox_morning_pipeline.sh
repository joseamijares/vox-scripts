#!/bin/bash
# VOX Morning Pipeline v9.2
# Pre-market intelligence briefing
# Run this at 8:00 AM before market open

set -e

echo "🌅 VOX Morning Pipeline"
echo "=============================="
echo "Started: $(date)"
echo ""

cd /Users/jos/.hermes/scripts

# Step 1: Fetch overnight news
echo "📰 Step 1: News Digest"
python3 vox_news_digest.py --output vox_news_digest.json

# Step 2: Update portfolio snapshot
echo "📊 Step 2: Portfolio Snapshot"
python3 vox_portfolio_scanner.py --output snapshots/snapshot_$(date +%Y%m%d).json

# Step 3: Update grades
echo "📈 Step 3: Grade Update"
python3 vox_grade_system.py --update-all

# Step 4: Generate daily brief
echo "📰 Step 4: Daily Brief"
python3 vox_autonomous_agent.py --mode daily

# Step 5: Social sentiment
echo "📱 Step 5: Social Sentiment"
python3 vox_social_tracker.py --scan --output vox_social_sentiment.json

# Step 6: Generate morning debrief
echo "🌅 Step 6: Morning Debrief"
python3 vox_morning_debrief.py --send-telegram

echo ""
echo "=============================="
echo "✅ Morning pipeline complete: $(date)"
echo ""
echo "📝 Vault: ~/Documents/Obsidian Vault/Portfolio-Finance/06-Tracking/Daily/"
echo "📱 Telegram: Sent"
