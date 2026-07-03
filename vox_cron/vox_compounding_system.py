#!/usr/bin/env python3
"""
VOX COMPOUNDING SYSTEM v1.0
Tracks portfolio growth, sets weekly goals, measures progress, creates feedback loops.

Tables created:
- portfolio_goals: weekly/monthly targets
- portfolio_history: daily snapshots
- trade_journal: every trade with lessons
- performance_metrics: win rate, avg return, sharpe, etc
- compounding_projections: forward-looking scenarios
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime, timedelta
import json

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    # Fallback to hardcoded for Railway (env may be masked)
    DB_PASSWORD = ""
DB_NAME = os.environ.get("DB_NAME", "railway")

def connect():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )

def init_tables():
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_goals (
            id SERIAL PRIMARY KEY,
            goal_type VARCHAR(20) NOT NULL,
            target_date DATE NOT NULL,
            target_aum DECIMAL(15,2),
            target_return_pct DECIMAL(5,2),
            target_new_positions INTEGER,
            target_best_plays INTEGER,
            aggressive_focus_pct DECIMAL(5,2),
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_history (
            id SERIAL PRIMARY KEY,
            snapshot_date DATE NOT NULL UNIQUE,
            total_aum DECIMAL(15,2),
            cash_available DECIMAL(15,2),
            invested_amount DECIMAL(15,2),
            num_positions INTEGER,
            avg_grade DECIMAL(5,2),
            top_5_avg_grade DECIMAL(5,2),
            best_ticker VARCHAR(10),
            best_grade INTEGER,
            worst_ticker VARCHAR(10),
            worst_grade INTEGER,
            new_positions_this_week INTEGER,
            closed_positions_this_week INTEGER,
            weekly_return_pct DECIMAL(5,2),
            ytd_return_pct DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            action VARCHAR(10) NOT NULL,
            shares INTEGER,
            price DECIMAL(10,2),
            total_amount DECIMAL(12,2),
            broker VARCHAR(50),
            vox_grade_at_trade INTEGER,
            unified_grade_at_trade INTEGER,
            thesis TEXT,
            outcome VARCHAR(20),
            return_pct DECIMAL(5,2),
            lessons_learned TEXT,
            would_repeat BOOLEAN,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id SERIAL PRIMARY KEY,
            metric_period VARCHAR(20) NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            win_rate_pct DECIMAL(5,2),
            avg_win_pct DECIMAL(5,2),
            avg_loss_pct DECIMAL(5,2),
            profit_factor DECIMAL(5,2),
            avg_holding_days INTEGER,
            best_trade_ticker VARCHAR(10),
            best_trade_return_pct DECIMAL(5,2),
            worst_trade_ticker VARCHAR(10),
            worst_trade_return_pct DECIMAL(5,2),
            sharpe_ratio DECIMAL(5,2),
            max_drawdown_pct DECIMAL(5,2),
            vox_grade_correlation DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compounding_projections (
            id SERIAL PRIMARY KEY,
            scenario_name VARCHAR(50) NOT NULL,
            starting_aum DECIMAL(15,2),
            monthly_return_pct DECIMAL(5,2),
            monthly_contribution DECIMAL(10,2),
            projection_months INTEGER,
            projected_aum DECIMAL(15,2),
            projected_return_pct DECIMAL(5,2),
            aggressive_allocation_pct DECIMAL(5,2),
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Compounding tables created")

def set_current_goals():
    conn = connect()
    cur = conn.cursor()
    
    today = datetime.now().date()
    week_end = today + timedelta(days=(6 - today.weekday()))
    month_end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
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
    conn.close()
    print(f"✅ Goals set. Current AUM: ${current_aum:,.2f}")

def take_daily_snapshot():
    conn = connect()
    cur = conn.cursor()
    
    today = datetime.now().date()
    
    cur.execute("""
        SELECT 
            SUM(live_value_usd) as aum,
            COUNT(*) as positions,
            AVG(grade) as avg_grade,
            MAX(grade) as best_grade,
            MIN(grade) as worst_grade
        FROM positions
    """)
    row = cur.fetchone()
    aum, positions, avg_grade, best_grade, worst_grade = row
    
    cur.execute("SELECT ticker FROM positions ORDER BY grade DESC LIMIT 1")
    best_ticker = cur.fetchone()[0] if cur.rowcount > 0 else None
    
    cur.execute("SELECT ticker FROM positions ORDER BY grade ASC LIMIT 1")
    worst_ticker = cur.fetchone()[0] if cur.rowcount > 0 else None
    
    cur.execute("SELECT AVG(grade) FROM (SELECT grade FROM positions ORDER BY live_value_usd DESC LIMIT 5) t")
    top_5_avg = cur.fetchone()[0]
    
    cur.execute("SELECT total_aum FROM portfolio_history WHERE snapshot_date = %s", (today - timedelta(days=7),))
    prev = cur.fetchone()
    weekly_return = ((aum - prev[0]) / prev[0] * 100) if prev and prev[0] else 0
    
    cur.execute("""
        INSERT INTO portfolio_history 
        (snapshot_date, total_aum, num_positions, avg_grade, top_5_avg_grade,
         best_ticker, best_grade, worst_ticker, worst_grade, weekly_return_pct)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (snapshot_date) DO UPDATE SET
            total_aum = EXCLUDED.total_aum,
            num_positions = EXCLUDED.num_positions,
            avg_grade = EXCLUDED.avg_grade,
            weekly_return_pct = EXCLUDED.weekly_return_pct
    """, (today, aum, positions, avg_grade, top_5_avg, best_ticker, best_grade, worst_ticker, worst_grade, weekly_return))
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Snapshot: ${aum:,.2f} | {positions} positions | Avg grade {avg_grade:.1f}")

def generate_projections():
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("SELECT total_aum FROM portfolio_history ORDER BY snapshot_date DESC LIMIT 1")
    row = cur.fetchone()
    current_aum = float(row[0]) if row and row[0] else 200000.0
    
    scenarios = [
        ('Conservative (2%/mo)', 2.0, 1000),
        ('Moderate (4%/mo)', 4.0, 2000),
        ('Aggressive (6%/mo)', 6.0, 3000),
        ('VOX Target (8%/mo)', 8.0, 5000),
        ('High Risk (12%/mo)', 12.0, 5000),
    ]
    
    print("\n📈 COMPOUNDING PROJECTIONS (12 months)")
    print("=" * 60)
    print(f"Starting AUM: ${current_aum:,.2f}")
    print("-" * 60)
    print(f"{'Scenario':<25} {'Monthly':<10} {'12-Mo AUM':<15} {'Return':<10}")
    print("-" * 60)
    
    for name, ret, contrib in scenarios:
        future = current_aum * ((1 + ret/100) ** 12)
        future += contrib * 12
        total_return = ((future - current_aum) / current_aum) * 100
        
        print(f"{name:<25} {ret:>5.1f}%     ${future:>12,.0f}  {total_return:>6.1f}%")
        
        cur.execute("""
            INSERT INTO compounding_projections 
            (scenario_name, starting_aum, monthly_return_pct, monthly_contribution, 
             projection_months, projected_aum, projected_return_pct, aggressive_allocation_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (name, current_aum, ret, contrib, 12, future, total_return, 70.0))
    
    conn.commit()
    cur.close()
    conn.close()
    print("-" * 60)

