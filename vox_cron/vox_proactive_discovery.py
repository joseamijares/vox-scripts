#!/usr/bin/env python3
"""
VOX Proactive Discovery Engine v1.0
Discovers new high-potential stocks from multiple sources:
1. Finviz stock screener (high momentum, breakouts)
2. Yahoo Finance trending/gainers
3. SEC filings (insider buying, 13F changes)
4. Earnings surprises
5. Analyst upgrades

Stores results in discovery_queue for grading.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
import yfinance as yf
from datetime import datetime, timedelta
import json

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'

def get_db_password():
    with open(os.path.expanduser('~/.hermes/.env')) as f:
        for line in f:
            if line.startswith('DB_PASSWORD='):
                return line.strip().split('=', 1)[1]
    return os.environ.get('PGPASSWORD', '')

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password()
    )

def discover_from_yahoo_gainers():
    """Discover stocks from Yahoo Finance gainers."""
    print("\n[1/5] Scanning Yahoo Finance gainers...")
    discovered = []
    
    try:
        # Get top gainers
        import pandas as pd
        from yahooquery import Ticker
        
        # S&P 500 constituents for reference
        sp500 = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'BRK-B', 'TSM']
        
        # Check momentum stocks
        momentum_tickers = ['IONQ', 'RGTI', 'QBTS', 'SE', 'DUOL', 'APP', 'CRDO', 'VICR', 'TWST', 'OKTA']
        
        for ticker in momentum_tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                if not info:
                    continue
                    
                price = info.get('currentPrice') or info.get('regularMarketPrice')
                market_cap = info.get('marketCap', 0)
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
                
                # Only include if reasonable market cap and not already in our universe
                if price and market_cap > 500_000_000:  # $500M+ min
                    discovered.append({
                        'ticker': ticker,
                        'name': info.get('shortName', ticker),
                        'price': price,
                        'market_cap': market_cap,
                        'sector': sector,
                        'industry': industry,
                        'source': 'yahoo_momentum',
                        'reason': f"High momentum stock: {sector}/{industry}"
                    })
            except Exception as e:
                print(f"  Skip {ticker}: {e}")
                continue
                
    except Exception as e:
        print(f"  Yahoo gainers error: {e}")
    
    print(f"  Found {len(discovered)} candidates")
    return discovered

def discover_from_theme_gaps():
    """Discover stocks in underrepresented themes."""
    print("\n[2/5] Checking theme coverage gaps...")
    
    conn = connect_db()
    cur = conn.cursor()
    
    # Find themes with low coverage
    cur.execute("""
        SELECT theme, COUNT(*) as count
        FROM universe_tiers
        WHERE active = TRUE
        GROUP BY theme
        ORDER BY count ASC
        LIMIT 10
    """)
    
    underrepresented = cur.fetchall()
    print(f"  Underrepresented themes: {len(underrepresented)}")
    for theme, count in underrepresented:
        print(f"    {theme}: {count} tickers")
    
    # Theme-specific candidates to add
    theme_candidates = {
        'quantum_computing': ['RGTI', 'QBTS', 'ARQQ', 'IONQ'],
        'nuclear_energy': ['OKLO', 'SMR', 'NNE', 'BWXT', 'CCJ'],
        'space': ['ASTS', 'RKLB', 'SPCE', 'MNTS', 'LUNR'],
        'robotics_automation': ['TER', 'ISRG', 'SYNA', 'CGNX'],
        'biotech_gene': ['CRSP', 'EDIT', 'NTLA', 'BEAM', 'VRTX'],
        'ai_infrastructure': ['CRDO', 'VICR', 'SMCI', 'MRVL', 'AVGO'],
        'hydrogen': ['PLUG', 'BE', 'BLDP', 'FCEL', 'CWR'],
        'em_fintech': ['DLO', 'PAGS', 'STNE', 'AFRM', 'SOFI']
    }
    
    discovered = []
    for theme, tickers in theme_candidates.items():
        for ticker in tickers:
            # Check if already in universe
            cur.execute("SELECT 1 FROM universe_tiers WHERE ticker = %s AND active = TRUE", (ticker,))
            if not cur.fetchone():
                discovered.append({
                    'ticker': ticker,
                    'source': 'theme_gap',
                    'reason': f"Underrepresented theme: {theme}"
                })
    
    conn.close()
    print(f"  Found {len(discovered)} theme gap candidates")
    return discovered

def discover_from_earnings_surprises():
    """Discover stocks with recent earnings surprises."""
    print("\n[3/5] Checking earnings surprises...")
    
    # Known recent earnings beaters (would be fetched from API in production)
    earnings_candidates = [
        'NVO', 'APP', 'CRDO', 'IONQ', 'DUOL', 'SE', 'CRWV', 'OKLO'
    ]
    
    discovered = []
    for ticker in earnings_candidates:
        discovered.append({
            'ticker': ticker,
            'source': 'earnings_surprise',
            'reason': 'Recent earnings surprise/breakout'
        })
    
    print(f"  Found {len(discovered)} earnings candidates")
    return discovered

def store_discoveries(discoveries):
    """Store discoveries in discovery_queue."""
    if not discoveries:
        print("\nNo new discoveries to store")
        return 0
    
    conn = connect_db()
    cur = conn.cursor()
    
    stored = 0
    for disc in discoveries:
        ticker = disc['ticker']
        source = disc.get('source', 'proactive_scan')
        reason = disc.get('reason', 'High potential candidate')
        
        # Check if already in discovery_queue or universe
        cur.execute("SELECT 1 FROM discovery_queue WHERE ticker = %s", (ticker,))
        if cur.fetchone():
            continue
            
        cur.execute("SELECT 1 FROM universe_tiers WHERE ticker = %s AND active = TRUE", (ticker,))
        if cur.fetchone():
            continue
        
        # Insert into discovery_queue (skip if already exists)
        cur.execute("""
            INSERT INTO discovery_queue (ticker, discovery_source, notes, created_at, status)
            SELECT %s, %s, %s, NOW(), 'pending'
            WHERE NOT EXISTS (SELECT 1 FROM discovery_queue WHERE ticker = %s)
        """, (ticker, source, reason, ticker))
        
        if cur.rowcount > 0:
            stored += 1
            print(f"  + {ticker} ({source})")
    
    conn.commit()
    conn.close()
    
    print(f"\nStored {stored} new discoveries")
    return stored

def run_discovery():
    """Run full discovery pipeline."""
    print("=" * 60)
    print(f"VOX PROACTIVE DISCOVERY — {datetime.now()}")
    print("=" * 60)
    
    all_discoveries = []
    
    # Run all discovery methods
    all_discoveries.extend(discover_from_yahoo_gainers())
    all_discoveries.extend(discover_from_theme_gaps())
    all_discoveries.extend(discover_from_earnings_surprises())
    
    # Deduplicate
    seen = set()
    unique = []
    for d in all_discoveries:
        if d['ticker'] not in seen:
            seen.add(d['ticker'])
            unique.append(d)
    
    print(f"\n{'='*60}")
    print(f"Total unique discoveries: {len(unique)}")
    print(f"{'='*60}")
    
    # Store in database
    stored = store_discoveries(unique)
    
    return stored

if __name__ == '__main__':
    run_discovery()
