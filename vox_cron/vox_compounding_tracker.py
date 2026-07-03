#!/usr/bin/env python3
"""
VOX Compounding Tracker v1.0
Tracks portfolio AUM, returns, and benchmarks over time.
Stores snapshots in portfolio_snapshots table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime, timedelta
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))
    )

def create_snapshot_table():
    """Create portfolio snapshots table."""
    conn = connect_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_date DATE NOT NULL UNIQUE,
            total_aum NUMERIC(15,2),
            total_positions INTEGER,
            total_brokers INTEGER,
            day_return_pct NUMERIC(8,4),
            week_return_pct NUMERIC(8,4),
            month_return_pct NUMERIC(8,4),
            ytd_return_pct NUMERIC(8,4),
            sp500_benchmark NUMERIC(8,4),
            nasdaq_benchmark NUMERIC(8,4),
            top_performer VARCHAR(20),
            top_performer_return NUMERIC(8,4),
            worst_performer VARCHAR(20),
            worst_performer_return NUMERIC(8,4),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ portfolio_snapshots table ready")

def calculate_portfolio_metrics():
    """Calculate current portfolio metrics."""
    conn = connect_db()
    cur = conn.cursor()
    
    # Total AUM (sum of live_value_usd)
    cur.execute("""
    SELECT 
        COALESCE(SUM(live_value_usd), 0), COUNT(DISTINCT ticker), COUNT(DISTINCT broker)
    FROM (
        SELECT ticker, live_value_usd, UNNEST(brokers) as broker
        FROM positions
    ) sub
    """)
    
    total_aum, total_positions, total_brokers = cur.fetchone()
    
    # Calculate returns (would need historical data in production)
    # For now, use placeholder
    day_return = 0.0
    week_return = 0.0
    month_return = 0.0
    ytd_return = 0.0
    
    # Top/worst performers
    cur.execute("""
    SELECT ticker, live_value_usd, avg_cost, shares
    FROM positions
    WHERE shares > 0 AND live_value_usd IS NOT NULL
    ORDER BY live_value_usd DESC
    LIMIT 5
    """)
    
    positions = cur.fetchall()
    
    top_performer = None
    top_return = 0
    worst_performer = None
    worst_return = 0
    
    for pos in positions:
        ticker, live_value, avg_cost, shares = pos
        if avg_cost and shares and avg_cost > 0:
            current_price = live_value / shares if shares > 0 else 0
            return_pct = ((current_price - avg_cost) / avg_cost) * 100
            # Cap extreme outliers to avoid numeric overflow
            return_pct = max(-1000.0, min(1000.0, return_pct))

            if return_pct > top_return:
                top_return = return_pct
                top_performer = ticker
            if return_pct < worst_return:
                worst_return = return_pct
                worst_performer = ticker

    conn.close()

    return {
        'total_aum': float(total_aum) if total_aum else 0,
        'total_positions': total_positions or 0,
        'total_brokers': total_brokers or 0,
        'day_return': day_return,
        'week_return': week_return,
        'month_return': month_return,
        'ytd_return': ytd_return,
        'top_performer': top_performer,
        'top_return': top_return,
        'worst_performer': worst_performer,
        'worst_return': worst_return
    }

def store_snapshot(metrics):
    """Store daily snapshot."""
    conn = connect_db()
    cur = conn.cursor()
    
    today = datetime.now().date()
    
    cur.execute("""
        INSERT INTO portfolio_snapshots 
        (snapshot_date, total_aum, total_positions, total_brokers,
         day_return_pct, week_return_pct, month_return_pct, ytd_return_pct,
         top_performer, top_performer_return, worst_performer, worst_performer_return)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (snapshot_date) DO UPDATE SET
            total_aum = EXCLUDED.total_aum,
            total_positions = EXCLUDED.total_positions,
            total_brokers = EXCLUDED.total_brokers,
            day_return_pct = EXCLUDED.day_return_pct,
            week_return_pct = EXCLUDED.week_return_pct,
            month_return_pct = EXCLUDED.month_return_pct,
            ytd_return_pct = EXCLUDED.ytd_return_pct,
            top_performer = EXCLUDED.top_performer,
            top_performer_return = EXCLUDED.top_performer_return,
            worst_performer = EXCLUDED.worst_performer,
            worst_performer_return = EXCLUDED.worst_performer_return,
            created_at = NOW()
    """, (today, metrics['total_aum'], metrics['total_positions'], metrics['total_brokers'],
          metrics['day_return'], metrics['week_return'], metrics['month_return'], metrics['ytd_return'],
          metrics['top_performer'], metrics['top_return'], metrics['worst_performer'], metrics['worst_return']))
    
    conn.commit()
    conn.close()
    print(f"✅ Snapshot stored for {today}")

def generate_compounding_report():
    """Generate compounding report."""
    conn = connect_db()
    cur = conn.cursor()
    
    # Get last 30 days of snapshots
    cur.execute("""
        SELECT snapshot_date, total_aum, day_return_pct, week_return_pct, month_return_pct
        FROM portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 30
    """)
    
    snapshots = cur.fetchall()
    
    print(f"\n{'='*60}")
    print(f"PORTFOLIO COMPOUNDING REPORT")
    print(f"{'='*60}")
    
    if snapshots:
        latest = snapshots[0]
        print(f"\nCurrent AUM: ${latest[1]:,.2f}")
        print(f"Day Return: {latest[2]:.2f}%")
        print(f"Week Return: {latest[3]:.2f}%")
        print(f"Month Return: {latest[4]:.2f}%")
        
        print(f"\n{'Date':<12} {'AUM':<15} {'Day %':<8} {'Week %':<8} {'Month %'}")
        print(f"{'-'*60}")
        
        for snap in snapshots[:10]:
            date, aum, day, week, month = snap
            print(f"{str(date):<12} ${aum:>13,.2f} {day:>6.2f}% {week:>6.2f}% {month:>6.2f}%")
    else:
        print("No snapshots yet. Run daily to build history.")
    
    print(f"{'='*60}")
    conn.close()

def run_compounding_tracker():
    """Main entry point."""
    print("=" * 60)
    print(f"VOX COMPOUNDING TRACKER — {datetime.now()}")
    print("=" * 60)
    
    create_snapshot_table()
    
    metrics = calculate_portfolio_metrics()
    print(f"\nCurrent Portfolio:")
    print(f"  AUM: ${metrics['total_aum']:,.2f}")
    print(f"  Positions: {metrics['total_positions']}")
    print(f"  Brokers: {metrics['total_brokers']}")
    
    store_snapshot(metrics)
    generate_compounding_report()
    
    return metrics

if __name__ == '__main__':
    run_compounding_tracker()
