#!/usr/bin/env python3
"""
VOX eToro API Sync — Full Portfolio Integration
Fetches live positions from eToro API and syncs to PostgreSQL database.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import requests
import uuid
import json
import psycopg2
from datetime import datetime

# eToro API credentials from environment
ETORO_API_KEY = os.environ.get('ETORO_API_KEY')
ETORO_USER_KEY = os.environ.get('ETORO_USER_KEY')

# Database credentials
DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'
DB_PASS = os.environ.get('PGPASSWORD', '')

def get_headers():
    """Generate API headers with fresh UUID."""
    return {
        'x-api-key': ETORO_API_KEY,
        'x-user-key': ETORO_USER_KEY,
        'x-request-id': str(uuid.uuid4()),
        'Content-Type': 'application/json'
    }

def fetch_portfolio():
    """Fetch portfolio from eToro API."""
    response = requests.get(
        'https://public-api.etoro.com/api/v1/trading/info/portfolio',
        headers=get_headers(),
        timeout=30
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching portfolio: {response.status_code} - {response.text[:200]}")
        return None

def fetch_instrument_details(instrument_ids):
    """Fetch instrument details by IDs to get symbols."""
    # Try to discover instruments
    symbols = {}
    
    # First try the discover endpoint with instrument IDs
    for inst_id in instrument_ids:
        try:
            response = requests.get(
                f'https://public-api.etoro.com/api/v1/instruments/{inst_id}',
                headers=get_headers(),
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                symbol = data.get('symbol')
                if symbol:
                    symbols[inst_id] = symbol
            else:
                # Try alternative endpoint
                response = requests.get(
                    'https://public-api.etoro.com/api/v1/instruments/discover',
                    headers=get_headers(),
                    params={'instrumentId': inst_id, 'fields': 'instrumentId,symbol,displayName'},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    for item in items:
                        if item.get('instrumentId') == inst_id:
                            symbols[inst_id] = item.get('symbol')
        except Exception as e:
            print(f"Error fetching instrument {inst_id}: {e}")
    
    return symbols

def sync_to_database(positions, symbols_map):
    """Sync eToro positions to PostgreSQL database."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor()
    
    print("=" * 100)
    print("SYNCING ETORO POSITIONS TO DATABASE")
    print("=" * 100)
    
    added = 0
    updated = 0
    
    for pos in positions:
        instrument_id = pos.get('instrumentID')
        symbol = symbols_map.get(instrument_id, f"ID_{instrument_id}")
        
        # Map eToro fields to our schema
        shares = pos.get('units', 0)
        avg_cost = pos.get('openRate', 0)
        live_price = pos.get('closeRate', 0)  # Will need to fetch current price
        is_buy = pos.get('isBuy', True)
        
        # Calculate live value (approximate)
        live_value = shares * live_price if live_price else 0
        
        # Check if position exists
        cur.execute("""
            SELECT id, brokers FROM positions 
            WHERE ticker = %s
        """, (symbol,))
        
        row = cur.fetchone()
        
        if row:
            # Update existing position
            pos_id, brokers = row
            if 'eToro' not in brokers:
                brokers.append('eToro')
            
            cur.execute("""
                UPDATE positions 
                SET shares = %s, avg_cost = %s, live_price = %s, live_value = %s,
                    brokers = %s, updated_at = NOW()
                WHERE id = %s
            """, (shares, avg_cost, live_price, live_value, brokers, pos_id))
            updated += 1
        else:
            # Insert new position
            cur.execute("""
                INSERT INTO positions (ticker, shares, avg_cost, live_price, live_value, brokers, currency, updated_at)
                VALUES (%s, %s, %s, %s, %s, ARRAY['eToro'], 'USD', NOW())
            """, (symbol, shares, avg_cost, live_price, live_value))
            added += 1
    
    conn.commit()
    
    print(f"\n{'='*100}")
    print(f"SYNC COMPLETE: {added} added, {updated} updated")
    print(f"{'='*100}")
    
    conn.close()
    return added, updated

def main():
    print("=" * 100)
    print("VOX ETORO API SYNC")
    print("=" * 100)
    
    if not ETORO_API_KEY or not ETORO_USER_KEY:
        print("ERROR: ETORO_API_KEY and ETORO_USER_KEY must be set in environment")
        return
    
    # Fetch portfolio
    portfolio = fetch_portfolio()
    if not portfolio:
        return
    
    positions = portfolio.get('clientPortfolio', {}).get('positions', [])
    print(f"\nFetched {len(positions)} positions from eToro")
    
    # Get unique instrument IDs
    instrument_ids = set()
    for pos in positions:
        instrument_ids.add(pos.get('instrumentID'))
    
    print(f"Unique instrument IDs: {len(instrument_ids)}")
    
    # Fetch instrument symbols
    print("\nFetching instrument symbols...")
    symbols_map = fetch_instrument_details(instrument_ids)
    print(f"Resolved {len(symbols_map)} symbols")
    
    # Show sample mappings
    print("\nSample symbol mappings:")
    for inst_id, symbol in list(symbols_map.items())[:10]:
        print(f"  {inst_id} -> {symbol}")
    
    # Sync to database
    added, updated = sync_to_database(positions, symbols_map)
    
    # Save raw data for reference
    with open('/tmp/etoro_sync.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'positions_count': len(positions),
            'symbols_resolved': len(symbols_map),
            'added': added,
            'updated': updated
        }, f, indent=2)

if __name__ == "__main__":
    main()
