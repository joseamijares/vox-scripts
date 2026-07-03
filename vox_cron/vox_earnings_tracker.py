#!/usr/bin/env python3
"""
VOX Earnings & Catalyst Tracker v1.0
Tracks upcoming earnings, analyst upgrades, and key catalysts for portfolio + watchlist.
Stores in new table: earnings_calendar
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime, timedelta
import json

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from deepseek_review import deepseek_review

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

def create_earnings_table():
    """Create earnings calendar table if not exists."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            report_date DATE NOT NULL,
            report_time VARCHAR(10), -- 'BMO', 'AMC', 'TNS'
            eps_estimate NUMERIC(10,4),
            revenue_estimate NUMERIC(15,2),
            eps_actual NUMERIC(10,4),
            revenue_actual NUMERIC(15,2),
            surprise_pct NUMERIC(8,4),
            importance VARCHAR(20) DEFAULT 'medium', -- 'high', 'medium', 'low'
            status VARCHAR(20) DEFAULT 'upcoming', -- 'upcoming', 'reported', 'confirmed'
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, report_date)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ earnings_calendar table ready")

def get_portfolio_and_watchlist():
    """Get all tickers we care about."""
    conn = connect_db()
    cur = conn.cursor()
    
    tickers = set()
    
    # Portfolio positions
    cur.execute("SELECT DISTINCT ticker FROM positions WHERE shares > 0")
    for row in cur.fetchall():
        tickers.add(row[0])
    
    # Watchlist
    cur.execute("SELECT DISTINCT ticker FROM watchlist")
    for row in cur.fetchall():
        tickers.add(row[0])
    
    # High-graded stocks
    cur.execute("SELECT DISTINCT ticker FROM unified_grades WHERE unified_grade >= 70")
    for row in cur.fetchall():
        tickers.add(row[0])
    
    conn.close()
    return sorted(tickers)

def fetch_earnings_dates(tickers, days_ahead=45):
    """Fetch earnings dates from Yahoo Finance via yfinance."""
    print(f"\n[1/3] Fetching earnings for {len(tickers)} tickers from Yahoo Finance...")
    import yfinance as yf
    import time

    cutoff = datetime.now() + timedelta(days=days_ahead)
    results = []
    skipped = 0
    for ticker in tickers:
        if not ticker or not isinstance(ticker, str):
            skipped += 1
            continue
        t = ticker.strip().upper()
        if ' ' in t or '-' in t or '/' in t or len(t) > 8:
            skipped += 1
            continue
        try:
            tk = yf.Ticker(t)
            cal = tk.calendar
            if cal is None or (hasattr(cal, 'empty') and cal.empty) or (hasattr(cal, '__len__') and len(cal) == 0):
                continue
            # Normalize to a dict-like row
            if hasattr(cal, 'iloc'):
                row = cal.iloc[0]
                get = lambda k: row.get(k) if hasattr(row, 'get') else getattr(row, k, None)
            else:
                get = lambda k: cal.get(k)
            raw_date = get('Earnings Date') or get('Earnings Date Low') or get('earningsDate')
            if raw_date is None or raw_date == '' or (not isinstance(raw_date, (datetime, str)) and str(raw_date).lower() in ('nan', 'none', 'nat')):
                continue
            if isinstance(raw_date, str):
                try:
                    raw_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
                except Exception:
                    continue
            eps_est = get('EPS Estimate')
            rev_est = get('Revenue Estimate')
            if isinstance(eps_est, str):
                eps_est = eps_est.replace(',', '').replace('$', '')
            if isinstance(rev_est, str):
                rev_est = rev_est.replace(',', '').replace('$', '')
            try:
                eps_est = float(eps_est) if eps_est is not None and str(eps_est).lower() not in ('nan', 'none', 'nat') else None
            except Exception:
                eps_est = None
            try:
                rev_est = float(rev_est) if rev_est is not None and str(rev_est).lower() not in ('nan', 'none', 'nat') else None
            except Exception:
                rev_est = None
            try:
                d = raw_date.date()
            except Exception:
                continue
            if d <= cutoff.date() and d >= datetime.now().date():
                results.append({
                    'ticker': t,
                    'report_date': d.strftime('%Y-%m-%d'),
                    'report_time': 'TNS',
                    'eps_estimate': eps_est,
                    'revenue_estimate': rev_est,
                    'importance': 'medium',
                    'data_source': 'yfinance'
                })
            time.sleep(0.15)
        except Exception as e:
            skipped += 1
            continue
    print(f"  Found {len(results)} upcoming earnings ({skipped} skipped)")
    return results

