#!/usr/bin/env python3
"""
VOX Earnings Tracker v2.0
Replaces sparse v1 with real Yahoo Finance earnings data + analyst sentiment.
Tracks upcoming earnings for positions, watchlist, discovery_queue, and high-graded stocks.
Stores in earnings_calendar, earnings_surprises, and earnings_analyst_sentiment.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime, timedelta
import time
import yfinance as yf

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'


def get_db_password():
    return os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))


def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password()
    )


def ensure_tables():
    """Apply idempotent migration."""
    sql_path = Path(__file__).parent.parent / 'migrations' / '003_earnings_enrichment.sql'
    if sql_path.exists():
        with open(sql_path) as f:
            sql = f.read()
        conn = connect_db()
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        conn.close()
        print("✅ earnings migration applied")
    else:
        print("⚠️ migration file not found, continuing anyway")


def get_tickers():
    """Get tickers from positions, watchlist, discovery_queue, and high-graded unified_grades."""
    conn = connect_db()
    cur = conn.cursor()
    tickers = set()

    cur.execute("SELECT DISTINCT ticker FROM positions WHERE ticker IS NOT NULL AND shares > 0")
    for row in cur.fetchall():
        tickers.add(row[0])

    cur.execute("SELECT DISTINCT ticker FROM watchlist WHERE ticker IS NOT NULL")
    for row in cur.fetchall():
        tickers.add(row[0])

    cur.execute("SELECT DISTINCT ticker FROM discovery_queue WHERE ticker IS NOT NULL AND status IN ('pending', 'active', 'new')")
    for row in cur.fetchall():
        tickers.add(row[0])

    cur.execute("SELECT DISTINCT ticker FROM unified_grades WHERE ticker IS NOT NULL AND unified_grade >= 60")
    for row in cur.fetchall():
        tickers.add(row[0])

    conn.close()
    return sorted(t for t in tickers if t and isinstance(t, str) and len(t) <= 8 and ' ' not in t and '-' not in t and '/' not in t)


def get_grades(tickers):
    """Map latest unified_grade for importance scoring."""
    if not tickers:
        return {}
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (ticker) ticker, unified_grade
        FROM unified_grades
        ORDER BY ticker, computed_at DESC
    """)
    grades = {row[0]: float(row[1]) if row[1] is not None else 0 for row in cur.fetchall()}
    conn.close()
    return grades


def get_positions():
    """Set of held tickers."""
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker FROM positions WHERE shares > 0 AND ticker IS NOT NULL")
    held = {row[0] for row in cur.fetchall()}
    conn.close()
    return held


def normalize_value(val):
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ('nan', 'none', 'nat', ''):
        return None
    try:
        return float(s.replace(',', '').replace('$', ''))
    except Exception:
        return None


def parse_date(raw):
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
        except Exception:
            pass
        try:
            return datetime.strptime(raw.split(' ')[0], '%Y-%m-%d').date()
        except Exception:
            return None
    return None