def show_progress_dashboard():
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT total_aum, num_positions, avg_grade, weekly_return_pct, best_ticker, best_grade
        FROM portfolio_history ORDER BY snapshot_date DESC LIMIT 1
    """)
    current = cur.fetchone()
    
    cur.execute("""
        SELECT goal_type, target_date, target_aum, target_return_pct, 
               target_new_positions, aggressive_focus_pct
        FROM portfolio_goals WHERE status = 'active' ORDER BY target_date
    """)
    goals = cur.fetchall()
    
    print("\n🎯 PROGRESS DASHBOARD")
    print("=" * 70)
    
    if current:
        print(f"Current AUM:      ${current[0]:>12,.2f}")
        print(f"Positions:        {current[1]}")
        print(f"Avg Grade:        {current[2]:.1f}")
        print(f"Weekly Return:    {current[3]:.2f}%")
        print(f"Best Position:    {current[4]} (grade {current[5]})")
    
    print("\n📋 GOALS")
    print("-" * 70)
    print(f"{'Type':<12} {'Target Date':<12} {'Target AUM':<15} {'Return':<10} {'New Pos':<8} {'Agg%':<6}")
    print("-" * 70)
    
    for g in goals:
        print(f"{g[0]:<12} {str(g[1]):<12} ${g[2]:>12,.0f}  {g[3]:>5.1f}%   {g[4]:>3}      {g[5]:>4.0f}%")
    
    print("\n✅ GOAL TRACKING")
    print("-" * 70)
    
    for g in goals:
        goal_type, target_date, target_aum, target_ret = g[0], g[1], g[2], g[3]
        days_left = (target_date - datetime.now().date()).days
        
        if current and target_aum:
            progress = (current[0] / target_aum) * 100
            needed = target_aum - current[0]
            print(f"{goal_type:<12} {progress:>5.1f}% of ${target_aum:,.0f} target | ${needed:>10,.2f} to go | {days_left} days left")
    
    conn.close()

def log_trade(ticker, action, shares, price, total, broker, vox_grade, unified_grade, thesis):
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO trade_journal 
        (trade_date, ticker, action, shares, price, total_amount, broker,
         vox_grade_at_trade, unified_grade_at_trade, thesis)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (datetime.now().date(), ticker, action, shares, price, total, broker, 
          vox_grade, unified_grade, thesis))
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Trade logged: {action} {shares} {ticker} @ ${price}")

def update_trade_outcome(ticker, action, return_pct, lessons, would_repeat):
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE trade_journal 
        SET outcome = %s, return_pct = %s, lessons_learned = %s, would_repeat = %s
        WHERE ticker = %s AND action = %s AND outcome IS NULL
        ORDER BY trade_date DESC LIMIT 1
    """, ('win' if return_pct > 0 else 'loss', return_pct, lessons, would_repeat, ticker, action))
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Outcome updated: {ticker} {return_pct:.2f}%")