def store_earnings(earnings):
    """Store earnings in database."""
    if not earnings:
        return 0
    
    conn = connect_db()
    cur = conn.cursor()
    
    stored = 0
    for e in earnings:
        cur.execute("""
            INSERT INTO earnings_calendar 
            (ticker, report_date, report_time, eps_estimate, revenue_estimate, importance, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'upcoming')
            ON CONFLICT (ticker, report_date) DO UPDATE SET
                eps_estimate = EXCLUDED.eps_estimate,
                revenue_estimate = EXCLUDED.revenue_estimate,
                importance = EXCLUDED.importance,
                updated_at = NOW()
        """, (e['ticker'], e['report_date'], e['report_time'], 
              e['eps_estimate'], e['revenue_estimate'], e['importance']))
        
        if cur.rowcount > 0:
            stored += 1
    
    conn.commit()
    conn.close()
    return stored

def generate_earnings_report():
    """Generate earnings report for next 30 days."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT ticker, report_date, report_time, eps_estimate, revenue_estimate, importance
        FROM earnings_calendar
        WHERE report_date BETWEEN NOW() AND NOW() + INTERVAL '30 days'
        ORDER BY report_date ASC
    """)
    
    upcoming = cur.fetchall()
    
    print(f"\n{'='*60}")
    print(f"EARNINGS CALENDAR — Next 30 Days")
    print(f"{'='*60}")
    print(f"{'Ticker':<10} {'Date':<12} {'Time':<6} {'EPS Est':<10} {'Rev Est ($M)':<15} {'Importance'}")
    print(f"{'-'*60}")
    
    for row in upcoming:
        ticker, date, time, eps, rev, importance = row
        rev_m = rev / 1000 if rev else 0
        print(f"{ticker:<10} {str(date):<12} {time or 'TNS':<6} {eps or 'N/A':<10} {rev_m:,.1f}M{'':<8} {'🔴' if importance == 'high' else '🟡'} {importance}")
    
    print(f"{'='*60}")
    print(f"Total: {len(upcoming)} earnings events")
    
    # DeepSeek second-layer review: flag high-impact events near report date
    candidates = [{'ticker': row[0], 'report_date': str(row[1]), 'time': row[2], 'eps': float(row[3] or 0), 'revenue': float(row[4] or 0), 'importance': row[5]} for row in upcoming if row[5] == 'high']
    approved = deepseek_review(candidates, "Earnings tracker high-importance upcoming events (next 30 days)")
    approved_tickers = {a['ticker'] for a in approved}
    if approved:
        print(f"\n🔴 DeepSeek-approved high-impact earnings: {', '.join(sorted(approved_tickers)[:10])}")
    
    conn.close()
    return [u for u in upcoming if u[0] in approved_tickers]

def run_earnings_tracker():
    """Main entry point."""
    print("=" * 60)
    print(f"VOX EARNINGS & CATALYST TRACKER — {datetime.now()}")
    print("=" * 60)
    
    # Setup
    create_earnings_table()
    
    # Get tickers
    tickers = get_portfolio_and_watchlist()
    print(f"\nTracking {len(tickers)} tickers (portfolio + watchlist + high-grade)")
    
    # Fetch and store
    earnings = fetch_earnings_dates(tickers)
    stored = store_earnings(earnings)
    print(f"Stored/updated {stored} earnings records")
    
    # Generate report
    upcoming = generate_earnings_report()
    
    return upcoming

if __name__ == '__main__':
    run_earnings_tracker()
