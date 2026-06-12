#!/usr/bin/env python3
"""
VOX Trump Tracker Agent
Monitors Truth Social, news, X for Trump mentions of portfolio stocks
Stores: mentions, context, sentiment, impact score
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict

SCRIPT_DIR = Path.home() / ".hermes/scripts"
TRUMP_DIR = SCRIPT_DIR / "trump_intelligence"
TRUMP_DIR.mkdir(exist_ok=True)

# Trump impact keywords
IMPACT_KEYWORDS = [
    "tariff", "tariffs", "trade war", "china", "mexico", "canada",
    "semiconductor", "chip", "ai", "crypto", "bitcoin", "oil", "energy",
    "nuclear", "defense", "military", "fed", "interest rates", "dollar"
]

# Portfolio sectors Trump cares about
TRUMP_SENSITIVE = {
    "MU": "semiconductor", "NVDA": "ai", "AMD": "semiconductor",
    "TSLA": "ev", "COIN": "crypto", "MSTR": "crypto",
    "XOM": "oil", "CVX": "oil", "CEG": "nuclear",
    "RTX": "defense", "LMT": "defense", "NOC": "defense",
    "BABA": "china", "PDD": "china", "TSM": "china",
    "META": "tech", "GOOGL": "tech", "AMZN": "tech"
}

def load_env():
    env_path = Path.home() / ".hermes/.env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v
    return keys

def search_x_trump() -> List[Dict]:
    """Search X for Trump posts mentioning stocks."""
    env = load_env()
    bearer = env.get("X_BEARER_TOKEN", "")
    
    if not bearer:
        return []
    
    queries = [
        "from:realDonaldTrump stock",
        "from:realDonaldTrump tariff",
        "Trump semiconductor",
        "Trump crypto"
    ]
    
    results = []
    for query in queries[:2]:  # Limit API calls
        url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&max_results=10"
        headers = {"Authorization": f"Bearer {bearer}"}
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for tweet in data.get("data", []):
                    results.append({
                        "text": tweet.get("text", ""),
                        "id": tweet.get("id", ""),
                        "created_at": tweet.get("created_at", ""),
                        "source": "X"
                    })
        except:
            pass
    
    return results

def analyze_trump_impact(text: str) -> Dict:
    """Analyze potential market impact of Trump statement."""
    text_lower = text.lower()
    
    impact_score = 0
    affected_sectors = []
    affected_tickers = []
    
    # Check impact keywords
    for keyword in IMPACT_KEYWORDS:
        if keyword in text_lower:
            impact_score += 15
            affected_sectors.append(keyword)
    
    # Check portfolio tickers
    for ticker, sector in TRUMP_SENSITIVE.items():
        if ticker.lower() in text_lower or sector in text_lower:
            impact_score += 20
            affected_tickers.append(ticker)
    
    # Sentiment
    bullish = ["great", "best", "strong", "win", "tremendous", "huge"]
    bearish = ["disaster", "terrible", "weak", "fail", "sad", "worst"]
    
    b = sum(1 for w in bullish if w in text_lower)
    be = sum(1 for w in bearish if w in text_lower)
    
    sentiment = "BULLISH" if b > be else "BEARISH" if be > b else "NEUTRAL"
    
    return {
        "impact_score": min(100, impact_score),
        "sentiment": sentiment,
        "affected_sectors": list(set(affected_sectors)),
        "affected_tickers": list(set(affected_tickers)),
        "is_market_moving": impact_score >= 40
    }

def run_trump_tracker():
    """Main Trump tracking loop."""
    
    # Search for Trump mentions
    mentions = search_x_trump()
    
    analyzed = []
    market_moving = []
    
    for mention in mentions:
        analysis = analyze_trump_impact(mention["text"])
        
        entry = {
            **mention,
            **analysis,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        analyzed.append(entry)
        
        if analysis["is_market_moving"]:
            market_moving.append(entry)
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mentions_found": len(analyzed),
        "market_moving": len(market_moving),
        "mentions": analyzed,
        "alerts": market_moving
    }
    
    with open(TRUMP_DIR / "trump_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Only print if there are market-moving mentions
    if market_moving:
        print(f"🇺🇸 TRUMP ALERT — {len(market_moving)} market-moving mentions")
        for alert in market_moving[:3]:
            print(f"   🚨 {alert['impact_score']}pts | {alert['text'][:80]}...")
            if alert['affected_tickers']:
                print(f"      Tickers: {', '.join(alert['affected_tickers'])}")
    
    # Store alerts
    if market_moving:
        try:
            from vox_supabase_sync import get_client
            sb = get_client()
            for alert in market_moving[:3]:
                sb.table('alerts').insert({
                    "ticker": alert["affected_tickers"][0] if alert["affected_tickers"] else "MARKET",
                    "type": "TRUMP",
                    "message": alert["text"][:200],
                    "priority": "CRITICAL" if alert["impact_score"] >= 70 else "HIGH",
                    "timestamp": alert["timestamp"]
                }).execute()
        except:
            pass

if __name__ == "__main__":
    run_trump_tracker()
