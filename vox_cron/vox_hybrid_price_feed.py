#!/usr/bin/env python3
"""
VOX HYBRID PRICE FEED v2.0
Primary: Alpaca Market Data API (free, reliable, US stocks/ETFs)
Fallback: Yahoo Finance via yfinance (global coverage, crypto, ADRs, MXN)
Updates positions and vox_grades with sanity checks and source tagging.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
import time
import requests
import urllib.parse
from decimal import Decimal
from datetime import datetime

# Try to import yfinance, install if missing
try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system("pip install yfinance --quiet")
    import yfinance as yf

def load_env_var(name, fallback=''):
    """Load from env or ~/.hermes/.env file (handles commented-out credential lines)."""
    val = os.environ.get(name, '')
    if val and len(val) > 3:
        return val
    env_path = os.path.expanduser('~/.hermes/.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or '=' not in line:
                    continue
                # Allow commented-out credential lines like: # ALPACA_API_KEY=...
                clean = line[1:].strip() if line.startswith('#') else line
                if clean.startswith('#') or '=' not in clean:
                    continue
                k, v = clean.split('=', 1)
                if k.strip() == name:
                    v = v.strip().strip('"').strip("'")
                    # Skip placeholder values like 'your_key_here'
                    if v and 'your_' not in v.lower() and 'p...' not in v.lower():
                        return v
    return fallback

DB_PASSWORD = load_env_var('DB_PASSWORD', '')
ALPACA_API_KEY = load_env_var('ALPACA_API_KEY', '')
ALPACA_SECRET_KEY = load_env_var('ALPACA_SECRET_KEY', '')
ALPACA_PAPER = load_env_var('ALPACA_PAPER', 'true').lower() == 'true'

ALPACA_BASE_URL = 'https://paper-api.alpaca.markets' if ALPACA_PAPER else 'https://api.alpaca.markets'
ALPACA_DATA_URL = 'https://data.alpaca.markets'


def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )


def log_price(cur, ticker, price, source, notes=''):
    """Store price audit trail for debugging."""
    try:
        cur.execute("""
            INSERT INTO price_feed_log (ticker, price, source, notes, logged_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (ticker, logged_at) DO NOTHING
        """, (ticker, price, source, notes))
    except Exception as e:
        # Table may not exist yet; ignore
        pass


def is_alpaca_eligible(ticker):
    """Alpaca US stocks/ETFs only: no crypto, no FX, no MXN fund tickers, no spaces."""
    if not ticker:
        return False
    t = ticker.upper().strip()
    # Skip anything with spaces, hyphens, or slashes (crypto pairs, FX)
    if ' ' in t or '-' in t or '/' in t:
        return False
    # Skip MXN/GBM fund tickers that start with $ or are known non-US
    if t.startswith('$'):
        return False
    # Skip known crypto tickers (common ones without hyphen in DB)
    if t in {'BTC', 'ETH', 'ADA', 'BNB', 'DOGE', 'HBAR', 'TRX', 'SOL', 'XRP', 'LTC', 'DOT', 'LINK', 'AVAX', 'MATIC', 'UNI', 'ATOM', 'FIL', 'ETC', 'BCH', 'ALGO', 'XLM', 'VET', 'ICP', 'AAVE', 'SUSHI', 'COMP', 'MKR', 'YFI', 'CRV', '1INCH', 'ZRX', 'BAT', 'ENJ', 'MANA', 'SAND', 'AXS', 'GALA', 'CHZ', 'FLOW', 'NEAR', 'APT', 'ARB', 'OP', 'LDO', 'RNDR', 'GRT', 'SUI', 'SEI', 'TIA', 'WLD', 'STRK', 'BERA', 'HYPE'}:
        return False
    # Must look like a US stock/ETF symbol (letters/digits only)
    if not t.isalnum():
        return False
    return True


def fetch_alpaca_batch(batch, headers):
    """Fetch one batch from Alpaca snapshots; returns (prices_dict, ok)."""
    prices = {}
    if not batch:
        return prices, True
    batch = [t.strip() for t in batch]
    symbols = ','.join(urllib.parse.quote(s, safe='') for s in batch)
    url = f"{ALPACA_DATA_URL}/v2/stocks/snapshots?symbols={symbols}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            for symbol, snapshot in data.items():
                try:
                    trade = snapshot.get('latestTrade', {})
                    price = float(trade.get('p', 0))
                    if price <= 0:
                        quote = snapshot.get('latestQuote', {})
                        price = (float(quote.get('bp', 0)) + float(quote.get('ap', 0))) / 2
                    if price > 0:
                        prices[symbol] = price
                except Exception as e:
                    print(f"  ⚠️ Alpaca parse error for {symbol}: {e}")
            return prices, True
        elif r.status_code == 400 and 'invalid symbol' in r.text.lower():
            # Bad symbol in batch; caller will split and retry
            return prices, False
        else:
            print(f"  ⚠️ Alpaca API error {r.status_code}: {r.text[:200]}")
            return prices, False
    except Exception as e:
        print(f"  ⚠️ Alpaca request error: {e}")
        return prices, False


def fetch_alpaca_prices(tickers):
    """Fetch latest trade prices from Alpaca for eligible US symbols.
    If a batch fails due to one bad symbol, split and retry recursively."""
    prices = {}
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("  ⚠️ Alpaca credentials not configured, skipping Alpaca")
        return prices

    # Fetch active US equity assets from Alpaca once per day and cache.
    # This lets us send a single big batch instead of binary-splitting on bad symbols.
    eligible_symbols = load_alpaca_eligible_symbols()
    if not eligible_symbols:
        print("  ⚠️ Could not load Alpaca eligible symbols, falling back to binary splitting")
        return fetch_alpaca_prices_legacy(tickers)

    eligible = [t for t in tickers if t.upper().strip() in eligible_symbols]
    skipped = len(tickers) - len(eligible)
    if skipped:
        print(f"  ⏭️ {skipped} tickers not in Alpaca active US equity list")
    if not eligible:
        return prices

    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }

    # Single batch request for all eligible symbols
    for i in range(0, len(eligible), 1000):
        batch = [t.strip() for t in eligible[i:i+1000]]
        symbols = ','.join(urllib.parse.quote(s, safe='') for s in batch)
        url = f"{ALPACA_DATA_URL}/v2/stocks/snapshots?symbols={symbols}"
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                for symbol, snapshot in data.items():
                    try:
                        trade = snapshot.get('latestTrade', {})
                        price = float(trade.get('p', 0))
                        if price <= 0:
                            quote = snapshot.get('latestQuote', {})
                            price = (float(quote.get('bp', 0)) + float(quote.get('ap', 0))) / 2
                        if price > 0:
                            prices[symbol] = price
                    except Exception as e:
                        print(f"  ⚠️ Alpaca parse error for {symbol}: {e}")
            else:
                print(f"  ⚠️ Alpaca API error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"  ⚠️ Alpaca request error: {e}")
        time.sleep(0.2)

    return prices


def fetch_alpaca_prices_legacy(tickers):
    """Legacy binary-split fallback when eligible-symbol cache is unavailable."""
    prices = {}
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("  ⚠️ Alpaca credentials not configured, skipping Alpaca")
        return prices

    eligible = [t for t in tickers if is_alpaca_eligible(t)]
    skipped = len(tickers) - len(eligible)
    if skipped:
        print(f"  ⏭️ {skipped} tickers not eligible for Alpaca (crypto/FX/MXN)")
    if not eligible:
        return prices

    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }

    def fetch_batch(batch):
        if not batch:
            return {}
        if len(batch) == 1:
            p = fetch_alpaca_batch(batch, headers)
            time.sleep(0.05)
            return p
        p = fetch_alpaca_batch(batch, headers)
        if p:
            time.sleep(0.05)
            return p
        mid = len(batch) // 2
        left = fetch_batch(batch[:mid])
        right = fetch_batch(batch[mid:])
        left.update(right)
        return left

    for i in range(0, len(eligible), 100):
        batch = eligible[i:i+100]
        batch_prices = fetch_batch(batch)
        prices.update(batch_prices)

    return prices


def load_alpaca_eligible_symbols():
    """Load/cached set of active US equity symbols from Alpaca. Cache is refreshed daily."""
    cache_path = '/tmp/alpaca_active_symbols.json'
    try:
        import json
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                cache = json.load(f)
            if cache.get('date') == datetime.now().strftime('%Y-%m-%d'):
                return set(cache['symbols'])
    except Exception:
        pass

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return set()

    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }
    try:
        url = f"{ALPACA_BASE_URL}/v2/assets?status=active&asset_class=us_equity"
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 200:
            assets = r.json()
            symbols = {a['symbol'] for a in assets if a.get('symbol') and a.get('tradable')}
            try:
                import json
                with open(cache_path, 'w') as f:
                    json.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'symbols': sorted(symbols)}, f)
            except Exception:
                pass
            return symbols
        else:
            print(f"  ⚠️ Alpaca assets API error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  ⚠️ Alpaca assets request error: {e}")
    return set()


def fetch_yahoo_prices(tickers):
    """Fetch prices from Yahoo Finance as fallback."""
    prices = {}
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i+50]
        symbols_str = ' '.join(batch)
        try:
            data = yf.download(symbols_str, period='1d', interval='1m', progress=False, threads=True)
            if len(batch) == 1:
                ticker = batch[0]
                if not data.empty:
                    last = data['Close'].iloc[-1]
                    prices[ticker] = float(last) if last is not None else 0.0
            else:
                for ticker in batch:
                    try:
                        if ticker in data['Close'].columns:
                            last = data['Close'][ticker].iloc[-1]
                            if last is not None:
                                prices[ticker] = float(last)
                    except Exception:
                        pass
        except Exception as e:
            print(f"  ⚠️ Yahoo error for batch {batch}: {e}")
        time.sleep(0.5)
    return prices


def sanity_check(ticker, new_price, old_price):
    """Return (ok, reason) tuple. Reject extreme spikes."""
    if new_price <= 0:
        return False, 'zero_price'
    if old_price and old_price > 0:
        ratio = new_price / old_price
        if ratio > 10 or ratio < 0.1:
            return False, f'extreme_ratio_{ratio:.2f}'
    return True, 'ok'


def get_tickers_with_old_prices(cur):
    """Get all tickers plus their current live_price for sanity checks."""
    cur.execute("SELECT DISTINCT ticker, live_price FROM positions WHERE ticker IS NOT NULL")
    pos = {row[0]: float(row[1]) if row[1] else 0 for row in cur.fetchall()}

    cur.execute("SELECT DISTINCT ticker, live_price FROM broker_positions WHERE broker='eToro' AND ticker IS NOT NULL AND ticker NOT IN ('MIRROR_TOTAL', 'CASH')")
    broker = {row[0]: float(row[1]) if row[1] else 0 for row in cur.fetchall()}

    cur.execute("SELECT DISTINCT ticker, current_price FROM vox_grades WHERE generated_at > NOW() - INTERVAL '30 days'")
    grades = {row[0]: float(row[1]) if row[1] else 0 for row in cur.fetchall()}

    return pos, broker, grades


def update_prices(ticker_map, table='positions', use_yahoo_fallback=True):
    """
    ticker_map: dict {ticker: old_price}
    table: 'positions', 'broker_positions', or 'vox_grades'
    use_yahoo_fallback: if False, only use Alpaca (fast for large watchlists)
    Returns updated count.
    """
    conn = connect()
    cur = conn.cursor()

    tickers = list(ticker_map.keys())
    print(f"Fetching prices for {len(tickers)} tickers from {table}...")

    # 1. Primary: Alpaca
    alpaca_prices = fetch_alpaca_prices(tickers)
    print(f"  Alpaca returned {len(alpaca_prices)} prices")

    # 2. Identify missing and sanity-failed tickers
    yahoo_tickers = []
    for ticker in tickers:
        old_price = ticker_map[ticker]
        alpaca_price = alpaca_prices.get(ticker)

        if alpaca_price:
            ok, reason = sanity_check(ticker, alpaca_price, old_price)
            if not ok:
                print(f"  ⚠️ {ticker}: Alpaca price ${alpaca_price} failed sanity ({reason}), will try Yahoo")
                yahoo_tickers.append(ticker)
        else:
            yahoo_tickers.append(ticker)

    # 3. Fallback: Yahoo (optional)
    yahoo_prices = {}
    if use_yahoo_fallback and yahoo_tickers:
        yahoo_prices = fetch_yahoo_prices(yahoo_tickers)
        print(f"  Yahoo returned {len(yahoo_prices)} fallback prices")

    # 4. Merge and write to DB
    final_prices = {}
    for ticker in tickers:
        old_price = ticker_map[ticker]
        alpaca_price = alpaca_prices.get(ticker)
        yahoo_price = yahoo_prices.get(ticker)

        chosen = None
        source = None

        if alpaca_price:
            ok, reason = sanity_check(ticker, alpaca_price, old_price)
            if ok:
                chosen = alpaca_price
                source = 'alpaca'

        if not chosen and yahoo_price:
            ok, reason = sanity_check(ticker, yahoo_price, old_price)
            if ok:
                chosen = yahoo_price
                source = 'yahoo'

        if not chosen and alpaca_price:
            # Fallback to alpaca even if sanity failed, but log warning
            chosen = alpaca_price
            source = 'alpaca_no_sanity'
        elif not chosen and yahoo_price:
            chosen = yahoo_price
            source = 'yahoo_no_sanity'

        if chosen and chosen > 0:
            final_prices[ticker] = (chosen, source)

    if table == 'vox_grades':
        # Bulk update the latest row per ticker using a CTE.
        # Pre-computing latest IDs makes this much faster than row-by-row subqueries.
        values = list(final_prices.items())
        if values:
            cur.execute("CREATE TEMP TABLE IF NOT EXISTS _price_update (ticker text, price numeric, source text)")
            cur.execute("TRUNCATE _price_update")
            cur.executemany(
                "INSERT INTO _price_update (ticker, price, source) VALUES (%s, %s, %s)",
                [(t, p, s) for t, (p, s) in values]
            )
            cur.execute("""
                WITH latest AS (
                    SELECT DISTINCT ON (ticker) id, ticker
                    FROM vox_grades
                    ORDER BY ticker, generated_at DESC
                )
                UPDATE vox_grades vg
                SET current_price = pu.price,
                    generated_at = NOW(),
                    price_source = pu.source
                FROM _price_update pu
                JOIN latest l ON l.ticker = pu.ticker
                WHERE vg.id = l.id
            """)
            updated = cur.rowcount
        else:
            updated = 0
    else:
        updated = 0
        for ticker, (price, source) in final_prices.items():
            try:
                if table == 'positions':
                    cur.execute("""
                        UPDATE positions
                        SET live_price = %s,
                            live_value = shares * %s,
                            live_value_usd = CASE
                                WHEN currency = 'MXN' THEN shares * %s * 0.055
                                ELSE shares * %s
                            END,
                            price_source = %s,
                            price_asof = NOW(),
                            updated_at = NOW()
                        WHERE ticker = %s
                    """, (price, price, price, price, source, ticker))
                    updated += cur.rowcount
                elif table == 'broker_positions':
                    # Update per-broker rows; preserve broker-level currency
                    cur.execute("""
                        UPDATE broker_positions
                        SET live_price = %s,
                            live_value = CASE
                                WHEN currency = 'MXN' THEN shares * %s * 0.055
                                ELSE shares * %s
                            END,
                            live_value_usd = CASE
                                WHEN currency = 'MXN' THEN shares * %s * 0.055
                                ELSE shares * %s
                            END,
                            price_source = %s,
                            updated_at = NOW()
                        WHERE ticker = %s AND broker = 'eToro'
                    """, (price, price, price, price, price, source, ticker))
                    updated += cur.rowcount
            except Exception as e:
                print(f"  ❌ DB update error for {ticker}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"Updated {updated} rows in {table}")
    return updated


def show_price_summary():
    conn = connect()
    cur = conn.cursor()
    print("\nPRICE SUMMARY")
    print("=" * 80)
    cur.execute("""
        SELECT ticker, live_price, live_value_usd, grade, price_source
        FROM positions
        ORDER BY live_value_usd DESC
        LIMIT 15
    """)
    print(f"{'Ticker':<8} {'Price':<12} {'Value USD':<14} {'Grade':<8} {'Source'}")
    print("-" * 80)
    for row in cur.fetchall():
        print(f"{row[0]:<8} ${row[1]:<11.2f} ${row[2]:<13,.2f} {row[3]:<8} {row[4] or 'none'}")
    conn.close()


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'all'

    conn = connect()
    cur = conn.cursor()
    pos_tickers, broker_tickers, grade_tickers = get_tickers_with_old_prices(cur)
    cur.close()
    conn.close()

    if action in ('all', 'portfolio'):
        update_prices(pos_tickers, table='positions')
    if action in ('all', 'broker'):
        update_prices(broker_tickers, table='broker_positions')
    if action in ('all', 'vox'):
        update_prices(grade_tickers, table='vox_grades')
    if action == 'all':
        show_price_summary()


if __name__ == '__main__':
    main()
