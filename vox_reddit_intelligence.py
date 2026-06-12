#!/usr/bin/env python3
"""
VOX Reddit Intelligence Agent
Monitors subreddits for ticker mentions, sentiment, and discussion quality
Tracks: r/wallstreetbets, r/stocks, r/investing, r/pennystocks, r/cryptocurrency
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List
from collections import defaultdict

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
REDDIT_DIR = SCRIPT_DIR / "reddit_intelligence"
REDDIT_DIR.mkdir(exist_ok=True)

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

def fetch_reddit(subreddit: str, limit: int = 25) -> List[dict]:
    """Fetch hot posts from subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    headers = {"User-Agent": "VOX-Research-Bot/1.0"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("data", {}).get("children", [])
    except Exception as e:
        print(f"[Reddit] Error fetching r/{subreddit}: {e}")
        return []

def extract_tickers(text: str) -> List[str]:
    """Extract ticker symbols from text."""
    import re
    # Match $TICKER or standalone uppercase 1-5 letters
    tickers = re.findall(r'\$([A-Z]{1,5})', text)
    tickers += re.findall(r'\b([A-Z]{2,5})\b', text)
    return list(set(tickers))

def analyze_subreddit(subreddit: str) -> Dict[str, dict]:
    """Analyze a subreddit for ticker mentions."""
    print(f"   Scanning r/{subreddit}...")
    
    posts = fetch_reddit(subreddit)
    ticker_data = defaultdict(lambda: {"mentions": 0, "upvotes": 0, "comments": 0, "titles": []})
    
    for post in posts:
        data = post.get("data", {})
        title = data.get("title", "")
        text = data.get("selftext", "")
        upvotes = data.get("ups", 0)
        comment_count = data.get("num_comments", 0)
        
        tickers = extract_tickers(title + " " + text)
        
        for ticker in tickers:
            ticker_data[ticker]["mentions"] += 1
            ticker_data[ticker]["upvotes"] += upvotes
            ticker_data[ticker]["comments"] += comment_count
            if len(ticker_data[ticker]["titles"]) < 3:
                ticker_data[ticker]["titles"].append(title[:100])
    
    # Convert to scores
    results = {}
    for ticker, data in ticker_data.items():
        # Score based on mentions + engagement
        score = min(data["mentions"] * 10 + data["upvotes"] / 100, 100)
        
        results[ticker] = {
            "ticker": ticker,
            "mentions": data["mentions"],
            "upvotes": data["upvotes"],
            "comments": data["comments"],
            "score": round(score, 1),
            "sample_titles": data["titles"]
        }
    
    return results

def scan_all_subreddits():
    """Scan multiple subreddits."""
    print("📱 VOX Reddit Intelligence Agent")
    print("=" * 50)
    
    subreddits = ["wallstreetbets", "stocks", "investing", "pennystocks", "cryptocurrency", "wallstreetbetsOGs"]
    
    all_mentions = defaultdict(lambda: {"mentions": 0, "upvotes": 0, "subreddits": set(), "titles": []})
    
    for subreddit in subreddits:
        try:
            results = analyze_subreddit(subreddit)
            for ticker, data in results.items():
                all_mentions[ticker]["mentions"] += data["mentions"]
                all_mentions[ticker]["upvotes"] += data["upvotes"]
                all_mentions[ticker]["subreddits"].add(subreddit)
                all_mentions[ticker]["titles"].extend(data["sample_titles"])
        except Exception as e:
            print(f"   Error with r/{subreddit}: {e}")
    
    # Rank by score
    ranked = []
    for ticker, data in all_mentions.items():
        if data["mentions"] >= 2:  # Minimum threshold
            score = min(data["mentions"] * 15 + data["upvotes"] / 50, 100)
            ranked.append({
                "ticker": ticker,
                "mentions": data["mentions"],
                "upvotes": data["upvotes"],
                "subreddits": list(data["subreddits"]),
                "score": round(score, 1),
                "sample_titles": data["titles"][:3]
            })
    
    ranked.sort(key=lambda x: x["score"], reverse=True)
    
    # Display top
    print(f"\n📊 Top Mentions:")
    for r in ranked[:10]:
        print(f"   {r['ticker']:6s} | Score: {r['score']:5.1f} | {r['mentions']} mentions | r/{', r/'.join(r['subreddits'][:2])}")
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subreddits_scanned": len(subreddits),
        "total_mentions": sum(r["mentions"] for r in ranked),
        "top_mentions": ranked[:20]
    }
    
    with open(REDDIT_DIR / "reddit_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Saved {len(ranked)} tickers to reddit_intelligence.json")
    return output

if __name__ == "__main__":
    scan_all_subreddits()
