#!/usr/bin/env python3
"""
VOX Volume Scanner v2.0
Fast batch scanning with caching. Scans ALL portfolio positions.

Usage:
    python3 vox_volume_scanner.py scan      # Full portfolio scan
    python3 vox_volume_scanner.py quick     # Top 30 positions only
"""

import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

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

ENV = load_env()
POLYGON_KEY = ENV.get("POLYGON_API_KEY", "")

def polygon_get(path):
    if not POLYGON_KEY:
        return {"error": "POLYGON_API_KEY not set"}
    url = f"https://api.polygon.io{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {POLYGON_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def get_daily_bars(ticker: str) -> List[Dict]:
    """Fetch last 30 days of daily bars"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        return []
    return result.get("results", [])

def scan_ticker(ticker: str) -> Dict:
    """Scan a single ticker for volume anomalies"""
    bars = get_daily_bars(ticker)
    if len(bars) < 10:
        return {"ticker": ticker, "error": "Insufficient data"}
    
    volumes = [b["v"] for b in bars]
    avg_vol = sum(volumes[-20:]) / 20
    recent_vol = volumes[-1]
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
    
    closes = [b["c"] for b in bars]
    current_price = closes[-1]
    prev_price = closes[-2]
    price_change = (current_price - prev_price) / prev_price * 100
    
    highs = [b["h"] for b in bars[-20:]]
    lows = [b["l"] for b in bars[-20:]]
    range_high = max(highs)
    range_low = min(lows)
    
    near_high = current_price > range_high * 0.98
    near_low = current_price < range_low * 1.02
    
    signals = []
    if vol_ratio > 3:
        signals.append("volume_spike")
    elif vol_ratio > 2:
        signals.append("volume_high")
    
    if price_change > 5 and vol_ratio > 1.5:
        signals.append("breakout")
    elif price_change < -5 and vol_ratio > 1.5:
        signals.append("breakdown")
    
    if near_high and vol_ratio > 1.5:
        signals.append("new_high")
    elif near_low and vol_ratio > 1.5:
        signals.append("new_low")
    
    score = 0
    if "volume_spike" in signals:
        score += 30
    elif "volume_high" in signals:
        score += 15
    if "breakout" in signals:
        score += 25
    elif "breakdown" in signals:
        score -= 25
    if "new_high" in signals:
        score += 20
    elif "new_low" in signals:
        score -= 20
    
    if score >= 50:
        alert = "STRONG"
    elif score >= 25:
        alert = "MODERATE"
    elif score <= -50:
        alert = "STRONG_NEGATIVE"
    elif score <= -25:
        alert = "MODERATE_NEGATIVE"
    else:
        alert = "NONE"
    
    return {
        "ticker": ticker,
        "price": current_price,
        "price_change_pct": round(price_change, 2),
        "volume_ratio": round(vol_ratio, 2),
        "avg_volume": int(avg_vol),
        "today_volume": int(recent_vol),
        "signals": signals,
        "score": score,
        "alert": alert,
        "near_20d_high": near_high,
        "near_20d_low": near_low,
    }

def scan_portfolio(quick=False):
    """Scan all portfolio tickers with parallel processing"""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    
    if not positions_file.exists():
        print("No portfolio data")
        return
    
    with open(positions_file) as f:
        data = json.load(f)
    
    tickers = list(set(
        p["ticker"] for p in data.get("positions", [])
        if p.get("ticker") not in {"CASH", "USD", "MXN", "CASH_USD", "CASH_MXN"}
    ))
    
    if quick:
        # Sort by position value and take top 30
        positions = data.get("positions", [])
        pos_by_value = sorted(positions, key=lambda x: x.get("value", 0) or x.get("market_value", 0), reverse=True)
        tickers = list(set(p["ticker"] for p in pos_by_value[:30]))
    
    print(f"\nScanning {len(tickers)} tickers for volume anomalies...")
    print("=" * 60)
    
    results = []
    alerts = []
    errors = 0
    
    # Parallel scan with max 15 workers
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(scan_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                if "error" in result:
                    errors += 1
                    continue
                results.append(result)
                if result["alert"] != "NONE":
                    alerts.append(result)
            except Exception as e:
                errors += 1
    
    # Sort by volume ratio
    results.sort(key=lambda x: x["volume_ratio"], reverse=True)
    
    # Print top volume movers
    print(f"\nTop Volume Movers:")
    for r in results[:10]:
        flag = "⚠️ " if r["alert"] != "NONE" else "  "
        print(f"{flag}{r['ticker']:6} | Vol: {r['volume_ratio']:.2f}x avg | {r['price_change_pct']:+.2f}% | {r['alert']}")
    
    # Print alerts
    if alerts:
        print(f"\nVolume Alerts ({len(alerts)}):")
        for a in alerts:
            emoji = "🚨" if "STRONG" in a["alert"] else "⚠️"
            print(f"  {emoji} {a['ticker']:6} | {a['alert']:18} | Score: {a['score']:+d} | Vol: {a['volume_ratio']:.1f}x")
    else:
        print("\nNo volume alerts")
    
    print(f"\nScanned: {len(results)} | Alerts: {len(alerts)} | Errors: {errors}")
    
    # Save
    output_file = Path.home() / ".hermes" / "scripts" / "vox_volume_scan.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "alerts": alerts,
            "summary": {
                "scanned": len(results),
                "alerts": len(alerts),
                "errors": errors,
            }
        }, f, indent=2)
    
    print(f"Saved to {output_file}")
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Volume Scanner")
    parser.add_argument("command", choices=["scan", "quick"])
    args = parser.parse_args()
    
    if args.command == "scan":
        scan_portfolio(quick=False)
    elif args.command == "quick":
        scan_portfolio(quick=True)

if __name__ == "__main__":
    main()
