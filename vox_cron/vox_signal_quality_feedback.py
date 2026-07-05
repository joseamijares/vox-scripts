#!/usr/bin/env python3
"""
VOX Signal Quality / Alpha Decay Feedback Loop v0.2
Pure SQL + Python: measures whether grades, council calls, and trader calls
actually made money. Uses existing position live prices and price_at_call data.
Writes to Railway signal_performance and Obsidian SignalQuality/YYYY-MM-DD.md.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
    "dbname": "railway",
}

OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian" / "VOX" / "SignalQuality"


def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signal_performance (
            id SERIAL PRIMARY KEY,
            signal_type TEXT NOT NULL,
            signal_source TEXT,
            ticker TEXT,
            action TEXT,
            signal_date DATE NOT NULL,
            entry_price NUMERIC(18,4),
            current_price NUMERIC(18,4),
            return_1d NUMERIC(10,4),
            return_5d NUMERIC(10,4),
            return_20d NUMERIC(10,4),
            return_60d NUMERIC(10,4),
            return_since_signal NUMERIC(10,4),
            return_method VARCHAR(20) DEFAULT 'live_price',
            signal_count INT DEFAULT 1,
            win_rate NUMERIC(6,2),
            avg_return NUMERIC(10,4),
            grade_bucket TEXT,
            snapshot_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(signal_type, signal_source, ticker, signal_date, snapshot_date)
        );
    """)
    cur.execute("""
        ALTER TABLE signal_performance
        ADD COLUMN IF NOT EXISTS return_1d NUMERIC(10,4),
        ADD COLUMN IF NOT EXISTS return_5d NUMERIC(10,4),
        ADD COLUMN IF NOT EXISTS return_20d NUMERIC(10,4),
        ADD COLUMN IF NOT EXISTS return_60d NUMERIC(10,4),
        ADD COLUMN IF NOT EXISTS return_method VARCHAR(20) DEFAULT 'live_price'
    """)


def get_current_price(cur, ticker):
    cur.execute("""
        SELECT COALESCE(p.live_price, vg.current_price) AS price
        FROM (SELECT %s AS ticker) q
        LEFT JOIN positions p ON p.ticker = q.ticker
        LEFT JOIN vox_grades vg ON vg.ticker = q.ticker
    """, (ticker,))
    r = cur.fetchone()
    return r[0] if r else None


def price_at_date(cur, ticker, as_of_date):
    """Return close price from price_history for a given date if available."""
    cur.execute("""
        SELECT close FROM price_history
        WHERE ticker = %s AND date = %s
        ORDER BY source
        LIMIT 1
    """, (ticker, as_of_date))
    r = cur.fetchone()
    return r[0] if r else None


def compute_forward_returns(cur, ticker, sig_date, current_price):
    """Compute 1d/5d/20d/60d forward returns using price_history close prices.
    Falls back to current live price for the latest window if history is missing."""
    from datetime import date
    today = date.today()
    live_price = get_current_price(cur, ticker)

    def get_price_for_offset(days):
        target = sig_date + timedelta(days=days)
        if target > today:
            return None, None
        price = price_at_date(cur, ticker, target)
        if price is not None:
            return float(price), 'history'
        # If target is the most recent date we can observe, fall back to live price
        if target == today and live_price:
            return float(live_price), 'live_price'
        return None, None

    r1d = r5d = r20d = r60d = None
    method = 'live_price'
    p1, m1 = get_price_for_offset(1)
    p5, m5 = get_price_for_offset(5)
    p20, m20 = get_price_for_offset(20)
    p60, m60 = get_price_for_offset(60)

    try:
        cp = float(current_price) if current_price is not None else 0.0
    except Exception:
        cp = 0.0
    if cp > 0:
        current_price = cp
        if p1 is not None:
            r1d = round((p1 - current_price) / current_price * 100, 4)
        if p5 is not None:
            r5d = round((p5 - current_price) / current_price * 100, 4)
        if p20 is not None:
            r20d = round((p20 - current_price) / current_price * 100, 4)
        if p60 is not None:
            r60d = round((p60 - current_price) / current_price * 100, 4)

    methods = {m for m in (m1, m5, m20, m60) if m}
    if methods == {'history'}:
        method = 'history'
    elif 'history' in methods and 'live_price' in methods:
        method = 'history_live'
    elif live_price and not methods:
        method = 'live_price'
    return r1d, r5d, r20d, r60d, method


