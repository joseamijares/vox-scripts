#!/usr/bin/env python3
"""VOX DB noise cleanup — each step commits independently."""
from __future__ import annotations

import os
import sys

import psycopg2

DRY = "--apply" not in sys.argv

def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=30,
    )


def step(name, sql_count, sql_apply=None):
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute(sql_count)
        n = cur.fetchone()[0]
        print(f"{name}: {n}")
        if DRY or not sql_apply or n == 0:
            conn.rollback()
            return n
        cur.execute(sql_apply)
        conn.commit()
        print(f"  -> applied")
        return n
    except Exception as e:
        conn.rollback()
        print(f"{name}: ERR {e}")
        return None
    finally:
        conn.close()


def main():
    print("DRY" if DRY else "APPLY", datetime_now())
    step(
        "ghost_positions",
        """SELECT COUNT(*) FROM positions
           WHERE COALESCE(live_value_usd, live_value, 0) <= 0 AND COALESCE(shares, 0) <= 0""",
        """DELETE FROM positions
           WHERE COALESCE(live_value_usd, live_value, 0) <= 0 AND COALESCE(shares, 0) <= 0""",
    )
    step(
        "trade_signals_all",
        "SELECT COUNT(*) FROM trade_signals",
        "TRUNCATE trade_signals",
    )
    step(
        "alerts_old_14d",
        "SELECT COUNT(*) FROM alerts WHERE timestamp < NOW() - INTERVAL '14 days'",
        "DELETE FROM alerts WHERE timestamp < NOW() - INTERVAL '14 days'",
    )
    step(
        "grade_alerts_old_30d",
        "SELECT COUNT(*) FROM grade_alerts WHERE triggered_at < NOW() - INTERVAL '30 days'",
        "DELETE FROM grade_alerts WHERE triggered_at < NOW() - INTERVAL '30 days'",
    )
    # grades: delete old non-latest
    step(
        "vox_grades_old_non_latest",
        """
        SELECT COUNT(*) FROM vox_grades g
        WHERE g.generated_at < NOW() - INTERVAL '14 days'
          AND (g.ticker, g.generated_at) NOT IN (
            SELECT DISTINCT ON (ticker) ticker, generated_at
            FROM vox_grades ORDER BY ticker, generated_at DESC
          )
        """,
        """
        DELETE FROM vox_grades g
        WHERE g.generated_at < NOW() - INTERVAL '14 days'
          AND (g.ticker, g.generated_at) NOT IN (
            SELECT DISTINCT ON (ticker) ticker, generated_at
            FROM vox_grades ORDER BY ticker, generated_at DESC
          )
        """,
    )
    # post
    conn = connect()
    cur = conn.cursor()
    for t in ["positions", "vox_grades", "trade_signals", "alerts", "grade_alerts"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"after {t}: {cur.fetchone()[0]}")
    conn.close()
    return 0


def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
