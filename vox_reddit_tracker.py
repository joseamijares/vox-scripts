#!/usr/bin/env python3
"""
VOX Reddit Tracker v1.0
Scans subreddits for sentiment, trending tickers, and real intel

Monitored subreddits:
- r/wallstreetbets (sentiment, meme stocks)
- r/stocks (general discussion)
- r/investing (long-term thesis)
- r/SecurityAnalysis (deep dives)
- r/options (flow discussion)
- r/CryptoCurrency (crypto intel)

Usage:
    python3 vox_reddit_tracker.py --scan
    python3 vox_reddit_tracker.py --ticker NVDA
    python3 vox_reddit_tracker.py --subreddit wallstreetbets --limit 50
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import Counter

# Reddit API (no auth needed for public read)
REDDIT_API = "https://www.reddit.com"
USER_AGENT = "VOX-Tracker/1.0 (by /u/vox-trader)"

# Subreddits to monitor
DEFAULT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "SecurityAnalysis",
    "options",
    "CryptoCurrency",
    "pennystocks",
    "SPACs",
]

# Tickers in portfolio (for relevance scoring)
PORTFOLIO_TICKERS = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "CRM",
                     "PLTR", "CRWD", "OKLO", "CEG", "VST", "BYND", "OSCR", "JMIA", "BTC", "ETH"}


def reddit_request(endpoint: str) -> Dict:
    """Make Reddit API request with browser-like headers"""
    url = f"{REDDIT_API}{endpoint}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            # Handle gzip
            if resp.headers.get('Content-Encoding') == 'gzip':
                import gzip
                data = gzip.decompress(data)
            return json.loads(data)
    except Exception as e:
        print(f"Reddit API error: {e}")
        return {}


def extract_tickers(text: str) -> List[str]:
    """Extract stock tickers from text"""
    # Match $TICKER or standalone ALL-CAPS 1-5 chars
    patterns = [
        r'\$([A-Z]{1,5})',
        r'\b([A-Z]{2,5})\b',
    ]
    tickers = []
    for pattern in patterns:
        tickers.extend(re.findall(pattern, text))
    
    # Filter out common words
    common = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "USE", "DOW", "NASDAQ", "SPY", "QQQ", "ETF", "IPO", "CEO", "CFO", "EPS", "PE", "ATH", "DD", "YOLO", "FOMO", "ATH"}
    return list(set(t.upper() for t in tickers if t.upper() not in common and len(t) >= 2))


def analyze_sentiment(text: str) -> float:
    """Simple sentiment analysis"""
    bullish = ["bull", "long", "buy", "moon", "rocket", "tendies", "calls", "undervalued", "cheap", "discount", "opportunity", "growth", "beat", "strong", "bullish", "pump"]
    bearish = ["bear", "short", "sell", "crash", "dump", "puts", "overvalued", "expensive", "bubble", "recession", "weak", "bearish", "crash", "rug", "fraud", "scam"]
    
    text_lower = text.lower()
    bull_count = sum(1 for w in bullish if w in text_lower)
    bear_count = sum(1 for w in bearish if w in text_lower)
    
    total = bull_count + bear_count
    if total == 0:
        return 50  # Neutral
    
    return (bull_count / total) * 100


def get_subreddit_posts(subreddit: str, limit: int = 25, sort: str = "hot") -> List[Dict]:
    """Get posts from a subreddit"""
    data = reddit_request(f"/r/{subreddit}/{sort}.json?limit={limit}")
    
    if not data or "data" not in data:
        return []
    
    posts = []
    for child in data["data"].get("children", []):
        post = child["data"]
        posts.append({
            "title": post.get("title", ""),
            "text": post.get("selftext", ""),
            "author": post.get("author", ""),
            "score": post.get("score", 0),
            "comments": post.get("num_comments", 0),
            "upvote_ratio": post.get("upvote_ratio", 0),
            "created_utc": post.get("created_utc", 0),
            "url": f"https://reddit.com{post.get('permalink', '')}",
            "subreddit": subreddit,
        })
    
    return posts


def scan_all_subreddits() -> Dict:
    """Scan all monitored subreddits"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "subreddits": {},
        "ticker_mentions": Counter(),
        "sentiment_by_ticker": {},
        "top_posts": [],
    }
    
    for subreddit in DEFAULT_SUBREDDITS:
        print(f"Scanning r/{subreddit}...")
        posts = get_subreddit_posts(subreddit, limit=25)
        
        sub_data = {
            "posts_scanned": len(posts),
            "ticker_mentions": Counter(),
            "avg_sentiment": 50,
        }
        
        sentiments = []
        for post in posts:
            text = f"{post['title']} {post['text']}"
            tickers = extract_tickers(text)
            sentiment = analyze_sentiment(text)
            sentiments.append(sentiment)
            
            for ticker in tickers:
                results["ticker_mentions"][ticker] += 1
                sub_data["ticker_mentions"][ticker] += 1
                
                if ticker not in results["sentiment_by_ticker"]:
                    results["sentiment_by_ticker"][ticker] = []
                results["sentiment_by_ticker"][ticker].append({
                    "sentiment": sentiment,
                    "score": post["score"],
                    "subreddit": subreddit,
                    "title": post["title"][:100],
                })
            
            # Track top posts mentioning portfolio tickers
            portfolio_mentions = set(tickers) & PORTFOLIO_TICKERS
            if portfolio_mentions and post["score"] > 10:
                results["top_posts"].append({
                    **post,
                    "tickers": list(portfolio_mentions),
                    "sentiment": sentiment,
                })
        
        if sentiments:
            sub_data["avg_sentiment"] = sum(sentiments) / len(sentiments)
        
        results["subreddits"][subreddit] = sub_data
    
    # Sort top posts by score
    results["top_posts"].sort(key=lambda x: x["score"], reverse=True)
    results["top_posts"] = results["top_posts"][:20]
    
    # Calculate average sentiment per ticker
    for ticker, mentions in results["sentiment_by_ticker"].items():
        avg_sent = sum(m["sentiment"] for m in mentions) / len(mentions)
        total_score = sum(m["score"] for m in mentions)
        results["sentiment_by_ticker"][ticker] = {
            "mentions": len(mentions),
            "avg_sentiment": avg_sent,
            "total_score": total_score,
            "posts": mentions[:5],
        }
    
    return results


