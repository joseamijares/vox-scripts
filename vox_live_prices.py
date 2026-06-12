#!/usr/bin/env python3
"""
VOX Live Price Fetcher
Fetches real-time prices for all portfolio positions via Polygon.io
Updates dashboard_positions_live.json with fresh data.
"""

import json
import os
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── CONFIG ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
POSITIONS_FILE = SCRIPT_DIR / "dashboard_positions.json"
LIVE_PRICES_FILE = SCRIPT_DIR / "dashboard_positions_live.json"

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")
if not POLYGON_API_KEY:
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("POLYGON_API_KEY="):
                    POLYGON_API_KEY = line.split("=", 1)[1]
                    break

BASE_URL = "https://api.polygon.io"

# Crypto tickers that Polygon.io doesn't have (or has wrong stocks with same ticker)
CRYPTO_TICKERS = {'BTC', 'ETH', 'XRP', 'SOL', 'DOGE', 'BNB', 'HBAR', 'ADA', 'TRX', 'DASH'}

# ─── DATA LOADING ────────────────────────────────────────────────────
def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def load_portfolio_tickers():
    """Extract unique tickers from portfolio."""
    data = load_json(POSITIONS_FILE, {})
    tickers = set()
    positions = []
    
    if isinstance(data, dict):
        positions = data.get("positions", [])
    elif isinstance(data, list):
        positions = data
    
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker and ticker not in {"CASH", "USD", "MXN", "CASH_USD", "CASH_MXN"}:
            tickers.add(ticker)
    
    return tickers, positions


# ─── PRICE FETCHING ──────────────────────────────────────────────────
def fetch_polygon_quote(ticker):
    """Fetch snapshot quote from Polygon."""
    if not POLYGON_API_KEY:
        return None
    
    url = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {POLYGON_API_KEY}"})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
            if data.get("status") == "OK" and "ticker" in data:
                t = data["ticker"]
                day = t.get("day", {})
                prev = t.get("prevDay", {})
                tod = t.get("todaysChange", 0)
                tod_pct = t.get("todaysChangePerc", 0)
                
                return {
                    "ticker": ticker,
                    "price": t.get("lastTrade", {}).get("p") or day.get("c") or prev.get("c", 0),
                    "open": day.get("o", 0),
                    "high": day.get("h", 0),
                    "low": day.get("l", 0),
                    "volume": day.get("v", 0),
                    "vwap": day.get("vw", 0),
                    "change": tod,
                    "change_pct": tod_pct,
                    "prev_close": prev.get("c", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "polygon"
                }
    except Exception as e:
        print(f"  ⚠️ {ticker}: {e}")
    
    return None


def fetch_all_prices(tickers, max_workers=10):
    """Fetch prices for all tickers in parallel."""
    results = {}
    
    # Separate crypto from stocks
    stock_tickers = [t for t in tickers if t not in CRYPTO_TICKERS]
    crypto_tickers = [t for t in tickers if t in CRYPTO_TICKERS]
    
    # Fetch stock prices from Polygon
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_polygon_quote, t): t for t in stock_tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                if result:
                    results[ticker] = result
                    print(f"  ✓ {ticker}: ${result['price']:.2f} ({result['change_pct']:+.2f}%)")
                else:
                    print(f"  ✗ {ticker}: no data")
            except Exception as e:
                print(f"  ✗ {ticker}: {e}")
    
    # For crypto, load from binance_portfolio.json or keep original
    if crypto_tickers:
        print(f"\n   Loading {len(crypto_tickers)} crypto prices from Binance...")
        binance_data = load_json(SCRIPT_DIR / "binance_portfolio.json", {})
        binance_prices = {}
        for bal in binance_data.get("balances", []):
            asset = bal.get("asset", "")
            if asset in crypto_tickers:
                binance_prices[asset] = bal.get("price_usd", 0)
        
        for ticker in crypto_tickers:
            if ticker in binance_prices and binance_prices[ticker] > 0:
                results[ticker] = {
                    "ticker": ticker,
                    "price": binance_prices[ticker],
                    "open": 0, "high": 0, "low": 0,
                    "volume": 0, "vwap": 0,
                    "change": 0, "change_pct": 0,
                    "prev_close": binance_prices[ticker],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "binance"
                }
                print(f"  ✓ {ticker}: ${binance_prices[ticker]:,.4f} (from Binance)")
            else:
                print(f"  ⚠️ {ticker}: no Binance price, keeping original")
    
    return results


