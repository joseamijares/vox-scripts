#!/usr/bin/env python3
"""
VOX Compounding Job v2.0
Unifies: vox_compounding_tracker, vox_compounding_system, weekly_portfolio_sync.
- Daily snapshot of AUM, positions, brokers, top/worst performers
- Weekly goals update + projections
- Monday progress report
- Optional --weekly flag to only emit weekly progress
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime, timedelta
import argparse

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', '')),
        sslmode='require'
    )

def ensure_tables(conn):
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_goals (
            id SERIAL PRIMARY KEY,
            goal_type VARCHAR(20) NOT NULL,
            target_date DATE NOT NULL,
            target_aum NUMERIC(15,2),
            target_return_pct NUMERIC(5,2),
            target_new_positions INTEGER,
            target_best_plays INTEGER,
            aggressive_focus_pct NUMERIC(5,2),
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compounding_projections (
            id SERIAL PRIMARY KEY,
            scenario_name VARCHAR(50) NOT NULL,
            starting_aum NUMERIC(15,2),
            monthly_return_pct NUMERIC(5,2),
            monthly_contribution NUMERIC(10,2),
            projection_months INTEGER,
            projected_aum NUMERIC(15,2),
            projected_return_pct NUMERIC(5,2),
            aggressive_allocation_pct NUMERIC(5,2),
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'portfolio_goals_goal_type_key') THEN
                DELETE FROM portfolio_goals a USING portfolio_goals b WHERE a.id < b.id AND a.goal_type = b.goal_type;
                ALTER TABLE portfolio_goals ADD CONSTRAINT portfolio_goals_goal_type_key UNIQUE (goal_type);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'compounding_projections_scenario_name_key') THEN
                DELETE FROM compounding_projections a USING compounding_projections b WHERE a.id < b.id AND a.scenario_name = b.scenario_name;
                ALTER TABLE compounding_projections ADD CONSTRAINT compounding_projections_scenario_name_key UNIQUE (scenario_name);
            END IF;
        END
        $$;
    """)
    conn.commit()
    cur.close()

