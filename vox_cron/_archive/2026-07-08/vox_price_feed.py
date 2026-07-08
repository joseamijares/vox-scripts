#!/usr/bin/env python3
"""
VOX PRICE FEED v1.0
Fetches real-time prices from Yahoo Finance and updates portfolio + vox_grades.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
import time
from datetime import datetime

# Try to import yfinance, install if missing
try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system("pip install yfinance --quiet")
    import yfinance as yf

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = ''

def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )

def fetch_prices(tickers):
    """Fetch prices for a list of tickers using yfinance"""
    prices = {}
    
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i+50]
        symbols_str = " ".join(batch)
        
        try:
            data = yf.download(symbols_str, period="1d", interval="1m", progress=False, threads=True)
            
            if len(batch) == 1:
                ticker = batch[0]
                if not data.empty:
                    last_price = data['Close'].iloc[-1]
                    prices[ticker] = float(last_price) if last_price is not None else 0.0
            else:
                for ticker in batch:
                    try:
                        if ticker in data['Close'].columns:
                            last_price = data['Close'][ticker].iloc[-1]
                            prices[ticker] = float(last_price) if last_price is not None else 0.0
                    except:
                        pass
        except Exception as e:
            print(f"Error fetching batch {batch}: {e}")
        
        time.sleep(0.5)
    
    return prices

def update_portfolio_prices():
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("SELECT DISTINCT ticker FROM positions WHERE ticker IS NOT NULL")
    tickers = [row[0] for row in cur.fetchall()]
    
    print(f"Fetching prices for {len(tickers)} positions...")
    prices = fetch_prices(tickers)
    
    updated = 0
    for ticker, price in prices.items():
        if price <= 0:
            continue
        
        cur.execute("""
            UPDATE positions 
            SET live_price = %s,
                live_value = shares * %s,
                live_value_usd = CASE 
                    WHEN currency = 'MXN' THEN shares * %s * 0.055
                    ELSE shares * %s 
                END,
                updated_at = NOW()
            WHERE ticker = %s
        """, (price, price, price, price, ticker))
        
        updated += cur.rowcount
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Updated {updated} positions")
    return updated

def update_vox_grades_prices():
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("SELECT DISTINCT ticker FROM vox_grades WHERE generated_at > NOW() - INTERVAL '30 days'")
    tickers = [row[0] for row in cur.fetchall()]
    
    print(f"Fetching prices for {len(tickers)} vox_grades...")
    prices = fetch_prices(tickers)
    
    updated = 0
    for ticker, price in prices.items():
        if price <= 0:
            continue
        
        cur.execute("UPDATE vox_grades SET current_price = %s, generated_at = NOW() WHERE ticker = %s",
                    (price, ticker))
        updated += cur.rowcount
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Updated {updated} vox_grades prices")
    return updated

def show_price_summary():
    conn = connect()
    cur = conn.cursor()
    
    print("\nPRICE SUMMARY")
    print("=" * 60)
    
    cur.execute("SELECT ticker, live_price, live_value_usd, grade FROM positions ORDER BY live_value_usd DESC LIMIT 10")
    
    print(f"{'Ticker':<8} {'Price':<10} {'Value USD':<12} {'Grade'}")
    print("-" * 60)
    for row in cur.fetchall():
        print(f"{row[0]:<8} ${row[1]:<9.2f} ${row[2]:<11,.2f} {row[3]}")
    
    conn.close()

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'all'
    
    if action == 'portfolio':
        update_portfolio_prices()
    elif action == 'vox':
        update_vox_grades_prices()
    elif action == 'all':
        update_portfolio_prices()
        update_vox_grades_prices()
        show_price_summary()
    else:
        print("Usage: portfolio, vox, all")

if __name__ == '__main__':
    main()