def insert_performance(cur, rows):
    for row in rows:
        cur.execute("""
            INSERT INTO signal_performance
            (signal_type, signal_source, ticker, action, signal_date, entry_price, current_price,
             return_1d, return_5d, return_20d, return_60d, return_since_signal, return_method, grade_bucket, snapshot_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT (signal_type, signal_source, ticker, signal_date, snapshot_date) DO UPDATE SET
                entry_price = EXCLUDED.entry_price,
                current_price = EXCLUDED.current_price,
                return_1d = EXCLUDED.return_1d,
                return_5d = EXCLUDED.return_5d,
                return_20d = EXCLUDED.return_20d,
                return_60d = EXCLUDED.return_60d,
                return_since_signal = EXCLUDED.return_since_signal,
                return_method = EXCLUDED.return_method,
                grade_bucket = EXCLUDED.grade_bucket,
                created_at = NOW()
        """, row)


def score_positions(cur):
    cur.execute("""
        SELECT ticker, avg_cost, live_price, updated_at::DATE
        FROM positions
        WHERE avg_cost IS NOT NULL AND live_price IS NOT NULL
    """)
    rows = []
    for ticker, avg_cost, live_price, sig_date in cur.fetchall():
        ret = round((live_price - avg_cost) / avg_cost * 100, 4) if avg_cost > 0 else None
        r1, r5, r20, r60, method = compute_forward_returns(cur, ticker, sig_date, avg_cost)
        rows.append(("position", "portfolio", ticker, "LONG", sig_date, avg_cost, live_price,
                     r1, r5, r20, r60, ret, method, None))
    insert_performance(cur, rows)


def score_trader_calls(cur):
    cur.execute("""
        SELECT DISTINCT ON (trader_name, ticker, call_date::DATE)
            trader_name, ticker, call_type, call_date::DATE, price_at_call
        FROM trader_calls
        WHERE price_at_call IS NOT NULL
        AND resolved = FALSE
        ORDER BY trader_name, ticker, call_date::DATE, call_date DESC
    """)
    rows = []
    for trader_name, ticker, call_type, sig_date, price_at_call in cur.fetchall():
        current = get_current_price(cur, ticker)
        ret = round((current - price_at_call) / price_at_call * 100, 4) if price_at_call > 0 and current else None
        r1, r5, r20, r60, method = compute_forward_returns(cur, ticker, sig_date, price_at_call)
        rows.append(("trader_call", trader_name, ticker, call_type, sig_date, price_at_call, current,
                     r1, r5, r20, r60, ret, method, None))
    insert_performance(cur, rows)

    # mark resolved if > 30 days old
    cur.execute("""
        UPDATE trader_calls
        SET resolved = TRUE,
            result = CASE WHEN sp.return_since_signal >= 0 THEN 'win' ELSE 'loss' END,
            return_pct = sp.return_since_signal
        FROM signal_performance sp
        WHERE trader_calls.ticker = sp.ticker
        AND trader_calls.trader_name = sp.signal_source
        AND trader_calls.call_date::DATE = sp.signal_date
        AND sp.signal_type = 'trader_call'
        AND sp.snapshot_date = CURRENT_DATE
        AND trader_calls.call_date <= NOW() - INTERVAL '30 days'
    """)


def score_council(cur):
    cur.execute("""
        SELECT ticker, final_action, timestamp::DATE
        FROM council_deliberations
        WHERE timestamp >= NOW() - INTERVAL '90 days'
    """)
    rows = []
    for ticker, action, sig_date in cur.fetchall():
        current = get_current_price(cur, ticker)
        r1, r5, r20, r60, method = compute_forward_returns(cur, ticker, sig_date, current)
        rows.append(("council", "vox-ai-council", ticker, action, sig_date, None, current,
                     r1, r5, r20, r60, None, method, None))
    insert_performance(cur, rows)


