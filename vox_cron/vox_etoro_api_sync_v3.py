#!/usr/bin/env python3
"""
VOX eToro API Sync v3 — Complete Rewrite
Syncs ALL positions with units > 0 from eToro API (including settled).
Uses urllib instead of requests to avoid header issues.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import urllib.request
import urllib.error
import uuid
import json
import psycopg2
from datetime import datetime
import time
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# Load credentials from ~/.hermes/.env (more reliable than os.environ)
def load_env():
    """Load API keys from ~/.hermes/.env"""
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    keys[key] = val
    return keys

env = load_env()
ETORO_API_KEY = env.get('ETORO_API_KEY')
ETORO_USER_KEY = env.get('ETORO_USER_KEY')

# Database credentials
DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'
DB_PASS = os.environ.get('PGPASSWORD', '')

# =============================================================================
# API FUNCTIONS
# =============================================================================

def etoro_request(endpoint: str) -> dict:
    """Make authenticated request to eToro public API using urllib."""
    url = f"https://public-api.etoro.com/api/v1{endpoint}"
    request_id = str(uuid.uuid4())

    req = urllib.request.Request(url)
    req.add_header("x-api-key", ETORO_API_KEY)
    req.add_header("x-user-key", ETORO_USER_KEY)
    req.add_header("x-request-id", request_id)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
    req.add_header("Origin", "https://etoro.com")
    req.add_header("Referer", "https://etoro.com/")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        try:
            body = json.loads(e.read().decode("utf-8"))
            print(json.dumps(body, indent=2))
        except:
            pass
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def fetch_portfolio():
    """Fetch portfolio from eToro API."""
    return etoro_request("/trading/info/real/pnl")

def fetch_instruments(instrument_ids: list) -> dict:
    """Fetch instrument metadata to map IDs to symbols."""
    if not instrument_ids:
        return {}
    ids_str = ",".join(map(str, instrument_ids))
    data = etoro_request(f"/market-data/instruments?instrumentIds={ids_str}")
    if not data:
        return {}
    mapping = {}
    for inst in data.get("instrumentDisplayDatas", []):
        iid = inst.get("instrumentID")
        mapping[iid] = inst.get("symbolFull", "?")
    return mapping

# =============================================================================
# SYNC LOGIC
# =============================================================================

def sync_all_positions():
    """Sync ALL eToro positions with units > 0 to database."""
    
    if not ETORO_API_KEY or not ETORO_USER_KEY:
        print("ERROR: ETORO_API_KEY and ETORO_USER_KEY must be set in ~/.hermes/.env")
        return
    
    print("=" * 100)
    print("VOX ETORO API SYNC v3 — ALL POSITIONS WITH UNITS > 0")
    print("=" * 100)
    
    # Fetch portfolio
    portfolio = fetch_portfolio()
    if not portfolio:
        return
    
    all_positions = portfolio.get('clientPortfolio', {}).get('positions', [])
    print(f"\n📊 Total positions from API: {len(all_positions)}")
    
    # Include ALL positions with units > 0, regardless of isSettled flag
    # CRITICAL: isSettled does NOT mean zero value — settled positions still hold shares
    active_count = len([p for p in all_positions if not p.get('isSettled', False)])
    positions_to_sync = [p for p in all_positions if p.get('units', 0) > 0]
    settled_with_units = [p for p in all_positions if p.get('isSettled', False) and p.get('units', 0) > 0]
    
    print(f"   Active (non-settled): {active_count}")
    print(f"   Settled WITH units > 0: {len(settled_with_units)}")
    print(f"   ✅ Total to sync: {len(positions_to_sync)}")
    
    if len(positions_to_sync) == 0:
        print("No positions with units > 0 found!")
        return
    
    # Build instrument symbol cache
    print(f"\n🔍 Fetching instrument symbols...")
    instrument_ids = sorted(set(p.get('instrumentID') for p in positions_to_sync if p.get('instrumentID')))
    symbol_map = fetch_instruments(instrument_ids)
    print(f"   Resolved {len(symbol_map)} symbols")
    
    # Connect to database
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor()
    
    print("\n" + "=" * 100)
    print("SYNCING POSITIONS")
    print("=" * 100)
    
    added = 0
    updated = 0
    failed = 0
    skipped = 0
    total_value = 0
    
    for pos in positions_to_sync:
        try:
            instrument_id = pos.get('instrumentID')
            position_id = pos.get('positionID')
            
            # Get symbol from mapping
            symbol = symbol_map.get(instrument_id)
            if not symbol or symbol == "?":
                print(f"  ⚠️  Could not resolve symbol for instrument {instrument_id}")
                failed += 1
                continue
            
            # Get position data
            shares = pos.get('units', 0)
            avg_cost = pos.get('openRate', 0)
            
            # Get current price from P&L data (already in portfolio response)
            pnl_data = pos.get('unrealizedPnL', {})
            close_rate = pnl_data.get('closeRate', 0)
            live_price = close_rate if close_rate else avg_cost
            
            # Calculate live value
            live_value = shares * live_price if shares and live_price else 0
            total_value += live_value
            
            # Check if position exists in database
            cur.execute("""
                SELECT id, brokers, shares FROM positions 
                WHERE ticker = %s
            """, (symbol,))
            
            row = cur.fetchone()
            
            if row:
                # Update existing position
                pos_id, brokers, old_shares = row
                if 'eToro' not in brokers:
                    brokers.append('eToro')
                
                # If eToro-only position, update shares. If multi-broker, add to existing
                if len(brokers) == 1 and brokers[0] == 'eToro':
                    cur.execute("""
                        UPDATE positions 
                        SET shares = %s, avg_cost = %s, live_price = %s, live_value = %s,
                            brokers = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (shares, avg_cost, live_price, live_value, brokers, pos_id))
                else:
                    # Multi-broker: just update price
                    cur.execute("""
                        UPDATE positions 
                        SET live_price = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (live_price, pos_id))
                updated += 1
            else:
                # Insert new position
                cur.execute("""
                    INSERT INTO positions (ticker, shares, avg_cost, live_price, live_value, brokers, currency, updated_at)
                    VALUES (%s, %s, %s, %s, %s, ARRAY['eToro'], 'USD', NOW())
                """, (symbol, shares, avg_cost, live_price, live_value))
                added += 1
            
            time.sleep(0.05)  # Rate limit
            
        except Exception as e:
            print(f"  ❌ Error processing position {position_id}: {e}")
            failed += 1
    
    conn.commit()
    
    print(f"\n{'='*100}")
    print(f"SYNC COMPLETE: {added} added, {updated} updated, {failed} failed")
    print(f"Total Portfolio Value (from API): ${total_value:,.2f}")
    print(f"{'='*100}")
    
    # Update sync timestamp
    cur.execute("""
        UPDATE broker_accounts 
        SET last_sync_at = NOW()
        WHERE broker = 'eToro'
    """)
    conn.commit()
    
    conn.close()
    
    # Save summary
    with open('/tmp/etoro_sync_summary.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_api_positions': len(all_positions),
            'active_positions': active_count,
            'settled_with_units': len(settled_with_units),
            'synced': len(positions_to_sync),
            'symbols_resolved': len(symbol_map),
            'added': added,
            'updated': updated,
            'failed': failed,
            'total_value': total_value
        }, f, indent=2)

if __name__ == "__main__":
    sync_all_positions()
