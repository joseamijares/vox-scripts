#!/usr/bin/env python3
"""
VOX Live Price Feed v1.0
Real-time stock and crypto prices via Polygon.io API

Features:
- Fetch live prices for all portfolio tickers
- Calculate real-time P&L
- Update dashboard_positions.json with current prices
- Generate price alerts for significant moves

Usage:
    python3 vox_live_prices.py --update
    python3 vox_live_prices.py --ticker AAPL
    python3 vox_live_prices.py --alert-threshold 5
"""

import os
import sys
import json
import argparse
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

# Load API key from .env
def load_polygon_key() -> str:
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""

POLYGON_KEY = load_polygon_key()
SCRIPTS_DIR = os.path.expanduser("~/.hermes/scripts")


def polygon_request(endpoint: str) -> Dict:
    """Make Polygon API request"""
    if not POLYGON_KEY:
        return {}
    
    url = f"https://api.polygon.io/{endpoint}"
    if "?" in url:
        url += f"&apiKey={POLYGON_KEY}"
    else:
        url += f"?apiKey={POLYGON_KEY}"
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "VOX-LivePrices/1.0"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"API error: {e}")
        return {}


def get_stock_price(ticker: str) -> Optional[Dict]:
    """Get previous close price for a stock"""
    data = polygon_request(f"v2/aggs/ticker/{ticker}/prev")
    
    if not data or "results" not in data or not data["results"]:
        return None
    
    result = data["results"][0]
    return {
        "ticker": ticker,
        "price": result.get("c", 0),
        "open": result.get("o", 0),
        "high": result.get("h", 0),
        "low": result.get("l", 0),
        "volume": result.get("v", 0),
        "vwap": result.get("vw", 0),
        "timestamp": result.get("t", 0),
        "change_pct": ((result.get("c", 0) - result.get("o", 0)) / result.get("o", 0) * 100) if result.get("o", 0) > 0 else 0,
    }


def get_crypto_price(ticker: str) -> Optional[Dict]:
    """Get crypto price (uses X:BTCUSD format)"""
    # Polygon uses X:BTCUSD format for crypto
    crypto_map = {
        "BTC": "X:BTCUSD",
        "ETH": "X:ETHUSD",
        "BNB": "X:BNBUSD",
        "ADA": "X:ADAUSD",
    }
    
    polygon_ticker = crypto_map.get(ticker, f"X:{ticker}USD")
    data = polygon_request(f"v2/aggs/ticker/{polygon_ticker}/prev")
    
    if not data or "results" not in data or not data["results"]:
        return None
    
    result = data["results"][0]
    return {
        "ticker": ticker,
        "price": result.get("c", 0),
        "open": result.get("o", 0),
        "high": result.get("h", 0),
        "low": result.get("l", 0),
        "volume": result.get("v", 0),
        "change_pct": ((result.get("c", 0) - result.get("o", 0)) / result.get("o", 0) * 100) if result.get("o", 0) > 0 else 0,
    }


def load_portfolio() -> List[Dict]:
    """Load portfolio positions"""
    filepath = os.path.join(SCRIPTS_DIR, "dashboard_positions.json")
    if not os.path.exists(filepath):
        return []
    
    with open(filepath) as f:
        data = json.load(f)
    
    if isinstance(data, dict):
        return data.get("positions", [])
    return data


