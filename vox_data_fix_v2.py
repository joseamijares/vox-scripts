#!/usr/bin/env python3
"""
VOX Data Integrity Fix v2
Comprehensive fix for crypto/stock collisions and missing positions across all brokers
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Tickers that exist as BOTH crypto and stock - prioritize stock broker
TICKER_COLLISIONS = {
    "MIRA": {"priority": "stock", "stock_broker": "eToro", "crypto_broker": "Binance"},
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

def get_fx_rate():
    """Get USD/MXN rate."""
    try:
        result = subprocess.run(
            ["python3", "vox_fx_rate.py"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        for line in result.stdout.split("\n"):
            if "USD/MXN:" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    rate_str = parts[1].split("(")[0].strip()
                    return float(rate_str)
    except:
        pass
    return 17.5  # fallback

def extract_etoro_positions():
    """Extract eToro positions with proper symbol mapping."""
    etoro = load_json(SCRIPT_DIR / "etoro_portfolio.json", {})
    if not etoro or "clientPortfolio" not in etoro:
        return []
    
    mapping = etoro.get("_instrumentMapping", {})
    positions = etoro["clientPortfolio"].get("positions", [])
    
    extracted = []
    for pos in positions:
        instrument_id = str(pos.get("instrumentID", ""))
        symbol_info = mapping.get(instrument_id, {})
        symbol = symbol_info.get("symbol", instrument_id)
        
        if not symbol:
            continue
        
        amount = pos.get("amount", 0)
        open_rate = pos.get("openRate", 0)
        shares = amount / open_rate if open_rate else 0
        
        extracted.append({
            "ticker": symbol,
            "shares": shares,
            "value": amount,
            "pnl": 0,  # eToro doesn't provide PnL in this export
            "broker": "eToro",
            "price": open_rate,
            "type": "stock"  # eToro positions are stocks
        })
    
    return extracted

def extract_binance_positions():
    """Extract Binance positions (crypto only)."""
    binance = load_json(SCRIPT_DIR / "binance_portfolio.json", {})
    
    extracted = []
    for bal in binance.get("balances", []):
        asset = bal.get("asset", "")
        if not asset or asset not in CRYPTO_ONLY:
            continue  # Only include known crypto
        
        extracted.append({
            "ticker": asset,
            "shares": bal.get("total", 0),
            "value": bal.get("value_usd", 0),
            "pnl": 0,
            "broker": "Binance",
            "price": bal.get("price_usd", 0),
            "type": "crypto"
        })
    
    return extracted

def extract_gbm_main_positions():
    """Extract GBM Main positions."""
    gbm = load_json(SCRIPT_DIR / "gbm_main_portfolio.json", {})
    fx_rate = get_fx_rate()
    
    extracted = []
    all_positions = gbm.get("sic_positions", []) + gbm.get("national_positions", [])
    
    for pos in all_positions:
        ticker = pos.get("ticker", "").replace("GBM ", "").replace(" ISHRS", "").strip()
        if not ticker:
            continue
        
        market_value_mxn = pos.get("market_value_mxn", 0)
        pnl_mxn = pos.get("pnl_mxn", 0)
        qty = pos.get("qty", 0)
        price_mxn = pos.get("price_mxn", 0)
        
        extracted.append({
            "ticker": ticker,
            "shares": qty,
            "value": market_value_mxn / fx_rate,  # Convert to USD
            "pnl": pnl_mxn / fx_rate,
            "broker": "GBM Main",
            "price": price_mxn / fx_rate,
            "type": "stock"
        })
    
    return extracted

def extract_gbm_usa_positions():
    """Extract GBM USA positions."""
    gbm = load_json(SCRIPT_DIR / "gbm_usa_portfolio.json", {})
    
    extracted = []
    for pos in gbm.get("positions", []):
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        
        extracted.append({
            "ticker": ticker,
            "shares": pos.get("qty", 0),
            "value": pos.get("market_value_usd", 0),
            "pnl": pos.get("pnl_usd", 0),
            "broker": "GBM USA",
            "price": pos.get("price_usd", 0),
            "type": "stock"
        })
    
    return extracted

def extract_ibkr_positions():
    """Extract IBKR positions."""
    ibkr = load_json(SCRIPT_DIR / "ibkr_portfolio.json", {})
    
    extracted = []
    for pos in ibkr.get("positions", []):
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        
        extracted.append({
            "ticker": ticker,
            "shares": pos.get("shares", 0),
            "value": pos.get("market_value", 0),
            "pnl": pos.get("unrealized_pnl", 0),
            "broker": "IBKR",
            "price": pos.get("last_price", 0),
            "type": "stock"
        })
    
    return extracted

def extract_schwab_positions():
    """Extract Schwab positions."""
    schwab = load_json(SCRIPT_DIR / "schwab_portfolio.json", {})
    
    extracted = []
    for pos in schwab.get("positions", []):
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        
        extracted.append({
            "ticker": ticker,
            "shares": pos.get("shares", 0),
            "value": pos.get("market_value", 0),
            "pnl": pos.get("unrealized_pnl", 0),
            "broker": "Schwab",
            "price": pos.get("last_price", 0),
            "type": "stock"
        })
    
    return extracted

def merge_positions(all_positions):
    """Merge positions by ticker, handling collisions."""
    unified = {}
    
    for pos in all_positions:
        ticker = pos["ticker"]
        if not ticker:
            continue
        
        # Handle ticker collisions
        if ticker in TICKER_COLLISIONS:
            collision = TICKER_COLLISIONS[ticker]
            pos_broker = pos.get("broker", "")
            
            # Skip crypto broker if we have stock version
            if collision["priority"] == "stock" and pos_broker == collision.get("crypto_broker"):
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
        
        broker = pos.get("broker", "")
        if broker and broker not in u["brokers"]:
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
    
    return positions_list, total_value

def load_grades():
    """Load watchlist grades."""
    grades = {}
    try:
        with open(SCRIPT_DIR / "vox_watchlist_graded.json") as f:
            data = json.load(f)
        for item in data.get("results", []):
            if isinstance(item, dict) and "ticker" in item:
                grades[item["ticker"]] = item.get("grade", 0)
    except:
        pass
    return grades

def main():
    print("=" * 70)
    print("🔧 VOX DATA INTEGRITY FIX v2")
    print("=" * 70)
    
    # Extract all positions
    print("\n📥 Extracting positions from all brokers...")
    
    etoro = extract_etoro_positions()
    print(f"  eToro: {len(etoro)} positions")
    
    binance = extract_binance_positions()
    print(f"  Binance: {len(binance)} positions")
    
    gbm_main = extract_gbm_main_positions()
    print(f"  GBM Main: {len(gbm_main)} positions")
    
    gbm_usa = extract_gbm_usa_positions()
    print(f"  GBM USA: {len(gbm_usa)} positions")
    
    ibkr = extract_ibkr_positions()
    print(f"  IBKR: {len(ibkr)} positions")
    
    schwab = extract_schwab_positions()
    print(f"  Schwab: {len(schwab)} positions")
    
    # Merge all
    all_positions = etoro + binance + gbm_main + gbm_usa + ibkr + schwab
    print(f"\n🔄 Merging {len(all_positions)} total positions...")
    
    positions_list, total_value = merge_positions(all_positions)
    print(f"✅ Unified: {len(positions_list)} unique positions")
    print(f"   Total value: ${total_value:,.2f}")
    
    # Load grades
    grades = load_grades()
    print(f"   Grades loaded: {len(grades)} tickers")
    
    # Build dashboard format
    dashboard_positions = []
    for pos in positions_list:
        ticker = pos["ticker"]
        dashboard_positions.append({
            "ticker": ticker,
            "value": pos["value"],
            "pnl": pos["pnl"],
            "shares": pos["shares"],
            "brokers": pos["brokers"],
            "price": pos["price"],
            "pct": pos.get("pct", 0),
            "grade": grades.get(ticker, 0)
        })
    
    # Save dashboard_positions.json
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_value": total_value,
        "total_positions": len(dashboard_positions),
        "broker_breakdown": {},
        "broker_status": {},
        "positions": dashboard_positions
    }
    
    with open(SCRIPT_DIR / "dashboard_positions.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Saved dashboard_positions.json")
    
    # Save dashboard_positions_live.json
    live_positions = []
    for pos in dashboard_positions:
        live_positions.append({
            **pos,
            "live_price": pos["price"],
            "live_value": pos["value"],
            "live_pnl": pos["pnl"],
            "price_change": 0,
            "price_change_pct": 0,
            "volume": 0,
            "price_updated": datetime.now(timezone.utc).isoformat()
        })
    
    live_output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "fixed_v2",
        "count": len(live_positions),
        "positions": live_positions
    }
    
    with open(SCRIPT_DIR / "dashboard_positions_live.json", "w") as f:
        json.dump(live_output, f, indent=2)
    print(f"💾 Saved dashboard_positions_live.json")
    
    # Show MIRA and SIDU
    print("\n📊 MIRA and SIDU Status:")
    for pos in positions_list:
        if pos["ticker"] in ["MIRA", "SIDU"]:
            print(f"   {pos['ticker']}: ${pos['value']:,.2f} | {pos['shares']:.2f} shares | Brokers: {pos['brokers']} | Grade: {grades.get(pos['ticker'], 'N/A')}")
    
    # Show top 10
    print("\n📊 Top 10 Positions:")
    for pos in positions_list[:10]:
        print(f"   {pos['ticker']}: ${pos['value']:,.2f} | {pos['brokers']}")
    
    print("\n✅ Fix complete! Run vox_live_prices.py to fetch fresh prices.")

if __name__ == "__main__":
    import subprocess
    main()
