#!/usr/bin/env python3
"""
VOX Daily RAG Briefing Generator
Reads portfolio data, generates actionable intelligence, writes to dashboard
"""

import json
import os
from datetime import datetime, timezone

# Read from PUBLIC folder (has grades merged)
DASHBOARD_DIR = "/Users/jos/dev/vox-dashboard/public"

def load_json(filename):
    path = os.path.join(DASHBOARD_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def generate_daily_briefing():
    # Load data from PUBLIC (grades merged)
    data = load_json("dashboard_positions.json")
    positions = data.get("positions", [])
    
    if not positions:
        print("❌ No positions found")
        return
    
    # Calculate metrics
    total_value = data.get("total_value", sum(p.get("value", 0) for p in positions))
    total_pnl = data.get("total_pnl", sum(p.get("pnl", 0) for p in positions))
    
    # Grade distribution
    strong = [p for p in positions if p.get("grade", 0) >= 70]
    moderate = [p for p in positions if 60 <= p.get("grade", 0) < 70]
    weak = [p for p in positions if 0 < p.get("grade", 0) < 55]
    
    # Top movers
    gainers = sorted([p for p in positions if p.get("pnl", 0) > 0], key=lambda x: x["pnl"], reverse=True)[:5]
    losers = sorted([p for p in positions if p.get("pnl", 0) < 0], key=lambda x: x["pnl"])[:5]
    
    # SELL candidates
    sell_now = [p for p in positions if p.get("grade", 0) > 0 and p.get("grade", 0) < 50]
    sell_now.sort(key=lambda x: x["value"], reverse=True)
    
    # TRIM candidates
    trim = [p for p in positions if 50 <= p.get("grade", 0) < 55]
    
    # Crypto check
    crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX", "SUI"]
    crypto_value = sum(p["value"] for p in positions if p["ticker"] in crypto_tickers)
    crypto_pct = (crypto_value / total_value * 100) if total_value > 0 else 0
    
    # USD/MXN
    usd_mxn = data.get("usd_mxn_rate", 17.31)
    
    briefing = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": {
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "positions_count": len(positions),
            "avg_grade": round(sum(p.get("grade", 0) for p in positions) / len([p for p in positions if p.get("grade", 0) > 0]), 1) if any(p.get("grade", 0) > 0 for p in positions) else 0,
            "usd_mxn": usd_mxn,
        },
        "grades": {
            "strong": len(strong),
            "moderate": len(moderate),
            "weak": len(weak),
            "ungraded": len([p for p in positions if p.get("grade", 0) == 0]),
        },
        "actions": {
            "sell_now": [{"ticker": p["ticker"], "value": p["value"], "grade": p["grade"], "brokers": p.get("brokers", [])} for p in sell_now[:10]],
            "sell_total_value": round(sum(p["value"] for p in sell_now), 2),
            "trim": [{"ticker": p["ticker"], "value": p["value"], "grade": p["grade"]} for p in trim[:5]],
        },
        "movers": {
            "gainers": [{"ticker": p["ticker"], "pnl": round(p["pnl"], 2)} for p in gainers],
            "losers": [{"ticker": p["ticker"], "pnl": round(p["pnl"], 2)} for p in losers],
        },
        "crypto": {
            "value": round(crypto_value, 2),
            "pct": round(crypto_pct, 1),
            "over_limit": crypto_pct > 10,
        },
        "checklist": [
            f"🔴 Review {len(sell_now)} SELL candidates (grade < 50) — ${sum(p['value'] for p in sell_now):,.0f}",
            f"🟡 Check {len(trim)} TRIM candidates (grade 50-54)" if trim else "✅ No trim candidates",
            f"🟢 {len(strong)} core holdings (grade 70+) — consider adding" if strong else "⚠️ No strong buys",
            f"💰 Crypto at {crypto_pct:.1f}% — {'TRIM if > 10%' if crypto_pct > 10 else 'allocation OK'}",
            f"💱 USD/MXN at {usd_mxn:.2f}",
            "📰 Review overnight news on top 5 holdings",
        ],
    }
    
    # Write to dashboard
    output_path = os.path.join(DASHBOARD_DIR, "vox_daily_brief.json")
    with open(output_path, "w") as f:
        json.dump(briefing, f, indent=2)
    
    print(f"✅ Daily briefing generated")
    print(f"   Portfolio: ${total_value:,.0f} | P&L: ${total_pnl:,.0f}")
    print(f"   SELL: {len(sell_now)} | TRIM: {len(trim)} | Strong: {len(strong)}")
    print(f"   Crypto: {crypto_pct:.1f}% | USD/MXN: {usd_mxn:.2f}")
    
    return briefing

if __name__ == "__main__":
    generate_daily_briefing()
