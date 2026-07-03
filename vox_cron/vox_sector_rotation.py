#!/usr/bin/env python3
"""
VOX Sector Rotation Detector v1.0
Tracks money flow between sectors to detect rotation patterns.
Uses SP500 sector ETFs as proxies and calculates:
- Sector momentum (1w, 1m, 3m)
- Relative strength vs SPY
- Flow intensity (volume + price change)
- Rotation signals (early, confirmed, late)

Stores in sector_rotation table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
import yfinance as yf
from datetime import datetime, timedelta
import json
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from hermes_secrets import get_env

DB_HOST = get_env('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = get_env('DB_PORT', '35577')
DB_NAME = get_env('DB_NAME', 'railway')
DB_USER = get_env('DB_USER', 'postgres')

def get_db_password():
    return get_env('PGPASSWORD', get_env('DB_PASSWORD', ''))

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password(), sslmode='require'
    )

# Sector ETFs as proxies
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financials': 'XLF',
    'Energy': 'XLE',
    'Industrials': 'XLI',
    'Consumer Discretionary': 'XLY',
    'Consumer Staples': 'XLP',
    'Materials': 'XLB',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Communication Services': 'XLC',
}

def create_sector_rotation_table():
    """Create sector rotation tracking table."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_rotation (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(50) NOT NULL,
            etf_ticker VARCHAR(10) NOT NULL,
            snapshot_date DATE NOT NULL,
            price NUMERIC(10,2),
            volume BIGINT,
            return_1w NUMERIC(8,4),
            return_1m NUMERIC(8,4),
            return_3m NUMERIC(8,4),
            relative_strength NUMERIC(8,4),
            momentum_score NUMERIC(8,4),
            flow_intensity NUMERIC(8,4),
            rotation_signal VARCHAR(20),
            rank INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(sector, snapshot_date)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ sector_rotation table ready")

def fetch_sector_data(etf, period='3mo'):
    """Fetch sector ETF data."""
    try:
        ticker = yf.Ticker(etf)
        hist = ticker.history(period=period)
        
        if hist.empty:
            return None
        
        current_price = float(hist['Close'].iloc[-1])
        current_volume = int(hist['Volume'].iloc[-1])
        
        # Calculate returns
        price_1w = float(hist['Close'].iloc[-5]) if len(hist) >= 5 else current_price
        price_1m = float(hist['Close'].iloc[-20]) if len(hist) >= 20 else current_price
        price_3m = float(hist['Close'].iloc[0])
        
        return_1w = ((current_price - price_1w) / price_1w) * 100 if price_1w > 0 else 0
        return_1m = ((current_price - price_1m) / price_1m) * 100 if price_1m > 0 else 0
        return_3m = ((current_price - price_3m) / price_3m) * 100 if price_3m > 0 else 0
        
        return {
            'price': current_price,
            'volume': current_volume,
            'return_1w': return_1w,
            'return_1m': return_1m,
            'return_3m': return_3m
        }
    except Exception as e:
        print(f"  Error fetching {etf}: {e}")
        return None

def calculate_relative_strength(sector_returns, spy_return):
    """Calculate relative strength vs SPY."""
    if spy_return == 0:
        return 0
    return sector_returns - spy_return

def calculate_momentum_score(data):
    """Calculate composite momentum score."""
    return (data['return_1w'] * 0.4 + 
            data['return_1m'] * 0.35 + 
            data['return_3m'] * 0.25)

def calculate_flow_intensity(data):
    """Calculate money flow intensity."""
    return abs(data['return_1w']) * (data['volume'] / 1000000)

def detect_rotation_signal(data, rank, total_sectors):
    """Detect rotation signal based on momentum and rank."""
    momentum = data['momentum_score']
    
    if rank <= 3 and momentum > 5 and data['return_1w'] > data['return_1m']:
        return 'early'
    elif rank <= 3 and momentum > 3:
        return 'confirmed'
    elif rank <= 3 and momentum > 0 and data['return_1w'] < data['return_1m']:
        return 'late'
    
    return 'none'

