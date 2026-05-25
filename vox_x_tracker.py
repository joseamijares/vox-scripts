#!/usr/bin/env python3
"""
VOX X/Twitter Tracker v1.0
Monitors X/Twitter for sentiment, trending tickers, and market intel

Uses X API v2 (requires bearer token) or falls back to web scraping

Features:
- Search by ticker, keyword, or hashtag
- Sentiment analysis
- Portfolio-relevant filtering
- Trending topics detection

Usage:
    python3 vox_x_tracker.py --search NVDA --limit 20
    python3 vox_x_tracker.py --trending
    python3 vox_x_tracker.py --scan-portfolio
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import re
from datetime import datetime
from typing import Dict, List
from collections import Counter

# Portfolio tickers
PORTFOLIO_TICKERS = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "CRM",
                     "PLTR", "CRWD", "OKLO", "CEG", "VST", "BYND", "OSCR", "JMIA", "BTC", "ETH"}


def load_bearer_token() -> str:
    """Load X API bearer token from .env"""
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("X_BEARER_TOKEN="):
                    return line.strip().split("=", 1)[1]
    return ""


def x_api_search(query: str, bearer_token: str, limit: int = 20) -> List[Dict]:
    """Search X via API v2"""
    if not bearer_token:
        return []
    
    url = f"https://api.twitter.com/2/tweets/search/recent?query={urllib.parse.quote(query)}&max_results={min(limit, 100)}&tweet.fields=created_at,public_metrics,author_id"
    
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "VOX-Tracker/1.0"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            tweets = data.get("data", [])
            return [{
                "text": t["text"],
                "id": t["id"],
                "created_at": t.get("created_at", ""),
                "likes": t.get("public_metrics", {}).get("like_count", 0),
                "retweets": t.get("public_metrics", {}).get("retweet_count", 0),
                "source": "x_api",
            } for t in tweets]
    except Exception as e:
        print(f"X API error: {e}")
        return []


def x_scrape_search(query: str, limit: int = 20) -> List[Dict]:
    """Search X via web scraping (fallback)"""
    # Try multiple X frontends
    instances = [
        f"https://nitter.net/search?f=tweets&q={urllib.parse.quote(query)}&n={limit}",
        f"https://nitter.it/search?f=tweets&q={urllib.parse.quote(query)}&n={limit}",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    for url in instances:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                
                # Parse tweets from nitter HTML
                tweets = []
                # Look for tweet text in timeline items
                timeline_items = re.findall(r'<timeline-item[^\u003e]*>(.*?)</timeline-item>', html, re.DOTALL)
                
                for item in timeline_items[:limit]:
                    # Extract tweet text
                    text_match = re.search(r'<div class="tweet-content[^"]*">.*?<div class="tweet-body[^"]*"><div[^\u003e]*>(.*?)</div>', item, re.DOTALL)
                    if text_match:
                        text = re.sub(r'<[^>]+>', '', text_match.group(1))
                        text = re.sub(r'\s+', ' ', text).strip()
                        
                        # Extract stats
                        likes = re.search(r'likes[^\u003e]*>([\d,]+)', item)
                        retweets = re.search(r'retweets[^\u003e]*>([\d,]+)', item)
                        
                        if text and len(text) > 10:
                            tweets.append({
                                "text": text,
                                "likes": int(likes.group(1).replace(",", "")) if likes else 0,
                                "retweets": int(retweets.group(1).replace(",", "")) if retweets else 0,
                                "source": "nitter",
                            })
                
                if tweets:
                    return tweets
        except Exception:
            continue
    
    return []


def search_x(query: str, limit: int = 20) -> List[Dict]:
    """Search X with API fallback to scraping"""
    bearer = load_bearer_token()
    
    if bearer:
        tweets = x_api_search(query, bearer, limit)
        if tweets:
            return tweets
    
    return x_scrape_search(query, limit)


def extract_tickers(text: str) -> List[str]:
    """Extract stock tickers from text"""
    patterns = [r'\$([A-Z]{1,5})', r'\b([A-Z]{2,5})\b']
    tickers = []
    for pattern in patterns:
        tickers.extend(re.findall(pattern, text))
    
    common = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "USE", "DOW", "NASDAQ", "SPY", "QQQ", "ETF", "IPO", "CEO", "CFO", "EPS", "PE", "ATH", "DD", "YOLO", "FOMO", "AI", "USA", "US", "UK", "EU", "GDP", "CPI", "FED", "SEC", "THEY", "THEM", "THAN", "THEN", "THAT", "THIS", "WITH", "HAVE", "FROM", "WILL", "BEEN", "SAID", "EACH", "WHICH", "THEIR", "TIME", "WOULD", "THERE", "COULD", "SHOULD"}
    return list(set(t.upper() for t in tickers if t.upper() not in common and len(t) >= 2))


def analyze_sentiment(text: str) -> float:
    """Simple sentiment analysis"""
    bullish = ["bull", "long", "buy", "moon", "rocket", "calls", "undervalued", "cheap", "discount", "opportunity", "growth", "beat", "strong", "bullish", "pump", "accumulate", "load", "dip", "support", "breakout", "rally", "surge", "soar", "gain", "up", "rise", "pop"]
    bearish = ["bear", "short", "sell", "crash", "dump", "puts", "overvalued", "expensive", "bubble", "recession", "weak", "bearish", "rug", "fraud", "scam", "avoid", "stay away", "correction", "pullback", "resistance", "drop", "fall", "decline", "down", "lose", "loss", "crash"]
    
    text_lower = text.lower()
    bull_count = sum(1 for w in bullish if w in text_lower)
    bear_count = sum(1 for w in bearish if w in text_lower)
    
    total = bull_count + bear_count
    if total == 0:
        return 50
    return (bull_count / total) * 100


def scan_portfolio():
    """Scan X for portfolio tickers"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "ticker_mentions": Counter(),
        "sentiment_by_ticker": {},
        "top_tweets": [],
    }
    
    for ticker in sorted(PORTFOLIO_TICKERS):
        print(f"Scanning ${ticker}...")
        tweets = search_x(f"${ticker}", limit=10)
        
        for tweet in tweets:
            text = tweet["text"]
            sentiment = analyze_sentiment(text)
            tickers = extract_tickers(text)
            
            for t in tickers:
                results["ticker_mentions"][t] += 1
                if t not in results["sentiment_by_ticker"]:
                    results["sentiment_by_ticker"][t] = []
                results["sentiment_by_ticker"][t].append(sentiment)
            
            if ticker in tickers and len(text) > 20:
                results["top_tweets"].append({
                    "text": text[:200],
                    "ticker": ticker,
                    "sentiment": sentiment,
                    "likes": tweet.get("likes", 0),
                    "source": tweet.get("source", "unknown"),
                })
    
    for ticker, sentiments in results["sentiment_by_ticker"].items():
        results["sentiment_by_ticker"][ticker] = {
            "mentions": len(sentiments),
            "avg_sentiment": sum(sentiments) / len(sentiments),
        }
    
    results["top_tweets"].sort(key=lambda x: abs(x["sentiment"] - 50), reverse=True)
    results["top_tweets"] = results["top_tweets"][:20]
    
    return results


