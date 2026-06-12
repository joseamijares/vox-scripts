#!/usr/bin/env python3
"""
VOX Debrief Agent
Aggregates ALL intelligence sources into a unified daily debrief
Stores: comprehensive report in Supabase + JSON

Sources:
- News intelligence
- Trump tracker
- Reddit intelligence
- X/Twitter intelligence
- Volume anomalies
- Sector rotation
- Macro regime

Outputs: Daily debrief with actionable insights
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPT_DIR = Path.home() / ".hermes/scripts"
DEBRIEF_DIR = SCRIPT_DIR / "debriefs"
DEBRIEF_DIR.mkdir(exist_ok=True)

def load_intelligence() -> Dict:
    """Load all intelligence sources."""
    intel = {}
    
    # News
    news_file = SCRIPT_DIR / "news_intelligence" / "news_intelligence.json"
    if news_file.exists():
        with open(news_file) as f:
            intel["news"] = json.load(f)
    
    # Trump
    trump_file = SCRIPT_DIR / "trump_intelligence" / "trump_intelligence.json"
    if trump_file.exists():
        with open(trump_file) as f:
            intel["trump"] = json.load(f)
    
    # Reddit
    reddit_file = SCRIPT_DIR / "reddit_intelligence" / "reddit_intelligence.json"
    if reddit_file.exists():
        with open(reddit_file) as f:
            intel["reddit"] = json.load(f)
    
    # X
    x_file = SCRIPT_DIR / "x_intelligence" / "x_intelligence.json"
    if x_file.exists():
        with open(x_file) as f:
            intel["x"] = json.load(f)
    
    # Volume
    volume_file = SCRIPT_DIR / "volume_intelligence" / "volume_intelligence.json"
    if volume_file.exists():
        with open(volume_file) as f:
            intel["volume"] = json.load(f)
    
    # Macro
    macro_file = SCRIPT_DIR / "vox_macro_analysis.json"
    if macro_file.exists():
        with open(macro_file) as f:
            intel["macro"] = json.load(f)
    
    return intel

def generate_debrief(intel: Dict) -> Dict:
    """Generate unified debrief from all sources."""
    
    debrief = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {},
        "alerts": [],
        "watchlist_adds": [],
        "sector_rotation": {},
        "macro_context": {},
        "actions": []
    }
    
    # News summary
    news = intel.get("news", {})
    breaking = news.get("breaking", [])
    debrief["summary"]["news"] = {
        "articles_found": news.get("articles_found", 0),
        "high_relevance": len(breaking),
        "top_headlines": [a["title"] for a in breaking[:3]]
    }
    
    # Trump summary
    trump = intel.get("trump", {})
    alerts = trump.get("alerts", [])
    debrief["summary"]["trump"] = {
        "mentions_found": trump.get("mentions_found", 0),
        "market_moving": len(alerts),
        "key_statements": [a["text"][:100] for a in alerts[:2]]
    }
    
    # Reddit summary
    reddit = intel.get("reddit", {})
    top = reddit.get("top_mentions", [])
    debrief["summary"]["reddit"] = {
        "tickers_tracked": reddit.get("tickers_tracked", 0),
        "top_hype": [r["ticker"] for r in top[:5]],
        "bullish_count": len([r for r in top if r.get("sentiment_label") == "BULLISH"]),
        "bearish_count": len([r for r in top if r.get("sentiment_label") == "BEARISH"])
    }
    
    # X summary
    x_data = intel.get("x", {})
    x_results = x_data.get("results", [])
    debrief["summary"]["x"] = {
        "tickers_with_mentions": x_data.get("tickers_with_mentions", 0),
        "top_momentum": [r["ticker"] for r in x_results[:5]],
        "bullish_count": len([r for r in x_results if r.get("sentiment_label") == "BULLISH"]),
        "bearish_count": len([r for r in x_results if r.get("sentiment_label") == "BEARISH"])
    }
    
    # Volume anomalies
    volume = intel.get("volume", {})
    anomalies = volume.get("anomalies", [])
    debrief["summary"]["volume"] = {
        "anomalies_found": len(anomalies),
        "top_signals": [a["ticker"] for a in anomalies[:5]]
    }
    
    # Generate cross-signal alerts
    # Ticker mentioned in multiple sources
    all_tickers = set()
    for source in ["news", "reddit", "x", "volume"]:
        data = intel.get(source, {})
        if source == "news":
            for a in data.get("articles", []):
                all_tickers.add(a.get("ticker", ""))
        elif source == "volume":
            for a in data.get("anomalies", []):
                all_tickers.add(a.get("ticker", ""))
        else:
            for r in data.get("top_mentions", data.get("results", [])):
                all_tickers.add(r.get("ticker", ""))
    
    # Cross-reference
    for ticker in all_tickers:
        signals = []
        
        # Check news
        for a in news.get("articles", []):
            if a.get("ticker") == ticker and a.get("relevance", 0) >= 70:
                signals.append("news")
        
        # Check reddit
        for r in reddit.get("top_mentions", []):
            if r.get("ticker") == ticker and r.get("hype_score", 0) >= 60:
                signals.append("reddit")
        
        # Check X
        for r in x_data.get("results", []):
            if r.get("ticker") == ticker and r.get("momentum_score", 0) >= 60:
                signals.append("x")
        
        # Check volume
        for a in volume.get("anomalies", []):
            if a.get("ticker") == ticker:
                signals.append("volume")
        
        # Check trump
        for alert in alerts:
            if ticker in alert.get("affected_tickers", []):
                signals.append("trump")
        
        if len(signals) >= 2:
            debrief["alerts"].append({
                "ticker": ticker,
                "signals": signals,
                "strength": len(signals),
                "message": f"{ticker}: Cross-signal alert ({', '.join(signals)})"
            })
    
    # Sort by strength
    debrief["alerts"].sort(key=lambda x: x["strength"], reverse=True)
    
    # Generate watchlist adds
    for alert in debrief["alerts"][:5]:
        if alert["strength"] >= 3:
            debrief["watchlist_adds"].append(alert["ticker"])
    
    # Macro context
    macro = intel.get("macro", {})
    debrief["macro_context"] = {
        "vix": macro.get("vix", "N/A"),
        "yield_10y": macro.get("yield_10y", "N/A"),
        "dxy": macro.get("dxy", "N/A"),
        "regime": macro.get("regime", "NEUTRAL"),
        "risk_level": macro.get("risk_level", "MEDIUM")
    }
    
    # Recommended actions
    if debrief["alerts"]:
        debrief["actions"].append(f"Review {len(debrief['alerts'])} cross-signal alerts")
    if debrief["watchlist_adds"]:
        debrief["actions"].append(f"Add {', '.join(debrief['watchlist_adds'])} to watchlist")
    if alerts:
        debrief["actions"].append("Review Trump impact on portfolio")
    if anomalies:
        debrief["actions"].append(f"Check {len(anomalies)} volume anomalies")
    
    return debrief

def store_debrief(debrief: Dict):
    """Store debrief in Supabase and JSON."""
    
    # Save JSON
    date_str = debrief["date"]
    with open(DEBRIEF_DIR / f"debrief_{date_str}.json", 'w') as f:
        json.dump(debrief, f, indent=2)
    
    # Save latest
    with open(DEBRIEF_DIR / "debrief_latest.json", 'w') as f:
        json.dump(debrief, f, indent=2)
    
    # Store in Supabase
    try:
        from vox_supabase_sync import get_client
        sb = get_client()
        
        # Store as alert
        sb.table('alerts').insert({
            "ticker": "DEBRIEF",
            "message": f"Daily debrief: {len(debrief['alerts'])} alerts, {len(debrief['watchlist_adds'])} watchlist adds"
        }).execute()
        
        print("💾 Stored debrief in Supabase")
    except Exception as e:
        print(f"Supabase error: {e}")

def print_debrief(debrief: Dict):
    """Print formatted debrief."""
    print("\n" + "=" * 70)
    print("📋 VOX DAILY DEBRIEF")
    print(f"   {debrief['date']}")
    print("=" * 70)
    
    print("\n📰 NEWS:")
    print(f"   Articles: {debrief['summary']['news']['articles_found']}")
    print(f"   High relevance: {debrief['summary']['news']['high_relevance']}")
    for h in debrief['summary']['news']['top_headlines'][:2]:
        print(f"   • {h[:70]}...")
    
    print("\n🇺🇸 TRUMP:")
    print(f"   Mentions: {debrief['summary']['trump']['mentions_found']}")
    print(f"   Market-moving: {debrief['summary']['trump']['market_moving']}")
    
    print("\n📱 REDDIT:")
    print(f"   Tickers: {debrief['summary']['reddit']['tickers_tracked']}")
    print(f"   Top hype: {', '.join(debrief['summary']['reddit']['top_hype'][:5])}")
    
    print("\n🐦 X/TWITTER:")
    print(f"   Tickers: {debrief['summary']['x']['tickers_with_mentions']}")
    print(f"   Top momentum: {', '.join(debrief['summary']['x']['top_momentum'][:5])}")
    
    print("\n📊 VOLUME:")
    print(f"   Anomalies: {debrief['summary']['volume']['anomalies_found']}")
    print(f"   Signals: {', '.join(debrief['summary']['volume']['top_signals'][:5])}")
    
    print("\n🚨 CROSS-SIGNAL ALERTS:")
    for alert in debrief['alerts'][:5]:
        print(f"   {alert['ticker']:6s} | {alert['strength']} signals: {', '.join(alert['signals'])}")
    
    print("\n👁️  WATCHLIST ADDS:")
    for ticker in debrief['watchlist_adds']:
        print(f"   • {ticker}")
    
    print("\n📋 RECOMMENDED ACTIONS:")
    for action in debrief['actions']:
        print(f"   → {action}")
    
    print("\n" + "=" * 70)

def run_debrief():
    """Main debrief loop."""
    print("🤖 VOX Debrief Agent")
    print("=" * 60)
    
    # Load all intelligence
    intel = load_intelligence()
    
    # Generate debrief
    debrief = generate_debrief(intel)
    
    # Print
    print_debrief(debrief)
    
    # Store
    store_debrief(debrief)
    
    print(f"\n✅ Debrief complete. {len(debrief['alerts'])} alerts, {len(debrief['watchlist_adds'])} watchlist adds.")

if __name__ == "__main__":
    run_debrief()