def analyze_sector_rotation():
    """Analyze sector rotation."""
    print("\n[1/3] Fetching sector ETF data...")
    
    # Fetch SPY as benchmark
    spy_data = fetch_sector_data('SPY')
    spy_return_1m = spy_data['return_1m'] if spy_data else 0
    
    sector_data = {}
    for sector, etf in SECTOR_ETFS.items():
        data = fetch_sector_data(etf)
        if data:
            data['relative_strength'] = calculate_relative_strength(data['return_1m'], spy_return_1m)
            data['momentum_score'] = calculate_momentum_score(data)
            data['flow_intensity'] = calculate_flow_intensity(data)
            sector_data[sector] = data
    
    print(f"  Analyzed {len(sector_data)} sectors")
    
    return sector_data, spy_data

def store_sector_data(sector_data, spy_data):
    """Store sector rotation data."""
    conn = connect_db()
    cur = conn.cursor()
    
    today = datetime.now().date()
    stored = 0
    
    # Rank by momentum
    ranked = sorted(sector_data.items(), key=lambda x: x[1]['momentum_score'], reverse=True)
    
    for rank, (sector, data) in enumerate(ranked, 1):
        signal = detect_rotation_signal(data, rank, len(ranked))
        
        cur.execute("""
            INSERT INTO sector_rotation 
            (sector, etf_ticker, snapshot_date, price, volume, return_1w, return_1m, return_3m,
             relative_strength, momentum_score, flow_intensity, rotation_signal, rank)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sector, snapshot_date) DO UPDATE SET
                price = EXCLUDED.price,
                volume = EXCLUDED.volume,
                return_1w = EXCLUDED.return_1w,
                return_1m = EXCLUDED.return_1m,
                return_3m = EXCLUDED.return_3m,
                relative_strength = EXCLUDED.relative_strength,
                momentum_score = EXCLUDED.momentum_score,
                flow_intensity = EXCLUDED.flow_intensity,
                rotation_signal = EXCLUDED.rotation_signal,
                rank = EXCLUDED.rank,
                created_at = NOW()
        """, (sector, SECTOR_ETFS[sector], today, data['price'], data['volume'],
              data['return_1w'], data['return_1m'], data['return_3m'],
              data['relative_strength'], data['momentum_score'], data['flow_intensity'],
              signal, rank))
        
        if cur.rowcount > 0:
            stored += 1
    
    conn.commit()
    conn.close()
    print(f"  Stored {stored} sector records")
    return stored

def generate_rotation_report():
    """Generate sector rotation report."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT sector, etf_ticker, return_1w, return_1m, return_3m,
               relative_strength, momentum_score, rotation_signal, rank
        FROM sector_rotation
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM sector_rotation)
        ORDER BY rank ASC
    """)
    
    print(f"\n{'='*80}")
    print(f"📊 SECTOR ROTATION REPORT — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*80}")
    print(f"{'Rank':<6} {'Sector':<25} {'ETF':<6} {'1W':<8} {'1M':<8} {'3M':<8} {'RelStr':<8} {'Momentum':<10} {'Signal'}")
    print(f"{'-'*80}")
    
    rotation_sectors = []
    
    for row in cur.fetchall():
        sector, etf, r1w, r1m, r3m, rs, mom, signal, rank = row
        
        signal_icon = '🚀' if signal == 'early' else '✅' if signal == 'confirmed' else '⚠️' if signal == 'late' else '  '
        print(f"{rank:<6} {sector:<25} {etf:<6} {r1w:>6.1f}% {r1m:>6.1f}% {r3m:>6.1f}% {rs:>6.1f}% {mom:>8.1f}   {signal_icon} {signal}")
        
        if signal in ['early', 'confirmed']:
            rotation_sectors.append({
                'sector': sector,
                'etf': etf,
                'signal': signal,
                'momentum': mom
            })
    
    print(f"{'='*80}")
    
    if rotation_sectors:
        print(f"\n🎯 ROTATION OPPORTUNITIES:")
        for rs in rotation_sectors:
            print(f"  {rs['signal'].upper()}: {rs['sector']} ({rs['etf']}) — Momentum: {rs['momentum']:.1f}")
    else:
        print(f"\n⚠️ No clear rotation signals detected")
    
    conn.close()
    return rotation_sectors

def run_sector_rotation_detector():
    """Main entry point."""
    print("=" * 80)
    print(f"VOX SECTOR ROTATION DETECTOR — {datetime.now()}")
    print("=" * 80)
    
    create_sector_rotation_table()
    
    sector_data, spy_data = analyze_sector_rotation()
    store_sector_data(sector_data, spy_data)
    rotation_sectors = generate_rotation_report()
    
    return rotation_sectors

if __name__ == '__main__':
    run_sector_rotation_detector()
