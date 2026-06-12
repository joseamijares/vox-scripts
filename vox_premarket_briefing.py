#!/usr/bin/env python3
"""
VOX Pre-Market Briefing Generator
Aggregates overnight data into a concise briefing for market open
"""

import json, os
from datetime import datetime

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def main():
    print("=" * 60)
    print("VOX PRE-MARKET BRIEFING")
    print("=" * 60)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}")
    print()

    # Load data sources
    prices = load_json("dashboard_positions_live.json", {})
    watchlist = load_json("vox_watchlist_graded.json", {})
    portfolio = load_json("vox_portfolio_graded.json", {})
    news = load_json("vox_news_digest.json", {})
    volume = load_json("vox_volume_scan.json", {})
    macro = load_json("vox_macro_regime.json", {})

    positions = prices.get("positions", [])

    # === TOP MOVERS ===
    print("📈 OVERNIGHT MOVERS")
    print("-" * 40)
    movers = sorted([p for p in positions if abs(p.get("price_change_pct", 0)) > 2],
                    key=lambda x: abs(x.get("price_change_pct", 0)), reverse=True)[:5]
    if movers:
        for p in movers:
            direction = "🟢" if p["price_change_pct"] > 0 else "🔴"
            print(f"  {direction} {p['ticker']}: {p['price_change_pct']:+.2f}% @ ${p.get('live_price', p['price'])}")
    else:
        print("  No significant overnight moves (>2%)")
    print()

    # === WATCHLIST OPPORTUNITIES ===
    print("🎯 WATCHLIST OPPORTUNITIES")
    print("-" * 40)
    wl_results = watchlist.get("results", [])
    strong_buy = [w for w in wl_results if w.get("signal") == "STRONG_BUY"][:3]
    buy = [w for w in wl_results if w.get("signal") == "BUY"][:3]

    if strong_buy:
        print("  STRONG BUY:")
        for w in strong_buy:
            print(f"    {w['ticker']}: Grade {w['grade']} | Buy @ ${w['buy_zone']} → ${w['target_1']}")
    if buy:
        print("  BUY:")
        for w in buy:
            print(f"    {w['ticker']}: Grade {w['grade']} | Buy @ ${w['buy_zone']} → ${w['target_1']}")
    if not strong_buy and not buy:
        print("  No strong opportunities today")
    print()

    # === PORTFOLIO ALERTS ===
    print("🚨 PORTFOLIO ALERTS")
    print("-" * 40)
    pf_results = portfolio.get("results", [])
    trim = [p for p in pf_results if p.get("signal") in ["TRIM", "CUT_LOSS"]][:3]
    strong = [p for p in pf_results if p.get("signal") == "STRONG_HOLD" and p.get("pnl_pct", 0) > 10][:3]

    if trim:
        print("  TRIM/CUT:")
        for p in trim:
            print(f"    {p['ticker']}: {p['signal']} | Grade {p['grade']} | PnL {p['pnl_pct']:+.1f}%")
    if strong:
        print("  STRONG PERFORMERS:")
        for p in strong:
            print(f"    {p['ticker']}: +{p['pnl_pct']:.1f}% | Grade {p['grade']}")
    if not trim and not strong:
        print("  No portfolio alerts")
    print()

    # === VOLUME SPIKES ===
    print("📊 VOLUME SPIKES")
    print("-" * 40)
    alerts = volume.get("alerts", [])
    if alerts:
        for a in alerts[:3]:
            print(f"  {a['ticker']}: {a.get('volume_ratio', 0):.1f}x volume | {a.get('price_change_pct', 0):+.1f}%")
    else:
        print("  No volume spikes detected")
    print()

    # === MACRO REGIME ===
    print("🌍 MACRO REGIME")
    print("-" * 40)
    if macro:
        regime = macro.get("regime", "UNKNOWN")
        vix = macro.get("vix", "N/A")
        print(f"  Regime: {regime}")
        print(f"  VIX: {vix}")
        print(f"  10Y Yield: {macro.get('yield_10y', 'N/A')}")
        print(f"  DXY: {macro.get('dxy', 'N/A')}")
    else:
        print("  Macro data unavailable")
    print()

    # === NEWS HEADLINES ===
    print("📰 TOP NEWS")
    print("-" * 40)
    headlines = news.get("headlines", []) if isinstance(news, dict) else []
    if headlines:
        for h in headlines[:5]:
            ticker = h.get("ticker", "")
            title = h.get("title", "")[:60]
            print(f"  [{ticker}] {title}...")
    else:
        print("  No overnight news")
    print()

    # === MARKET OPEN CHECKLIST ===
    print("✅ MARKET OPEN CHECKLIST")
    print("-" * 40)
    total_positions = len(positions)
    total_value = sum(p.get("live_value", 0) for p in positions)
    print(f"  Portfolio: {total_positions} positions | ${total_value:,.0f}")
    print(f"  Watchlist: {len(wl_results)} graded")
    print(f"  Data freshness: {prices.get('timestamp', 'unknown')}")
    print()

    # Save briefing
    briefing = {
        "timestamp": datetime.now().isoformat(),
        "movers": [{"ticker": p["ticker"], "change": p["price_change_pct"]} for p in movers],
        "opportunities": strong_buy + buy,
        "alerts": trim,
        "macro": macro,
        "headlines_count": len(headlines)
    }

    with open("vox_premarket_briefing.json", "w") as f:
        json.dump(briefing, f, indent=2)

    print("=" * 60)
    print("Briefing saved to vox_premarket_briefing.json")

if __name__ == "__main__":
    main()
