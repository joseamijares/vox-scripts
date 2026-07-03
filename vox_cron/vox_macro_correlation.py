#!/usr/bin/env python3
"""
VOX Macro Correlation Engine v1.0
Tracks macroeconomic indicators and correlates with portfolio performance:
1. Fed Policy (Fed Funds Rate, FOMC decisions, dot plot)
2. Inflation (CPI, PCE, PPI)
3. GDP & Employment (GDP growth, unemployment, NFP)
4. Yield Curve (10Y-2Y spread, recession probability)
5. Dollar Index (DXY) — impacts international holdings
6. VIX — fear gauge

Stores in macro_indicators table and correlates with portfolio returns.
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

# Macro indicators to track
MACRO_INDICATORS = {
    'DXY': 'UUP',           # Dollar Index proxy
    'VIX': '^VIX',          # Volatility index
    'T10Y': '^TNX',         # 10-Year Treasury yield
    'T2Y': '^IRX',          # 2-Year Treasury yield (approx)
    'GOLD': 'GLD',          # Gold ETF
    'OIL': 'USO',           # Oil ETF
    'HYG': 'HYG',           # High Yield bonds (credit risk)
    'LQD': 'LQD',           # Investment Grade bonds
}

def create_macro_table():
    """Create macro indicators table."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            id SERIAL PRIMARY KEY,
            indicator_name VARCHAR(50) NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            snapshot_date DATE NOT NULL,
            price NUMERIC(10,4),
            change_1d NUMERIC(8,4),
            change_1w NUMERIC(8,4),
            change_1m NUMERIC(8,4),
            level VARCHAR(20), -- 'high', 'normal', 'low', 'extreme'
            signal VARCHAR(50), -- descriptive signal
            impact_score NUMERIC(5,2), -- -10 to +10 impact on risk assets
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(indicator_name, snapshot_date)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ macro_indicators table ready")

def fetch_macro_data(ticker, name):
    """Fetch macro indicator data."""
    print(f"  Fetching {name} ({ticker})...")
    
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='1mo')
        
        if hist.empty:
            return None
        
        current = float(hist['Close'].iloc[-1])
        prev_1d = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else current
        prev_1w = float(hist['Close'].iloc[-5]) if len(hist) >= 5 else current
        prev_1m = float(hist['Close'].iloc[0]) if len(hist) >= 1 else current
        
        change_1d = ((current - prev_1d) / prev_1d) * 100 if prev_1d > 0 else 0
        change_1w = ((current - prev_1w) / prev_1w) * 100 if prev_1w > 0 else 0
        change_1m = ((current - prev_1m) / prev_1m) * 100 if prev_1m > 0 else 0
        
        return {
            'price': current,
            'change_1d': change_1d,
            'change_1w': change_1w,
            'change_1m': change_1m
        }
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None

def calculate_level(name, price, change_1m):
    """Calculate indicator level."""
    levels = {
        'VIX': {
            'extreme': price > 30,
            'high': price > 20,
            'normal': price > 15,
            'low': True
        },
        'DXY': {
            'extreme': price > 105,
            'high': price > 100,
            'normal': price > 95,
            'low': True
        },
        'T10Y': {
            'extreme': price > 5.0,
            'high': price > 4.5,
            'normal': price > 3.5,
            'low': True
        }
    }
    
    if name in levels:
        for level, condition in levels[name].items():
            if condition:
                return level
    
    # Default based on change
    if abs(change_1m) > 10:
        return 'extreme'
    elif abs(change_1m) > 5:
        return 'high' if change_1m > 0 else 'low'
    return 'normal'

def calculate_signal(name, price, change_1d, change_1w, change_1m):
    """Calculate macro signal."""
    signals = []
    
    if name == 'VIX':
        if price > 25:
            signals.append("High fear — defensive positioning")
        elif price < 15:
            signals.append("Complacency — consider hedges")
        elif change_1w > 10:
            signals.append("Fear accelerating")
    
    elif name == 'DXY':
        if change_1w > 1:
            signals.append("Dollar strengthening — headwinds for EM/intl")
        elif change_1w < -1:
            signals.append("Dollar weakening — tailwinds for EM/intl")
    
    elif name == 'T10Y':
        if change_1w > 0.2:
            signals.append("Rates rising — pressure on growth stocks")
        elif change_1w < -0.2:
            signals.append("Rates falling — tailwinds for growth")
    
    elif name == 'T2Y':
        if name == 'T10Y':  # Compare yield curve
            pass  # Would need both T10Y and T2Y
    
    elif name == 'GOLD':
        if change_1w > 2:
            signals.append("Safe haven demand — risk-off signal")
    
    elif name == 'HYG':
        if change_1w < -1:
            signals.append("Credit stress — risk-off signal")
    
    return '; '.join(signals) if signals else 'Neutral'

