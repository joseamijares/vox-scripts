#!/usr/bin/env python3
"""
VOX eToro Price Updater v3 — Updates broker_positions table (correct per-broker allocations)
Fetches live prices from Yahoo Finance and updates the broker_positions table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
import yfinance as yf
from datetime import datetime
import time

# Database connection
DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'
DB_PASS = os.environ.get('PGPASSWORD', '')

def get_yf_ticker(db_ticker, cursor):
    """Get the correct Yahoo Finance ticker from mapping table."""
    cursor.execute("SELECT yf_ticker FROM ticker_mappings WHERE db_ticker = %s", (db_ticker,))
    result = cursor.fetchone()
    if result:
        return result[0]
    return db_ticker

def fetch_price(yf_ticker):
    """Fetch current price from Yahoo Finance with fallbacks."""
    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        
        # Try multiple price fields
        price = (info.get('currentPrice') or 
                info.get('regularMarketPrice') or 
                info.get('previousClose') or 0)
        
        # If no price, try history
        if not price or price == 0:
            hist = stock.history(period="5d")
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
        
        return price
    except Exception as e:
        print(f"  Error fetching {yf_ticker}: {e}")
        return 0

def update_etoro_prices():
    """Update all eToro position prices in broker_positions table."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor()
    
    print("=" * 100)
    print(f"VOX eToro Price Update — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    # Get all eToro positions from broker_positions (correct per-broker table)
    cur.execute("""
        SELECT ticker, shares, avg_cost, currency, live_value_usd
        FROM broker_positions 
        WHERE broker = 'eToro'
        ORDER BY ticker
    """)
    positions = cur.fetchall()
    
    updated = 0
    failed = 0
    total_value_usd = 0
    total_value_mxn = 0
    
    for ticker, shares, avg_cost, currency, old_live_value_usd in positions:
        try:
            shares_float = float(shares) if shares else 0
            
            # Skip MIRROR_TOTAL and CASH - these are special entries
            if ticker in ['MIRROR_TOTAL', 'CASH']:
                if old_live_value_usd:
                    total_value_usd += float(old_live_value_usd)
                print(f"  ⏭️  {ticker}: ${old_live_value_usd or 0:,.2f} (skipped - manual entry)")
                continue
            
            # Get correct Yahoo Finance ticker
            yf_ticker = get_yf_ticker(ticker, cur)
            
            # Fetch price
            price = fetch_price(yf_ticker)
            
            if price and price > 0:
                live_value = shares_float * price
                
                # Update broker_positions table
                cur.execute("""
                    UPDATE broker_positions 
                    SET live_price = %s, live_value = %s, live_value_usd = %s, updated_at = NOW()
                    WHERE broker = 'eToro' AND ticker = %s
                """, (price, live_value, live_value, ticker))
                
                # Track totals
                if currency == 'MXN':
                    total_value_mxn += live_value
                else:
                    total_value_usd += live_value
                
                updated += 1
                print(f"  ✅ {ticker} ({yf_ticker}): ${price:,.4f} → ${live_value:,.2f}")
            else:
                failed += 1
                print(f"  ⚠️  {ticker}: No price found")
            
            time.sleep(0.2)  # Rate limit
            
        except Exception as e:
            failed += 1
            print(f"  ❌ {ticker}: {str(e)[:60]}")
    
    conn.commit()
    
    # Update sync timestamp
    cur.execute("""
        UPDATE broker_accounts 
        SET last_sync_at = NOW()
        WHERE broker = 'eToro'
    """)
    conn.commit()
    
    # Summary
    print(f"\n{'='*100}")
    print(f"UPDATE COMPLETE: {updated} updated, {failed} failed")
    print(f"Portfolio Value: ${total_value_usd:,.2f} USD + ${total_value_mxn:,.2f} MXN")
    print(f"Total (USD equiv): ~${total_value_usd + total_value_mxn/17:,.2f}")
    print(f"{'='*100}")
    
    conn.close()
    return updated, failed

if __name__ == "__main__":
    update_etoro_prices()
