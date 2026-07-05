#!/usr/bin/env python3
"""
VOX Price History Backfill v1.0
One-time script (not a cron) that backfills one year of daily closing prices
for all tickers currently in vox_grades and positions.

Uses Alpaca for eligible US equities and Yahoo Finance for fallback.
Idempotent: only inserts missing dates.
"""
import os
import sys
import time
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2

# Reuse sync helpers and DB connection from the daily sync script
sys.path.insert(0, str(Path(__file__).parent))
from vox_price_history_sync import (
    connect, ensure_tables, get_active_tickers, sync_tickers, BATCH_SIZE, is_valid_ticker
)

LOOKBACK_DAYS = 365


def get_all_tickers(cur):
    """Backfill tickers that matter: positions + broker_positions + top 200 recent vox_grades."""
    cur.execute("""
        SELECT DISTINCT ticker FROM (
            SELECT ticker FROM positions WHERE ticker IS NOT NULL
            UNION
            SELECT ticker FROM broker_positions
            WHERE ticker IS NOT NULL AND ticker NOT IN ('MIRROR_TOTAL', 'CASH')
            UNION
            SELECT ticker FROM (
                SELECT ticker, MAX(generated_at) AS last_graded
                FROM vox_grades
                WHERE generated_at > NOW() - INTERVAL '7 days'
                AND ticker IS NOT NULL
                GROUP BY ticker
                ORDER BY last_graded DESC
                LIMIT 200
            ) recent_grades
        ) sq
        ORDER BY ticker
    """)
    return [r[0].strip().upper() for r in cur.fetchall() if r[0] and r[0].strip() and is_valid_ticker(r[0])]


def main():
    conn = connect()
    cur = conn.cursor()
    start_time = time.time()
    try:
        ensure_tables(cur)
        tickers = get_all_tickers(cur)
        print(f"Price History Backfill: {len(tickers)} unique tickers")
        total_inserted = 0
        total_failed = 0
        all_failed = []

        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i:i+BATCH_SIZE]
            print(f"Batch {i//BATCH_SIZE + 1}/{(len(tickers)-1)//BATCH_SIZE + 1}: {len(batch)} tickers")
            inserted, failed, failed_tickers = sync_tickers(cur, batch, lookback_days=LOOKBACK_DAYS)
            total_inserted += inserted
            total_failed += failed
            all_failed.extend(failed_tickers)
            conn.commit()
            elapsed = time.time() - start_time
            print(f"  elapsed {elapsed:.1f}s | inserted {total_inserted} | failed {total_failed}")
            if elapsed > 3300:  # 55m hard guard; full run can be long
                print("  Approaching 1h limit, stopping.")
                break
            time.sleep(0.2)

        print(f"\nBackfill complete. Inserted {total_inserted} rows; {total_failed} tickers failed.")
        if all_failed:
            print(f"Failed tickers ({len(all_failed)}): {', '.join(all_failed[:100])}")
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