# ─── MAIN ────────────────────────────────────────────────────────────
def update_live_prices():
    print("🔵 VOX Live Price Fetcher")
    print(f"   API Key: {'✓' if POLYGON_API_KEY else '✗ MISSING'}")
    
    tickers, positions = load_portfolio_tickers()
    print(f"   Portfolio: {len(positions)} positions, {len(tickers)} unique tickers")
    
    if not tickers:
        print("   No tickers to fetch.")
        return {}
    
    if not POLYGON_API_KEY:
        print("   ERROR: POLYGON_API_KEY not found in .env")
        return {}
    
    print(f"\n   Fetching {len(tickers)} prices from Polygon...")
    prices = fetch_all_prices(tickers)
    
    # Load grades
    grades_file = SCRIPT_DIR / "portfolio_grades.json"
    grades = {}
    if grades_file.exists():
        try:
            with open(grades_file) as f:
                gdata = json.load(f)
            # New format: grades are in strong_buy, moderate_buy, avoid lists
            for cat in ["strong_buy", "moderate_buy", "avoid"]:
                for item in gdata.get(cat, []):
                    if isinstance(item, dict) and "ticker" in item:
                        grades[item["ticker"]] = item.get("grade", 0)
            # Also check old flat format
            if not grades and "results" in gdata:
                results = gdata["results"]
                if isinstance(results, list):
                    for item in results:
                        if isinstance(item, dict) and "ticker" in item:
                            grades[item["ticker"]] = item.get("grade", 0)
                elif isinstance(results, dict):
                    for k, v in results.items():
                        if isinstance(v, dict):
                            grades[k] = v.get("grade", 0)
                        else:
                            grades[k] = v
        except Exception as e:
            print(f"   ⚠️ Could not load grades: {e}")
    
    print(f"   Grades loaded: {len(grades)} tickers")
    
    # Build live positions array
    live_positions = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        price_data = prices.get(ticker, {})
        
        live_pos = dict(pos)
        if price_data:
            live_price = price_data["price"]
            shares = pos.get("shares", 0) or pos.get("quantity", 0)
            cost_basis = pos.get("cost_basis", 0) or pos.get("avg_cost", 0)
            
            live_pos["live_price"] = live_price
            live_pos["price_change"] = price_data.get("change", 0)
            live_pos["price_change_pct"] = price_data.get("change_pct", 0)
            live_pos["live_value"] = live_price * shares if shares else pos.get("value", 0)
            live_pos["live_pnl"] = (live_price - cost_basis) * shares if (shares and cost_basis) else pos.get("pnl", 0)
            live_pos["volume"] = price_data.get("volume", 0)
            live_pos["price_updated"] = price_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        elif ticker in CRYPTO_TICKERS:
            # For crypto without price data, keep original values
            print(f"   ⚠️ {ticker}: crypto ticker, keeping original price ${pos.get('price', 0)}")
            live_pos["live_price"] = pos.get("price", 0)
            live_pos["live_value"] = pos.get("value", 0)
            live_pos["live_pnl"] = pos.get("pnl", 0)
            live_pos["price_change"] = 0
            live_pos["price_change_pct"] = 0
            live_pos["volume"] = 0
            live_pos["price_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Merge grade
        live_pos["grade"] = grades.get(ticker, 0)
        
        live_positions.append(live_pos)
    
    # Save to JSON (legacy)
    output = {
        "timestamp": datetime.now().isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "polygon",
        "count": len(live_positions),
        "positions": live_positions,
        "prices": prices
    }
    
    with open(LIVE_PRICES_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    # Sync to Supabase
    try:
        from vox_supabase_sync import sync_positions
        synced = sync_positions(live_positions)
        print(f"   ✅ Synced {synced} positions to Supabase")
    except Exception as e:
        print(f"   ⚠️ Supabase sync failed: {e}")
    
    print(f"\n✅ Saved {len(live_positions)} positions to {LIVE_PRICES_FILE.name}")
    print(f"   Updated at: {output['updated_at']}")
    
    return prices


if __name__ == "__main__":
    update_live_prices()
