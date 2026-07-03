#!/usr/bin/env python3
"""VOX Hybrid Price Feed — Full watchlist update.
Only updates vox_grades tickers whose current_price is stale (<=0 or older than 7 days)
to fit inside the 120s cron window. Positions and broker_positions are handled by the
hourly wrapper (vox_hybrid_price_feed_hourly.py).
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_hybrid_price_feed as pf

conn = pf.connect()
cur = conn.cursor()

# Only stale grades: current_price <= 0 or older than 7 days
cur.execute("""
    SELECT DISTINCT ON (ticker) ticker, current_price, generated_at
    FROM vox_grades
    ORDER BY ticker, generated_at DESC
""")
grade_tickers = {}
for row in cur.fetchall():
    ticker, price, generated_at = row
    if price is None or float(price) <= 0 or generated_at is None or generated_at < datetime.now() - timedelta(days=7):
        grade_tickers[ticker] = float(price) if price else 0.0

cur.close()
conn.close()

print(f"Full feed: {len(grade_tickers)} stale vox_grades tickers to update")
if grade_tickers:
    # Cap per run to fit inside 120s cron window; prioritize oldest (lowest current_price / oldest)
    sorted_tickers = dict(sorted(grade_tickers.items(), key=lambda x: (x[1] if x[1] else 0, x[0]))[:200])
    print(f"  Processing first 200 capped: {list(sorted_tickers.keys())[:5]}...")
    pf.update_prices(sorted_tickers, table='vox_grades', use_yahoo_fallback=True)
