#!/usr/bin/env python3
"""
VOX Price History Sync v0.2
Batch download daily prices from yfinance for relevant tickers and store in Railway.
"""
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
import yfinance as yf

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
    "dbname": "railway",
}


def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            price_date DATE NOT NULL,
            open_price NUMERIC(18,4),
            high_price NUMERIC(18,4),
            low_price NUMERIC(18,4),
            close_price NUMERIC(18,4) NOT NULL,
            volume BIGINT,
            adj_close NUMERIC(18,4),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, price_date)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date
        ON price_history(ticker, price_date DESC);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_unavailable (
            ticker TEXT PRIMARY KEY,
            first_seen DATE DEFAULT CURRENT_DATE,
            last_tried DATE DEFAULT CURRENT_DATE,
            reason TEXT
        );
    """)



def clean_ticker(t):
    t = (t or "").strip().upper()
    return t.lstrip("$")


BAD_TICKERS = ('ADA', 'ADA-USD', 'NAFC', 'NLC', 'SZYM', 'ATFX', 'SRDX', 'CYBN', 'SGH', 'MKFG', 'CANOO', 'IMMU', 'DMTK', 'PRO', 'SRAC', 'CNVA', 'OCFT', 'COBH', 'SQ', 'DMG', 'MULN', 'EXAS', 'CAR-T', 'VLD', 'ME', 'VIPKID', 'LILIUM', 'SHPW', 'TCRR', 'ARVL', 'HDNG')


def get_tickers(cur, max_tickers=30):
    cur.execute("""
        SELECT DISTINCT ticker FROM (
            SELECT ticker FROM positions WHERE ticker IS NOT NULL
            UNION
            SELECT ticker FROM council_deliberations WHERE ticker IS NOT NULL AND timestamp >= NOW() - INTERVAL '90 days'
            UNION
            SELECT ticker FROM trader_calls WHERE ticker IS NOT NULL AND call_date >= NOW() - INTERVAL '90 days'
            UNION
            SELECT ticker FROM discovery_queue WHERE ticker IS NOT NULL AND status='pending'
        ) sq
        WHERE ticker NOT IN (
            SELECT DISTINCT ticker FROM price_history WHERE price_date = CURRENT_DATE - INTERVAL '1 day'
        )
        AND ticker NOT IN (SELECT ticker FROM price_unavailable WHERE last_tried >= CURRENT_DATE - INTERVAL '7 days')
        AND ticker NOT IN %s
        AND ticker !~ '^[0-9]'
        LIMIT %s
    """, (BAD_TICKERS, max_tickers))
    return [clean_ticker(r[0]) for r in cur.fetchall()]


def is_valid_num(v):
    if v is None:
        return False
    try:
        return str(v).lower() not in ('nan', 'none', 'nat', '')
    except Exception:
        return False


def fetch_history_batch(tickers, period="60d"):
    if not tickers:
        return {}
    try:
        hist = yf.download(
            tickers,
            period=period,
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,
            prepost=False
        )
        if hist is None or hist.empty:
            return {}
        records_by_ticker = {}
        single = len(tickers) == 1
        for t in tickers:
            df = hist if single else hist.get(t)
            if df is None or df.empty:
                continue
            records = []
            for date, row in df.iterrows():
                records.append({
                    "ticker": t,
                    "price_date": date.date() if hasattr(date, 'date') else date,
                    "open_price": float(row.get("Open")) if is_valid_num(row.get("Open")) else None,
                    "high_price": float(row.get("High")) if is_valid_num(row.get("High")) else None,
                    "low_price": float(row.get("Low")) if is_valid_num(row.get("Low")) else None,
                    "close_price": float(row.get("Close")) if is_valid_num(row.get("Close")) else None,
                    "volume": int(row.get("Volume")) if is_valid_num(row.get("Volume")) else None,
                    "adj_close": float(row.get("Adj Close")) if is_valid_num(row.get("Adj Close")) else None,
                })
            records_by_ticker[t] = records
        return records_by_ticker
    except Exception as e:
        print(f"Batch download error: {e}")
        return {}


def fetch_with_timeout(tickers, timeout=60):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_history_batch, tickers)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            return {}


def mark_unavailable(cur, ticker, reason):
    cur.execute("""
        INSERT INTO price_unavailable (ticker, reason, last_tried)
        VALUES (%s, %s, CURRENT_DATE)
        ON CONFLICT (ticker) DO UPDATE SET
            last_tried = CURRENT_DATE,
            reason = EXCLUDED.reason
    """, (ticker, reason))


def persist(cur, records):
    valid = [r for r in records if r["close_price"] is not None]
    if not valid:
        return False
    for rec in valid:
        cur.execute("""
            INSERT INTO price_history (ticker, price_date, open_price, high_price, low_price, close_price, volume, adj_close)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, price_date) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                adj_close = EXCLUDED.adj_close,
                created_at = NOW()
        """, (
            rec["ticker"], rec["price_date"], rec["open_price"], rec["high_price"],
            rec["low_price"], rec["close_price"], rec["volume"], rec["adj_close"]
        ))
    return True


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        ensure_tables(cur)
        tickers = get_tickers(cur, max_tickers=100)
        print(f"Price History Sync: {len(tickers)} tickers to refresh")
        fetched = 0
        unavailable = 0
        batch_size = 25
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            print(f"  batch {i//batch_size + 1}: {len(batch)} tickers")
            results = fetch_with_timeout(batch, timeout=60)
            for t in batch:
                recs = results.get(t, [])
                if recs and persist(cur, recs):
                    fetched += 1
                else:
                    mark_unavailable(cur, t, "no valid close prices")
                    unavailable += 1
            conn.commit()
        print(f"Done. Fetched {fetched}, unavailable {unavailable}/{len(tickers)}.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
