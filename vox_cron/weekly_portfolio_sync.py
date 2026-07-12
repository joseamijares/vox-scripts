#!/usr/bin/env python3
"""
Daily Portfolio Sync & Grade Update Script
Runs every day at 7 AM CT to:
1. Sync Binance positions via API
2. Sync eToro positions via API
3. Sync Bitso positions via API
4. Update grades for all positions
5. Generate portfolio report
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
import requests
import hmac
import hashlib
import time
import uuid
from datetime import datetime
from decimal import Decimal

def get_db_connection():
    """Get database connection"""
    import os
    pwd = os.environ.get('PGPASSWORD', '')
    if not pwd or len(pwd) < 10:
        # Fallback: read from .env file
        env_path = os.path.expanduser('~/.hermes/.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith('PGPASSWORD=') or line.startswith('DB_PASSWORD='):
                        pwd = line.strip().split('=', 1)[1]
                        break
    return psycopg2.connect(
        host='acela.proxy.rlwy.net',
        port=35577,
        database='railway',
        user='postgres',
        password=pwd
    )

def sync_binance():
    """Sync Binance positions.

    Rules:
    - Aggregate LD* earn tokens into base asset (prevents BTC + LDBTC double-count)
    - Price via USDT tickers
    - Zero out Binance rows not present in this pull (stale cleanup)
    """
    print("📊 Syncing Binance...")

    api_key = os.environ.get('BINANCE_API_KEY')
    api_secret = os.environ.get('BINANCE_API_SECRET')
    if not api_key or not api_secret:
        # Fall back to .env load
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("BINANCE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["BINANCE_API_KEY"] = api_key
                elif line.startswith("BINANCE_API_SECRET="):
                    api_secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["BINANCE_API_SECRET"] = api_secret

    if not api_key or not api_secret or api_key.startswith("***"):
        print("❌ Missing Binance credentials")
        return 0

    base_url = "https://api.binance.com"
    headers = {"X-MBX-APIKEY": api_key}

    # Align local clock to Binance server time (avoids -1021 recvWindow errors)
    try:
        server_time = int(requests.get(f"{base_url}/api/v3/time", timeout=10).json()["serverTime"])
        local_time = int(time.time() * 1000)
        time_offset = server_time - local_time
    except Exception:
        time_offset = 0

    timestamp = int(time.time() * 1000) + time_offset
    query_string = f"timestamp={timestamp}&recvWindow=60000"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    response = requests.get(
        f"{base_url}/api/v3/account?{query_string}&signature={signature}",
        headers=headers,
        timeout=30,
    )
    if response.status_code != 200:
        print(f"❌ Binance API error: {response.status_code} {response.text[:200]}")
        return 0

    # Price map once
    prices = {}
    try:
        for t in requests.get(f"{base_url}/api/v3/ticker/price", timeout=30).json():
            sym = t.get("symbol", "")
            if sym.endswith("USDT"):
                prices[sym[:-4]] = Decimal(str(t.get("price", 0)))
    except Exception as e:
        print(f"⚠️ price map error: {e}")

    stable = {
        "USDT", "FDUSD", "BUSD", "USDC", "TUSD", "DAI", "USD1", "USDS",
        "USDE", "EURI", "AEUR", "RLUSD", "XUSD", "BFUSD",
    }

    # Aggregate by base asset: LD* -> base
    aggregated = {}
    for balance in response.json().get("balances", []):
        asset = balance.get("asset", "")
        total = Decimal(str(balance.get("free", "0"))) + Decimal(str(balance.get("locked", "0")))
        if total <= 0:
            continue
        base = asset[2:] if asset.startswith("LD") else asset
        if base.startswith("LD"):  # nested safety
            base = base[2:]
        if base not in aggregated:
            aggregated[base] = {"qty": Decimal("0"), "sources": []}
        aggregated[base]["qty"] += total
        aggregated[base]["sources"].append(asset)

    conn = get_db_connection()
    cur = conn.cursor()
    now = datetime.now()
    live_tickers = set()
    imported = 0
    total_usd = Decimal("0")

    for base, data in aggregated.items():
        qty = data["qty"]
        if base in stable:
            price = Decimal("1")
        elif base in ("BETH", "WBETH"):
            price = prices.get("ETH", Decimal("0"))
        elif base == "WBTC":
            price = prices.get("BTC", Decimal("0"))
        elif base.startswith("1000") and base[4:] in prices:
            price = prices[base[4:]] / Decimal("1000")
        else:
            price = prices.get(base, Decimal("0"))

        value = qty * price
        if value < Decimal("0.5"):
            continue

        live_tickers.add(base)
        cur.execute("SELECT grade, council, sector FROM positions WHERE ticker = %s", (base,))
        result = cur.fetchone()
        grade, council, sector = result if result else (None, None, None)

        cur.execute(
            """
            INSERT INTO broker_positions
            (broker, ticker, shares, live_price, live_value, currency, live_value_usd,
             grade, council, sector, source, last_sync_at, price_source, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (broker, ticker)
            DO UPDATE SET
                shares = EXCLUDED.shares,
                live_price = EXCLUDED.live_price,
                live_value = EXCLUDED.live_value,
                live_value_usd = EXCLUDED.live_value_usd,
                grade = COALESCE(EXCLUDED.grade, broker_positions.grade),
                council = COALESCE(EXCLUDED.council, broker_positions.council),
                sector = COALESCE(EXCLUDED.sector, broker_positions.sector),
                source = EXCLUDED.source,
                last_sync_at = EXCLUDED.last_sync_at,
                price_source = EXCLUDED.price_source,
                updated_at = NOW()
            """,
            (
                "Binance", base, float(qty), float(price), float(value), "USD",
                float(value), grade, council, sector, "api", now, "binance_usdt",
            ),
        )
        imported += 1
        total_usd += value
        print(f"  ✅ {base}: {float(qty):.8f} @ ${float(price):,.4f} = ${float(value):,.2f} src={data['sources']}")

    # Zero stale Binance rows (incl old LD* tickers)
    if live_tickers:
        cur.execute(
            """
            UPDATE broker_positions
            SET shares = 0, live_value = 0, live_value_usd = 0, updated_at = NOW(),
                source = 'api_stale_zero'
            WHERE broker = 'Binance'
              AND ticker <> ALL(%s)
              AND COALESCE(shares, 0) > 0
            """,
            (list(live_tickers),),
        )
        zeroed = cur.rowcount
        if zeroed:
            print(f"  🧹 Zeroed {zeroed} stale Binance rows")

    # Touch broker_accounts
    try:
        cur.execute(
            """
            UPDATE broker_accounts
            SET last_sync_at = NOW(), updated_at = NOW()
            WHERE broker = 'Binance'
            """
        )
    except Exception:
        pass

    conn.commit()
    conn.close()
    print(f"✅ Synced {imported} Binance base assets | total ${float(total_usd):,.2f}")
    return imported

def sync_etoro():
    """Sync eToro positions"""
    print("📊 Syncing eToro...")
    
    api_key = os.environ.get('ETORO_API_KEY')
    user_key = os.environ.get('ETORO_USER_KEY')
    
    if not api_key or not user_key:
        print("⚠️  Missing eToro credentials, skipping")
        return 0
    
    headers = {
        'x-api-key': api_key,
        'x-user-key': user_key,
        'x-request-id': str(uuid.uuid4()),
        'Content-Type': 'application/json'
    }
    
    base_url = 'https://public-api.etoro.com/api/v1'
    
    try:
        # Get portfolio data with timeout
        response = requests.get(f'{base_url}/trading/info/portfolio', headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"⚠️  eToro API error: {response.status_code}, skipping")
            return 0
        
        portfolio = response.json()
        positions = portfolio.get('clientPortfolio', {}).get('positions', [])
        
        # Get instrument metadata with timeout
        resp_instruments = requests.get(f'{base_url}/market-data/instruments', headers=headers, timeout=15)
        instruments = {}
        
        if resp_instruments.status_code == 200:
            inst_data = resp_instruments.json()
            for inst in inst_data.get('instrumentDisplayDatas', []):
                instruments[inst.get('instrumentID')] = inst
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Aggregate by ticker since eToro returns one row per trade
        aggregated = {}
        for pos in positions:
            instrument_id = pos.get('instrumentID')
            instrument = instruments.get(instrument_id, {})
            ticker = instrument.get('symbolFull', instrument_id)
            
            # Skip positions without a valid ticker
            if not ticker or ticker == instrument_id:
                print(f"  ⚠️ Skipping position with instrumentID {instrument_id}: no symbol mapping")
                continue
            
            quantity = Decimal(str(pos.get('units', 0)))
            amount = Decimal(str(pos.get('amount', 0)))  # amount is in dollars
            open_rate = Decimal(str(pos.get('openRate', 0)))
            
            if ticker in aggregated:
                aggregated[ticker]['units'] += quantity
                aggregated[ticker]['amount'] += amount
                aggregated[ticker]['cost_basis'] += quantity * open_rate
            else:
                aggregated[ticker] = {
                    'units': quantity,
                    'amount': amount,
                    'cost_basis': quantity * open_rate,
                    'instrument_id': instrument_id
                }
        
        updated = 0
        for ticker, agg in aggregated.items():
            quantity = agg['units']
            value = agg['amount']
            cost_basis = agg['cost_basis']
            avg_price = cost_basis / quantity if quantity != 0 else Decimal('0')
            live_price = avg_price  # will be updated by price updater
            
            # Get grade/council from main positions table
            cur.execute("SELECT grade, council, sector FROM positions WHERE ticker = %s", (ticker,))
            result = cur.fetchone()
            grade, council, sector = result if result else (None, None, None)
            
            # Update broker_positions
            cur.execute("""
                INSERT INTO broker_positions 
                (broker, ticker, shares, avg_cost, live_price, live_value, currency, live_value_usd, grade, council, sector, source, last_sync_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (broker, ticker) 
                DO UPDATE SET
                    shares = EXCLUDED.shares,
                    avg_cost = EXCLUDED.avg_cost,
                    live_price = EXCLUDED.live_price,
                    live_value = EXCLUDED.live_value,
                    live_value_usd = EXCLUDED.live_value_usd,
                    grade = EXCLUDED.grade,
                    council = EXCLUDED.council,
                    sector = EXCLUDED.sector,
                    source = EXCLUDED.source,
                    last_sync_at = EXCLUDED.last_sync_at,
                    updated_at = NOW()
            """, ('eToro', ticker, quantity, avg_price, live_price, value, 'USD', float(value), grade, council, sector, 'api', datetime.now()))
            updated += 1
        
        conn.commit()
        conn.close()
        print(f"✅ Synced {updated} unique eToro tickers ({len(positions)} raw positions)")
        return updated
        
    except requests.exceptions.Timeout:
        print("⚠️  eToro API timeout, skipping")
        return 0
    except Exception as e:
        print(f"⚠️  eToro sync error: {e}, skipping")
        return 0

def update_grades():
    """Update grades for all positions from positions table"""
    print("📊 Updating grades...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Update grades for all broker positions
    cur.execute("""
        UPDATE broker_positions bp
        SET grade = p.grade,
            council = p.council,
            sector = p.sector
        FROM positions p
        WHERE bp.ticker = p.ticker
        AND bp.grade IS NULL
    """)
    
    updated = cur.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ Updated {updated} positions with grades")
    return updated

def generate_weekly_report():
    """Generate weekly portfolio report"""
    print("📊 Generating weekly report...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get portfolio summary
    cur.execute("""
        SELECT 
            broker,
            COUNT(*) as positions,
            SUM(live_value_usd) as total_usd,
            AVG(grade) as avg_grade
        FROM broker_positions
        WHERE live_value_usd > 0
        GROUP BY broker
        ORDER BY total_usd DESC
    """)
    
    print("\n📊 WEEKLY PORTFOLIO REPORT")
    print("=" * 80)
    
    total_portfolio = 0
    for row in cur.fetchall():
        broker, count, total, avg_grade = row
        total_usd = float(total) if total else 0
        total_portfolio += total_usd
        grade_str = f"{avg_grade:.1f}" if avg_grade else "N/A"
        print(f"{broker:<15} {count:>3} positions  ${total_usd:>12,.2f}  Avg Grade: {grade_str}")
    
    print(f"{'TOTAL':<15} {'':>3}          ${total_portfolio:>12,.2f}")
    
    # Get council distribution
    cur.execute("""
        SELECT council, SUM(live_value_usd) as total
        FROM broker_positions
        WHERE live_value_usd > 0 AND council IS NOT NULL
        GROUP BY council
        ORDER BY total DESC
    """)
    
    print("\nCouncil Distribution:")
    for row in cur.fetchall():
        council, total = row
        total_usd = float(total) if total else 0
        pct = (total_usd / total_portfolio * 100) if total_portfolio > 0 else 0
        print(f"  {council}: ${total_usd:,.2f} ({pct:.1f}%)")
    
    conn.close()

def sync_bitso():
    """Sync Bitso positions"""
    print("📊 Syncing Bitso...")
    
    import subprocess
    result = subprocess.run(
        ["python3", "/Users/jos/.hermes/scripts/vox_cron/sync_bitso.py"],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    if result.returncode == 0:
        print("✅ Bitso sync completed")
        return 1
    else:
        print(f"❌ Bitso sync failed: {result.stderr[:200]}")
        return 0

def main():
    """Main function"""
    print("=" * 80)
    print("WEEKLY PORTFOLIO SYNC & REPORT")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Sync APIs
    binance_count = sync_binance()
    etoro_count = sync_etoro()
    bitso_count = sync_bitso()
    
    # Update grades
    grade_count = update_grades()
    
    # Generate report
    generate_weekly_report()
    
    print("\n" + "=" * 80)
    print("✅ WEEKLY SYNC COMPLETE")
    print("=" * 80)
    print(f"Binance: {binance_count} positions")
    print(f"eToro: {etoro_count} positions")
    print(f"Bitso: {bitso_count} positions")
    print(f"Grades updated: {grade_count} positions")

if __name__ == "__main__":
    main()
