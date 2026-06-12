#!/usr/bin/env python3
"""
VOX X Momentum Tracker v2
Scans X/Twitter for ALL portfolio ticker mentions
Reads portfolio from dashboard_positions.json
"""
import os, json, urllib.request
from datetime import datetime
from pathlib import Path

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

ENV = load_env()
BEARER_TOKEN = ENV.get("X_BEARER_TOKEN", "")

def search_x(query, max_results=10):
    """Search X API v2 using bearer token"""
    if not BEARER_TOKEN:
        return [{"text": f"X_BEARER_TOKEN not set", "id": "no_auth"}]
    
    try:
        url = f"https://api.twitter.com/2/tweets/search/recent?query={query.replace(' ', '%20')}&max_results={max_results}&tweet.fields=created_at,public_metrics"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "User-Agent": "Vox-Finance/1.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("data", [])
    except Exception as e:
        return [{"text": f"Error: {str(e)}", "id": "error"}]

def load_portfolio_tickers():
    """Load tickers from portfolio"""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    if not positions_file.exists():
        return []
    
    with open(positions_file) as f:
        data = json.load(f)
    
    tickers = []
    for p in data.get("positions", []):
        t = p.get("ticker", "")
        if t and t not in {"CASH", "USD", "MXN", "CASH_USD", "CASH_MXN"} and len(t) <= 5 and t.isalpha():
            tickers.append(t)
    
    return list(set(tickers))

def analyze_sentiment(text):
    """Simple sentiment analysis with SCORE"""
    text_lower = text.lower()
    bullish = ["bull", "long", "buy", "moon", "rocket", "🚀", "calls", "up", "rally", "breakout", " ath", " ath ", "all time high", "squeeze", "gamma", "tendies"]
    bearish = ["bear", "short", "sell", "dump", "crash", "puts", "down", "tank", "breakdown", "rug", "pullback", "correction", "overvalued"]
    
    b_score = sum(1 for w in bullish if w in text_lower)
    be_score = sum(1 for w in bearish if w in text_lower)
    
    # Calculate net sentiment score (-10 to +10 range)
    net_score = b_score - be_score
    
    if b_score > be_score:
        return "BULLISH", net_score
    elif be_score > b_score:
        return "BEARISH", net_score
    return "NEUTRAL", 0

def calculate_momentum_score(mentions, sentiment, bull_count, bear_count, top_likes):
    """Calculate momentum score 0-100 based on activity and sentiment"""
    # Base score from mention volume (0-40)
    volume_score = min(40, mentions * 4)
    
    # Sentiment score (0-30)
    if sentiment == "BULLISH":
        sent_score = 30
    elif sentiment == "BEARISH":
        sent_score = 10
    else:
        sent_score = 20
    
    # Engagement score from likes (0-20)
    engagement_score = min(20, top_likes / 10)
    
    # Consensus score (0-10)
    total = bull_count + bear_count
    if total > 0:
        if sentiment == "BULLISH":
            consensus = (bull_count / total) * 10
        else:
            consensus = (bear_count / total) * 10
    else:
        consensus = 5
    
    return volume_score + sent_score + engagement_score + consensus

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"🐦 VOX X MOMENTUM TRACKER — {timestamp}")
    print("=" * 60)
    
    tickers = load_portfolio_tickers()
    print(f"Portfolio tickers: {len(tickers)}")
    
    if not BEARER_TOKEN:
        print("❌ X_BEARER_TOKEN not found in ~/.hermes/.env")
        return
    
    results = []
    
    for ticker in tickers:
        query = f"${ticker}"
        posts = search_x(query, max_results=10)
        
        if not posts or posts[0].get("id") in {"no_auth", "error"}:
            continue
        
        mention_count = len(posts)
        
        # Analyze sentiment across all posts
        sentiments = []
        top_post = ""
        top_likes = 0
        
        for post in posts:
            text = post.get("text", "")
            metrics = post.get("public_metrics", {})
            likes = metrics.get("like_count", 0)
            
            sent, score = analyze_sentiment(text)
            sentiments.append((sent, score))
            
            if likes > top_likes:
                top_likes = likes
                top_post = text[:120]
        
        # Aggregate sentiment
        bull_count = sum(1 for s, _ in sentiments if s == "BULLISH")
        bear_count = sum(1 for s, _ in sentiments if s == "BEARISH")
        
        if bull_count > bear_count:
            sentiment = "BULLISH"
        elif bear_count > bull_count:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"
        
        # Only save if there's actual activity AND post mentions ticker
        if mention_count >= 2:
            momentum_score = calculate_momentum_score(mention_count, sentiment, bull_count, bear_count, top_likes)
            
            # Validate: check if ANY post actually mentions ticker by name (not just $ symbol match)
            import re
            # Ticker must appear as standalone word or $ prefix in the text
            ticker_pattern = rf'(?:\$|\b){re.escape(ticker)}\b'
            validated = any(bool(re.search(ticker_pattern, post.get("text", ""), re.IGNORECASE)) for post in posts)
            
            # Only include validated results in the main feed
            # But save unvalidated for debugging
            results.append({
                "ticker": ticker,
                "mentions": mention_count,
                "sentiment": sentiment,
                "score": momentum_score,
                "bullish_posts": bull_count,
                "bearish_posts": bear_count,
                "top_post": top_post,
                "top_likes": top_likes,
                "validated": validated
            })
            
            # Only print validated results (skip spam)
            if validated:
                emoji = "🟢" if sentiment == "BULLISH" else "🔴" if sentiment == "BEARISH" else "⚪"
                print(f"  {emoji} {ticker:6} | {mention_count:2d} mentions | {sentiment:8} | score:{momentum_score:3.0f} | ✓ | {top_post[:35]}...")
            else:
                print(f"  ⚪ {ticker:6} | {mention_count:2d} mentions | {sentiment:8} | score:{momentum_score:3.0f} | ✗ SPAM | {top_post[:35]}...")
    
    # Save
    out = {"timestamp": timestamp, "results": results}
    os.makedirs("/Users/jos/.hermes/scripts/snapshots", exist_ok=True)
    with open("/Users/jos/.hermes/scripts/snapshots/x_momentum_latest.json", "w") as f:
        json.dump(out, f, indent=2)
    
    print(f"\n💾 Saved {len(results)} tickers with activity to snapshots/x_momentum_latest.json")
    return out

if __name__ == "__main__":
    main()