def fetch_earnings(tickers, days_ahead=45, sleep=0.2):
    """Fetch earnings calendar from Yahoo Finance per ticker."""
    held = get_positions()
    grades = get_grades(tickers)
    cutoff = (datetime.now() + timedelta(days=days_ahead)).date()
    today = datetime.now().date()
    results = []
    skipped = 0

    for ticker in tickers:
        try:
            tk = yf.Ticker(ticker)
            cal = tk.calendar
            if cal is None or getattr(cal, 'empty', False) or len(cal) == 0:
                skipped += 1
                time.sleep(sleep)
                continue

            row = cal.iloc[0] if hasattr(cal, 'iloc') else cal
            get = lambda k: row.get(k) if hasattr(row, 'get') else getattr(row, k, None)
            d = parse_date(get('Earnings Date') or get('Earnings Date Low') or get('earningsDate'))
            if d is None or d < today or d > cutoff:
                time.sleep(sleep)
                continue

            eps_est = normalize_value(get('EPS Estimate'))
            rev_est = normalize_value(get('Revenue Estimate'))
            eps_actual = normalize_value(get('EPS Actual'))
            rev_actual = normalize_value(get('Revenue Actual'))
            surprise = normalize_value(get('Surprise(%)')) or normalize_value(get('Surprise %'))

            grade = grades.get(ticker, 0)
            in_pos = ticker in held
            if in_pos or grade >= 75:
                importance = 'high'
                score = 3
            elif grade >= 60 or any(True for _ in []):
                importance = 'medium'
                score = 2
            else:
                importance = 'low'
                score = 1

            # Report time: infer from reportTime if present, else TNS
            report_time = 'TNS'
            try:
                rt = get('Report Time') or get('reportTime')
                if rt:
                    rt_str = str(rt).lower()
                    if 'am' in rt_str or 'before' in rt_str:
                        report_time = 'BMO'
                    elif 'pm' in rt_str or 'after' in rt_str:
                        report_time = 'AMC'
            except Exception:
                pass

            results.append({
                'ticker': ticker,
                'report_date': d,
                'report_time': report_time,
                'eps_estimate': eps_est,
                'revenue_estimate': rev_est,
                'eps_actual': eps_actual,
                'revenue_actual': rev_actual,
                'surprise_pct': surprise,
                'importance': importance,
                'importance_score': score,
                'data_source': 'yfinance',
                'status': 'reported' if (eps_actual is not None or rev_actual is not None) else 'upcoming',
            })
        except Exception as e:
            skipped += 1
        time.sleep(sleep)

    print(f"Found {len(results)} upcoming earnings events ({skipped} skipped/no data)")
    return results


def fetch_analyst_sentiment(ticker, report_date):
    """Fetch analyst recommendations around earnings if available."""
    try:
        tk = yf.Ticker(ticker)
        rec = tk.recommendations
        if rec is None or getattr(rec, 'empty', True):
            return None
        # nearest row to report_date (yfinance returns a DataFrame with index as dates)
        nearest = rec.iloc[rec.index.get_indexer([report_date], method='nearest')[0]]
        strong_buy = int(nearest.get('strongBuy', 0) or 0)
        buy = int(nearest.get('buy', 0) or 0)
        hold = int(nearest.get('hold', 0) or 0)
        sell = int(nearest.get('sell', 0) or 0)
        strong_sell = int(nearest.get('strongSell', 0) or 0)
        total = strong_buy + buy + hold + sell + strong_sell
        mean = None
        if total > 0:
            mean = round((strong_buy*5 + buy*4 + hold*3 + sell*2 + strong_sell*1) / total, 2)
        return {
            'strong_buy': strong_buy,
            'buy': buy,
            'hold': hold,
            'sell': sell,
            'strong_sell': strong_sell,
            'mean_rating': mean,
        }
    except Exception:
        return None


