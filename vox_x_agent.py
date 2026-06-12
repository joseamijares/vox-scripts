#!/usr/bin/env python3
"""
VOX X/Twitter Intelligence Agent v2
Monitors X for ticker mentions, sentiment, influencer activity
Tracks: volume, sentiment shifts, key accounts, trending topics
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

SCRIPT_DIR = Path.home() / ".hermes/scripts"
X_DIR = SCRIPT_DIR / "x_intelligence"
X_DIR.mkdir(exist_ok=True)

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

def search_x(query: str, max_results: int = 50) -> list:
    """Search X/Twitter via API."""
    env = load_env()
    bearer = env.get("X_BEARER_TOKEN", "")
    
    if not bearer:
        return []
    
    url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&max_results={max_results}&tweet.fields=created_at,public_metrics,author_id"
    headers = {"Authorization": f"Bearer {bearer}"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            return data.get("data", [])
    except Exception as e:
        print(f"[X] API error: {e}")
        return []

def analyze_x_sentiment(text: str) -> dict:
    """Analyze X post sentiment."""
    text_lower = text.lower()
    
    bullish = ["bull", "long", "buy", "moon", "rocket", "breakout", "support", "accumulate", "undervalued"]
    bearish = ["bear", "short", "sell", "dump", "crash", "resistance", "bubble", "overvalued", "distribution"]
    
    b = sum(1 for w in bullish if w in text_lower)
    be = sum(1 for w in bearish if w in text_lower)
    
    engagement_words = ["🚀", "📈", "💰", "🔥", "💎", "🙌", "👀"]
    engagement = sum(1 for w in engagement_words if w in text)
    
    if b > be:
        return {"sentiment": "BULLISH", "score": min(100, 60 + b * 5 + engagement * 3)}
    elif be > b:
        return {"sentiment": "BEARISH", "score": max(0, 40 - be * 5)}
    return {"sentiment": "NEUTRAL", "score": 50 + engagement * 2}

def run_x_tracker():
    """Main X tracking loop."""
    
    # Load portfolio + watchlist tickers
    tickers = set()
    
    portfolio_file = SCRIPT_DIR / "dashboard_positions_live.json"
    if portfolio_file.exists():
        with open(portfolio_file) as f:
            data = json.load(f)
            for p in data.get("positions", []):
                tickers.add(p.get("ticker", ""))
    
    # Add watchlist
    try:
        from vox_supabase_sync import get_client
        sb = get_client()
        result = sb.table('watchlist').select('ticker').execute()
        for w in result.data:
            tickers.add(w.get('ticker', ''))
    except:
        pass
    
    tickers = [t for t in tickers if t and len(t) <= 5 and t not in ['CASH', 'USD']]
    
    ticker_data = defaultdict(lambda: {"mentions": 0, "engagement": 0, "sentiment_sum": 0, "bullish": 0, "bearish": 0, "posts": []})
    
    for ticker in tickers[:20]:  # Top 20 for API limits
        try:
            tweets = search_x(f"${ticker} -is:retweet", max_results=20)
            
            for tweet in tweets:
                text = tweet.get("text", "")
                metrics = tweet.get("public_metrics", {})
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)
                total_engagement = likes + retweets
                
                sentiment = analyze_x_sentiment(text)
                
                ticker_data[ticker]["mentions"] += 1
                ticker_data[ticker]["engagement"] += total_engagement
                ticker_data[ticker]["sentiment_sum"] += sentiment["score"]
                
                if sentiment["sentiment"] == "BULLISH":
                    ticker_data[ticker]["bullish"] += 1
                elif sentiment["sentiment"] == "BEARISH":
                    ticker_data[ticker]["bearish"] += 1
                
                if len(ticker_data[ticker]["posts"]) < 2:
                    ticker_data[ticker]["posts"].append({
                        "text": text[:120],
                        "engagement": total_engagement,
                        "sentiment": sentiment["sentiment"]
                    })
                    
        except:
            pass
    
    # Rank
    ranked = []
    for ticker, data in ticker_data.items():
        if data["mentions"] >= 2:
            avg_sentiment = data["sentiment_sum"] / data["mentions"]
            momentum = min(100, data["mentions"] * 5 + data["engagement"] / 20 + avg_sentiment / 2)
            
            ranked.append({
                "ticker": ticker,
                "mentions": data["mentions"],
                "engagement": data["engagement"],
                "avg_sentiment": round(avg_sentiment, 1),
                "sentiment_label": "BULLISH" if avg_sentiment > 60 else "BEARISH" if avg_sentiment < 40 else "NEUTRAL",
                "bullish_posts": data["bullish"],
                "bearish_posts": data["bearish"],
                "momentum_score": round(momentum, 1),
                "sample_posts": data["posts"]
            })
    
    ranked.sort(key=lambda x: x["momentum_score"], reverse=True)
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tickers_scanned": len(tickers),
        "tickers_with_mentions": len(ranked),
        "total_mentions": sum(r["mentions"] for r in ranked),
        "results": ranked[:25],
        "trending_bullish": [r for r in ranked if r["sentiment_label"] == "BULLISH"][:10],
        "trending_bearish": [r for r in ranked if r["sentiment_label"] == "BEARISH"][:10]
    }
    
    with open(X_DIR / "x_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Only print if there are trending tickers with momentum >= 60
    trending = [r for r in ranked if r["momentum_score"] >= 60]
    if trending:
        print(f"🐦 X MOMENTUM — {len(trending)} tickers trending")
        for r in trending[:5]:
            emoji = "🚀" if r["sentiment_label"] == "BULLISH" else "📉"
            print(f"   {emoji} {r['ticker']} | Mom: {r['momentum_score']:.0f} | {r['mentions']} posts")

if __name__ == "__main__":
    run_x_tracker()
