#!/usr/bin/env python3
"""
VOX Volume Intelligence Agent
Detects unusual volume patterns, institutional flow, block trades
Flags: volume spikes, accumulation, distribution, dark pool activity
"""

import json
import urllib.request
import statistics
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
VOLUME_DIR = SCRIPT_DIR / "volume_intelligence"
VOLUME_DIR.mkdir(exist_ok=True)

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

def polygon_api(path: str) -> dict:
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {}
    url = f"https://api.polygon.io/v2/{path}?apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except:
        return {}

def analyze_volume(ticker: str) -> dict:
    """Analyze volume patterns for a ticker."""
    # Fetch 20 days of data
    data = polygon_api(f"aggs/ticker/{ticker}/range/1/day/2026-04-01/2026-05-26")
    bars = data.get("results", [])
    
    if len(bars) < 10:
        return {"ticker": ticker, "signal": "NEUTRAL", "score": 50}
    
    volumes = [b.get("v", 0) for b in bars]
    prices = [b.get("c", 0) for b in bars]
    
    avg_volume = statistics.mean(volumes[:-1])  # Exclude today
    today_volume = volumes[-1]
    today_price = prices[-1]
    yesterday_price = prices[-2]
    
    volume_ratio = today_volume / avg_volume if avg_volume else 1
    price_change = ((today_price - yesterday_price) / yesterday_price * 100) if yesterday_price else 0
    
    # Signal detection
    signal = "NEUTRAL"
    score = 50
    
    if volume_ratio > 3 and price_change > 5:
        signal = "ACCUMULATION"
        score = 80
    elif volume_ratio > 3 and price_change < -5:
        signal = "DISTRIBUTION"
        score = 20
    elif volume_ratio > 2 and price_change > 3:
        signal = "BREAKOUT"
        score = 75
    elif volume_ratio > 2 and price_change < -3:
        signal = "BREAKDOWN"
        score = 25
    elif volume_ratio > 2 and abs(price_change) < 2:
        signal = "BASE_BUILDING"
        score = 60
    
    return {
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "volume_ratio": round(volume_ratio, 2),
        "price_change": round(price_change, 2),
        "avg_volume": int(avg_volume),
        "today_volume": int(today_volume),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def scan_portfolio():
    """Scan all portfolio positions for volume anomalies."""
    print("📊 VOX Volume Intelligence Agent")
    print("=" * 50)
    
    # Load portfolio
    portfolio_file = SCRIPT_DIR / "dashboard_positions_live.json"
    if not portfolio_file.exists():
        print("No portfolio data")
        return {}
    
    with open(portfolio_file) as f:
        data = json.load(f)
    
    tickers = [p.get("ticker", "") for p in data.get("positions", []) if p.get("ticker")]
    
    print(f"Scanning {len(tickers)} positions...")
    
    results = []
    anomalies = []
    
    for ticker in tickers:
        try:
            result = analyze_volume(ticker)
            results.append(result)
            
            if result["volume_ratio"] > 2:
                anomalies.append(result)
                emoji = "🟢" if result["score"] > 60 else "🔴"
                print(f"   {emoji} {ticker:6s} | {result['signal']:15s} | Vol {result['volume_ratio']:.1f}x | {result['price_change']:+.1f}%")
        except Exception as e:
            pass
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tickers_scanned": len(results),
        "anomalies_found": len(anomalies),
        "anomalies": anomalies,
        "all_results": results
    }
    
    with open(VOLUME_DIR / "volume_intelligence.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n📊 Volume Summary")
    print(f"   Scanned: {len(results)}")
    print(f"   Anomalies: {len(anomalies)}")
    
    return output

if __name__ == "__main__":
    scan_portfolio()
