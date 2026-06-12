#!/bin/bash
# VOX Agentic Intelligence Pipeline
# Runs every 4 hours: Research all sources → Debrief → Alerts

cd "$HOME/.hermes/scripts"

echo "🤖 VOX AGENTIC INTELLIGENCE PIPELINE"
echo "======================================"
echo "Started: $(date)"
echo ""

# 1. Live prices
echo "📊 Step 1: Live Prices"
python3 vox_live_prices.py 2>/dev/null | tail -5

# 2. News intelligence
echo ""
echo "📰 Step 2: News Intelligence"
python3 vox_news_agent.py 2>&1 | tail -15

# 3. Trump tracker
echo ""
echo "🇺🇸 Step 3: Trump Tracker"
python3 vox_trump_agent.py 2>&1 | tail -10

# 4. Reddit intelligence
echo ""
echo "📱 Step 4: Reddit Intelligence"
python3 vox_reddit_agent.py 2>&1 | tail -20

# 5. X/Twitter intelligence
echo ""
echo "🐦 Step 5: X Intelligence"
python3 vox_x_agent.py 2>&1 | tail -20

# 6. Volume intelligence
echo ""
echo "📈 Step 6: Volume Intelligence"
python3 vox_volume_intelligence.py 2>&1 | tail -15

# 7. Research orchestrator (grades + entries)
echo ""
echo "🔬 Step 7: Research Orchestrator"
python3 vox_research_orchestrator.py 2>&1 | tail -20

# 8. Debrief (aggregate all)
echo ""
echo "📋 Step 8: Daily Debrief"
python3 vox_debrief_agent.py 2>&1

# 9. Smart alerts v8 (LLM-enhanced)
echo ""
echo "🚨 Step 9: Smart Alerts v8"
python3 vox_smart_alerts_v8.py 2>&1 | tail -15

# 10. Supabase sync
echo ""
echo "☁️  Step 10: Supabase Sync"
python3 vox_supabase_sync.py 2>/dev/null | tail -5

echo ""
echo "======================================"
echo "✅ Pipeline complete: $(date)"
