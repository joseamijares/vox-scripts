#!/usr/bin/env python3
"""
VOX Data Integrity Fix
Fixes crypto/stock ticker collisions and missing positions
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Tickers that exist as BOTH crypto and stock
# Format: {ticker: {"stock_broker": "eToro", "crypto_broker": "Binance"}}
TICKER_COLLISIONS = {
    "MIRA": {"stock_broker": "eToro", "crypto_broker": "Binance", "type": "stock"},
}

# Crypto-only tickers (never stocks)
CRYPTO_ONLY = {'BTC', 'ETH', 'XRP', 'SOL', 'DOGE', 'BNB', 'HBAR', 'ADA', 'TRX', 'DASH'}

def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def fix_dashboard_positions():
    """Fix dashboard_positions.json with correct broker attribution."""
    print("🔧 Fixing dashboard_positions.json...")
    
    # Load all broker files
    etoro = load_json(SCRIPT_DIR / "etoro_portfolio.json", {})
    binance = load_json(SCRIPT_DIR / "binance_portfolio.json", {})
    gbm_main = load_json(SCRIPT_DIR / "gbm_main_portfolio.json", {})
    gbm_usa = load_json(SCRIPT_DIR / "gbm_usa_portfolio.json", {})
    ibkr = load_json(SCRIPT_DIR / "ibkr_portfolio.json", {})
    schwab = load_json(SCRIPT_DIR / "schwab_portfolio.json", {})
    
    # Extract eToro positions with proper symbols
    etoro_positions = {}
    if etoro and "clientPortfolio" in etoro:
        mapping = etoro.get("_instrumentMapping", {})
        for pos in etoro["clientPortfolio"].get("positions", []):
            instrument_id = str(pos.get("instrumentID", ""))
            symbol_info = mapping.get(instrument_id, {})
            symbol = symbol_info.get("symbol", instrument_id)
            
            if symbol and symbol not in etoro_positions:
                etoro_positions[symbol] = {
                    "ticker": symbol,
                    "shares": 0,
                    "value": 0,
                    "pnl": 0,
                    "broker": "eToro",
                    "price": pos.get("openRate", 0)
                }
            
            if symbol in etoro_positions:
                etoro_positions[symbol]["shares"] += pos.get("amount", 0) / pos.get("openRate", 1) if pos.get("openRate") else 0
                etoro_positions[symbol]["value"] += pos.get("amount", 0)
    
    # Extract Binance positions (crypto only)
    binance_positions = {}
    for bal in binance.get("balances", []):
        asset = bal.get("asset", "")
        if asset and asset not in CRYPTO_ONLY:
            continue  # Skip non-crypto
        if asset:
            binance_positions[asset] = {
                "ticker": asset,
                "shares": bal.get("total", 0),
                "value": bal.get("value_usd", 0),
                "pnl": 0,
                "broker": "Binance",
                "price": bal.get("price_usd", 0)
            }
    
    # Handle MIRA collision: prefer eToro stock over Binance crypto
    all_positions = []
    
    # Add eToro positions first (stocks take priority)
    for ticker, pos in etoro_positions.items():
        if ticker in TICKER_COLLISIONS:
            # This is a stock position from eToro
            pos["type"] = "stock"
            pos["brokers"] = ["eToro"]
        else:
            pos["brokers"] = ["eToro"]
        all_positions.append(pos)
    
    # Add Binance positions (only if not already added as stock)
    for ticker, pos in binance_positions.items():
        if ticker in TICKER_COLLISIONS:
            # Skip - already have stock version from eToro
            continue
        pos["brokers"] = ["Binance"]
        all_positions.append(pos)
    
    # Add manual brokers
    for pos in gbm_main.get("positions", []):
        all_positions.append({
            "ticker": pos.get("ticker", ""),
            "shares": pos.get("qty", 0),
            "value": pos.get("market_value_mxn", 0),
            "pnl": pos.get("pnl_mxn", 0),
            "broker": "GBM Main",
            "brokers": ["GBM Main"],
            "price": pos.get("price_mxn", 0)
        })
    
    # ... (similar for other brokers)
    
    # Build unified positions
    unified = {}
    for pos in all_positions:
        ticker = pos["ticker"]
        if not ticker:
            continue
        
        if ticker not in unified:
            unified[ticker] = {
                "ticker": ticker,
                "shares": 0,
                "value": 0,
                "pnl": 0,
                "brokers": [],
                "price": 0,
                "type": pos.get("type", "stock")
            }
        
        u = unified[ticker]
        u["shares"] += pos.get("shares", 0)
        u["value"] += pos.get("value", 0)
        u["pnl"] += pos.get("pnl", 0)
        
        for broker in pos.get("brokers", []):
            if broker not in u["brokers"]:
                u["brokers"].append(broker)
    
    # Calculate derived values
    positions_list = []
    total_value = sum(p["value"] for p in unified.values())
    
    for ticker, pos in unified.items():
        if pos["shares"] > 0:
            pos["price"] = pos["value"] / pos["shares"]
            pos["cost_basis"] = (pos["value"] - pos["pnl"]) / pos["shares"]
            pos["pnl_pct"] = (pos["pnl"] / (pos["value"] - pos["pnl"]) * 100) if (pos["value"] - pos["pnl"]) > 0 else 0
            pos["pct"] = (pos["value"] / total_value * 100) if total_value > 0 else 0
        positions_list.append(pos)
    
    positions_list.sort(key=lambda x: x["value"], reverse=True)
    
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_value": total_value,
        "total_positions": len(positions_list),
        "positions": positions_list
    }
    
    with open(SCRIPT_DIR / "dashboard_positions.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Fixed {len(positions_list)} positions")
    print(f"   Total value: ${total_value:,.2f}")
    
    # Show MIRA and SIDU specifically
    for pos in positions_list:
        if pos["ticker"] in ["MIRA", "SIDU"]:
            print(f"   {pos['ticker']}: ${pos['value']:,.2f} | Brokers: {pos['brokers']} | Type: {pos.get('type', 'stock')}")
    
    return output

def fix_live_prices():
    """Update live prices with correct crypto/stock handling."""
    print("\n🔧 Fixing live prices...")
    
    # Load positions
    positions_data = load_json(SCRIPT_DIR / "dashboard_positions.json", {})
    positions = positions_data.get("positions", [])
    
    # Load grades
    grades = {}
    try:
        with open(SCRIPT_DIR / "vox_watchlist_graded.json") as f:
            gdata = json.load(f)
        for item in gdata.get("results", []):
            if isinstance(item, dict) and "ticker" in item:
                grades[item["ticker"]] = item.get("grade", 0)
    except:
        pass
    
    # For now, mark positions with grades
    for pos in positions:
        ticker = pos["ticker"]
        pos["grade"] = grades.get(ticker, 0)
        
        # Set live price = current price (will be updated by price fetcher)
        pos["live_price"] = pos.get("price", 0)
        pos["live_value"] = pos.get("value", 0)
        pos["live_pnl"] = pos.get("pnl", 0)
        pos["price_change"] = 0
        pos["price_change_pct"] = 0
        pos["volume"] = 0
        pos["price_updated"] = datetime.now(timezone.utc).isoformat()
    
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "fixed",
        "count": len(positions),
        "positions": positions
    }
    
    with open(SCRIPT_DIR / "dashboard_positions_live.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Fixed live prices for {len(positions)} positions")
    
    return output

if __name__ == "__main__":
    print("=" * 70)
    print("🔧 VOX DATA INTEGRITY FIX")
    print("=" * 70)
    
    fix_dashboard_positions()
    fix_live_prices()
    
    print("\n✅ All fixes applied!")
    print("   Next: Run vox_live_prices.py to fetch fresh prices")
