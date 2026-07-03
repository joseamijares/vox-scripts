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

def fetch_earnings_dates(tickers):
    """Fetch earnings dates for tickers (mock implementation - would use API in production)."""
    print(f"\n[1/3] Fetching earnings for {len(tickers)} tickers...")
    
    # Known upcoming earnings (Q2 2026)
    known_earnings = {
        'NVO': {'date': '2026-08-06', 'time': 'BMO', 'eps_est': 2.85, 'rev_est': 75000},
        'APP': {'date': '2026-08-07', 'time': 'AMC', 'eps_est': 0.45, 'rev_est': 1200},
        'CRDO': {'date': '2026-09-03', 'time': 'AMC', 'eps_est': 0.12, 'rev_est': 180},
        'IONQ': {'date': '2026-08-13', 'time': 'AMC', 'eps_est': -0.18, 'rev_est': 15},
        'DUOL': {'date': '2026-08-06', 'time': 'AMC', 'eps_est': 0.52, 'rev_est': 210},
        'SE': {'date': '2026-08-12', 'time': 'AMC', 'eps_est': 0.38, 'rev_est': 4800},
        'OKLO': {'date': '2026-08-14', 'time': 'AMC', 'eps_est': -0.15, 'rev_est': 8},
        'TSM': {'date': '2026-07-16', 'time': 'BMO', 'eps_est': 1.85, 'rev_est': 22000},
        'AMD': {'date': '2026-07-29', 'time': 'AMC', 'eps_est': 0.72, 'rev_est': 6800},
        'META': {'date': '2026-07-30', 'time': 'AMC', 'eps_est': 5.85, 'rev_est': 42000},
        'GOOGL': {'date': '2026-07-22', 'time': 'AMC', 'eps_est': 1.95, 'rev_est': 88000},
        'AAPL': {'date': '2026-07-30', 'time': 'AMC', 'eps_est': 1.35, 'rev_est': 95000},
        'MSFT': {'date': '2026-07-29', 'time': 'AMC', 'eps_est': 3.15, 'rev_est': 68000},
        'AMZN': {'date': '2026-07-31', 'time': 'AMC', 'eps_est': 1.25, 'rev_est': 155000},
        'NVDA': {'date': '2026-08-27', 'time': 'AMC', 'eps_est': 0.68, 'rev_est': 30000},
    }
    
    results = []
    for ticker in tickers:
        if ticker in known_earnings:
            e = known_earnings[ticker]
            results.append({
                'ticker': ticker,
                'report_date': e['date'],
                'report_time': e['time'],
                'eps_estimate': e['eps_est'],
                'revenue_estimate': e['rev_est'],
                'importance': 'high' if e['rev_est'] > 10000 else 'medium'
            })
    
    print(f"  Found {len(results)} upcoming earnings")
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