def print_summary(results: Dict):
    print("\n" + "="*60)
    print("X/TWITTER TRACKER SUMMARY")
    print("="*60)
    
    print("\n📊 Top Mentioned Tickers:")
    for ticker, count in results["ticker_mentions"].most_common(15):
        sent_data = results["sentiment_by_ticker"].get(ticker, {})
        sent = sent_data.get("avg_sentiment", 50)
        emoji = "🟢" if sent > 60 else "🔴" if sent < 40 else "⚪"
        print(f"  {emoji} ${ticker:6} | {count:3} mentions | Sentiment: {sent:.0f}")
    
    print("\n🔥 Top Tweets (Portfolio):")
    for tweet in results["top_tweets"][:10]:
        emoji = "🟢" if tweet["sentiment"] > 60 else "🔴" if tweet["sentiment"] < 40 else "⚪"
        print(f"  {emoji} ${tweet['ticker']:6} | {tweet['text'][:70]}...")
        print(f"      ❤️ {tweet.get('likes', 0)} | Source: {tweet.get('source', 'unknown')}")


def export_report(results: Dict, filepath: str):
    results["ticker_mentions"] = dict(results["ticker_mentions"])
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nReport exported to {filepath}")


def main():
    parser = argparse.ArgumentParser(description="VOX X/Twitter Tracker")
    parser.add_argument("--search", help="Search query")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--scan-portfolio", action="store_true")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    if args.search:
        print(f"Searching X for: {args.search}")
        tweets = search_x(args.search, args.limit)
        for tweet in tweets[:10]:
            print(f"\n{tweet['text'][:200]}")
            tickers = extract_tickers(tweet["text"])
            if tickers:
                print(f"  Tickers: {', '.join(tickers)}")
            print(f"  ❤️ {tweet.get('likes', 0)} | Source: {tweet.get('source', 'unknown')}")
    
    elif args.scan_portfolio:
        results = scan_portfolio()
        print_summary(results)
        
        if args.output:
            export_report(results, args.output)
        else:
            export_report(results, os.path.expanduser("~/.hermes/scripts/vox_x_report.json"))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
