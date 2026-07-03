#!/usr/bin/env python3
"""
VOX Pre-Monday Grading Pass
Grade any ticker mentioned by VOX systems that lacks a fresh vox_grade.
Runs before Monday top-10 / deep-dive / alert generation.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import psycopg2
from vox_live_grader import grade_ticker

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": __import__("os").environ.get("PGPASSWORD") or __import__("os").environ.get("DB_PASSWORD"),
    "dbname": "railway",
}

def q(sql):
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def main():
    rows = q("""
        SELECT DISTINCT ticker FROM (
            SELECT ticker FROM council_deliberations
            UNION SELECT ticker FROM top_opportunities
            UNION SELECT ticker FROM pattern_alerts
            UNION SELECT ticker FROM insider_trades
            UNION SELECT ticker FROM trader_calls
            UNION SELECT ticker FROM theme_alignment
            UNION SELECT ticker FROM discovery_queue
            UNION SELECT ticker FROM earnings_calendar
            UNION SELECT ticker FROM watchlist
            UNION SELECT ticker FROM positions
        ) m
        WHERE NOT EXISTS (
            SELECT 1 FROM vox_grades v WHERE v.ticker = m.ticker
            AND v.generated_at > NOW() - INTERVAL '1 day'
        )
        AND m.ticker ~ '^[A-Z]+$'
        ORDER BY ticker
    """)
    tickers = [r['ticker'] for r in rows]
    print(f"VOX Pre-Monday Grading Pass: {len(tickers)} tickers need grading")
    if not tickers:
        print("All mentioned tickers already have a grade within 24h.")
        return

    graded = failed = timeout = 0
    for ticker in tickers:
        res = grade_ticker(ticker, timeout_secs=15)
        if res is None:
            failed += 1
            print(f"  {ticker}: FAILED")
        elif res.get('timeout'):
            timeout += 1
            print(f"  {ticker}: TIMEOUT")
        elif res.get('updated'):
            print(f"  {ticker}: UNCHANGED grade={res['grade']}")
        else:
            graded += 1
            print(f"  {ticker}: GRADED {res['grade']} ({res['action']})")
        time.sleep(2)

    print(f"\nDone: {graded} newly graded, {timeout} timeouts, {failed} failed")

if __name__ == '__main__':
    main()
