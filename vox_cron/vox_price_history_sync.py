#!/usr/bin/env python3
"""
VOX Price History Sync v1.0
Daily cron that fetches daily closing prices for all active tickers and stores
them in Railway PostgreSQL. Uses Alpaca for eligible US equities and Yahoo
Finance as fallback for crypto/FX/MXN/ADRs/delisted cases.

Constraints:
- Per-run cap of 500 tickers to fit in ~120s cron window.
- 25-ticker batches with retry/backoff.
- Only inserts missing dates (idempotent).
- Tracks price_unavailable for dead tickers.
"""
import os
import sys
import re
import time
import json
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, date
from decimal import Decimal

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
import requests

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system("pip install yfinance --quiet")
    import yfinance as yf

# Import helpers from the hybrid price feed
sys.path.insert(0, str(Path(__file__).parent))
from vox_hybrid_price_feed import (
    load_env_var, is_alpaca_eligible, load_alpaca_eligible_symbols
)

DB_PASSWORD = load_env_var('DB_PASSWORD', '')
ALPACA_API_KEY = load_env_var('ALPACA_API_KEY', '')
ALPACA_SECRET_KEY = load_env_var('ALPACA_SECRET_KEY', '')
ALPACA_PAPER = load_env_var('ALPACA_PAPER', 'true').lower() == 'true'
ALPACA_BASE_URL = 'https://paper-api.alpaca.markets' if ALPACA_PAPER else 'https://api.alpaca.markets'
ALPACA_DATA_URL = 'https://data.alpaca.markets'

RUN_CAP = int(os.environ.get('PRICE_SYNC_CAP', '500'))
BATCH_SIZE = int(os.environ.get('PRICE_SYNC_BATCH', '25'))
DAYS_BACK = int(os.environ.get('PRICE_SYNC_DAYS', '30'))
MAX_RETRIES = 3


def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )


