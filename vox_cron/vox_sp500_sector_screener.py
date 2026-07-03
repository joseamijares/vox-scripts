#!/usr/bin/env python3
"""
S&P 500 Daily Sector Leaders Screener
Scans S&P 500 universe and stores top 3 leaders per sector in sp500_sector_leaders table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
from pathlib import Path
import psycopg2
from datetime import datetime

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from hermes_secrets import get_env

# Database connection
DB_HOST = get_env("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = get_env("DB_PORT", "35577")
DB_USER = get_env("DB_USER", "postgres")
DB_PASSWORD = get_env("DB_PASSWORD", "")
DB_NAME = get_env("DB_NAME", "railway")

def connect():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )

def get_sp500_universe(conn):
    """Get S&P 500 tickers from database"""
    cur = conn.cursor()
    cur.execute("SELECT ticker, sector FROM sp500_universe WHERE is_active = TRUE")
    rows = cur.fetchall()
    cur.close()
    return rows

def store_leaders(conn, leaders, run_date):
    """Store sector leaders in database"""
    cur = conn.cursor()
    for leader in leaders:
        ticker, sector, momentum, return_5d, rank = leader
        cur.execute("""
            INSERT INTO sp500_sector_leaders 
            (run_date, sector, ticker, momentum_score, return_5d, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (run_date, sector, ticker) DO UPDATE SET
                momentum_score = EXCLUDED.momentum_score,
                return_5d = EXCLUDED.return_5d,
                created_at = NOW()
        """, (run_date, sector, ticker, momentum, return_5d))
    conn.commit()
    cur.close()

def main():
    print(f"S&P 500 Sector Leaders Screener — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    conn = connect()
    
    # Get S&P 500 universe
    universe = get_sp500_universe(conn)
    print(f"Loaded {len(universe)} S&P 500 tickers")
    
    # Group by sector
    sectors = {}
    for ticker, sector in universe:
        if sector not in sectors:
            sectors[sector] = []
        sectors[sector].append(ticker)
    
    print(f"Found {len(sectors)} sectors")
    
    # For each sector, get top 3 by grade from vox_grades
    leaders = []
    run_date = datetime.now().date()
    for sector, tickers in sectors.items():
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, vox_grade, technical_score
            FROM vox_grades
            WHERE ticker = ANY(%s)
            ORDER BY vox_grade DESC, technical_score DESC
            LIMIT 3
        """, (tickers,))
        
        for rank, row in enumerate(cur.fetchall(), 1):
            ticker, grade, tech = row
            momentum = tech or 0
            return_5d = 0  # Would need historical data
            leaders.append((ticker, sector, momentum, return_5d, rank))
        
        cur.close()
    
    # Store leaders
    store_leaders(conn, leaders, run_date)
    print(f"Stored {len(leaders)} sector leaders ({len(sectors)} sectors × top 3)")
    
    conn.close()
    print("Done!")

if __name__ == "__main__":
    main()
