#!/usr/bin/env python3
"""
VOX X/Twitter Intelligence Agent
Monitors X for ticker mentions, sentiment, influencer activity
Tracks: volume of mentions, sentiment shift, key accounts, trending topics
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List
from collections import defaultdict

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
X_DIR = SCRIPT_DIR / "x_intelligence"
X_DIR.mkdir(exist_ok=True)

def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v
    return keys

def search_x(query: str, max_results: int = 50) -> List[dict]:
    """Search X/Twitter via API."""
    env = load_env()
    bearer = env.get("X_BEARER_TOKEN", "")
    
    if not bearer:
        print("[X] No bearer token, using mock data")
        return []
    
    url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&max_results={max_results}&tweet.fields=created_at,public_metrics,author_id"
    headers = {"Authorization": f"Bearer {bearer}"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("data", [])
    except Exception as e:
        print(f"[X] API error: {e}")
        return []

def analyze_ticker_mentions(ticker: str) -> dict:
    """Analyze X mentions for a ticker."""
    print(f"   Scanning X for ${ticker}...")
    
    # Search for ticker mentions
    tweets = search_x(f"${ticker} -is:retweet", max_results=30)
    
    if not tweets:
        return {
            "ticker": ticker,
            "mention_count": 0,
            "sentiment": "NEUTRAL",
            "score": 50,
            "trending": False,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Basic sentiment (keyword-based)
    bullish_words = ["bull", "long", "buy", "moon", "rocket", "breakout", " ATH", "support"]
    bearish_words = ["bear", "short", "sell", "dump", "crash", "resistance", "bubble", "scam"]
    
    bullish_count = 0
    bearish_count = 0
    total_engagement = 0
    
    for tweet in tweets:
        text = tweet.get("text", "").lower()
        metrics = tweet.get("public_metrics", {})
        engagement = metrics.get("like_count", 0) + metrics.get("retweet_count", 0)
        total_engagement += engagement
        
        if any(w in text for w in bullish_words):
            bullish_count += 1 + (engagement / 100)
        elif any(w in text for w in bearish_words):
            bearish_count += 1 + (engagement / 100)
    
    total_weighted = bullish_count + bearish_count
    if total_weighted > 0:
        sentiment_score = (bullish_count / total_weighted) * 100
    else:
        sentiment_score = 50
    
    # Volume score
    volume_score = min(len(tweets) * 2, 100)
    
    # Combined
    final_score = int(sentiment_score * 0.6 + volume_score * 0.4)
    
    sentiment = "BULLISH" if sentiment_score > 60 else "BEARISH" if sentiment_score < 40 else "NEUTRAL"
    trending = len(tweets) > 20 and total_engagement > 1000
    
    return {
        "ticker": ticker,
        "mention_count": len(tweets),
        "sentiment": sentiment,
        "sentiment_score": round(sentiment_score, 1),
        "volume_score": volume_score,
        "score": final_score,
        "engagement": total_engagement,
        "trending": trending,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def scan_watchlist():
    """Scan all watchlist tickers on X."""
    print("🐦 VOX X Intelligence Agent")
    print("=" * 50)
    
    # Load watchlist + portfolio
    tickers = set()
    
    # From portfolio
    portfolio_file = SCRIPT_DIR / "dashboard_positions_live.json"
    if portfolio_file.exists():
        with open(portfolio_file) as f:
            data = json.load(f)
            for p in data.get("positions", []):
                tickers.add(p.get("ticker", ""))
    
    # From watchlist
    watchlist_file = SCRIPT_DIR / "vox_research_watchlist.json"
    if watchlist_file.exists():
        with open(watchlist_file) as f:
            data = json.load(f)
            for r in data.get("recommendations", []):
                tickers.add(r.get("ticker", ""))
    
    tickers = [t for t in tickers if t and len(t) <= 5]  # Filter valid tickers
    
    print(f"Scanning {len(tickers)} tickers...")
    
    results = {}
    trending = []
    
    for ticker in tickers[:20]:  # Top 20 for speed
        try:
            result = analyze_ticker_mentions(ticker)
            results[ticker] = result
            
            if result["trending"]:
                trending.append(result)
            
            emoji = "🔥" if result["trending"] else "🟢" if result["sentiment"] == "BULLISH" else "🔴" if result["sentiment"] == "BEARISH" else "⚪"
            print(f"   {emoji} {ticker:6s} | {result['sentiment']:8s} | Score: {result['score']:2d} | {result['mention_count']} mentions")
        except Exception as e:
            print(f"   ⚪ {ticker:6s} | ERROR: {e}")
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tickers_scanned": len(results),
        "trending_count": len(trending),
        "trending": trending,
        "results": list(results.values())
    }
    
    with open(X_DIR / "x_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n📊 X Summary")
    print(f"   Scanned: {len(results)}")
    print(f"   Trending: {len(trending)}")
    if trending:
        print(f"   Hot: {', '.join([t['ticker'] for t in trending[:3]])}")
    
    return output

if __name__ == "__main__":
    scan_watchlist()
