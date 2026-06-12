#!/bin/bash
# VOX Agentic Intelligence Pipeline v2 — Optimized for 120s timeout
# Runs every 4 hours
# Strategy: Run slow network calls in background, aggregate results

cd "$HOME/.hermes/scripts"

# Capture all output, only show if there's something worth seeing
OUTPUT=""

# Helper: run command with timeout
trun() {
    timeout 25 "$@" 2>/dev/null
}

# 1. Live prices (fast - 30s max)
PRICES=$(trun python3 vox_live_prices.py | tail -5)
if [ -n "$PRICES" ]; then
    OUTPUT+="📊 Live Prices\n$PRICES\n\n"
fi

# 2. Volume scan (quick mode - 20s max)
VOLUME=$(trun python3 vox_volume_scanner.py quick | tail -5)
if echo "$VOLUME" | grep -q "Alerts:" && ! echo "$VOLUME" | grep -q "Alerts: 0"; then
    OUTPUT+="📈 Volume Scan\n$VOLUME\n\n"
fi

# 3. News digest (20s max)
NEWS=$(trun python3 vox_news_digest.py | tail -10)
if echo "$NEWS" | grep -q "portfolio_impact" || echo "$NEWS" | grep -q "relevance"; then
    OUTPUT+="📰 News Digest\n$NEWS\n\n"
fi

# 4. X momentum (20s max)
X=$(trun python3 vox_x_momentum.py | tail -5)
if echo "$X" | grep -q "tickers with activity" && ! echo "$X" | grep -q "0 tickers"; then
    OUTPUT+="🐦 X Momentum\n$X\n\n"
fi

# 5. Research orchestrator v2 (30s max - this is the heavy one)
RESEARCH=$(trun python3 vox_research_orchestrator_v2.py)
if echo "$RESEARCH" | grep -q "STRONG_BUY\|STRONG_SELL\|opportunities" && ! echo "$RESEARCH" | grep -q "opportunities: 0"; then
    OUTPUT+="🔬 Research\n$RESEARCH\n\n"
fi

# 6. Smart alerts v8 — ONLY output if there are actual alerts (15s max)
ALERTS=$(trun python3 vox_smart_alerts_v8.py)
if [ -n "$ALERTS" ]; then
    OUTPUT+="🚨 $ALERTS\n\n"
fi

# 7. Supabase sync — only show errors (15s max)
SUPA=$(trun python3 vox_supabase_sync.py | tail -3)
if echo "$SUPA" | grep -qi "error\|fail"; then
    OUTPUT+="☁️  Supabase\n$SUPA\n\n"
fi

# 8. Weather & Agriculture (15s max)
WEATHER=$(trun python3 vox_weather_agent.py)
if [ -n "$WEATHER" ]; then
    OUTPUT+="$WEATHER\n\n"
fi

# 9. Geopolitical Risk (15s max)
GEOPOL=$(trun python3 vox_geopolitical_agent.py)
if [ -n "$GEOPOL" ]; then
    OUTPUT+="$GEOPOL\n\n"
fi

# 10. Supply Chain (15s max)
SUPPLY=$(trun python3 vox_supply_chain_agent.py)
if [ -n "$SUPPLY" ]; then
    OUTPUT+="$SUPPLY\n\n"
fi

# 11. Discovery Agent — auto-discovers new opportunities (15s max)
DISCOVERY=$(trun python3 vox_discovery_agent.py)
if [ -n "$DISCOVERY" ]; then
    OUTPUT+="$DISCOVERY\n\n"
fi

# Only print if there's something to show
if [ -n "$OUTPUT" ]; then
    echo "🤖 VOX PIPELINE — $(date '+%H:%M %Z')"
    echo "========================================"
    echo -e "$OUTPUT"
    echo "========================================"
fi

exit 0