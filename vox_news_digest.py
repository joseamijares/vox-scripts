#!/usr/bin/env python3
"""
VOX News Digest v10
Aggregates news for portfolio relevance using Polygon API.
No external dependencies — reads .env directly.
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request

# ─── LOAD ENV ─────────────────────────────────────────────────────────
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
POLYGON_API_KEY = ENV.get("POLYGON_API_KEY", "")

# ─── CONFIG ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
OUTPUT_FILE = SCRIPT_DIR / 'vox_news_digest.json'

# ─── PORTFOLIO LOADER ────────────────────────────────────────────────
def load_portfolio_tickers():
    """Load tickers from dashboard_positions.json"""
    positions_file = SCRIPT_DIR / 'dashboard_positions.json'
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

# ─── NEWS FETCHERS ───────────────────────────────────────────────────
def fetch_polygon_news(ticker, limit=5):
    """Fetch news from Polygon API for a single ticker."""
    if not POLYGON_API_KEY:
        return []
    
    try:
        url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit={limit}&apiKey={POLYGON_API_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/10.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            headlines = []
            for item in data.get("results", []):
                headlines.append({
                    "ticker": ticker,
                    "title": item.get("title", ""),
                    "source": item.get("publisher", {}).get("name", "Polygon"),
                    "url": item.get("article_url", ""),
                    "published": item.get("published_utc", ""),
                    "summary": item.get("description", "")[:200],
                })
            return headlines
    except Exception as e:
        return []

def fetch_all_news(tickers, max_workers=10):
    """Fetch news for all tickers in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    all_headlines = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_polygon_news, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                headlines = future.result()
                all_headlines.extend(headlines)
                if headlines:
                    print(f"  ✓ {ticker}: {len(headlines)} headlines")
                else:
                    print(f"  ○ {ticker}: no news")
            except Exception as e:
                print(f"  ✗ {ticker}: {e}")
    
    return all_headlines

# ─── NEWS PROCESSOR ──────────────────────────────────────────────────
def score_headline(headline, portfolio_tickers):
    """Score headline relevance to portfolio."""
    score = 0
    title = headline.get("title", "").upper()
    ticker = headline.get("ticker", "")
    
    # Direct ticker mention
    if ticker in portfolio_tickers:
        score += 50
    
    # Keywords
    keywords = {
        "EARNINGS": 20, "GUIDANCE": 15, "UPGRADE": 15, "DOWNGRADE": 15,
        "BUYOUT": 25, "MERGER": 25, "ACQUISITION": 25, "FDA": 20,
        "SEC": 15, "BANKRUPTCY": 30, "LAYOFF": 15, "DIVIDEND": 10,
        "SPLIT": 10, "CEO": 10, "QUARTERLY": 15, "REVENUE": 15,
        "PROFIT": 15, "BEAT": 20, "MISS": 20, "RAISES": 15,
        "CUTS": 15, "TARGET": 10, "OUTLOOK": 15,
    }
    
    for keyword, points in keywords.items():
        if keyword in title:
            score += points
    
    # Source quality
    quality_sources = ["Reuters", "Bloomberg", "WSJ", "FT", "CNBC", "MarketWatch"]
    if headline.get("source") in quality_sources:
        score += 10
    
    return min(100, score)

def categorize_headline(headline):
    """Categorize headline by type."""
    title = headline.get("title", "").upper()
    categories = []
    
    if any(w in title for w in ["EARNINGS", "QUARTERLY", "REVENUE", "PROFIT", "BEAT", "MISS"]):
        categories.append("earnings")
    if any(w in title for w in ["UPGRADE", "DOWNGRADE", "RATING", "ANALYST", "TARGET"]):
        categories.append("analyst")
    if any(w in title for w in ["MERGER", "ACQUISITION", "BUYOUT", "DEAL"]):
        categories.append("m&a")
    if any(w in title for w in ["FDA", "CLINICAL", "DRUG", "TRIAL"]):
        categories.append("biotech")
    if any(w in title for w in ["CEO", "EXECUTIVE", "BOARD", "MANAGEMENT"]):
        categories.append("management")
    if any(w in title for w in ["LAYOFF", "HIRING", "WORKFORCE", "CUTS"]):
        categories.append("employment")
    if any(w in title for w in ["SUPPLY CHAIN", "PRODUCTION", "FACTORY"]):
        categories.append("operations")
    if any(w in title for w in ["GUIDANCE", "OUTLOOK", "FORECAST"]):
        categories.append("guidance")
    
    if not categories:
        categories.append("general")
    
    return categories

# ─── MAIN ────────────────────────────────────────────────────────────
def generate_news_digest(tickers=None):
    """Generate the news digest."""
    print("📰 VOX News Digest v10")
    print("=" * 60)
    
    # Load tickers
    if not tickers:
        tickers = load_portfolio_tickers()
    
    print(f"📊 Monitoring {len(tickers)} tickers")
    
    if not POLYGON_API_KEY:
        print("⚠️  No POLYGON_API_KEY in ~/.hermes/.env")
        return None
    
    # Fetch news
    print(f"\nFetching news from Polygon...")
    headlines = fetch_all_news(tickers[:30])  # Top 30 by position value would be better
    
    print(f"\n📰 Fetched {len(headlines)} headlines")
    
    # Score and categorize
    for h in headlines:
        h["relevance_score"] = score_headline(h, tickers)
        h["categories"] = categorize_headline(h)
    
    # Sort by relevance
    headlines.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    # Filter to relevant only
    relevant = [h for h in headlines if h["relevance_score"] >= 30]
    
    digest = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "total_headlines": len(headlines),
        "relevant_headlines": len(relevant),
        "headlines": headlines[:50],
        "portfolio_impact": [h for h in relevant if h.get("ticker") in tickers][:20],
        "by_category": {},
    }
    
    # Group by category
    for h in headlines:
        for cat in h.get("categories", ["general"]):
            if cat not in digest["by_category"]:
                digest["by_category"][cat] = []
            digest["by_category"][cat].append(h)
    
    return digest

def main():
    parser = argparse.ArgumentParser(description="VOX News Digest")
    parser.add_argument("--tickers", help="Comma-separated tickers")
    parser.add_argument("--output", default="vox_news_digest.json", help="Output file")
    
    args = parser.parse_args()
    
    tickers = args.tickers.split(",") if args.tickers else None
    digest = generate_news_digest(tickers)
    
    if not digest:
        return
    
    # Save
    output_path = SCRIPT_DIR / args.output
    with open(output_path, "w") as f:
        json.dump(digest, f, indent=2)
    
    print(f"\n💾 Saved: {output_path}")
    print(f"📰 Total: {digest['total_headlines']} | Relevant: {digest['relevant_headlines']}")
    print(f"🎯 Portfolio impact: {len(digest['portfolio_impact'])}")
    
    # Print top headlines
    print("\n🏆 Top Headlines:")
    for h in digest["headlines"][:10]:
        print(f"   [{h['relevance_score']:2d}] {h['ticker']:6} | {h['title'][:70]}...")

if __name__ == "__main__":
    main()
