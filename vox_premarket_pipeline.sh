#!/bin/bash
# VOX Pre-Market Pipeline v1.1 — Silent unless actionable
cd "$HOME/.hermes/scripts"

OUTPUT=""

# 1. Live Prices
PRICES=$(python3 vox_live_prices.py 2>&1 | tail -3)
if echo "$PRICES" | grep -qi "error\|fail"; then
    OUTPUT+="📈 Live Prices\n$PRICES\n\n"
fi

# 2. Volume Scan
VOL=$(python3 vox_volume_scanner.py quick 2>&1 | tail -5)
if echo "$VOL" | grep -q "Alerts:" && ! echo "$VOL" | grep -q "Alerts: 0"; then
    OUTPUT+="📊 Volume\n$VOL\n\n"
fi

# 3. News Digest
NEWS=$(python3 vox_news_digest.py 2>&1 | tail -5)
if echo "$NEWS" | grep -q "portfolio_impact\|relevance"; then
    OUTPUT+="📰 News\n$NEWS\n\n"
fi

# 4. Trump Tracker
TRUMP=$(python3 vox_trump_agent.py 2>&1 | tail -5)
if echo "$TRUMP" | grep -qi "trump\|alert\|mention" && ! echo "$TRUMP" | grep -q "0 mentions"; then
    OUTPUT+="🐦 Trump\n$TRUMP\n\n"
fi

# 5. X Intelligence
X=$(python3 vox_x_intelligence.py 2>&1 | tail -5)
if echo "$X" | grep -q "activity" && ! echo "$X" | grep -q "0 tickers"; then
    OUTPUT+="📱 X Intel\n$X\n\n"
fi

# 6. Macro
MACRO=$(python3 vox_macro_agent.py 2>&1 | tail -5)
if echo "$MACRO" | grep -qi "warning\|alert\|critical"; then
    OUTPUT+="🌍 Macro\n$MACRO\n\n"
fi

# 7-8. Grading (silent unless errors)
GRADES=$(python3 vox_watchlist_grader.py 2>&1 | tail -5)
if echo "$GRADES" | grep -qi "error\|fail"; then
    OUTPUT+="🎯 Watchlist Grades\n$GRADES\n\n"
fi

PGRADES=$(python3 vox_portfolio_grader.py 2>&1 | tail -5)
if echo "$PGRADES" | grep -qi "error\|fail"; then
    OUTPUT+="🎯 Portfolio Grades\n$PGRADES\n\n"
fi

# Copy graded data to dashboard
cp vox_watchlist_graded.json ~/dev/vox-dashboard/public/data/ 2>/dev/null
cp vox_portfolio_graded.json ~/dev/vox-dashboard/public/data/ 2>/dev/null

# 9. Pre-market briefing (always show — this is the main deliverable)
BRIEF=$(python3 vox_premarket_briefing.py 2>&1 | tail -20)
if [ -n "$BRIEF" ]; then
    OUTPUT+="📋 Pre-Market Brief\n$BRIEF\n\n"
fi

# Only output if there's something to show
if [ -n "$OUTPUT" ]; then
    echo "🌅 VOX PRE-MARKET — $(date '+%H:%M %Z')"
    echo "==============================="
    echo -e "$OUTPUT"
fi
