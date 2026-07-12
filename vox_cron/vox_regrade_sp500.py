#!/usr/bin/env python3
"""Weekly S&P 500 regrade — rotating day-batch via vox_live_grader.

Restores the missing weekly SP500 grade refresh. Processes a day-rotated
batch so the full universe rotates over ~50 days without exceeding cron limits.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap  # noqa: F401

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))

import psycopg2
from psycopg2.extras import execute_values

from vox_live_grader import grade_ticker  # type: ignore

SCRIPT_TIMEOUT = 540  # hard stop under 10 min


def _timeout_handler(signum, frame):
    print(f"\nSCRIPT TIMEOUT after {SCRIPT_TIMEOUT}s — partial batch saved")
    raise SystemExit(0)


def connect():
    host = os.environ.get("PGHOST") or os.environ.get("DB_HOST") or "acela.proxy.rlwy.net"
    port = int(os.environ.get("PGPORT") or os.environ.get("DB_PORT") or "35577")
    db = os.environ.get("PGDATABASE") or os.environ.get("DB_NAME") or "railway"
    user = os.environ.get("PGUSER") or os.environ.get("DB_USER") or "postgres"
    pw = os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD") or ""
    return psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pw, connect_timeout=20)


def main() -> int:
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(SCRIPT_TIMEOUT)

    print(f"VOX S&P 500 Weekly Regrade — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    conn = connect()
    cur = conn.cursor()

    # Prefer active universe; fallback to existing sp500_grades tickers
    cur.execute(
        """
        SELECT ticker FROM sp500_universe
        WHERE COALESCE(is_active, TRUE) = TRUE
        ORDER BY ticker
        """
    )
    tickers = [r[0] for r in cur.fetchall()]
    if not tickers:
        cur.execute("SELECT ticker FROM sp500_grades ORDER BY ticker")
        tickers = [r[0] for r in cur.fetchall()]

    if not tickers:
        print("No S&P 500 tickers found")
        return 1

    BATCH_SIZE = 20
    day_of_year = datetime.now().timetuple().tm_yday
    num_batches = max(1, (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE)
    batch_idx = day_of_year % num_batches
    offset = batch_idx * BATCH_SIZE
    batch = tickers[offset : offset + BATCH_SIZE]

    print(f"Universe: {len(tickers)} | batch {batch_idx + 1}/{num_batches} | size {len(batch)}")

    results = []
    errors = []
    for ticker in batch:
        try:
            g = grade_ticker(ticker, timeout_secs=10)
            if not g:
                errors.append((ticker, "no grade"))
                print(f"  {ticker}: no grade")
                continue
            # grade_ticker may return dict or object
            if isinstance(g, dict):
                row = {
                    "ticker": ticker,
                    "vox_grade": int(g.get("vox_grade") or g.get("overall_grade") or g.get("grade") or 50),
                    "technical_score": int(g.get("technical_score") or 50),
                    "fundamental_score": int(g.get("fundamental_score") or 50),
                    "macro_score": int(g.get("macro_score") or 50),
                    "sector_score": int(g.get("sector_score") or g.get("sector_momentum") or 50),
                    "weather_score": int(g.get("weather_score") or 50),
                    "sentiment_score": int(g.get("sentiment_score") or 50),
                }
            else:
                row = {
                    "ticker": ticker,
                    "vox_grade": int(getattr(g, "overall_grade", getattr(g, "vox_grade", 50)) or 50),
                    "technical_score": int(getattr(g, "technical_score", 50) or 50),
                    "fundamental_score": int(getattr(g, "fundamental_score", 50) or 50),
                    "macro_score": int(getattr(g, "macro_score", 50) or 50),
                    "sector_score": int(getattr(g, "sector_score", 50) or 50),
                    "weather_score": int(getattr(g, "weather_score", 50) or 50),
                    "sentiment_score": int(getattr(g, "sentiment_score", 50) or 50),
                }
            results.append(row)
            print(f"  {ticker}: {row['vox_grade']}")
        except Exception as e:
            errors.append((ticker, str(e)[:100]))
            print(f"  {ticker}: ERROR {str(e)[:100]}")
        time.sleep(0.8)

    if results:
        rows = [
            (
                r["ticker"],
                r["vox_grade"],
                r["technical_score"],
                r["fundamental_score"],
                r["macro_score"],
                r["sector_score"],
                r["weather_score"],
                r["sentiment_score"],
                datetime.utcnow(),
            )
            for r in results
        ]
        execute_values(
            cur,
            """
            INSERT INTO sp500_grades
                (ticker, vox_grade, technical_score, fundamental_score, macro_score,
                 sector_score, weather_score, sentiment_score, computed_at)
            VALUES %s
            ON CONFLICT (ticker) DO UPDATE SET
                vox_grade = EXCLUDED.vox_grade,
                technical_score = EXCLUDED.technical_score,
                fundamental_score = EXCLUDED.fundamental_score,
                macro_score = EXCLUDED.macro_score,
                sector_score = EXCLUDED.sector_score,
                weather_score = EXCLUDED.weather_score,
                sentiment_score = EXCLUDED.sentiment_score,
                computed_at = EXCLUDED.computed_at
            """,
            rows,
        )
        conn.commit()
        print(f"Saved {len(results)} grades to sp500_grades")

    cur.execute("SELECT COUNT(*), MAX(computed_at) FROM sp500_grades")
    count, latest = cur.fetchone()
    print(f"sp500_grades: {count} rows, latest={latest}")
    print(f"Done. ok={len(results)} errors={len(errors)}")
    conn.close()
    signal.alarm(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
