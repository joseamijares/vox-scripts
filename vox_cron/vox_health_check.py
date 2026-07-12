#!/usr/bin/env python3
"""
VOX Daily Health Check v2
Checks all systems for failures - alerts if anything broken
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, psycopg2, subprocess
from datetime import datetime, timedelta
import json
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_unified_grades():
    """Load unified grades from single source of truth"""
    unified_path = SCRIPT_DIR / "vox_unified_grades.json"
    if not unified_path.exists():
        return {}
    with open(unified_path) as f:
        return json.load(f)

def get_unified_grade(ticker, unified_grades):
    """Get grade from unified source"""
    if ticker in unified_grades.get("grades", {}):
        return unified_grades["grades"][ticker].get("grade", 0)
    return 0


def check_cron_health(cur):
    """Check for paused or failed cron jobs via Hermes cronjob API"""
    issues = []
    
    # The cron_jobs table is in Hermes local SQLite, not Railway Postgres.
    # We skip DB-based cron checks and rely on the cronjob tool or local file checks.
    # Check for recent error markers in the scripts directory
    error_marker = SCRIPT_DIR / "vox_cron" / ".last_errors"
    if error_marker.exists():
        with open(error_marker) as f:
            errors = f.read().strip()
        if errors:
            issues.append(f"⚠️ Recent errors logged: {errors[:200]}")
    
    return issues

def check_data_freshness(cur):
    """Check if grades are stale. Returns (critical_issues, soft_warnings)."""
    critical = []
    soft = []

    # Check S&P 500 grades age (use computed_at if available, fallback to other columns)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'sp500_grades' AND column_name IN ('computed_at', 'graded_at', 'updated_at', 'created_at')
    """)
    date_columns = [r[0] for r in cur.fetchall()]

    if date_columns:
        date_col = date_columns[0]  # Use first available date column
        cur.execute(f"SELECT MAX({date_col}) FROM sp500_grades")
        last_grade = cur.fetchone()[0]

        if last_grade:
            now = datetime.now()
            if last_grade.tzinfo:
                now = datetime.now(last_grade.tzinfo)
            age_days = (now - last_grade).days
            # Weekly regrade is intentional; only critical after 14d
            if age_days > 14:
                critical.append(f"🔴 Stale S&P 500 grades: {age_days} days old")
            elif age_days > 8:
                soft.append(f"⚠️ S&P 500 grades getting stale: {age_days} days old")

    # Latest vox_grades per ticker (not historical rows)
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT ticker, MAX(generated_at) AS last_grade
            FROM vox_grades
            GROUP BY ticker
            HAVING MAX(generated_at) < NOW() - INTERVAL '7 days'
        ) sq
    """)
    stale_latest = cur.fetchone()[0]
    if stale_latest and stale_latest > 200:
        soft.append(f"⚠️ {stale_latest} tickers with latest vox_grade older than 7d")

    # technical_signals freshness — stale tech scores corrupt unified blend
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'technical_signals' AND column_name IN ('computed_at', 'updated_at', 'created_at')
    """)
    tech_cols = [r[0] for r in cur.fetchall()]
    if tech_cols:
        col = tech_cols[0]
        cur.execute(f"SELECT MAX({col}) FROM technical_signals")
        last_tech = cur.fetchone()[0]
        if last_tech:
            now = datetime.now()
            if last_tech.tzinfo:
                now = datetime.now(last_tech.tzinfo)
            age_days = (now - last_tech).days
            if age_days > 7:
                critical.append(f"🔴 technical_signals stale: {age_days} days old")
            elif age_days > 2:
                soft.append(f"⚠️ technical_signals aging: {age_days} days old")
        else:
            soft.append("⚠️ technical_signals table empty")

    # Check portfolio grades (use positions table, not broker_positions)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'positions' AND column_name IN ('updated_at', 'last_sync', 'created_at')
    """)
    pos_date_columns = [r[0] for r in cur.fetchall()]

    if pos_date_columns:
        date_col = pos_date_columns[0]
        cur.execute(f"SELECT MAX({date_col}) FROM positions")
        last_update = cur.fetchone()[0]

        if last_update:
            now = datetime.now()
            if last_update.tzinfo:
                now = datetime.now(last_update.tzinfo)
            age_days = (now - last_update).days
            if age_days > 3:
                soft.append(f"⚠️ Portfolio data stale: {age_days} days old")

    return critical, soft

def check_database_health(cur):
    """Check database connectivity and issues. Returns (critical, soft)."""
    critical = []
    soft = []

    # Check for positions with NULL grades (use positions table, not broker_positions)
    cur.execute("""
        SELECT COUNT(*) FROM positions WHERE grade IS NULL
    """)
    null_count = cur.fetchone()[0]
    if null_count > 0:
        soft.append(f"⚠️ {null_count} positions with NULL grades")

    # Check for positions with 0 value
    cur.execute("""
        SELECT COUNT(*) FROM positions
        WHERE live_value = 0 OR live_value IS NULL
    """)
    zero_count = cur.fetchone()[0]
    if zero_count > 0:
        soft.append(f"⚠️ {zero_count} positions with $0 value")

    # Check for NaN values in live_value
    cur.execute("""
        SELECT COUNT(*) FROM positions
        WHERE live_value = 'NaN'::float OR live_value::text = 'NaN'
    """)
    nan_count = cur.fetchone()[0]
    if nan_count > 0:
        critical.append(f"🔴 {nan_count} positions with NaN live_value — data corruption!")

    # Check for positions with NaN live_price
    cur.execute("""
        SELECT COUNT(*) FROM positions
        WHERE live_price = 'NaN'::float OR live_price::text = 'NaN'
    """)
    nan_price_count = cur.fetchone()[0]
    if nan_price_count > 0:
        critical.append(f"🔴 {nan_price_count} positions with NaN live_price — price feed broken!")

    # Check unified_grades table freshness
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'unified_grades' AND column_name IN ('computed_at', 'updated_at', 'created_at')
    """)
    ug_date_columns = [r[0] for r in cur.fetchall()]
    if ug_date_columns:
        date_col = ug_date_columns[0]
        cur.execute(f"SELECT MAX({date_col}) FROM unified_grades")
        last_ug = cur.fetchone()[0]
        if last_ug:
            now = datetime.now()
            if last_ug.tzinfo:
                now = datetime.now(last_ug.tzinfo)
            age_days = (now - last_ug).days
            if age_days > 2:
                critical.append(f"🔴 Unified grades stale: {age_days} days old")
            elif age_days > 1:
                soft.append(f"⚠️ Unified grades aging: {age_days} days old")

    # Check for broken council_deliberations (missing sequence)
    cur.execute("""
        SELECT column_default FROM information_schema.columns
        WHERE table_name = 'council_deliberations' AND column_name = 'id'
    """)
    id_default = cur.fetchone()
    if not id_default or not id_default[0]:
        critical.append("🔴 council_deliberations.id has no default sequence — DoC will fail!")

    return critical, soft

