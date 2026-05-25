#!/usr/bin/env python3
"""
X Momentum Tracker — OpenClaw
Scans X/Twitter for ticker mentions using Bearer Token auth
"""
import os, json, urllib.request, subprocess
from datetime import datetime

BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")

def search_x(query, max_results=10):
    """Search X API v2 using bearer token"""
    if not BEARER_TOKEN:
        return [{"text": f"X_BEARER_TOKEN not set — search for '{query}' manually", "id": "no_auth"}]
    
    try:
        url = f"https://api.twitter.com/2/tweets/search/recent?query={query.replace(' ', '%20')}&max_results={max_results}&tweet.fields=created_at,public_metrics"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "User-Agent": "OpenClaw-Tracker/1.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            posts = data.get("data", [])
            return posts
    except Exception as e:
        return [{"text": f"Error: {str(e)} for '{query}'", "id": "error"}]

# Keywords per theme
TICKER_QUERIES = {
    "CEG": "$CEG OR Constellation Energy",
    "VST": "$VST OR Vistra",
    "NVDA": "$NVDA OR Nvidia",
    "AVGO": "$AVGO OR Broadcom",
    "RKLB": "$RKLB OR Rocket Lab",
    "SOL": "$SOL OR Solana",
    "VRT": "$VRT OR Vertiv",
    "LRCX": "$LRCX OR Lam Research",
}

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"🐦 X MOMENTUM TRACKER — {timestamp}")
    print("=" * 60)
    
    results = []
    for ticker, query in TICKER_QUERIES.items():
        posts = search_x(query, max_results=10)
        
        if "no_auth" in posts[0].get("id", ""):
            print(f"  {ticker}: {posts[0]['text']}")
            continue
            
        mention_count = len(posts)
        sentiment = "🔥 Bullish" if mention_count >= 5 else "⚖️ Mixed" if mention_count >= 2 else "😐 Quiet"
        
        top_text = ""
        if posts:
            top = posts[0]
            top_text = top.get("text", "")[:100]
            metrics = top.get("public_metrics", {})
            likes = metrics.get("like_count", 0)
            retweets = metrics.get("retweet_count", 0)
            top_text += f" | ❤️{likes} 🔁{retweets}"
        
        results.append({
            "ticker": ticker,
            "mentions": mention_count,
            "sentiment": sentiment,
            "top_post": top_text
        })
        
        print(f"  {ticker:6} | Mentions: {mention_count:2} | {sentiment} | {top_text[:60]}")
    
    # Save
    out = {"timestamp": timestamp, "results": results}
    os.makedirs("/Users/jos/.hermes/scripts/snapshots", exist_ok=True)
    with open("/Users/jos/.hermes/scripts/snapshots/x_momentum_latest.json", "w") as f:
        json.dump(out, f, indent=2)
    
    print(f"\n💾 Saved to snapshots/x_momentum_latest.json")
    return out

if __name__ == "__main__":
    main()
