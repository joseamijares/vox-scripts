#!/usr/bin/env python3
"""
VOX Market Monitor
Monitors market open and provides updated recommendations based on vox_grades.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
import os
import sys
from datetime import datetime

DB_HOST = os.environ.get('PGHOST', 'acela.proxy.rlwy.net')
DB_PORT = os.environ.get('PGPORT', '35577')
DB_USER = os.environ.get('PGUSER', 'postgres')
DB_PASS = os.environ.get('PGPASSWORD', '')
DB_NAME = os.environ.get('PGDATABASE', 'railway')

def monitor_market():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASS, dbname=DB_NAME, sslmode='require'
    )
    cur = conn.cursor()
    
    # Get top 10 actionable plays
    cur.execute('''
        SELECT ticker, vox_grade, action, current_price, technical_score, fundamental_score, macro_score
        FROM vox_grades
        WHERE generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = vox_grades.ticker)
        ORDER BY vox_grade DESC
        LIMIT 10
    ''')
    top10 = cur.fetchall()
    
    # Get market summary
    cur.execute('''
        SELECT 
            COUNT(*) FILTER (WHERE action IN ('BUY', 'STRONG_BUY')) as buys,
            COUNT(*) FILTER (WHERE action = 'HOLD') as holds,
            COUNT(*) FILTER (WHERE action IN ('SELL', 'TRIM')) as sells,
            MAX(vox_grade) as highest_grade,
            MIN(vox_grade) as lowest_grade,
            AVG(vox_grade)::int as avg_grade
        FROM vox_grades
        WHERE generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = vox_grades.ticker)
    ''')
    summary = cur.fetchone()
    
    conn.close()
    
    # Build report
    lines = []
    lines.append("=" * 60)
    lines.append("VOX MARKET MONITOR")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    
    lines.append(f"\n📊 MARKET SUMMARY:")
    lines.append(f"  BUY/STRONG_BUY: {summary[0]}")
    lines.append(f"  HOLD: {summary[1]}")
    lines.append(f"  SELL/TRIM: {summary[2]}")
    lines.append(f"  Highest grade: {summary[3]}")
    lines.append(f"  Lowest grade: {summary[4]}")
    lines.append(f"  Average grade: {summary[5]}")
    
    lines.append(f"\n🏆 TOP 10 PLAYS:")
    lines.append(f"{'Rank':<6} {'Ticker':<8} {'Grade':<6} {'Action':<10} {'Price':<10} {'Tech':<5} {'Fund':<5} {'Macro':<5}")
    lines.append("-" * 60)
    for i, row in enumerate(top10, 1):
        t, g, a, price, tech, fund, macro = row
        price_str = f"${price}" if price else "N/A"
        lines.append(f"{i:<6} {t:<8} {g:<6} {a:<10} {price_str:<10} {tech or 0:<5} {fund or 0:<5} {macro or 0:<5}")
    
    lines.append("\n" + "=" * 60)
    
    msg = "\n".join(lines)
    print(msg)
    return msg

if __name__ == '__main__':
    monitor_market()
