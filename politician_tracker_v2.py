#!/usr/bin/env python3
"""
Politician Tracker v2 — FREE (JOS-34)
Uses Finnhub API (free tier) + X/Twitter monitoring.
No $30/month Quiver Quant needed.
"""

import os
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta


def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    keys[key] = val
    return keys


def finnhub_get(endpoint, params=""):
    """Finnhub API GET."""
    env = load_env()
    api_key = env.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {"error": "FINNHUB_API_KEY not set"}

    url = f"https://finnhub.io/api/v1{endpoint}?token={api_key}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "details": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def get_congressional_trades(ticker, from_date, to_date):
    """Get congressional trades for a ticker via Finnhub."""
    result = finnhub_get("/stock/congressional-trading", f"&symbol={ticker}&from={from_date}&to={to_date}")
    return result.get("data", [])


def search_x_for_trades():
    """Search X/Twitter for politician trade mentions."""
    env = load_env()
    bearer = env.get("X_BEARER_TOKEN", "")
    if not bearer:
        return {"error": "X_BEARER_TOKEN not set"}

    # Search for congressional trading mentions
    query = "congressional trading OR Pelosi trade OR insider trading -is:retweet"
    url = f"https://api.twitter.com/2/tweets/search/recent?query={urllib.parse.quote(query)}&max_results=10&tweet.fields=created_at,author_id"

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {bearer}", "User-Agent": "Vox-Finance/1.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def run_tracker():
    """Main tracker runner."""
    print("=" * 70)
    print("🏛️ POLITICIAN TRACKER v2 — FREE")
    print("=" * 70)
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    env = load_env()

    # Check Finnhub
    if not env.get("FINNHUB_API_KEY"):
        print("⚠️ FINNHUB_API_KEY not set")
        print("Get free key: https://finnhub.io/register")
        print("Note: Congressional trading requires paid tier")
        print()
    else:
        print("✅ Finnhub key configured")
        print("⚠️ Congressional trading endpoint requires premium subscription")
        print("   Free tier works for: news, fundamentals, market data")
        print()

    # X/Twitter monitoring (primary free source)
    if env.get("X_BEARER_TOKEN"):
        print("🔍 Checking X/Twitter for trade mentions...")
        x_data = search_x_for_trades()
        if "data" in x_data:
            print(f"Found {len(x_data['data'])} recent tweets")
            print()
            for tweet in x_data["data"][:5]:
                text = tweet['text'][:120]
                print(f"  🐦 {text}{'...' if len(tweet['text']) > 120 else ''}")
                print()
        elif "error" in x_data:
            print(f"  X API error: {x_data['error']}")
    else:
        print("⚠️ X_BEARER_TOKEN not set")

    print()
    print("=" * 70)
    print("FREE POLITICIAN TRACKING SOURCES:")
    print("=" * 70)
    print("1. X/Twitter Accounts (follow for alerts):")
    print("   • @pelositracker — Nancy Pelosi trades")
    print("   • @unusual_whales — Congress + options flow")
    print("   • @Chrisjjosephs — Pelosi tracker founder")
    print("   • @SweatyInvesting — Congress analysis")
    print()
    print("2. Free Websites:")
    print("   • https://housestockwatcher.com/")
    print("   • https://senatestockwatcher.com/")
    print("   • https://pelositracker.app/ (free tier)")
    print()
    print("3. Finnhub (free tier — news/fundamentals only):")
    print("   • Congressional trading = premium ($$$)")
    print("   • Use for: company news, earnings, sentiment")
    print("=" * 70)


def main():
    run_tracker()


if __name__ == "__main__":
    main()