def check_schema_mismatches(cur):
    """Check for known schema issues that cause cron failures. Returns (critical, soft)."""
    critical = []
    soft = []

    # Check unified_grades.ticker length
    cur.execute("""
        SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'unified_grades' AND column_name = 'ticker'
    """)
    result = cur.fetchone()
    if result and result[0] and result[0] < 20:
        critical.append(
            f"🔴 unified_grades.ticker is VARCHAR({result[0]}) — too short for tickers like 'NAFTRAC ISHRS' (13 chars). Needs VARCHAR(20)."
        )

    return critical, soft

def main():
    # Use PGPASSWORD from environment, fallback to direct value for cron jobs
    pwd = os.environ.get('PGPASSWORD', os.environ.get('DB_PASSWORD', ''))

    try:
        conn = psycopg2.connect(
            host='acela.proxy.rlwy.net', port=35577,
            database='railway', user='postgres', password=pwd
        )
        cur = conn.cursor()
    except Exception as e:
        print(f"🔴 CRITICAL: Cannot connect to database: {e}")
        return 1

    critical = []
    soft = []

    soft.extend(check_cron_health(cur))
    c, s = check_data_freshness(cur)
    critical.extend(c); soft.extend(s)
    c, s = check_database_health(cur)
    critical.extend(c); soft.extend(s)
    c, s = check_schema_mismatches(cur)
    critical.extend(c); soft.extend(s)

    conn.close()

    # Exit semantics (Pattern 9b):
    # - 0 = check executed successfully (soft warnings still printed / delivered)
    # - 1 = real failure or critical data corruption
    if critical or soft:
        print("🚨 VOX HEALTH CHECK ALERTS:")
        for issue in critical + soft:
            print(f"  {issue}")
    else:
        print("✅ All systems healthy")

    return 1 if critical else 0

if __name__ == '__main__':
    exit(main())
