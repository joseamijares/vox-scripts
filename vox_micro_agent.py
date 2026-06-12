#!/usr/bin/env python3
"""
VOX Micro Analysis Agent
Monitors: Earnings, guidance, analyst upgrades/downgrades, insider activity
Generates: Stock-specific fundamental signals
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

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

def fetch_polygon(path: str) -> dict:
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {}
    url = f"https://api.polygon.io/v2/{path}?apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"Polygon error: {e}")
        return {}

def get_earnings(ticker: str) -> list:
    """Get recent earnings data."""
    data = fetch_polygon(f"reference/financials/{ticker}")
    return data.get("results", [])

def get_analyst_ratings(ticker: str) -> dict:
    """Get analyst ratings summary."""
    # Using a simple approach - in production use a proper API
    return {
        "strong_buy": 0,
        "buy": 0,
        "hold": 0,
        "sell": 0,
        "strong_sell": 0,
        "target_price": 0
    }

def analyze_ticker_fundamentals(ticker: str) -> dict:
    """Analyze fundamentals for a single ticker."""
    earnings = get_earnings(ticker)
    
    if not earnings:
        return {"ticker": ticker, "signal": "UNKNOWN", "confidence": 0}
    
    latest = earnings[0]
    revenue = latest.get("revenues", {}).get("value", 0)
    eps = latest.get("earnings_per_share", {}).get("value", 0)
    
    # Simple scoring
    score = 50
    if revenue > 0:
        score += 10
    if eps > 0:
        score += 15
    
    if score >= 70:
        signal = "STRONG"
    elif score >= 55:
        signal = "MODERATE"
    elif score >= 40:
        signal = "WEAK"
    else:
        signal = "AVOID"
    
    return {
        "ticker": ticker,
        "signal": signal,
        "confidence": score,
        "revenue": revenue,
        "eps": eps,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def analyze_portfolio_micro(tickers: list) -> dict:
    """Analyze all portfolio positions."""
    print("🔬 VOX Micro Agent analyzing...")
    
    results = []
    for ticker in tickers:
        result = analyze_ticker_fundamentals(ticker)
        results.append(result)
        print(f"   {ticker}: {result['signal']} (confidence: {result['confidence']})")
    
    analysis = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "strong_count": sum(1 for r in results if r["signal"] == "STRONG"),
        "weak_count": sum(1 for r in results if r["signal"] in ["WEAK", "AVOID"])
    }
    
    output_file = SCRIPT_DIR / "vox_micro_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print(f"\n   Strong: {analysis['strong_count']} | Weak: {analysis['weak_count']}")
    return analysis

if __name__ == "__main__":
    # Test with a few tickers
    test_tickers = ["AAPL", "MSFT", "NVDA", "META", "AMZN"]
    analyze_portfolio_micro(test_tickers)