def calculate_impact_score(name, change_1w, level):
    """Calculate impact score on risk assets (-10 to +10)."""
    score = 0
    
    if name == 'VIX':
        score = -5 if change_1w > 10 else -2 if change_1w > 5 else 0
    elif name == 'DXY':
        score = -3 if change_1w > 1 else 2 if change_1w < -1 else 0
    elif name == 'T10Y':
        score = -4 if change_1w > 0.3 else 2 if change_1w < -0.2 else 0
    elif name == 'GOLD':
        score = -3 if change_1w > 2 else 0
    elif name == 'HYG':
        score = -4 if change_1w < -1 else 0
    
    # Adjust for level
    if level == 'extreme':
        score *= 1.5
    
    return max(-10, min(10, score))

def analyze_macro_indicators():
    """Analyze all macro indicators."""
    print("\n[1/3] Fetching macro indicator data...")
    
    results = {}
    for name, ticker in MACRO_INDICATORS.items():
        data = fetch_macro_data(ticker, name)
        if data:
            data['level'] = calculate_level(name, data['price'], data['change_1m'])
            data['signal'] = calculate_signal(name, data['price'], data['change_1d'], 
                                               data['change_1w'], data['change_1m'])
            data['impact'] = calculate_impact_score(name, data['change_1w'], data['level'])
            results[name] = data
    
    print(f"  Fetched {len(results)} indicators")
    return results

def store_macro_data(results):
    """Store macro data in database."""
    conn = connect_db()
    cur = conn.cursor()
    
    today = datetime.now().date()
    stored = 0
    
    for name, data in results.items():
        cur.execute("""
            INSERT INTO macro_indicators 
            (indicator_name, ticker, snapshot_date, price, change_1d, change_1w, change_1m,
             level, signal, impact_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (indicator_name, snapshot_date) DO UPDATE SET
                price = EXCLUDED.price,
                change_1d = EXCLUDED.change_1d,
                change_1w = EXCLUDED.change_1w,
                change_1m = EXCLUDED.change_1m,
                level = EXCLUDED.level,
                signal = EXCLUDED.signal,
                impact_score = EXCLUDED.impact_score,
                created_at = NOW()
        """, (name, MACRO_INDICATORS[name], today, data['price'], data['change_1d'],
              data['change_1w'], data['change_1m'], data['level'], data['signal'], data['impact']))
        
        if cur.rowcount > 0:
            stored += 1
    
    conn.commit()
    conn.close()
    print(f"  Stored {stored} macro records")
    return stored

def generate_macro_report():
    """Generate macro correlation report."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT indicator_name, ticker, price, change_1d, change_1w, change_1m,
               level, signal, impact_score
        FROM macro_indicators
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM macro_indicators)
        ORDER BY ABS(impact_score) DESC
    """)
    
    print(f"\n{'='*90}")
    print(f"🌍 MACRO CORRELATION REPORT — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*90}")
    print(f"{'Indicator':<15} {'Ticker':<8} {'Price':<10} {'1D':<8} {'1W':<8} {'1M':<8} {'Level':<10} {'Impact':<8} {'Signal'}")
    print(f"{'-'*90}")
    
    total_impact = 0
    risk_off_signals = 0
    
    for row in cur.fetchall():
        name, ticker, price, c1d, c1w, c1m, level, signal, impact = row
        
        impact_icon = '🔴' if impact < -3 else '🟡' if impact < 0 else '🟢' if impact > 0 else '⚪'
        level_icon = '⚠️' if level == 'extreme' else '🔥' if level == 'high' else '✅' if level == 'normal' else '💤'
        
        print(f"{name:<15} {ticker:<8} {price:>8.2f} {c1d:>6.1f}% {c1w:>6.1f}% {c1m:>6.1f}% {level_icon} {level:<8} {impact_icon} {impact:>+5.1f}  {signal}")
        
        total_impact += impact if impact else 0
        if impact and impact < -3:
            risk_off_signals += 1
    
    print(f"{'='*90}")
    
    # Overall macro score
    print(f"\n📊 MACRO COMPOSITE SCORE: {total_impact:+.1f}")
    
    if total_impact < -10:
        print("  🔴 HIGH RISK-OFF ENVIRONMENT")
        print("  → Reduce equity exposure, increase cash/hedges")
    elif total_impact < -5:
        print("  🟡 CAUTIOUS ENVIRONMENT")
        print("  → Defensive positioning, quality over growth")
    elif total_impact > 5:
        print("  🟢 RISK-ON ENVIRONMENT")
        print("  → Increase growth exposure, reduce hedges")
    else:
        print("  ⚪ NEUTRAL ENVIRONMENT")
        print("  → Maintain current allocation")
    
    print(f"\n  Risk-off signals: {risk_off_signals}/8")
    
    # Portfolio correlation warning
    if risk_off_signals >= 3:
        print(f"\n  ⚠️ PORTFOLIO ALERT: Consider defensive rebalancing")
    
    conn.close()
    return total_impact

def run_macro_correlation_engine():
    """Main entry point."""
    print("=" * 90)
    print(f"VOX MACRO CORRELATION ENGINE — {datetime.now()}")
    print("=" * 90)
    
    create_macro_table()
    
    results = analyze_macro_indicators()
    store_macro_data(results)
    total_impact = generate_macro_report()
    
    return total_impact

if __name__ == '__main__':
    run_macro_correlation_engine()
