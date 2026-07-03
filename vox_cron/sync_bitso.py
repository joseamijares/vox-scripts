import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, psycopg2, requests, hmac, hashlib, json
from datetime import datetime
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from hermes_secrets import get_env

pwd = get_env('PGPASSWORD', get_env('DB_PASSWORD', ''))
conn = psycopg2.connect(
    host=get_env('DB_HOST', 'acela.proxy.rlwy.net'),
    port=get_env('DB_PORT', '35577'),
    user=get_env('DB_USER', 'postgres'),
    password=pwd,
    dbname=get_env('DB_NAME', 'railway'),
    sslmode='require',
)
cur = conn.cursor()

print("🔄 Syncing Bitso positions...")

# Bitso API credentials
api_key = os.environ.get('BITSO_API_KEY')
api_secret = os.environ.get('BITSO_API_SECRET')

if not api_key or not api_secret:
    print("❌ Missing Bitso credentials")
    conn.close()
    exit(1)

# Bitso API authentication
base_url = "https://api.bitso.com"
nonce = str(int(datetime.now().timestamp() * 1000))
http_method = "GET"
request_path = "/api/v3/balance/"
json_payload = ""

message = nonce + http_method + request_path + json_payload
signature = hmac.new(
    api_secret.encode('utf-8'),
    message.encode('utf-8'),
    hashlib.sha256
).hexdigest()

headers = {
    "Authorization": f"Bitso {api_key}:{nonce}:{signature}",
    "Content-Type": "application/json"
}

resp = requests.get(f"{base_url}{request_path}", headers=headers, timeout=30)

if resp.status_code != 200:
    print(f"❌ Bitso API error: {resp.status_code}")
    print(f"Error: {resp.text[:500]}")
    conn.close()
    exit(1)

data = resp.json()

if not data.get('success'):
    print(f"❌ Bitso API returned error: {data}")
    conn.close()
    exit(1)

balances = data.get('payload', {}).get('balances', [])

# Get BTC price for USD conversion
btc_resp = requests.get("https://api.bitso.com/api/v3/ticker/?book=btc_usd", timeout=10)
btc_price = 0
if btc_resp.status_code == 200:
    btc_data = btc_resp.json()
    if btc_data.get('success'):
        btc_price = float(btc_data.get('payload', {}).get('last', 0))

print(f"BTC price: ${btc_price:,.2f}")

imported = 0
total_usd = 0

for balance in balances:
    currency = balance.get('currency', '').upper()
    total = Decimal(balance.get('total', '0'))
    available = Decimal(balance.get('available', '0'))
    locked = Decimal(balance.get('locked', '0'))
    
    # Skip zero balances and MXN (fiat)
    if total <= 0 or currency == 'MXN':
        continue
    
    # Get USD price for this crypto
    price_usd = 0
    value_usd = 0
    
    if currency == 'BTC':
        price_usd = btc_price
        value_usd = float(total) * price_usd
    elif currency == 'USD':
        price_usd = 1
        value_usd = float(total)
    else:
        # Try to get price from Bitso book
        book = f"{currency.lower()}_usd"
        try:
            price_resp = requests.get(f"https://api.bitso.com/api/v3/ticker/?book={book}", timeout=10)
            if price_resp.status_code == 200:
                price_data = price_resp.json()
                if price_data.get('success'):
                    price_usd = float(price_data.get('payload', {}).get('last', 0))
                    value_usd = float(total) * price_usd
        except:
            pass
        
        # If no USD book, try BTC book
        if price_usd == 0:
            book = f"{currency.lower()}_btc"
            try:
                price_resp = requests.get(f"https://api.bitso.com/api/v3/ticker/?book={book}", timeout=10)
                if price_resp.status_code == 200:
                    price_data = price_resp.json()
                    if price_data.get('success'):
                        price_btc = float(price_data.get('payload', {}).get('last', 0))
                        price_usd = price_btc * btc_price
                        value_usd = float(total) * price_usd
            except:
                pass
    
    # Skip tiny balances (< $0.50)
    if value_usd < 0.5:
        continue
    
    # Get grade and council
    cur.execute("SELECT grade, council, sector FROM positions WHERE ticker = %s", (currency,))
    result = cur.fetchone()
    grade, council, sector = result if result else (None, None, None)
    
    cur.execute("""
        INSERT INTO broker_positions 
        (broker, ticker, shares, live_price, live_value, currency, live_value_usd, grade, council, sector, source, last_sync_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (broker, ticker) 
        DO UPDATE SET
            shares = EXCLUDED.shares,
            live_price = EXCLUDED.live_price,
            live_value = EXCLUDED.live_value,
            live_value_usd = EXCLUDED.live_value_usd,
            grade = EXCLUDED.grade,
            council = EXCLUDED.council,
            sector = EXCLUDED.sector,
            source = EXCLUDED.source,
            last_sync_at = EXCLUDED.last_sync_at,
            updated_at = NOW()
    """, ('Bitso', currency, float(total), price_usd, value_usd, 'USD', 
          value_usd, grade, council, sector, 'api', datetime.now()))
    
    imported += 1
    total_usd += value_usd
    print(f"✅ {currency}: {float(total):.8f} shares @ ${price_usd:,.2f} = ${value_usd:,.2f} USD")

conn.commit()

print(f"\n{'='*80}")
print(f"Bitso Sync Complete")
print(f"{'='*80}")
print(f"Positions: {imported}")
print(f"Total USD: ${total_usd:,.2f}")

conn.close()
