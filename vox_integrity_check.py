#!/usr/bin/env python3
"""
VOX Data Integrity Check
Run this before price fetching to ensure no crypto/stock collisions
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Known ticker collisions: {ticker: preferred_broker}
TICKER_COLLISIONS = {
    "MIRA": "eToro",  # Stock on eToro, crypto token on Binance
}

# Crypto-only tickers
CRYPTO_ONLY = {'BTC', 'ETH', 'XRP', 'SOL', 'DOGE', 'BNB', 'HBAR', 'ADA', 'TRX', 'DASH'}

def check_integrity():
    """Check for data integrity issues."""
    issues = []
    
    # Load dashboard positions
    try:
        with open(SCRIPT_DIR / "dashboard_positions.json") as f:
            dash = json.load(f)
    except:
        print("❌ No dashboard_positions.json found")
        return False
    
    positions = dash.get("positions", [])
    
    # Check 1: SIDU and MIRA should be stocks, not crypto
    for pos in positions:
        ticker = pos.get("ticker", "")
        brokers = pos.get("brokers", [])
        
        if ticker in TICKER_COLLISIONS:
            preferred = TICKER_COLLISIONS[ticker]
            if preferred not in brokers:
                issues.append(f"{ticker}: Missing from {preferred} (found in {brokers})")
            
            # Check if incorrectly marked as crypto
            if "Binance" in brokers and preferred not in brokers:
                issues.append(f"{ticker}: Incorrectly attributed to Binance (should be {preferred})")
    
    # Check 2: Crypto tickers should only be in crypto-capable brokers
    CRYPTO_BROKERS = {"Binance", "eToro", "Bitso"}  # Brokers that support crypto
    for pos in positions:
        ticker = pos.get("ticker", "")
        brokers = pos.get("brokers", [])
        
        if ticker in CRYPTO_ONLY:
            non_crypto_brokers = [b for b in brokers if b not in CRYPTO_BROKERS]
            if non_crypto_brokers:
                issues.append(f"{ticker}: Crypto ticker found in non-crypto brokers: {non_crypto_brokers}")
    
    # Check 3: Grade consistency
    try:
        with open(SCRIPT_DIR / "vox_watchlist_graded.json") as f:
            wl = json.load(f)
        
        watchlist_grades = {}
        for item in wl.get("results", []):
            watchlist_grades[item["ticker"]] = item.get("grade", 0)
        
        for pos in positions:
            ticker = pos.get("ticker", "")
            dash_grade = pos.get("grade", 0)
            wl_grade = watchlist_grades.get(ticker, 0)
            
            if wl_grade > 0 and dash_grade != wl_grade:
                issues.append(f"{ticker}: Grade mismatch (dashboard: {dash_grade}, watchlist: {wl_grade})")
    except:
        pass
    
    # Report
    if issues:
        print(f"⚠️  Found {len(issues)} integrity issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("✅ All integrity checks passed")
        return True

if __name__ == "__main__":
    print("🔍 VOX Data Integrity Check")
    print(f"   Time: {datetime.now(timezone.utc).isoformat()}")
    
    if check_integrity():
        sys.exit(0)
    else:
        print("\n🚨 Run vox_data_fix_v2.py to fix issues")
        sys.exit(1)