def update_portfolio_prices():
    """Update all portfolio positions with live prices"""
    positions = load_portfolio()
    if not positions:
        print("No portfolio positions found")
        return
    
    # Get unique tickers
    tickers = list(set(p.get("ticker", "") for p in positions if p.get("ticker")))
    print(f"Updating prices for {len(tickers)} tickers...")
    
    price_cache = {}
    updated_count = 0
    
    for ticker in tickers:
        # Determine if crypto
        is_crypto = ticker in {"BTC", "ETH", "BNB", "ADA"}
        
        if is_crypto:
            price_data = get_crypto_price(ticker)
        else:
            price_data = get_stock_price(ticker)
        
        if price_data:
            price_cache[ticker] = price_data
            print(f"  {ticker}: ${price_data['price']:.2f} ({price_data['change_pct']:+.2f}%)")
        else:
            print(f"  {ticker}: Failed to fetch")
    
    # Update positions
    for position in positions:
        ticker = position.get("ticker", "")
        if ticker in price_cache:
            price_data = price_cache[ticker]
            old_price = position.get("price", 0)
            shares = position.get("shares", 0)
            
            position["price"] = price_data["price"]
            position["value"] = price_data["price"] * shares
            position["unrealized_pnl"] = (price_data["price"] - position.get("cost_basis", old_price)) * shares
            position["price_change_pct"] = price_data["change_pct"]
            position["last_updated"] = datetime.now().isoformat()
            updated_count += 1
    
    # Save updated positions
    output_file = os.path.join(SCRIPTS_DIR, "dashboard_positions_live.json")
    with open(output_file, 'w') as f:
        json.dump({"positions": positions, "updated_at": datetime.now().isoformat()}, f, indent=2)
    
    print(f"\nUpdated {updated_count} positions")
    print(f"Saved to {output_file}")
    
    # Generate summary
    total_value = sum(p.get("value", 0) for p in positions)
    total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
    
    print(f"\nPortfolio Summary:")
    print(f"  Total Value: ${total_value:,.2f}")
    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Positions: {len(positions)}")


def check_price_alerts(threshold_pct: float = 5.0):
    """Check for significant price moves"""
    positions = load_portfolio()
    alerts = []
    
    for position in positions:
        ticker = position.get("ticker", "")
        change_pct = position.get("price_change_pct", 0)
        
        if abs(change_pct) >= threshold_pct:
            alerts.append({
                "ticker": ticker,
                "change_pct": change_pct,
                "price": position.get("price", 0),
                "direction": "UP" if change_pct > 0 else "DOWN",
            })
    
    if alerts:
        print(f"\n🚨 PRICE ALERTS (>{threshold_pct}%):")
        for alert in sorted(alerts, key=lambda x: abs(x["change_pct"]), reverse=True):
            emoji = "🟢" if alert["direction"] == "UP" else "🔴"
            print(f"  {emoji} {alert['ticker']}: {alert['change_pct']:+.2f}% @ ${alert['price']:.2f}")
    else:
        print(f"\n✅ No significant moves (>{threshold_pct}%)")
    
    return alerts


def main():
    parser = argparse.ArgumentParser(description="VOX Live Price Feed")
    parser.add_argument("--update", action="store_true", help="Update all portfolio prices")
    parser.add_argument("--ticker", help="Get price for specific ticker")
    parser.add_argument("--alert-threshold", type=float, default=5.0, help="Alert threshold %")
    parser.add_argument("--check-alerts", action="store_true", help="Check for price alerts")
    
    args = parser.parse_args()
    
    if args.ticker:
        # Determine if crypto
        is_crypto = args.ticker.upper() in {"BTC", "ETH", "BNB", "ADA"}
        
        if is_crypto:
            price_data = get_crypto_price(args.ticker.upper())
        else:
            price_data = get_stock_price(args.ticker.upper())
        
        if price_data:
            print(f"\n{price_data['ticker']}: ${price_data['price']:.2f}")
            print(f"  Change: {price_data['change_pct']:+.2f}%")
            print(f"  Open: ${price_data['open']:.2f}")
            print(f"  High: ${price_data['high']:.2f}")
            print(f"  Low: ${price_data['low']:.2f}")
            print(f"  Volume: {price_data['volume']:,.0f}")
        else:
            print(f"Failed to fetch {args.ticker}")
    
    elif args.update:
        update_portfolio_prices()
        check_price_alerts(args.alert_threshold)
    
    elif args.check_alerts:
        check_price_alerts(args.alert_threshold)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