def calculate_metrics(conn):
    cur = conn.cursor()
    cur.execute("""
    SELECT 
        COALESCE(SUM(live_value_usd), 0), COUNT(DISTINCT ticker), COUNT(DISTINCT broker)
    FROM (
        SELECT ticker, live_value_usd, UNNEST(brokers) as broker
        FROM positions
    ) sub
    """)
    total_aum, total_positions, total_brokers = cur.fetchone()

    cur.execute("""
    SELECT ticker, live_value_usd, avg_cost, shares
    FROM positions
    WHERE shares > 0 AND live_value_usd IS NOT NULL
    ORDER BY live_value_usd DESC
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
            return_pct = max(-1000.0, min(1000.0, return_pct))
            if top_performer is None or return_pct > top_return:
                top_return = return_pct
                top_performer = ticker
            if worst_performer is None or return_pct < worst_return:
                worst_return = return_pct
                worst_performer = ticker

    cur.close()
    return {
        'total_aum': float(total_aum) if total_aum else 0,
        'total_positions': total_positions or 0,
        'total_brokers': total_brokers or 0,
        'top_performer': top_performer,
        'top_return': top_return,
        'worst_performer': worst_performer,
        'worst_return': worst_return,
    }

def store_snapshot(conn, metrics):
    today = datetime.now().date()
    cur = conn.cursor()
    # Calculate weekly return from 7 days ago
    cur.execute("SELECT total_aum FROM portfolio_snapshots WHERE snapshot_date = %s", (today - timedelta(days=7),))
    prev = cur.fetchone()
    weekly_return = 0.0
    if prev and prev[0] and metrics['total_aum']:
        weekly_return = ((metrics['total_aum'] - float(prev[0])) / float(prev[0])) * 100

    cur.execute("""
        INSERT INTO portfolio_snapshots 
        (snapshot_date, total_aum, total_positions, total_brokers,
         week_return_pct, top_performer, top_performer_return, worst_performer, worst_performer_return)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (snapshot_date) DO UPDATE SET
            total_aum = EXCLUDED.total_aum,
            total_positions = EXCLUDED.total_positions,
            total_brokers = EXCLUDED.total_brokers,
            week_return_pct = EXCLUDED.week_return_pct,
            top_performer = EXCLUDED.top_performer,
            top_performer_return = EXCLUDED.top_performer_return,
            worst_performer = EXCLUDED.worst_performer,
            worst_performer_return = EXCLUDED.worst_performer_return,
            created_at = NOW()
    """, (today, metrics['total_aum'], metrics['total_positions'], metrics['total_brokers'],
          weekly_return, metrics['top_performer'], metrics['top_return'],
          metrics['worst_performer'], metrics['worst_return']))
    conn.commit()
    cur.close()

def update_goals(conn):
    today = datetime.now().date()
    week_end = today + timedelta(days=(6 - today.weekday()))
    month_end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    cur = conn.cursor()
    cur.execute("SELECT SUM(live_value_usd) FROM positions")
    row = cur.fetchone()
    current_aum = float(row[0]) if row and row[0] else 0.0

    goals = [
        ('weekly', week_end, current_aum * 1.005, 0.5, 1, 1, 70.0),
        ('monthly', month_end, current_aum * 1.02, 2.0, 3, 2, 65.0),
        ('quarterly', datetime(2026, 9, 30).date(), current_aum * 1.08, 8.0, 8, 5, 60.0),
        ('yearly', datetime(2026, 12, 31).date(), current_aum * 1.35, 35.0, 20, 12, 55.0),
    ]
    for g in goals:
        cur.execute("""
            INSERT INTO portfolio_goals (goal_type, target_date, target_aum, target_return_pct, 
                target_new_positions, target_best_plays, aggressive_focus_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, g)
    conn.commit()
    cur.close()
    return current_aum

def generate_projections(conn, current_aum):
    cur = conn.cursor()
    scenarios = [
        ('Conservative (2%/mo)', 2.0, 1000),
        ('Moderate (4%/mo)', 4.0, 2000),
        ('Aggressive (6%/mo)', 6.0, 3000),
        ('VOX Target (8%/mo)', 8.0, 5000),
        ('High Risk (12%/mo)', 12.0, 5000),
    ]
    results = []
    for name, monthly_return, contribution in scenarios:
        aum = current_aum
        for _ in range(12):
            aum = aum * (1 + monthly_return / 100) + contribution
        projected_return = ((aum - current_aum) / current_aum * 100) if current_aum > 0 else 0
        cur.execute("""
            INSERT INTO compounding_projections
            (scenario_name, starting_aum, monthly_return_pct, monthly_contribution, projection_months,
             projected_aum, projected_return_pct, aggressive_allocation_pct, notes)
            VALUES (%s, %s, %s, %s, 12, %s, %s, %s, %s)
            ON CONFLICT (scenario_name) DO UPDATE SET
                starting_aum = EXCLUDED.starting_aum,
                monthly_return_pct = EXCLUDED.monthly_return_pct,
                monthly_contribution = EXCLUDED.monthly_contribution,
                projection_months = EXCLUDED.projection_months,
                projected_aum = EXCLUDED.projected_aum,
                projected_return_pct = EXCLUDED.projected_return_pct,
                aggressive_allocation_pct = EXCLUDED.aggressive_allocation_pct,
                notes = EXCLUDED.notes,
                created_at = NOW()
        """, (name, current_aum, monthly_return, contribution, aum, projected_return,
              70.0 if monthly_return >= 8 else 50.0, f"12-month projection for {name}"))
        results.append((name, aum, projected_return))
    conn.commit()
    cur.close()
    return results

def weekly_progress(conn, current_aum):
    cur = conn.cursor()
    cur.execute("""
        SELECT snapshot_date, total_aum, week_return_pct
        FROM portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    cur.execute("""
        SELECT scenario_name, projected_aum, projected_return_pct
        FROM compounding_projections
        ORDER BY created_at DESC
        LIMIT 5
    """)
    projections = cur.fetchall()
    cur.close()

    lines = []
    lines.append("=" * 60)
    lines.append(f"📈 VOX COMPOUNDING WEEKLY PROGRESS — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("=" * 60)
    lines.append(f"Current AUM: ${current_aum:,.2f}")
    if rows:
        lines.append(f"\nRecent snapshots:")
        for r in rows:
            lines.append(f"  {r[0]} | AUM ${r[1]:,.2f} | Week {r[2]:+.2f}%")
    if projections:
        lines.append(f"\n12-month projections:")
        for p in projections:
            lines.append(f"  {p[0]}: ${p[1]:,.2f} ({p[2]:.1f}%)")
    lines.append("=" * 60)
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weekly', action='store_true', help='Only emit weekly progress report')
    args = parser.parse_args()

    conn = connect_db()
    ensure_tables(conn)

    if args.weekly:
        current_aum = update_goals(conn)
        generate_projections(conn, current_aum)
        report = weekly_progress(conn, current_aum)
        print(report)
        conn.close()
        return

    print(f"VOX COMPOUNDING JOB — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    metrics = calculate_metrics(conn)
    store_snapshot(conn, metrics)
    current_aum = update_goals(conn)
    projections = generate_projections(conn, current_aum)
    print(f"  AUM: ${metrics['total_aum']:,.2f} | Positions: {metrics['total_positions']} | Brokers: {metrics['total_brokers']}")
    print(f"  Top: {metrics['top_performer']} ({metrics['top_return']:+.1f}%) | Worst: {metrics['worst_performer']} ({metrics['worst_return']:+.1f}%)")
    print(f"  Projections: {len(projections)} scenarios updated")
    if datetime.now().weekday() == 0:  # Monday
        print("\n" + weekly_progress(conn, current_aum))
    conn.close()

if __name__ == '__main__':
    main()
