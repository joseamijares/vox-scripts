#!/usr/bin/env python3
"""
VOX Reddit Intelligence Agent v2
Monitors subreddits for ticker mentions, sentiment shifts, hype cycles
Uses pushshift.io or redditsearch.io as fallback
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

SCRIPT_DIR = Path.home() / ".hermes/scripts"
REDDIT_DIR = SCRIPT_DIR / "reddit_intelligence"
REDDIT_DIR.mkdir(exist_ok=True)

def fetch_subreddit(subreddit: str, limit: int = 50) -> list:
    """Fetch hot posts from a subreddit via multiple methods."""
    
    # Method 1: Reddit JSON API (may be blocked)
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            return data.get("data", {}).get("children", [])
    except Exception as e:
        print(f"  ⚠️  r/{subreddit}: {e}")
        return []

def extract_tickers(text: str) -> list:
    """Extract ticker symbols from text."""
    import re
    tickers = re.findall(r'\$([A-Z]{1,5})', text)
    standalone = re.findall(r'\b([A-Z]{2,5})\b', text)
    common_words = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'ANY', 'CAN', 'HAD', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'MAN', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'BOY', 'DID', 'ITS', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'DOW', 'NASDAQ', 'NYSE', 'ETF', 'IPO', 'CEO', 'CFO', 'COO', 'USA', 'GDP', 'CPI', 'FED', 'IRS', 'SEC'}
    standalone = [t for t in standalone if t not in common_words and len(t) >= 2]
    return list(set(tickers + standalone))

def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of text."""
    text_lower = text.lower()
    
    bullish = ["moon", "rocket", "tendies", "calls", "long", "buy", "bull", "squeeze", "gamma", "rally", "breakout", "undervalued", "cheap", "discount", "yolo", "all in"]
    bearish = ["puts", "short", "sell", "bear", "crash", "dump", "bagholder", "overvalued", "bubble", "panic", "recession", "rug pull"]
    
    b_score = sum(1 for w in bullish if w in text_lower)
    be_score = sum(1 for w in bearish if w in text_lower)
    
    if b_score > be_score:
        return {"sentiment": "BULLISH", "score": min(100, 50 + (b_score - be_score) * 10)}
    elif be_score > b_score:
        return {"sentiment": "BEARISH", "score": max(0, 50 - (be_score - b_score) * 10)}
    return {"sentiment": "NEUTRAL", "score": 50}

def run_reddit_tracker():
    """Main Reddit tracking loop."""
    
    subreddits = ["wallstreetbets", "stocks", "investing", "wallstreetbetsOGs", "cryptocurrency", "pennystocks"]
    
    ticker_mentions = defaultdict(lambda: {"mentions": 0, "upvotes": 0, "comments": 0, "sentiment_sum": 0, "posts": [], "subreddits": set()})
    
    for subreddit in subreddits:
        posts = fetch_subreddit(subreddit, limit=25)
        
        for post in posts:
            data = post.get("data", {})
            title = data.get("title", "")
            text = data.get("selftext", "")[:500]
            upvotes = data.get("ups", 0)
            num_comments = data.get("num_comments", 0)
            
            tickers = extract_tickers(title + " " + text)
            sentiment = analyze_sentiment(title + " " + text)
            
            for ticker in tickers:
                ticker_mentions[ticker]["mentions"] += 1
                ticker_mentions[ticker]["upvotes"] += upvotes
                ticker_mentions[ticker]["comments"] += num_comments
                ticker_mentions[ticker]["sentiment_sum"] += sentiment["score"]
                ticker_mentions[ticker]["subreddits"].add(subreddit)
                
                if len(ticker_mentions[ticker]["posts"]) < 3:
                    ticker_mentions[ticker]["posts"].append({
                        "title": title[:100],
                        "subreddit": subreddit,
                        "upvotes": upvotes,
                        "sentiment": sentiment["sentiment"]
                    })
    
    # Rank tickers
    ranked = []
    for ticker, data in ticker_mentions.items():
        if data["mentions"] >= 2:
            avg_sentiment = data["sentiment_sum"] / data["mentions"]
            hype_score = min(100, data["mentions"] * 8 + data["upvotes"] / 50 + avg_sentiment / 2)
            
            ranked.append({
                "ticker": ticker,
                "mentions": data["mentions"],
                "upvotes": data["upvotes"],
                "comments": data["comments"],
                "avg_sentiment": round(avg_sentiment, 1),
                "sentiment_label": "BULLISH" if avg_sentiment > 60 else "BEARISH" if avg_sentiment < 40 else "NEUTRAL",
                "hype_score": round(hype_score, 1),
                "subreddits": list(data["subreddits"]),
                "sample_posts": data["posts"]
            })
    
    ranked.sort(key=lambda x: x["hype_score"], reverse=True)
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subreddits_scanned": len(subreddits),
        "total_mentions": sum(r["mentions"] for r in ranked),
        "tickers_tracked": len(ranked),
        "top_mentions": ranked[:25],
        "bullish_tickers": [r for r in ranked if r["sentiment_label"] == "BULLISH"][:10],
        "bearish_tickers": [r for r in ranked if r["sentiment_label"] == "BEARISH"][:10]
    }
    
    with open(REDDIT_DIR / "reddit_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Only print if there are high-hype tickers in portfolio or watchlist
    high_hype = [r for r in ranked if r["hype_score"] >= 60 and r["mentions"] >= 5]
    if high_hype:
        print(f"📱 REDDIT HYPE — {len(high_hype)} tickers trending")
        for r in high_hype[:5]:
            emoji = "🚀" if r["sentiment_label"] == "BULLISH" else "📉"
            print(f"   {emoji} {r['ticker']} | Hype: {r['hype_score']:.0f} | {r['mentions']} mentions")

if __name__ == "__main__":
    run_reddit_tracker()
