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
from datetime import datetime

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
            signal_count INT DEFAULT 1,
            win_rate NUMERIC(6,2),
            avg_return NUMERIC(10,4),
            grade_bucket TEXT,
            snapshot_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(signal_type, signal_source, ticker, signal_date, snapshot_date)
        );
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


def insert_performance(cur, rows):
    for row in rows:
        cur.execute("""
            INSERT INTO signal_performance
            (signal_type, signal_source, ticker, action, signal_date, entry_price, current_price,
             return_since_signal, grade_bucket, snapshot_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT (signal_type, signal_source, ticker, signal_date, snapshot_date) DO UPDATE SET
                entry_price = EXCLUDED.entry_price,
                current_price = EXCLUDED.current_price,
                return_since_signal = EXCLUDED.return_since_signal,
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
        rows.append(("position", "portfolio", ticker, "LONG", sig_date, avg_cost, live_price, ret, None))
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
        rows.append(("trader_call", trader_name, ticker, call_type, sig_date, price_at_call, current, ret, None))
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
        rows.append(("council", "vox-ai-council", ticker, action, sig_date, None, current, None, None))
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
        rows.append(("unified_grade", "vox-unified", ticker, action, sig_date, None, current, None, bucket))
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
