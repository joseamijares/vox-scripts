#!/usr/bin/env python3
"""
VOX Grade Improvement Alert
Monitors vox_grades for tickers that improve to 75+ or cross key thresholds.
Sends alert when actionable opportunities emerge.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
import os
import sys

DB_HOST = os.environ.get('PGHOST', 'acela.proxy.rlwy.net')
DB_PORT = os.environ.get('PGPORT', '35577')
DB_USER = os.environ.get('PGUSER', 'postgres')
DB_PASS = os.environ.get('PGPASSWORD', '')
DB_NAME = os.environ.get('PGDATABASE', 'railway')

def check_grade_improvements():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASS, dbname=DB_NAME, sslmode='require'
    )
    cur = conn.cursor()
    
    # Find tickers that crossed 75+ today (improved from below 75)
    cur.execute('''
        SELECT v.ticker, v.vox_grade, v.action, v.previous_grade, v.current_price
        FROM vox_grades v
        WHERE v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
          AND v.vox_grade >= 75
          AND v.previous_grade < 75
        ORDER BY v.vox_grade DESC
    ''')
    improved = cur.fetchall()
    
    # Find tickers that changed to BUY/STRONG_BUY today
    cur.execute('''
        SELECT v.ticker, v.vox_grade, v.action, v.previous_grade
        FROM vox_grades v
        WHERE v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
          AND v.action IN ('BUY', 'STRONG_BUY')
          AND v.vox_grade >= 65
        ORDER BY v.vox_grade DESC
    ''')
    buy_signals = cur.fetchall()
    
    # Find highest grade overall
    cur.execute('''
        SELECT ticker, vox_grade, action, current_price
        FROM vox_grades
        WHERE generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = vox_grades.ticker)
        ORDER BY vox_grade DESC
        LIMIT 1
    ''')
    highest = cur.fetchone()
    
    conn.close()
    
    # Build alert message
    lines = []
    lines.append("=" * 60)
    lines.append("VOX GRADE IMPROVEMENT ALERT")
    lines.append(f"Date: {os.popen('date').read().strip()}")
    lines.append("=" * 60)
    
    if improved:
        lines.append(f"\n🚀 TICKERS THAT IMPROVED TO 75+:")
        for row in improved:
            t, g, a, prev, price = row
            lines.append(f"  {t}: {prev} → {g} ({a}) @ ${price or 'N/A'}")
    
    if buy_signals:
        lines.append(f"\n✅ NEW BUY/STRONG_BUY SIGNALS:")
        for row in buy_signals:
            t, g, a, prev = row
            lines.append(f"  {t}: {g} ({a}) — was {prev}")
    
    if highest:
        t, g, a, price = highest
        lines.append(f"\n📊 HIGHEST GRADE: {t} = {g} ({a}) @ ${price or 'N/A'}")
    
    if not improved and not buy_signals:
        lines.append("\n⏳ No grade improvements today.")
        lines.append(f"Highest grade: {highest[0]} = {highest[1]} ({highest[2]})")
    
    lines.append("\n" + "=" * 60)
    
    msg = "\n".join(lines)
    print(msg)
    return msg

if __name__ == '__main__':
    check_grade_improvements()