def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            open NUMERIC(12,4),
            high NUMERIC(12,4),
            low NUMERIC(12,4),
            close NUMERIC(12,4) NOT NULL,
            volume BIGINT,
            adj_close NUMERIC(12,4),
            source VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (ticker, date)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date
        ON price_history (ticker, date DESC);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_unavailable (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL UNIQUE,
            reason TEXT,
            fail_count INT DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Idempotent column additions for legacy tables
    cur.execute("""
        ALTER TABLE price_unavailable
        ADD COLUMN IF NOT EXISTS fail_count INT DEFAULT 0,
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();
    """)


def is_valid_ticker(t):
    """Accept 1-5 uppercase letters/digits, or crypto pairs like BTC-USD.
    Reject descriptive names with ., spaces, or common words."""
    if not t:
        return False
    t = t.strip().upper()
    if len(t) > 10 or ' ' in t or '.' in t:
        return False
    # Standard equity-like symbols: 1-5 alphanumeric
    if re.match(r'^[A-Z0-9]{1,5}$', t):
        return True
    # Crypto pairs like BTC-USD, ETH-USD
    if re.match(r'^[A-Z0-9]{2,6}-[A-Z]{3,4}$', t):
        return True
    return False


def get_active_tickers(cur, max_tickers=RUN_CAP):
    """All tickers from vox_grades (last 30 days) and positions."""
    cur.execute("""
        SELECT DISTINCT ticker FROM (
            SELECT ticker FROM vox_grades
            WHERE generated_at > NOW() - INTERVAL '30 days'
            AND ticker IS NOT NULL
            UNION
            SELECT ticker FROM positions
            WHERE ticker IS NOT NULL
            UNION
            SELECT ticker FROM broker_positions
            WHERE ticker IS NOT NULL
              AND ticker NOT IN ('MIRROR_TOTAL', 'CASH')
        ) sq
        WHERE ticker !~ '^[0-9]'
          AND ticker NOT IN (
              SELECT ticker FROM price_unavailable
              WHERE updated_at > CURRENT_DATE - INTERVAL '7 days'
          )
        ORDER BY ticker
        LIMIT %s
    """, (max_tickers,))
    return [r[0].strip().upper() for r in cur.fetchall() if r[0] and r[0].strip() and is_valid_ticker(r[0])]


def latest_history_dates(cur, tickers):
    """Return dict {ticker: latest_date} for existing price_history rows."""
    if not tickers:
        return {}
    cur.execute("""
        SELECT ticker, MAX(date) FROM price_history
        WHERE ticker = ANY(%s)
        GROUP BY ticker
    """, (tickers,))
    return {r[0]: r[1] for r in cur.fetchall()}


def clean_records(records, source):
    """Normalize records and ensure close > 0."""
    clean = []
    for rec in records:
        close = rec.get('close') or rec.get('close_price')
        if close is None:
            continue
        try:
            close_val = float(close)
            if close_val <= 0 or close_val != close_val:  # NaN check
                continue
        except Exception:
            continue
        raw_date = rec['date']
        if isinstance(raw_date, date):
            dt = raw_date
        elif isinstance(raw_date, datetime):
            dt = raw_date.date()
        else:
            dt = datetime.strptime(str(raw_date)[:10], '%Y-%m-%d').date()
        def _float(v):
            if v is None:
                return None
            try:
                return float(v)
            except Exception:
                return None

        clean.append({
            'ticker': rec['ticker'].strip().upper(),
            'date': dt,
            'open': _float(rec.get('open') or rec.get('open_price')),
            'high': _float(rec.get('high') or rec.get('high_price')),
            'low': _float(rec.get('low') or rec.get('low_price')),
            'close': close_val,
            'volume': _float(rec.get('volume')),
            'adj_close': _float(rec.get('adj_close') or rec.get('adj_close_price')),
            'source': source,
        })
    return clean


def persist_records(cur, records, upsert: bool = True):
    """Insert new dates; by default UPSERT so corrections/late bars overwrite stale."""
    if not records:
        return 0
    inserted = 0
    for rec in records:
        if upsert:
            cur.execute(
                """
                INSERT INTO price_history
                (ticker, date, open, high, low, close, volume, adj_close, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO UPDATE SET
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  volume = EXCLUDED.volume,
                  adj_close = EXCLUDED.adj_close,
                  source = EXCLUDED.source
                """,
                (
                    rec["ticker"],
                    rec["date"],
                    rec["open"],
                    rec["high"],
                    rec["low"],
                    rec["close"],
                    rec["volume"],
                    rec["adj_close"],
                    rec["source"],
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO price_history
                (ticker, date, open, high, low, close, volume, adj_close, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO NOTHING
                """,
                (
                    rec["ticker"],
                    rec["date"],
                    rec["open"],
                    rec["high"],
                    rec["low"],
                    rec["close"],
                    rec["volume"],
                    rec["adj_close"],
                    rec["source"],
                ),
            )
        if cur.rowcount > 0:
            inserted += 1
    return inserted


def fetch_yahoo_chart_bars(tickers, range_="2mo"):
    """Primary Yahoo path via chart API (fresher than yfinance history)."""
    from vox_price_quote import yahoo_chart

    records_by_ticker = {}
    for t in tickers:
        try:
            _meta, rows = yahoo_chart(t, range_=range_, interval="1d")
            if rows:
                records_by_ticker[t] = rows
        except Exception as e:
            print(f"  ⚠️ Yahoo chart error for {t}: {e}")
        time.sleep(0.08)
    return records_by_ticker


def fetch_yahoo_bars(tickers, period="60d"):
    """Fetch daily bars — chart API first, yfinance fallback."""
    if not tickers:
        return {}
    # map period-ish to chart range
    range_ = "2mo" if period in ("60d", "2mo", "1mo") else "3mo"
    chart = fetch_yahoo_chart_bars(tickers, range_=range_)
    missing = [t for t in tickers if t not in chart]
    if not missing:
        return chart
    # fallback yfinance for leftovers
    for t in missing:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period=period, interval="1d", timeout=8)
            if hist is None or hist.empty:
                continue
            records = []
            for idx, row in hist.iterrows():
                dt = idx.date() if hasattr(idx, "date") else idx
                records.append(
                    {
                        "ticker": t,
                        "date": dt,
                        "open": row.get("Open"),
                        "high": row.get("High"),
                        "low": row.get("Low"),
                        "close": row.get("Close"),
                        "volume": row.get("Volume"),
                        "adj_close": row.get("Adj Close"),
                        "source": "yahoo",
                    }
                )
            if records:
                chart[t] = records
        except Exception as e:
            print(f"  ⚠️ Yahoo yf error for {t}: {e}")
        time.sleep(0.05)
    return chart


def mark_unavailable(cur, ticker, reason):
    cur.execute(
        """
        INSERT INTO price_unavailable (ticker, reason)
        VALUES (%s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            reason = EXCLUDED.reason,
            updated_at = NOW(),
            fail_count = price_unavailable.fail_count + 1
        """,
        (ticker, reason),
    )


def fetch_alpaca_bars(tickers, start, end):
    """Fetch daily bars from Alpaca for a list of tickers. Returns dict {ticker: [records]}."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY or not tickers:
        return {}
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }
    records_by_ticker = {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i : i + 100]
        symbols = ",".join(urllib.parse.quote(s, safe="") for s in batch)
        url = (
            f"{ALPACA_DATA_URL}/v2/stocks/bars?symbols={symbols}"
            f"&timeframe=1Day&start={start}&end={end}&limit=1000&adjustment=all"
        )
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200:
                print(f"  ⚠️ Alpaca bars error {r.status_code}: {r.text[:200]}")
                continue
            data = r.json()
            bars_by_symbol = data.get("bars", {})
            for symbol, bars in bars_by_symbol.items():
                records = []
                for bar in bars:
                    t = bar.get("t")
                    if not t:
                        continue
                    dt = datetime.fromisoformat(t.replace("Z", "+00:00")).date()
                    records.append(
                        {
                            "ticker": symbol,
                            "date": dt,
                            "open": bar.get("o"),
                            "high": bar.get("h"),
                            "low": bar.get("l"),
                            "close": bar.get("c"),
                            "volume": bar.get("v"),
                            "adj_close": bar.get("c"),
                            "source": "alpaca",
                        }
                    )
                records_by_ticker[symbol] = records
        except Exception as e:
            print(f"  ⚠️ Alpaca bars request error: {e}")
    return records_by_ticker


def fetch_batch_with_retry(tickers, start, end, retries=MAX_RETRIES):
    """Try Yahoo chart first (fresh), then Alpaca, then yfinance fallback."""
    for attempt in range(retries):
        # Primary: Yahoo chart API (most reliable for same-day crash visibility)
        result = fetch_yahoo_bars(tickers, period="60d")
        if result:
            return result, "yahoo_chart"
        eligible = [t for t in tickers if is_alpaca_eligible(t)]
        if eligible:
            result = fetch_alpaca_bars(eligible, start, end)
            if result:
                return result, "alpaca"
        if attempt < retries - 1:
            sleep = 2**attempt
            print(f"  ⏳ Retry {attempt+1} after {sleep}s")
            time.sleep(sleep)
    return {}, "failed"


def sync_tickers(cur, tickers, lookback_days=DAYS_BACK):
    """Sync price_history — always refresh last ~7 calendar days (UPSERT)."""
    if not tickers:
        return 0, 0, []
    end = date.today()
    start = end - timedelta(days=lookback_days + 5)
    # Force refresh if latest bar older than today OR we want rolling week upsert
    FORCE_REFRESH_DAYS = 7
    latest_dates = latest_history_dates(cur, tickers)
    need_fetch = []
    for t in tickers:
        latest = latest_dates.get(t)
        if latest is None or (end - latest).days >= 0:
            # always include if not same-day bar, or always for force window
            if latest is None or (end - latest).days > 0 or True:
                need_fetch.append(t)
    # Always fetch all in batch for correctness after IBM-class misses
    need_fetch = list(tickers)

    print(f"  Fetching/upserting bars for {len(need_fetch)} tickers (last {lookback_days}d + force refresh)")
    results, source = fetch_batch_with_retry(
        need_fetch, start.isoformat(), end.isoformat()
    )

    inserted = 0
    failed = 0
    failed_tickers = []
    cutoff = end - timedelta(days=FORCE_REFRESH_DAYS)
    for t in need_fetch:
        records = results.get(t, [])
        if not records:
            recs, src = fetch_batch_with_retry(
                [t], start.isoformat(), end.isoformat(), retries=1
            )
            records = recs.get(t, [])
            if records:
                source = src
        if records:
            cleaned = clean_records(records, source)
            # Upsert entire lookback window (fixes stale same-day / missed crash bars)
            cleaned = [r for r in cleaned if r["date"] >= start]
            if cleaned:
                inserted += persist_records(cur, cleaned, upsert=True)
        else:
            mark_unavailable(cur, t, "no bars returned")
            failed += 1
            failed_tickers.append(t)
    return inserted, failed, failed_tickers


def main():
    start_time = time.time()
    conn = connect()
    cur = conn.cursor()
    try:
        ensure_tables(cur)
        tickers = get_active_tickers(cur, max_tickers=RUN_CAP)
        print(f"Price History Sync: {len(tickers)} tickers to check")
        total_inserted = 0
        total_failed = 0
        all_failed = []

        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i:i+BATCH_SIZE]
            print(f"  Batch {i//BATCH_SIZE + 1}/{(len(tickers)-1)//BATCH_SIZE + 1}: {len(batch)} tickers")
            inserted, failed, failed_tickers = sync_tickers(cur, batch, DAYS_BACK)
            total_inserted += inserted
            total_failed += failed
            all_failed.extend(failed_tickers)
            conn.commit()
            elapsed = time.time() - start_time
            if elapsed > 100:
                print(f"  ⏰ Approaching 120s limit, stopping after {i+len(batch)} tickers")
                break
            time.sleep(0.2)

        print(f"Done. Inserted {total_inserted} rows; {total_failed} tickers failed.")
        if all_failed:
            print(f"Failed tickers: {', '.join(all_failed[:50])}")
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
