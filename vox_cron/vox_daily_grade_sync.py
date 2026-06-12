#!/usr/bin/env python3
"""
VOX Daily Grade Sync

Syncs positions.grade with the correct source of truth:
- S&P 500 tickers: use sp500_grades.vox_grade
- Non-S&P 500 tickers: use latest vox_grades.vox_grade

Then applies council logic based on grade thresholds:
- SELL: grade < 45
- TRIM: 45 <= grade < 50
- HOLD: 50 <= grade < 60
- BUY: 60 <= grade < 70
- CORE: grade >= 70

Run daily at 7 AM CT via cron.
"""
import os
import sys
from datetime import datetime

import psycopg2

# Load env from ~/.env (primary) and ~/.hermes/.env (fallback)
for env_path in [os.path.expanduser("~/.env"), os.path.expanduser("~/.hermes/.env")]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "railway")


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def sync_sp500_grades(conn):
    """Sync positions.grade with sp500_grades for S&P 500 tickers."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE positions p
        SET grade = s.vox_grade
        FROM sp500_grades s
        WHERE p.ticker = s.ticker
        AND p.grade != s.vox_grade
    """)
    updated = cur.rowcount
    conn.commit()
    cur.close()
    return updated


def sync_vox_grades(conn):
    """Sync positions.grade with latest vox_grades for non-S&P 500 tickers."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE positions p
        SET grade = v.vox_grade
        FROM (
            SELECT DISTINCT ON (ticker) ticker, vox_grade
            FROM vox_grades
            ORDER BY ticker, generated_at DESC
        ) v
        WHERE p.ticker = v.ticker
        AND p.grade != v.vox_grade
        AND p.ticker NOT IN (SELECT ticker FROM sp500_grades)
    """)
    updated = cur.rowcount
    conn.commit()
    cur.close()
    return updated


def apply_council_logic(conn):
    """Apply council logic based on grade thresholds."""
    cur = conn.cursor()

    # SELL: grade < 45
    cur.execute("UPDATE positions SET council = 'SELL' WHERE grade < 45")
    sell_count = cur.rowcount

    # TRIM: 45 <= grade < 50
    cur.execute("UPDATE positions SET council = 'TRIM' WHERE grade >= 45 AND grade < 50")
    trim_count = cur.rowcount

    # HOLD: 50 <= grade < 60
    cur.execute("UPDATE positions SET council = 'HOLD' WHERE grade >= 50 AND grade < 60")
    hold_count = cur.rowcount

    # BUY: 60 <= grade < 70
    cur.execute("UPDATE positions SET council = 'BUY' WHERE grade >= 60 AND grade < 70")
    buy_count = cur.rowcount

    # CORE: grade >= 70
    cur.execute("UPDATE positions SET council = 'CORE' WHERE grade >= 70")
    core_count = cur.rowcount

    conn.commit()
    cur.close()
    return {
        "SELL": sell_count,
        "TRIM": trim_count,
        "HOLD": hold_count,
        "BUY": buy_count,
        "CORE": core_count,
    }


def get_stats(conn):
    """Get current positions stats."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*), SUM(live_value) FROM positions")
    pos_count, aum = cur.fetchone()

    cur.execute("SELECT council, COUNT(*), SUM(live_value) FROM positions GROUP BY council ORDER BY council")
    council_dist = {r[0]: {"count": r[1], "value": float(r[2]) if r[2] else 0} for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) FROM positions WHERE grade < 45")
    sell_zone = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM positions p
        JOIN sp500_grades s ON p.ticker = s.ticker
        WHERE p.grade != s.vox_grade
    """)
    sp500_mismatch = cur.fetchone()[0]

    cur.close()
    return {
        "positions": pos_count,
        "aum": float(aum) if aum else 0,
        "council": council_dist,
        "sell_zone": sell_zone,
        "sp500_mismatch": sp500_mismatch,
    }


def run_sync():
    conn = get_db()

    # Get before stats
    before = get_stats(conn)

    # Sync S&P 500 grades
    sp500_updated = sync_sp500_grades(conn)

    # Sync non-S&P 500 grades from vox_grades
    vox_updated = sync_vox_grades(conn)

    # Apply council logic
    council_changes = apply_council_logic(conn)

    # Get after stats
    after = get_stats(conn)

    conn.close()

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "sp500_grades_synced": sp500_updated,
        "vox_grades_synced": vox_updated,
        "council_changes": council_changes,
        "before": before,
        "after": after,
    }

    return report


if __name__ == "__main__":
    report = run_sync()

    # Print summary
    print("=" * 60)
    print("VOX Daily Grade Sync — Complete")
    print("=" * 60)
    print(f"Timestamp: {report['timestamp']}")
    print(f"S&P 500 grades synced: {report['sp500_grades_synced']}")
    print(f"vox_grades synced: {report['vox_grades_synced']}")
    print(f"\nCouncil changes:")
    for council, count in report["council_changes"].items():
        if count > 0:
            print(f"  {council}: {count} positions")
    print(f"\nFinal state:")
    print(f"  Positions: {report['after']['positions']}")
    print(f"  AUM: ${report['after']['aum']:,.2f}")
    print(f"  SELL zone (<45): {report['after']['sell_zone']}")
    print(f"  sp500 mismatches: {report['after']['sp500_mismatch']}")
    print("=" * 60)

    sys.exit(0)
