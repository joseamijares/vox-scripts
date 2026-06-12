#!/usr/bin/env python3
"""
VOX News Intelligence Agent
Continuously monitors news for portfolio positions and watchlist
Stores: headlines, sentiment, relevance, source
Outputs: news_intelligence.json + Supabase alerts
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict

SCRIPT_DIR = Path.home() / ".hermes/scripts"
NEWS_DIR = SCRIPT_DIR / "news_intelligence"
NEWS_DIR.mkdir(exist_ok=True)

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

def fetch_news(ticker: str) -> List[Dict]:
    """Fetch news for a ticker via Polygon."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return []
    
    url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit=5&apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("results", [])
    except Exception as e:
        return []

def analyze_sentiment(title: str) -> str:
    """Simple keyword-based sentiment."""
    bullish = ["surge", "rally", "beat", "growth", "upgrade", "bull", "moon", "rocket", "breakout", "strong", "gain"]
    bearish = ["crash", "drop", "miss", "cut", "downgrade", "bear", "dump", "sell", "weak", "loss", "fall"]
    
    title_lower = title.lower()
    b_score = sum(1 for w in bullish if w in title_lower)
    be_score = sum(1 for w in bearish if w in title_lower)
    
    if b_score > be_score:
        return "BULLISH"
    elif be_score > b_score:
        return "BEARISH"
    return "NEUTRAL"

def score_relevance(news_item: Dict, ticker: str) -> int:
    """Score news relevance 0-100."""
    score = 50
    title = (news_item.get("title", "") + " " + news_item.get("description", "")).lower()
    
    # Direct ticker mention
    if ticker.lower() in title:
        score += 20
    
    # Earnings related
    if any(w in title for w in ["earnings", "revenue", "profit", "guidance"]):
        score += 15
    
    # Analyst action
    if any(w in title for w in ["upgrade", "downgrade", "price target", "initiated"]):
        score += 10
    
    # Breaking
    if news_item.get("publisher", {}).get("name", "") in ["Bloomberg", "Reuters", "CNBC", "Wall Street Journal"]:
        score += 10
    
    return min(100, score)

def scan_portfolio_news():
    """Scan all portfolio positions for news."""
    print("📰 VOX News Intelligence Agent")
    print("=" * 60)
    
    # Load portfolio
    portfolio_file = SCRIPT_DIR / "dashboard_positions_live.json"
    watchlist_file = SCRIPT_DIR / "vox_autonomous_watchlist.json"
    
    tickers = set()
    
    if portfolio_file.exists():
        with open(portfolio_file) as f:
            data = json.load(f)
            for p in data.get("positions", []):
                tickers.add(p.get("ticker", ""))
    
    # Also check watchlist from Supabase
    try:
        from vox_supabase_sync import get_client
        sb = get_client()
        result = sb.table('watchlist').select('ticker').execute()
        for w in result.data:
            tickers.add(w.get('ticker', ''))
    except:
        pass
    
    tickers = [t for t in tickers if t and len(t) <= 5]
    
    print(f"Scanning {len(tickers)} tickers...")
    
    all_news = []
    high_relevance = []
    
    for ticker in tickers[:30]:  # Top 30 for speed
        try:
            news = fetch_news(ticker)
            for item in news:
                sentiment = analyze_sentiment(item.get("title", ""))
                relevance = score_relevance(item, ticker)
                
                entry = {
                    "ticker": ticker,
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", {}).get("name", "Unknown"),
                    "published": item.get("published_utc", ""),
                    "sentiment": sentiment,
                    "relevance": relevance,
                    "url": item.get("article_url", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                all_news.append(entry)
                
                if relevance >= 70:
                    high_relevance.append(entry)
                    print(f"  🔥 {ticker:6s} | {sentiment:8s} | Rel: {relevance:2d} | {item['title'][:60]}...")
                elif relevance >= 50:
                    print(f"  📰 {ticker:6s} | {sentiment:8s} | Rel: {relevance:2d} | {item['title'][:50]}...")
                    
        except Exception as e:
            print(f"  ⚠️  {ticker}: {e}")
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_scanned": len(tickers),
        "articles_found": len(all_news),
        "high_relevance": len(high_relevance),
        "articles": sorted(all_news, key=lambda x: x["relevance"], reverse=True)[:50],
        "breaking": high_relevance[:10]
    }
    
    with open(NEWS_DIR / "news_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Saved {len(all_news)} articles, {len(high_relevance)} high relevance")
    
    # Store alerts in Supabase
    if high_relevance:
        try:
            from vox_supabase_sync import get_client
            sb = get_client()
            for alert in high_relevance[:5]:
                sb.table('alerts').insert({
                    "ticker": alert["ticker"],
                    "type": "NEWS",
                    "message": alert["title"],
                    "priority": "HIGH" if alert["relevance"] >= 80 else "MEDIUM",
                    "timestamp": alert["timestamp"]
                }).execute()
            print(f"🚨 Stored {min(len(high_relevance), 5)} news alerts in Supabase")
        except Exception as e:
            print(f"Supabase alert error: {e}")

if __name__ == "__main__":
    scan_portfolio_news()
