#!/usr/bin/env python3
"""
VOX SECTOR MAPPING SYSTEM v2
Fast batch sector mapping using cached Yahoo Finance data + manual overrides.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

THEMATIC_OVERRIDES = {
    'IONQ': 'Quantum Computing', 'RGTI': 'Quantum Computing', 'QBTS': 'Quantum Computing',
    'QUBT': 'Quantum Computing', 'ARQQ': 'Quantum Computing',
    'OKLO': 'Nuclear Energy', 'SMR': 'Nuclear Energy', 'NNE': 'Nuclear Energy',
    'BWXT': 'Nuclear Energy', 'CCJ': 'Nuclear Energy', 'LEU': 'Nuclear Energy',
    'SPCE': 'Space', 'RKLB': 'Space', 'ASTS': 'Space', 'SPIR': 'Space',
    'SATS': 'Space', 'SPCX': 'Space',
    'NVDA': 'AI Infrastructure', 'TSLA': 'AI Infrastructure', 'PLTR': 'AI Infrastructure',
    'AI': 'AI Infrastructure', 'SOUN': 'AI Infrastructure', 'BBAI': 'AI Infrastructure',
    'MARA': 'Bitcoin Mining / Data Centers', 'RIOT': 'Bitcoin Mining / Data Centers',
    'CLSK': 'Bitcoin Mining / Data Centers', 'CORZ': 'Bitcoin Mining / Data Centers',
    'WULF': 'Bitcoin Mining / Data Centers', 'BTBT': 'Bitcoin Mining / Data Centers',
    'IREN': 'Bitcoin Mining / Data Centers', 'HUT': 'Bitcoin Mining / Data Centers',
    'BTC': 'Crypto', 'ETH': 'Crypto', 'DOGE': 'Crypto', 'HBAR': 'Crypto',
    'SOL': 'Crypto', 'ADA': 'Crypto', 'XRP': 'Crypto', 'DOT': 'Crypto',
    'LINK': 'Crypto', 'UNI': 'Crypto', 'AAVE': 'Crypto', 'LTC': 'Crypto',
    'BCH': 'Crypto', 'ETC': 'Crypto', 'XLM': 'Crypto', 'XTZ': 'Crypto',
    'ALGO': 'Crypto', 'VET': 'Crypto', 'FIL': 'Crypto', 'TRX': 'Crypto',
    'CRWD': 'Cybersecurity', 'PANW': 'Cybersecurity', 'FTNT': 'Cybersecurity',
    'ZS': 'Cybersecurity', 'S': 'Cybersecurity', 'OKTA': 'Cybersecurity', 'CYBR': 'Cybersecurity',
    'CRSP': 'Biotechnology', 'EDIT': 'Biotechnology', 'NTLA': 'Biotechnology',
    'BEAM': 'Biotechnology', 'VERV': 'Biotechnology', 'BLUE': 'Biotechnology',
    'SRPT': 'Biotechnology', 'VRTX': 'Biotechnology',
    'ISRG': 'Robotics / Automation', 'TER': 'Robotics / Automation',
    'AMBA': 'Robotics / Automation', 'CGNX': 'Robotics / Automation', 'OLED': 'Robotics / Automation',
    'SE': 'EM Fintech', 'MELI': 'EM Fintech', 'NU': 'EM Fintech',
    'STNE': 'EM Fintech', 'PAGS': 'EM Fintech', 'DLO': 'EM Fintech',
    'PLUG': 'Hydrogen', 'BE': 'Hydrogen', 'FCEL': 'Hydrogen',
    'BLDP': 'Hydrogen', 'CMI': 'Hydrogen',
    'QS': 'EV / Battery', 'SLDP': 'EV / Battery', 'ENVX': 'EV / Battery',
    'MP': 'Materials', 'CPSH': 'Materials', 'LAZR': 'Materials',
}

GICS_MAP = {
    'Technology': 'Technology', 'Healthcare': 'Healthcare',
    'Financial Services': 'Financial Services', 'Consumer Cyclical': 'Consumer Cyclical',
    'Consumer Defensive': 'Consumer Defensive', 'Industrials': 'Industrials',
    'Communication Services': 'Communication Services', 'Energy': 'Energy',
    'Basic Materials': 'Basic Materials', 'Real Estate': 'Real Estate',
    'Utilities': 'Utilities',
}


def connect():
    with open('/Users/jos/.hermes/.env', 'r') as f:
        env = f.read()
    for line in env.split('\n'):
        if line.startswith('DB_PASSWORD'):
            pwd = line.split('=', 1)[1].strip()
            break
    return psycopg2.connect(host='acela.proxy.rlwy.net', port=35577, dbname='railway', user='postgres', password=pwd)


def fetch_sector(ticker):
    """Fetch sector for a single ticker"""
    if ticker in THEMATIC_OVERRIDES:
        return ticker, THEMATIC_OVERRIDES[ticker], 'manual', 'high'
    try:
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'Unknown')
        return ticker, GICS_MAP.get(sector, sector), 'yahoo', 'high'
    except Exception:
        return ticker, 'Unknown', 'fallback', 'low'


def main():
    print("=" * 60)
    print("VOX SECTOR MAPPING SYSTEM v2")
    print("=" * 60)
    
    conn = connect()
    cur = conn.cursor()
    
    # Ensure table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticker_sectors (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) UNIQUE NOT NULL,
            sector VARCHAR(100),
            sub_sector VARCHAR(100),
            source VARCHAR(50),
            confidence VARCHAR(20),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    
    # Get all unique tickers
    cur.execute("""
        SELECT DISTINCT ticker FROM vox_grades WHERE generated_at > NOW() - INTERVAL '7 days'
        UNION
        SELECT DISTINCT ticker FROM positions
    """)
    tickers = [r[0] for r in cur.fetchall()]
    print(f"Mapping {len(tickers)} tickers...")
    
    # Batch fetch with thread pool
    mapped = 0
    manual_count = 0
    yahoo_count = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_sector, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, sector, source, confidence = future.result()
            
            cur.execute("""
                INSERT INTO ticker_sectors (ticker, sector, source, confidence, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    sector = EXCLUDED.sector,
                    source = EXCLUDED.source,
                    confidence = EXCLUDED.confidence,
                    updated_at = NOW()
            """, (ticker, sector, source, confidence))
            
            mapped += 1
            if source == 'manual':
                manual_count += 1
            elif source == 'yahoo':
                yahoo_count += 1
            
            if mapped % 50 == 0:
                print(f"  {mapped}/{len(tickers)}...")
                conn.commit()
    
    conn.commit()
    
    # Add sector column to vox_grades if missing
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'vox_grades' AND column_name = 'sector'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE vox_grades ADD COLUMN sector VARCHAR(100)")
        conn.commit()
        print("Added sector column to vox_grades")
    
    # Update vox_grades sectors
    cur.execute("""
        UPDATE vox_grades v SET sector = ts.sector
        FROM ticker_sectors ts WHERE v.ticker = ts.ticker AND v.sector IS DISTINCT FROM ts.sector
    """)
    vg_updated = cur.rowcount
    conn.commit()
    
    # Update positions sectors
    cur.execute("""
        UPDATE positions p SET sector = ts.sector
        FROM ticker_sectors ts WHERE p.ticker = ts.ticker
          AND (p.sector IS NULL OR p.sector = 'Unknown' OR p.sector = '')
    """)
    pos_updated = cur.rowcount
    conn.commit()
    
    print(f"\nResults:")
    print(f"  Yahoo Finance: {yahoo_count}")
    print(f"  Manual override: {manual_count}")
    print(f"  Total: {mapped}")
    print(f"  vox_grades updated: {vg_updated}")
    print(f"  positions updated: {pos_updated}")
    
    print("\nSector Distribution:")
    cur.execute("SELECT sector, COUNT(*) FROM ticker_sectors GROUP BY sector ORDER BY COUNT(*) DESC")
    for r in cur.fetchall():
        print(f"  {r[0] or 'Unknown'}: {r[1]}")
    
    cur.close()
    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
