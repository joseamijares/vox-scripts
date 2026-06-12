#!/usr/bin/env python3
"""
VOX Morning Briefing Generator
Generates a Telegram-friendly pre-market digest from live Railway data.
Run at 8 AM CT on weekdays.
"""

import json
import urllib.request
from datetime import datetime
from collections import Counter

DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"


def fetch(endpoint):
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/{endpoint}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_macro_indicators(regime_data):
    r = regime_data.get("regime", {})
    vix = float(r.get("vix_level", 0))
    yield_curve = float(r.get("yield_curve", 0))
    
    vix_signal = "🟢 BULLISH" if vix < 20 else "🟡 NEUTRAL" if vix < 25 else "🔴 BEARISH"
    yield_signal = "🟢 BULLISH" if yield_curve > 0.5 else "🟡 NEUTRAL" if yield_curve > 0 else "🔴 BEARISH"
    
    return {
        "regime": r.get("regime", "UNKNOWN"),
        "confidence": r.get("confidence", "0"),
        "vix": vix,
        "vix_signal": vix_signal,
        "yield_curve": yield_curve,
        "yield_signal": yield_signal,
        "fed_stance": r.get("fed_stance", "Unknown"),
        "spy_trend": r.get("spy_trend", "Unknown"),
    }


def generate_briefing():
    positions_data = fetch("positions")
    grades_data = fetch("grades")
    alerts_data = fetch("alerts")
    regime_data = fetch("regime")
    
    positions = positions_data.get("positions", [])
    grades = grades_data.get("grades", [])
    alerts = alerts_data.get("alerts", [])
    
    if not positions:
        return "❌ No position data available"
    
    # Portfolio summary
    total_value = sum(p.get("live_value", 0) for p in positions)
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    total_cost = sum(p.get("avg_cost", 0) * p.get("shares", 0) for p in positions)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    
    # Grade distribution
    pos_grades = [p.get("grade", 0) for p in positions]
    green = sum(1 for g in pos_grades if g >= 60)
    yellow = sum(1 for g in pos_grades if 50 <= g < 60)
    red = sum(1 for g in pos_grades if g < 50)
    
    # Council distribution
    council_counts = Counter(p.get("council", "N/A") for p in positions)
    
    # Macro
    macro = get_macro_indicators(regime_data)
    
    # Top gainers/losers
    gainers = sorted([p for p in positions if p.get("pnl", 0) > 0], key=lambda x: x["pnl"], reverse=True)[:5]
    losers = sorted([p for p in positions if p.get("pnl", 0) < 0], key=lambda x: x["pnl"])[:5]
    
    # SELL candidates (grade < 45)
    sell_now = [p for p in positions if 0 < p.get("grade", 0) < 45]
    
    # Council SELL positions (top 5 by value)
    council_sell = sorted(
        [p for p in positions if p.get("council", "") == "SELL"],
        key=lambda x: x.get("live_value", 0),
        reverse=True
    )[:5]
    
    # Watchlist opportunities (not in portfolio, grade >= 75)
    portfolio_tickers = {p["ticker"] for p in positions}
    watchlist = [g for g in grades if g["ticker"] not in portfolio_tickers and g.get("vox_grade", 0) >= 75]
    watchlist_sorted = sorted(watchlist, key=lambda x: x.get("vox_grade", 0), reverse=True)[:5]
    
    # Build output
    lines = []
    lines.append(f"# 🌅 VOX Morning Briefing — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append(f"**TL;DR:** Market regime: **{macro['regime']}**. Portfolio: {len(positions)} positions, ${total_value:,.0f} AUM. {len(sell_now)} critical alerts, {green + yellow + red} action items.")
    lines.append("")
    
    # Market Snapshot
    lines.append("## Market Snapshot")
    lines.append(f"- Regime: **{macro['regime']}** (confidence: {macro['confidence']})")
    lines.append(f"- `vix`: {macro['vix']} ({macro['vix_signal']})")
    lines.append(f"- `yield_curve`: {macro['yield_curve']:.2f} ({macro['yield_signal']})")
    lines.append(f"- `fed_stance`: {macro['fed_stance']}")
    lines.append(f"- `spy_trend`: {macro['spy_trend']}")
    lines.append("")
    
    # Portfolio State
    lines.append("## Portfolio State")
    lines.append(f"- AUM: **${total_value:,.0f}** ({len(positions)} positions)")
    lines.append(f"- P&L: ${total_pnl:,.0f} ({total_pnl_pct:+.1f}%)")
    lines.append(f"- Grades: 🟢 {green} | 🟡 {yellow} | 🔴 {red}")
    lines.append(f"- Council: SELL {council_counts.get('SELL', 0)} | HOLD {council_counts.get('HOLD', 0)}")
    lines.append("")
    
    # Critical Alerts
    if sell_now or council_sell:
        lines.append("## 🚨 Critical Alerts")
        if sell_now:
            lines.append("**SELL Candidates (Grade < 45):**")
            for p in sell_now[:5]:
                lines.append(f"- `{p['ticker']}` — Grade {p['grade']}, ${p['live_value']:,.0f}, {p.get('pnl_pct', 0):+.1f}%")
        if council_sell:
            lines.append("**Council SELL (Top by Value):**")
            for p in council_sell:
                lines.append(f"- `{p['ticker']}` — ${p['live_value']:,.0f}, {p.get('pnl_pct', 0):+.1f}%")
        lines.append("")
    
    # Top Movers
    if gainers or losers:
        lines.append("## 📈 Top Movers")
        if gainers:
            lines.append("**Gainers:**")
            for p in gainers:
                lines.append(f"- 🟢 `{p['ticker']}` +${p['pnl']:,.0f} ({p['pnl_pct']:+.1f}%)")
        if losers:
            lines.append("**Losers:**")
            for p in losers:
                lines.append(f"- 🔴 `{p['ticker']}` ${p['pnl']:,.0f} ({p['pnl_pct']:+.1f}%)")
        lines.append("")
    
    # Watchlist
    if watchlist_sorted:
        lines.append("## 👀 Top Watchlist")
        for g in watchlist_sorted:
            lines.append(f"- `{g['ticker']}` — Grade {g['vox_grade']}, ${g.get('current_price', 0):.2f}")
        lines.append("")
    
    lines.append(f"_Generated at {datetime.now().isoformat()}_")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_briefing())
