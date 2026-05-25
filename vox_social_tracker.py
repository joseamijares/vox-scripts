#!/usr/bin/env python3
"""
VOX Social Media Tracker v1.0
Unified Reddit + X/Twitter sentiment tracker

Uses free APIs and web scraping. No paid keys required for basic functionality.

Features:
- Reddit: r/wallstreetbets, r/stocks, r/investing, r/options, r/CryptoCurrency
- X/Twitter: Search via xurl CLI or web scraping
- Sentiment analysis per ticker
- Portfolio-relevant filtering
- Daily reports

Usage:
    python3 vox_social_tracker.py --reddit
    python3 vox_social_tracker.py --x-search "NVDA"
    python3 vox_social_tracker.py --full-scan
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error
import re
import subprocess
from datetime import datetime
from typing import Dict, List
from collections import Counter

PORTFOLIO_TICKERS = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "CRM",
                     "PLTR", "CRWD", "OKLO", "CEG", "VST", "BYND", "OSCR", "JMIA", "BTC", "ETH"}

REDDIT_SUBREDDITS = ["wallstreetbets", "stocks", "investing", "options", "CryptoCurrency"]


def reddit_request(endpoint: str) -> Dict:
    """Make Reddit API request with full browser headers"""
    url = f"https://www.reddit.com{endpoint}"
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
            if resp.headers.get('Content-Encoding') == 'gzip':
                import gzip
                data = gzip.decompress(data)
            return json.loads(data)
    except Exception as e:
        return {}


def get_reddit_posts(subreddit: str, limit: int = 25) -> List[Dict]:
    data = reddit_request(f"/r/{subreddit}/hot.json?limit={limit}")
    posts = []
    for child in data.get("data", {}).get("children", []):
        p = child["data"]
        posts.append({
            "title": p.get("title", ""),
            "text": p.get("selftext", ""),
            "score": p.get("score", 0),
            "comments": p.get("num_comments", 0),
            "subreddit": subreddit,
        })
    return posts


def extract_tickers(text: str) -> List[str]:
    patterns = [r'\$([A-Z]{1,5})', r'\b([A-Z]{2,5})\b']
    tickers = []
    for pattern in patterns:
        tickers.extend(re.findall(pattern, text))
    common = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "USE", "DOW", "NASDAQ", "SPY", "QQQ", "ETF", "IPO", "CEO", "CFO", "EPS", "PE", "ATH", "DD", "YOLO", "FOMO", "AI", "USA", "US", "UK", "EU", "GDP", "CPI", "FED", "SEC", "THEY", "THEM", "THAN", "THEN", "THAT", "THIS", "WITH", "HAVE", "FROM", "WILL", "BEEN", "SAID", "EACH", "WHICH", "THEIR", "TIME", "WOULD", "THERE", "COULD", "SHOULD", "VERY", "MUCH", "MORE", "MOST", "SOME", "ONLY", "JUST", "ALSO", "BACK", "AFTER", "FIRST", "WELL", "YEAR", "WORK", "WHERE", "BEING", "EVERY", "GOOD", "ANY", "SAME", "RIGHT", "THINK", "TAKE", "COME", "KNOW", "LAST", "OVER", "BEFORE", "LIFE", "EVEN", "HERE", "BOTH", "TOO", "OFF", "OWN", "UNDER", "NEVER", "ALWAYS", "GREAT", "THREE", "MADE", "MAKE", "PART", "MAY", "SUCH", "LOOK", "FIND", "GIVE", "DOES", "DONE", "WANT", "BETWEEN", "PLACE", "HAND", "HIGH", "SURE", "HEAD", "HELP", "HOME", "SIDE", "MOVE", "BOTH", "FIVE", "ONCE", "UPON", "ABOUT", "INTO", "THROUGH", "DURING", "ABOVE", "BELOW", "AROUND", "NEAR", "FAR", "BECAUSE", "WHILE", "UNTIL", "SINCE", "ALTHOUGH", "THOUGH", "HOWEVER", "THEREFORE", "THUS", "HENCE", "MEANWHILE", "INSTEAD", "OTHERWISE", "MOREOVER", "FURTHERMORE", "NEVERTHELESS", "NONETHELESS", "REGARDLESS", "NOTWITHSTANDING", "WHEREAS", "WHEREVER", "WHENEVER", "HOWSOEVER", "WHATSOEVER", "WHOSOEVER", "WHOMSOEVER", "WHERESOEVER", "WHENSOEVER", "HOWSOEVER", "NOT", "NO", "YES", "OK", "OKAY", "YEAH", "YEP", "NOPE", "NAH", "YUP", "HUH", "WOW", "OMG", "LOL", "LMAO", "ROFL", "WTF", "WTH", "FTW", "FML", "SMH", "TBH", "IMO", "IMHO", "TLDR", "TL;DR", "AFAIK", "IIRC", "FWIW", "BTW", "FYI", "ASAP", "ETA", "ETD", "TBD", "TBA", "N/A", "NA", "TBD", "TBA", "ETA", "ETD", "ASAP", "FYI", "BTW", "FWIW", "IIRC", "AFAIK", "TLDR", "TL;DR", "IMHO", "IMO", "TBH", "SMH", "FML", "FTW", "WTH", "WTF", "ROFL", "LMAO", "LOL", "OMG", "WOW", "HUH", "YUP", "NOPE", "NAH", "YEP", "YEAH", "OKAY", "OK", "YES", "NO"}
    return list(set(t.upper() for t in tickers if t.upper() not in common and len(t) >= 2))


def analyze_sentiment(text: str) -> float:
    bullish = ["bull", "long", "buy", "moon", "rocket", "calls", "undervalued", "cheap", "discount", "opportunity", "growth", "beat", "strong", "bullish", "pump", "accumulate", "load", "dip", "support", "breakout", "rally", "surge", "soar", "gain", "up", "rise", "pop", "green", "outperform", "upgrade", "target raised", "price target", "conviction", "core holding"]
    bearish = ["bear", "short", "sell", "crash", "dump", "puts", "overvalued", "expensive", "bubble", "recession", "weak", "bearish", "rug", "fraud", "scam", "avoid", "stay away", "correction", "pullback", "resistance", "drop", "fall", "decline", "down", "lose", "loss", "crash", "red", "underperform", "downgrade", "target cut", "sell rating", "cut", "trim", "reduce"]
    text_lower = text.lower()
    bull_count = sum(1 for w in bullish if w in text_lower)
    bear_count = sum(1 for w in bearish if w in text_lower)
    total = bull_count + bear_count
    if total == 0:
        return 50
    return (bull_count / total) * 100


def scan_reddit() -> Dict:
    """Scan Reddit for portfolio tickers"""
    print("=== Scanning Reddit ===\n")
    results = {
        "source": "reddit",
        "timestamp": datetime.now().isoformat(),
        "ticker_mentions": Counter(),
        "sentiment_by_ticker": {},
        "top_posts": [],
    }
    
    for subreddit in REDDIT_SUBREDDITS:
        print(f"  r/{subreddit}...")
        posts = get_reddit_posts(subreddit, limit=25)
        print(f"    Got {len(posts)} posts")
        
        for post in posts:
            text = f"{post['title']} {post['text']}"
            tickers = extract_tickers(text)
            sentiment = analyze_sentiment(text)
            
            for ticker in tickers:
                results["ticker_mentions"][ticker] += 1
                if ticker not in results["sentiment_by_ticker"]:
                    results["sentiment_by_ticker"][ticker] = []
                results["sentiment_by_ticker"][ticker].append(sentiment)
            
            portfolio_mentions = set(tickers) & PORTFOLIO_TICKERS
            if portfolio_mentions and post["score"] > 10:
                results["top_posts"].append({
                    "title": post["title"][:100],
                    "tickers": list(portfolio_mentions),
                    "sentiment": sentiment,
                    "score": post["score"],
                    "subreddit": subreddit,
                })
    
    for ticker, sentiments in results["sentiment_by_ticker"].items():
        results["sentiment_by_ticker"][ticker] = {
            "mentions": len(sentiments),
            "avg_sentiment": sum(sentiments) / len(sentiments),
        }
    
    results["top_posts"].sort(key=lambda x: x["score"], reverse=True)
    results["top_posts"] = results["top_posts"][:20]
    
    print(f"\n  Found {len(results['ticker_mentions'])} unique tickers")
    print(f"  Found {len(results['top_posts'])} portfolio-related posts")
    
    return results


def scan_x_twitter() -> Dict:
    """Scan X/Twitter using xurl CLI if available"""
    print("\n=== Scanning X/Twitter ===\n")
    results = {
        "source": "x_twitter",
        "timestamp": datetime.now().isoformat(),
        "ticker_mentions": Counter(),
        "sentiment_by_ticker": {},
        "top_tweets": [],
    }
    
    # Check if xurl CLI is available
    try:
        result = subprocess.run(["which", "xurl"], capture_output=True, text=True)
        has_xurl = result.returncode == 0
    except:
        has_xurl = False
    
    if not has_xurl:
        print("  xurl CLI not found. Install with: npm install -g xurl")
        print("  Skipping X/Twitter scan.")
        return results
    
    for ticker in sorted(PORTFOLIO_TICKERS)[:10]:
        print(f"  ${ticker}...")
        try:
            result = subprocess.run(
                ["xurl", "search", f"${ticker}", "--limit", "10"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                tweets = json.loads(result.stdout)
                for tweet in tweets:
                    text = tweet.get("text", "")
                    sentiment = analyze_sentiment(text)
                    tickers = extract_tickers(text)
                    
                    for t in tickers:
                        results["ticker_mentions"][t] += 1
                        if t not in results["sentiment_by_ticker"]:
                            results["sentiment_by_ticker"][t] = []
                        results["sentiment_by_ticker"][t].append(sentiment)
                    
                    if ticker in tickers:
                        results["top_tweets"].append({
                            "text": text[:150],
                            "ticker": ticker,
                            "sentiment": sentiment,
                            "likes": tweet.get("likes", 0),
                        })
        except Exception as e:
            print(f"    Error: {e}")
            continue
    
    for ticker, sentiments in results["sentiment_by_ticker"].items():
        results["sentiment_by_ticker"][ticker] = {
            "mentions": len(sentiments),
            "avg_sentiment": sum(sentiments) / len(sentiments),
        }
    
    results["top_tweets"].sort(key=lambda x: abs(x["sentiment"] - 50), reverse=True)
    results["top_tweets"] = results["top_tweets"][:15]
    
    return results


def print_combined_summary(reddit_data: Dict, x_data: Dict):
    """Print combined summary"""
    print("\n" + "="*70)
    print("VOX SOCIAL MEDIA TRACKER — COMBINED REPORT")
    print("="*70)
    
    # Merge mentions
    all_mentions = Counter(reddit_data.get("ticker_mentions", {}))
    all_mentions.update(x_data.get("ticker_mentions", {}))
    
    # Merge sentiment
    all_sentiment = {}
    for source in [reddit_data, x_data]:
        for ticker, data in source.get("sentiment_by_ticker", {}).items():
            if ticker not in all_sentiment:
                all_sentiment[ticker] = {"mentions": 0, "sentiments": []}
            all_sentiment[ticker]["mentions"] += data.get("mentions", 0)
            all_sentiment[ticker]["sentiments"].append(data.get("avg_sentiment", 50))
    
    for ticker in all_sentiment:
        sents = all_sentiment[ticker]["sentiments"]
        all_sentiment[ticker]["avg_sentiment"] = sum(sents) / len(sents)
    
    print("\n📊 Top Mentioned Tickers (Reddit + X):")
    for ticker, count in all_mentions.most_common(20):
        sent_data = all_sentiment.get(ticker, {})
        sent = sent_data.get("avg_sentiment", 50)
        emoji = "🟢" if sent > 60 else "🔴" if sent < 40 else "⚪"
        source_tags = []
        if ticker in reddit_data.get("ticker_mentions", {}):
            source_tags.append("R")
        if ticker in x_data.get("ticker_mentions", {}):
            source_tags.append("X")
        print(f"  {emoji} ${ticker:6} | {count:3} mentions | Sentiment: {sent:.0f} | [{'+'.join(source_tags)}]")
    
    print("\n🔥 Top Reddit Posts (Portfolio):")
    for post in reddit_data.get("top_posts", [])[:8]:
        emoji = "🟢" if post["sentiment"] > 60 else "🔴" if post["sentiment"] < 40 else "⚪"
        print(f"  {emoji} r/{post['subreddit']:18} | Score: {post['score']:4} | {post['title'][:55]}...")
        print(f"      Tickers: {', '.join(post['tickers'])}")
    
    if x_data.get("top_tweets"):
        print("\n🐦 Top X/Twitter Mentions (Portfolio):")
        for tweet in x_data["top_tweets"][:5]:
            emoji = "🟢" if tweet["sentiment"] > 60 else "🔴" if tweet["sentiment"] < 40 else "⚪"
            print(f"  {emoji} ${tweet['ticker']:6} | {tweet['text'][:60]}...")
    
    print("\n📈 Sentiment Summary:")
    bullish = sum(1 for t, d in all_sentiment.items() if d.get("avg_sentiment", 50) > 60)
    bearish = sum(1 for t, d in all_sentiment.items() if d.get("avg_sentiment", 50) < 40)
    neutral = len(all_sentiment) - bullish - bearish
    
    print(f"  🟢 Bullish:  {bullish} tickers")
    print(f"  ⚪ Neutral:  {neutral} tickers")
    print(f"  🔴 Bearish:  {bearish} tickers")


def export_combined_report(reddit_data: Dict, x_data: Dict, filepath: str):
    """Export combined report"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "reddit": {
            "ticker_mentions": dict(reddit_data.get("ticker_mentions", {})),
            "sentiment_by_ticker": reddit_data.get("sentiment_by_ticker", {}),
            "top_posts": reddit_data.get("top_posts", []),
        },
        "x_twitter": {
            "ticker_mentions": dict(x_data.get("ticker_mentions", {})),
            "sentiment_by_ticker": x_data.get("sentiment_by_ticker", {}),
            "top_tweets": x_data.get("top_tweets", []),
        },
    }
    
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nCombined report exported to {filepath}")


def main():
    parser = argparse.ArgumentParser(description="VOX Social Media Tracker")
    parser.add_argument("--reddit", action="store_true", help="Scan Reddit only")
    parser.add_argument("--x", action="store_true", help="Scan X/Twitter only")
    parser.add_argument("--full-scan", action="store_true", help="Scan both Reddit and X")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    if not any([args.reddit, args.x, args.full_scan]):
        args.full_scan = True
    
    reddit_data = scan_reddit() if (args.reddit or args.full_scan) else {"ticker_mentions": Counter(), "sentiment_by_ticker": {}, "top_posts": []}
    x_data = scan_x_twitter() if (args.x or args.full_scan) else {"ticker_mentions": Counter(), "sentiment_by_ticker": {}, "top_tweets": []}
    
    print_combined_summary(reddit_data, x_data)
    
    if args.output:
        export_combined_report(reddit_data, x_data, args.output)
    else:
        export_combined_report(reddit_data, x_data, os.path.expanduser("~/.hermes/scripts/vox_social_report.json"))


if __name__ == "__main__":
    main()