def score_grades(cur):
    cur.execute("""
        SELECT ticker, action, unified_grade, computed_at::DATE
        FROM unified_grades
        WHERE computed_at >= NOW() - INTERVAL '90 days'
    """)
    rows = []
    for ticker, action, grade, sig_date in cur.fetchall():
        current = get_current_price(cur, ticker)
        bucket = "80-100" if grade >= 80 else "60-79" if grade >= 60 else "40-59" if grade >= 40 else "0-39"
        r1, r5, r20, r60, method = compute_forward_returns(cur, ticker, sig_date, current)
        rows.append(("unified_grade", "vox-unified", ticker, action, sig_date, None, current,
                     r1, r5, r20, r60, None, method, bucket))
    insert_performance(cur, rows)


def aggregate_returns(cur):
    cur.execute("""
        SELECT
            signal_type,
            action,
            COUNT(*) AS n,
            ROUND(AVG(return_since_signal)::numeric, 2) AS avg_return,
            ROUND(SUM(CASE WHEN return_since_signal > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS win_rate
        FROM signal_performance
        WHERE snapshot_date = CURRENT_DATE
        AND return_since_signal IS NOT NULL
        GROUP BY signal_type, action
        ORDER BY avg_return DESC
    """)
    return cur.fetchall()


def write_obsidian(agg, top_winners, top_losers, grade_bucket_agg):
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OBSIDIAN_DIR / f"SignalQuality-{date_str}.md"

    lines = [
        f"# VOX Signal Quality — {date_str}",
        "",
        "## Aggregate by Signal Type + Action",
        "| Signal Type | Action | Count | Avg Return % | Win Rate % |",
        "|-------------|--------|-------|--------------|------------|",
    ]
    for r in agg:
        signal_type, action, n, avg_return, win_rate = r
        lines.append(f"| {signal_type} | {action or ''} | {n} | {avg_return or ''} | {win_rate or ''} |")

    lines.append("\n## Grade Bucket Performance")
    lines.append("| Grade Bucket | Count | Avg Return % |")
    lines.append("|--------------|-------|--------------|")
    for r in grade_bucket_agg:
        lines.append(f"| {r[0]} | {r[1]} | {r[2] or ''} |")

    lines.append("\n## Top 10 Winners (since signal)")
    lines.append("| Ticker | Signal | Source | Return % |")
    lines.append("|--------|--------|--------|----------|")
    for r in top_winners:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")

    lines.append("\n## Top 10 Losers (since signal)")
    lines.append("| Ticker | Signal | Source | Return % |")
    lines.append("|--------|--------|--------|----------|")
    for r in top_losers:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")

    path.write_text("\n".join(lines))
    return path


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        ensure_tables(cur)
        score_positions(cur)
        score_trader_calls(cur)
        score_council(cur)
        score_grades(cur)
        conn.commit()

        agg = aggregate_returns(cur)
        cur.execute("""
            SELECT ticker, signal_type, signal_source, return_since_signal
            FROM signal_performance
            WHERE snapshot_date = CURRENT_DATE
            AND return_since_signal IS NOT NULL
            ORDER BY return_since_signal DESC
            LIMIT 10
        """)
        top_winners = cur.fetchall()

        cur.execute("""
            SELECT ticker, signal_type, signal_source, return_since_signal
            FROM signal_performance
            WHERE snapshot_date = CURRENT_DATE
            AND return_since_signal IS NOT NULL
            ORDER BY return_since_signal ASC
            LIMIT 10
        """)
        top_losers = cur.fetchall()

        cur.execute("""
            SELECT grade_bucket, COUNT(*), ROUND(AVG(return_since_signal)::numeric, 2)
            FROM signal_performance
            WHERE snapshot_date = CURRENT_DATE
            AND grade_bucket IS NOT NULL
            AND return_since_signal IS NOT NULL
            GROUP BY grade_bucket
            ORDER BY grade_bucket
        """)
        grade_bucket_agg = cur.fetchall()

        path = write_obsidian(agg, top_winners, top_losers, grade_bucket_agg)
        print(f"Signal Quality Feedback: {len(agg)} aggregates")
        for r in agg:
            print(f"  {r[0]} / {r[1]}: n={r[2]}, avg={r[3]}%, win_rate={r[4]}%")
        print(f"Obsidian note: {path}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