def export_report(results: Dict, filepath: str):
    """Export scan results to JSON"""
    # Convert Counter to dict for JSON serialization
    results["ticker_mentions"] = dict(results["ticker_mentions"])
    for sub in results["subreddits"]:
        results["subreddits"][sub]["ticker_mentions"] = dict(results["subreddits"][sub]["ticker_mentions"])
    
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nReport exported to {filepath}")


def print_summary(results: Dict):
    """Print summary to console"""
    print("\n" + "="*60)
    print("REDDIT TRACKER SUMMARY")
    print("="*60)
    
    print("\n📊 Top Mentioned Tickers:")
    top_tickers = Counter(results["ticker_mentions"]).most_common(15)
    for ticker, count in top_tickers:
        sent_data = results["sentiment_by_ticker"].get(ticker, {})
        sent = sent_data.get("avg_sentiment", 50)
        emoji = "🟢" if sent > 60 else "🔴" if sent < 40 else "⚪"
        print(f"  {emoji} {ticker:6} | {count:3} mentions | Sentiment: {sent:.0f}")
    
    print("\n🔥 Top Posts (Portfolio Mentions):")
    for post in results["top_posts"][:10]:
        emoji = "🟢" if post["sentiment"] > 60 else "🔴" if post["sentiment"] < 40 else "⚪"
        print(f"  {emoji} r/{post['subreddit']:20} | Score: {post['score']:4} | {post['title'][:60]}")
        print(f"      Tickers: {', '.join(post['tickers'])} | {post['url']}")
    
    print("\n📈 Subreddit Sentiment:")
    for sub, data in results["subreddits"].items():
        sent = data["avg_sentiment"]
        emoji = "🟢" if sent > 60 else "🔴" if sent < 40 else "⚪"
        print(f"  {emoji} r/{sub:20} | Avg Sentiment: {sent:.0f} | Posts: {data['posts_scanned']}")


def main():
    parser = argparse.ArgumentParser(description="VOX Reddit Tracker")
    parser.add_argument("--scan", action="store_true", help="Scan all subreddits")
    parser.add_argument("--ticker", help="Filter by ticker")
    parser.add_argument("--subreddit", help="Scan specific subreddit")
    parser.add_argument("--limit", type=int, default=25, help="Posts per subreddit")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    if args.subreddit:
        posts = get_subreddit_posts(args.subreddit, args.limit)
        print(f"\n=== r/{args.subreddit} ===\n")
        for post in posts[:10]:
            tickers = extract_tickers(post["title"] + " " + post["text"])
            print(f"  [{post['score']}] {post['title'][:80]}")
            if tickers:
                print(f"      Tickers: {', '.join(tickers)}")
    
    elif args.ticker:
        print(f"\n=== Scanning for {args.ticker} ===\n")
        results = scan_all_subreddits()
        ticker_data = results["sentiment_by_ticker"].get(args.ticker.upper(), {})
        if ticker_data:
            print(f"Mentions: {ticker_data['mentions']}")
            print(f"Avg Sentiment: {ticker_data['avg_sentiment']:.0f}")
            print(f"\nTop Posts:")
            for post in ticker_data["posts"]:
                print(f"  [{post['score']}] {post['title']}")
        else:
            print("No mentions found")
    
    elif args.scan:
        results = scan_all_subreddits()
        print_summary(results)
        
        if args.output:
            export_report(results, args.output)
        else:
            default_output = os.path.expanduser("~/.hermes/scripts/vox_reddit_report.json")
            export_report(results, default_output)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