def store_earnings(earnings):
    if not earnings:
        return 0
    conn = connect_db()
    cur = conn.cursor()
    stored = 0
    for e in earnings:
        cur.execute("""
            INSERT INTO earnings_calendar
            (ticker, report_date, report_time, eps_estimate, revenue_estimate,
             eps_actual, revenue_actual, surprise_pct, importance, importance_score,
             data_source, status, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (ticker, report_date) DO UPDATE SET
                report_time = EXCLUDED.report_time,
                eps_estimate = EXCLUDED.eps_estimate,
                revenue_estimate = EXCLUDED.revenue_estimate,
                eps_actual = EXCLUDED.eps_actual,
                revenue_actual = EXCLUDED.revenue_actual,
                surprise_pct = EXCLUDED.surprise_pct,
                importance = EXCLUDED.importance,
                importance_score = EXCLUDED.importance_score,
                data_source = EXCLUDED.data_source,
                status = EXCLUDED.status,
                updated_at = NOW()
        """, (
            e['ticker'], e['report_date'], e['report_time'], e['eps_estimate'], e['revenue_estimate'],
            e['eps_actual'], e['revenue_actual'], e['surprise_pct'], e['importance'], e['importance_score'],
            e['data_source'], e['status']
        ))
        if cur.rowcount > 0:
            stored += 1

        if e['eps_actual'] is not None or e['surprise_pct'] is not None:
            cur.execute("""
                INSERT INTO earnings_surprises
                (ticker, report_date, eps_estimate, eps_actual, surprise_pct, revenue_estimate, revenue_actual)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, report_date) DO UPDATE SET
                    eps_estimate = EXCLUDED.eps_estimate,
                    eps_actual = EXCLUDED.eps_actual,
                    surprise_pct = EXCLUDED.surprise_pct,
                    revenue_estimate = EXCLUDED.revenue_estimate,
                    revenue_actual = EXCLUDED.revenue_actual,
                    created_at = NOW()
            """, (e['ticker'], e['report_date'], e['eps_estimate'], e['eps_actual'], e['surprise_pct'], e['revenue_estimate'], e['revenue_actual']))

        sentiment = fetch_analyst_sentiment(e['ticker'], e['report_date'])
        if sentiment:
            cur.execute("""
                INSERT INTO earnings_analyst_sentiment
                (ticker, report_date, strong_buy, buy, hold, sell, strong_sell, mean_rating, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker, report_date) DO UPDATE SET
                    strong_buy = EXCLUDED.strong_buy,
                    buy = EXCLUDED.buy,
                    hold = EXCLUDED.hold,
                    sell = EXCLUDED.sell,
                    strong_sell = EXCLUDED.strong_sell,
                    mean_rating = EXCLUDED.mean_rating,
                    updated_at = NOW()
            """, (e['ticker'], e['report_date'], sentiment['strong_buy'], sentiment['buy'], sentiment['hold'], sentiment['sell'], sentiment['strong_sell'], sentiment['mean_rating']))

    conn.commit()
    conn.close()
    return stored


def generate_obsidian_note():
    """Write summary of upcoming earnings to Obsidian."""
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, report_date, report_time, eps_estimate, revenue_estimate, importance, status
        FROM earnings_calendar
        WHERE report_date BETWEEN NOW() AND NOW() + INTERVAL '30 days'
        ORDER BY report_date ASC, importance_score DESC
    """)
    rows = cur.fetchall()
    conn.close()

    date_str = datetime.now().strftime('%Y-%m-%d')
    out_dir = Path.home() / 'Documents' / 'Obsidian' / 'VOX' / 'Earnings'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'Earnings-{date_str}.md'

    lines = [
        f"# VOX Earnings Tracker — {date_str}",
        "",
        f"**Upcoming earnings (next 30 days):** {len(rows)}",
        "",
        "| Ticker | Date | Time | EPS Est | Rev Est | Importance | Status |",
        "|--------|------|------|---------|---------|------------|--------|",
    ]
    for r in rows:
        ticker, rd, rt, eps, rev, importance, status = r
        eps_s = f"${eps:.2f}" if eps is not None else 'N/A'
        rev_s = f"${rev/1000:,.1f}M" if rev is not None else 'N/A'
        lines.append(f"| {ticker} | {rd} | {rt or 'TNS'} | {eps_s} | {rev_s} | {importance} | {status} |")

    lines.append("")
    lines.append("## High-Impact Events")
    high = [r for r in rows if r[5] == 'high']
    if high:
        for r in high:
            lines.append(f"- **{r[0]}** reports {r[2] or 'TNS'} on {r[1]} (EPS est ${r[3] if r[3] is not None else 'N/A'})")
    else:
        lines.append("_No high-importance earnings in the next 30 days._")

    path.write_text('\n'.join(lines))
    print(f"📝 Obsidian note: {path}")
    return path


def run():
    print("=" * 60)
    print(f"VOX EARNINGS TRACKER v2 — {datetime.now()}")
    print("=" * 60)
    ensure_tables()
    tickers = get_tickers()
    print(f"\nTracking {len(tickers)} tickers")
    earnings = fetch_earnings(tickers)
    stored = store_earnings(earnings)
    print(f"Stored/updated {stored} earnings records")
    generate_obsidian_note()
    return stored


if __name__ == '__main__':
    run()