def calculate_performance_metrics():
    conn = connect()
    cur = conn.cursor()
    
    week_start = datetime.now().date() - timedelta(days=7)
    week_end = datetime.now().date()
    
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN return_pct > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN return_pct < 0 THEN 1 ELSE 0 END) as losses,
            AVG(return_pct) as avg_return,
            MAX(return_pct) as best_return,
            MIN(return_pct) as worst_return
        FROM trade_journal 
        WHERE trade_date >= %s AND trade_date <= %s AND outcome IS NOT NULL
    """, (week_start, week_end))
    
    row = cur.fetchone()
    total, wins, losses, avg_return, best, worst = row
    win_rate = (wins / total * 100) if total > 0 else 0
    
    print(f"\n📊 WEEKLY PERFORMANCE")
    print(f"Total trades: {total}")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Avg return: {avg_return:.2f}%")
    print(f"Best: {best:.2f}% | Worst: {worst:.2f}%")
    
    conn.close()

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
    
    if action == 'init':
        init_tables()
        set_current_goals()
    elif action == 'snapshot':
        take_daily_snapshot()
    elif action == 'projections':
        generate_projections()
    elif action == 'dashboard':
        show_progress_dashboard()
    elif action == 'metrics':
        calculate_performance_metrics()
    elif action == 'log_trade':
        if len(sys.argv) < 9:
            print("Usage: log_trade <ticker> <action> <shares> <price> <total> <broker> <vox_grade> <unified_grade> <thesis>")
            return
        log_trade(sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5]), 
                  float(sys.argv[6]), sys.argv[7], int(sys.argv[8]), int(sys.argv[9]), 
                  ' '.join(sys.argv[10:]))
    elif action == 'update_outcome':
        if len(sys.argv) < 6:
            print("Usage: update_outcome <ticker> <action> <return_pct> <lessons> <would_repeat>")
            return
        update_trade_outcome(sys.argv[2], sys.argv[3], float(sys.argv[4]), 
                            sys.argv[5], sys.argv[6].lower() == 'true')
    else:
        print("Unknown action. Use: init, snapshot, projections, dashboard, metrics, log_trade, update_outcome")

if __name__ == '__main__':
    main()
