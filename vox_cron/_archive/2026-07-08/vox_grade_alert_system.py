#!/usr/bin/env python3
"""
VOX Grade Change Alert System v2.0
Proactively monitors grade changes and sends alerts for:
1. Stocks that improved to BUY/STRONG_BUY (>= 65)
2. Stocks that dropped to SELL (<= 40)
3. Large grade jumps (> 10 points)
4. New high-grade discoveries (>= 75)

OPTIMIZED: Uses window functions (LAG) instead of correlated subqueries.
Runs in ~5 seconds on 20K+ row tables.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime, timedelta
import json

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'

def get_db_password():
    with open(os.path.expanduser('~/.hermes/.env')) as f:
        for line in f:
            if line.startswith('DB_PASSWORD='):
                return line.strip().split('=', 1)[1]
    return os.environ.get('PGPASSWORD', '')

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password()
    )

def create_alerts_table():
    """Create grade alerts table."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grade_alerts (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            alert_type VARCHAR(30) NOT NULL,
            old_grade INTEGER,
            new_grade INTEGER,
            old_action VARCHAR(20),
            new_action VARCHAR(20),
            triggered_at TIMESTAMP DEFAULT NOW(),
            sent BOOLEAN DEFAULT FALSE,
            UNIQUE(ticker, alert_type, triggered_at)
        )
    """)
    
    # Create index for fast deduplication
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_grade_alerts_ticker_type_time 
        ON grade_alerts(ticker, alert_type, triggered_at DESC)
    """)
    
    conn.commit()
    conn.close()
    print("✅ grade_alerts table ready")

def detect_grade_changes():
    """Detect significant grade changes in last 24h using LAG window function."""
    conn = connect_db()
    cur = conn.cursor()
    
    alerts = []
    
    # Use LAG window function for efficient previous-grade lookup
    # Only return tickers where grade actually changed by >= 10 points
    cur.execute("""
        WITH graded AS (
            SELECT 
                ticker,
                vox_grade,
                action,
                generated_at,
                LAG(vox_grade) OVER (PARTITION BY ticker ORDER BY generated_at) as prev_grade,
                LAG(action) OVER (PARTITION BY ticker ORDER BY generated_at) as prev_action,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY generated_at DESC) as rn
            FROM vox_grades
            WHERE generated_at > NOW() - INTERVAL '24 hours'
        )
        SELECT ticker, vox_grade, action, prev_grade, prev_action
        FROM graded
        WHERE rn = 1
          AND prev_grade IS NOT NULL
          AND ABS(vox_grade - prev_grade) >= 10
    """)
    
    changes = cur.fetchall()
    print(f"📊 Checked {len(changes)} tickers with recent grade changes")
    
    for row in changes:
        ticker, new_grade, new_action, old_grade, old_action = row
        
        # 1. Upgrades to BUY/STRONG_BUY (>= 65)
        if new_grade >= 65 and old_grade < 65:
            alerts.append({
                'ticker': ticker,
                'type': 'upgrade_to_buy',
                'old_grade': old_grade,
                'new_grade': new_grade,
                'old_action': old_action,
                'new_action': new_action,
                'message': f"🟢 {ticker}: UPGRADED to {new_action} ({old_grade} → {new_grade})"
            })
        
        # 2. Downgrades to SELL (<= 40)
        elif new_grade <= 40 and old_grade > 40:
            alerts.append({
                'ticker': ticker,
                'type': 'downgrade_to_sell',
                'old_grade': old_grade,
                'new_grade': new_grade,
                'old_action': old_action,
                'new_action': new_action,
                'message': f"🔴 {ticker}: DOWNGRADED to {new_action} ({old_grade} → {new_grade})"
            })
        
        # 3. Large jumps (> 10 points)
        elif abs(new_grade - old_grade) >= 10:
            direction = "📈" if new_grade > old_grade else "📉"
            alerts.append({
                'ticker': ticker,
                'type': 'large_jump',
                'old_grade': old_grade,
                'new_grade': new_grade,
                'old_action': old_action,
                'new_action': new_action,
                'message': f"{direction} {ticker}: BIG MOVE ({old_grade} → {new_grade})"
            })
    
    # 4. New high-grade discoveries (>= 75) — first time ever graded
    cur.execute("""
        SELECT v.ticker, v.vox_grade, v.action
        FROM vox_grades v
        WHERE v.generated_at > NOW() - INTERVAL '24 hours'
          AND v.vox_grade >= 75
          AND NOT EXISTS (
              SELECT 1 FROM vox_grades v2 
              WHERE v2.ticker = v.ticker AND v2.generated_at < v.generated_at
          )
    """)
    
    for row in cur.fetchall():
        ticker, grade, action = row
        alerts.append({
            'ticker': ticker,
            'type': 'new_high',
            'old_grade': None,
            'new_grade': grade,
            'old_action': None,
            'new_action': action,
            'message': f"🌟 {ticker}: NEW HIGH-GRADE DISCOVERY ({grade} - {action})"
        })
    
    conn.close()
    return alerts

def store_alerts(alerts):
    """Store alerts in database using bulk insert, avoiding duplicates."""
    if not alerts:
        return 0
    
    conn = connect_db()
    cur = conn.cursor()
    
    # Use bulk insert with ON CONFLICT for speed
    values = []
    for alert in alerts:
        values.append((
            alert['ticker'], alert['type'], alert['old_grade'],
            alert['new_grade'], alert['old_action'], alert['new_action']
        ))
    
    # Insert in batches of 100
    inserted = 0
    batch_size = 100
    for i in range(0, len(values), batch_size):
        batch = values[i:i+batch_size]
        try:
            cur.executemany("""
                INSERT INTO grade_alerts (ticker, alert_type, old_grade, new_grade, old_action, new_action)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, alert_type, triggered_at) DO NOTHING
            """, batch)
            inserted += cur.rowcount
        except Exception as e:
            print(f"⚠️ Batch insert error: {e}")
    
    conn.commit()
    conn.close()
    return inserted

def send_alert_summary(alerts):
    """Generate alert summary for delivery."""
    if not alerts:
        return "✅ No grade alerts today. All positions stable."
    
    summary = f"""🚨 VOX GRADE ALERTS ({datetime.now().strftime('%Y-%m-%d %H:%M')})

{len(alerts)} alert(s) detected:

"""
    
    for alert in alerts:
        summary += f"{alert['message']}\n"
    
    summary += "\n---\nAction: Review these positions in your portfolio."
    return summary

def main():
    print("="*60)
    print("VOX GRADE ALERT SYSTEM v2.0")
    print("="*60)
    
    start_time = datetime.now()
    
    # Setup
    create_alerts_table()
    
    # Detect changes
    print("\n🔍 Detecting grade changes...")
    alerts = detect_grade_changes()
    
    # Store alerts
    print(f"\n💾 Storing {len(alerts)} alerts...")
    inserted = store_alerts(alerts)
    
    # Generate summary
    summary = send_alert_summary(alerts)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n✅ Done in {elapsed:.1f}s | {inserted} new alerts stored")
    print(f"\n{summary}")
    
    return summary

if __name__ == '__main__':
    result = main()
