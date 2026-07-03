#!/usr/bin/env python3
"""
VOX DISCOVERY ENGINE v1.0
Discovers new stocks from multiple sources, grades them, tracks discovery history.

Sources:
- Top momentum from vox_grades (already scanned)
- Sector momentum leaders
- Trade signal high composites
- Pattern alerts (breakouts)
- Macro-theme aligned sectors
- Weekly manual additions

Tables:
- discovery_queue: stocks to research
- discovery_history: all discoveries with outcomes
- sector_opportunities: sector-ranked plays
- theme_alignment: macro theme -> stock mapping
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = ""
DB_NAME = os.environ.get("DB_NAME", "railway")

def connect():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )

AGGRESSIVE_SECTORS = [
    'Quantum Computing', 'Artificial Intelligence', 'Nuclear Energy',
    'Hydrogen', 'Cryptocurrency', 'Emerging Markets Fintech',
    'Space', 'Biotechnology', 'Robotics', 'Autonomous Vehicles'
]

DEFENSIVE_TICKERS = ['PG','KO','VZ','JNJ','PEP','WMT','COST','HD','LOW','TGT',
                     'SPG','FRT','O','NNN','STAG','ADC','SRC','VICI','EPR',
                     'NEM','GOLD','AEM','WPM','RGLD','KGC','NG','AU',
                     'XLU','NEE','DUK','SO','AEP','SRE','EXC','ED','ETR','FE']

def init_tables():
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovery_queue (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            discovery_source VARCHAR(50) NOT NULL,
            vox_grade INTEGER,
            technical_score INTEGER,
            fundamental_score INTEGER,
            sector VARCHAR(50),
            theme_alignment VARCHAR(50),
            discovery_date DATE DEFAULT NOW(),
            status VARCHAR(20) DEFAULT 'pending', -- pending, researching, approved, rejected, added
            priority INTEGER DEFAULT 5, -- 1-10, 10 = highest
            notes TEXT,
            added_to_portfolio BOOLEAN DEFAULT FALSE,
            added_date DATE,
            outcome_return_pct DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovery_history (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            discovery_week DATE NOT NULL,
            discovery_source VARCHAR(50),
            initial_grade INTEGER,
            final_grade INTEGER,
            action_taken VARCHAR(20), -- added, rejected, watched
            return_pct DECIMAL(5,2),
            lessons TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_opportunities (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(50) NOT NULL,
            momentum_score INTEGER,
            top_tickers TEXT,
            buy_count INTEGER,
            hold_count INTEGER,
            sell_count INTEGER,
            avg_sector_grade DECIMAL(5,2),
            best_ticker VARCHAR(10),
            best_grade INTEGER,
            week_date DATE DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS theme_alignment (
            id SERIAL PRIMARY KEY,
            theme VARCHAR(50) NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            alignment_score INTEGER, -- 0-100
            vox_grade INTEGER,
            sector VARCHAR(50),
            macro_signal VARCHAR(50),
            confidence INTEGER,
            week_date DATE DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Discovery tables created")

def discover_from_momentum():
    """Find top momentum stocks from vox_grades"""
    conn = connect()
    cur = conn.cursor()
    
    # Find grade 75+ stocks not in portfolio
    cur.execute("""
        SELECT vg.ticker, vg.vox_grade, vg.technical_score, vg.fundamental_score, p.sector
        FROM vox_grades vg
        LEFT JOIN positions p ON vg.ticker = p.ticker
        WHERE vg.vox_grade >= 75
          AND vg.action IN ('BUY', 'STRONG_BUY', 'ACCUMULATE')
          AND p.ticker IS NULL
          AND vg.ticker NOT IN %s
        ORDER BY vg.vox_grade DESC
        LIMIT 20
    """, (tuple(DEFENSIVE_TICKERS),))
    
    new_discoveries = 0
    for row in cur.fetchall():
        ticker, grade, tech, fund, sector = row
        
        # Check if already in queue
        cur.execute("SELECT id FROM discovery_queue WHERE ticker = %s AND status = 'pending'", (ticker,))
        if cur.fetchone():
            continue
        
        # Determine theme alignment
        theme = 'General'
        if any(s in (sector or '') for s in ['Quantum', 'AI', 'Artificial']):
            theme = 'Artificial Intelligence'
        elif any(s in (sector or '') for s in ['Nuclear', 'Energy']):
            theme = 'Nuclear Energy'
        elif any(s in (sector or '') for s in ['Crypto', 'Bitcoin', 'Blockchain']):
            theme = 'Cryptocurrency'
        elif any(s in (sector or '') for s in ['Fintech', 'Payments', 'Banking']):
            theme = 'Emerging Markets Fintech'
        elif any(s in (sector or '') for s in ['Biotech', 'Gene', 'Health']):
            theme = 'Biotechnology'
        
        priority = min(10, max(1, (grade - 60) // 3))
        
        cur.execute("""
            INSERT INTO discovery_queue (ticker, discovery_source, vox_grade, 
                technical_score, fundamental_score, sector, theme_alignment, priority, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (ticker, 'momentum_scan', grade, tech, fund, sector, theme, priority, 
              f"Grade {grade} momentum stock from full market scan"))
        new_discoveries += 1
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Discovered {new_discoveries} new momentum stocks")
    return new_discoveries

def discover_from_sectors():
    """Find sector leaders"""
    conn = connect()
    cur = conn.cursor()
    
    # Get top sectors by momentum
    cur.execute("""
        SELECT sector, momentum_score, top_tickers, buy_count, hold_count, sell_count
        FROM sector_momentum
        WHERE momentum_score >= 50
        ORDER BY momentum_score DESC
        LIMIT 10
    """)
    
    new_discoveries = 0
    for row in cur.fetchall():
        sector, momentum, tickers, buy_count, hold_count, sell_count = row
        
        # Parse top tickers
        if tickers:
            if isinstance(tickers, list):
                ticker_list = tickers
            else:
                ticker_list = [t.strip() for t in tickers.split(',')]
            for ticker in ticker_list[:3]:  # Top 3 per sector
                # Check not in portfolio and not already queued
                cur.execute("SELECT ticker FROM positions WHERE ticker = %s", (ticker,))
                if cur.fetchone():
                    continue
                
                cur.execute("SELECT id FROM discovery_queue WHERE ticker = %s AND status = 'pending'", (ticker,))
                if cur.fetchone():
                    continue
                
                # Get grade
                cur.execute("SELECT vox_grade, technical_score, fundamental_score FROM vox_grades WHERE ticker = %s", (ticker,))
                grade_row = cur.fetchone()
                grade = grade_row[0] if grade_row else 50
                tech = grade_row[1] if grade_row else 50
                fund = grade_row[2] if grade_row else 50
                
                priority = min(10, max(1, momentum // 10))
                
                cur.execute("""
                    INSERT INTO discovery_queue (ticker, discovery_source, vox_grade,
                        technical_score, fundamental_score, sector, theme_alignment, priority, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (ticker, 'sector_momentum', grade, tech, fund, sector, sector, priority,
                      f"Top {sector} stock, sector momentum {momentum}"))
                new_discoveries += 1
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Discovered {new_discoveries} sector leaders")
    return new_discoveries

def discover_from_trade_signals():
    """Find high composite trade signals"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT ticker, composite_score, signal_type, target_price, stop_price
        FROM trade_signals
        WHERE composite_score >= 70
          AND ticker NOT IN (SELECT ticker FROM positions)
        ORDER BY composite_score DESC
        LIMIT 15
    """)
    
    new_discoveries = 0
    for row in cur.fetchall():
        ticker, composite, signal_type, target, stop = row
        
        cur.execute("SELECT id FROM discovery_queue WHERE ticker = %s AND status = 'pending'", (ticker,))
        if cur.fetchone():
            continue
        
        cur.execute("SELECT vox_grade, technical_score, fundamental_score, p.sector FROM vox_grades vg LEFT JOIN positions p ON vg.ticker = p.ticker WHERE vg.ticker = %s", (ticker,))
        grade_row = cur.fetchone()
        grade = grade_row[0] if grade_row else 50
        tech = grade_row[1] if grade_row else 50
        fund = grade_row[2] if grade_row else 50
        sector = grade_row[3] if grade_row else 'Unknown'
        
        priority = min(10, max(1, composite // 10))
        
        cur.execute("""
            INSERT INTO discovery_queue (ticker, discovery_source, vox_grade,
                technical_score, fundamental_score, sector, theme_alignment, priority, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (ticker, 'trade_signal', grade, tech, fund, sector, 'Trade Signal', priority,
              f"Trade signal {signal_type}, composite {composite}, target ${target}"))
        new_discoveries += 1
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Discovered {new_discoveries} trade signal stocks")
    return new_discoveries

def show_discovery_queue():
    """Display current discovery queue"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT ticker, vox_grade, discovery_source, sector, theme_alignment, priority, notes
        FROM discovery_queue
        WHERE status = 'pending'
        ORDER BY priority DESC, vox_grade DESC
        LIMIT 20
    """)
    
    rows = cur.fetchall()
    
    print("\n🔍 DISCOVERY QUEUE (Top 20)")
    print("=" * 100)
    print(f"{'Ticker':<8} {'Grade':<6} {'Source':<18} {'Sector':<20} {'Theme':<25} {'Prio':<5} {'Notes'}")
    print("-" * 100)
    
    for row in rows:
        ticker, grade, source, sector, theme, priority, notes = row
        print(f"{ticker:<8} {grade:<6} {source:<18} {sector or '':<20} {theme or '':<25} {priority:<5} {notes or ''}")
    
    print("-" * 100)
    print(f"Total pending: {len(rows)}")
    
    conn.close()

def show_sector_opportunities():
    """Display sector-ranked opportunities"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT sector, momentum_score, top_tickers, buy_count, avg_sector_grade, best_ticker, best_grade
        FROM sector_opportunities
        ORDER BY momentum_score DESC
        LIMIT 10
    """)
    
    rows = cur.fetchall()
    
    print("\n📊 SECTOR OPPORTUNITIES")
    print("=" * 90)
    print(f"{'Sector':<25} {'Momentum':<10} {'Top Tickers':<30} {'Buy':<5} {'Avg Grade':<10} {'Best':<8} {'Grade'}")
    print("-" * 90)
    
    for row in rows:
        sector, momentum, tickers, buy_count, avg_grade, best_ticker, best_grade = row
        print(f"{sector:<25} {momentum:<10} {tickers or '':<30} {buy_count or 0:<5} {avg_grade or 0:<10.1f} {best_ticker or '':<8} {best_grade or 0}")
    
    conn.close()

def run_full_discovery():
    """Run all discovery sources"""
    print("\n🚀 VOX DISCOVERY ENGINE — Full Scan")
    print("=" * 60)
    
    total = 0
    total += discover_from_momentum()
    total += discover_from_sectors()
    total += discover_from_trade_signals()
    
    print(f"\n✅ Total new discoveries: {total}")
    
    show_discovery_queue()
    show_sector_opportunities()

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'full'
    
    if action == 'init':
        init_tables()
    elif action == 'momentum':
        discover_from_momentum()
    elif action == 'sectors':
        discover_from_sectors()
    elif action == 'signals':
        discover_from_trade_signals()
    elif action == 'queue':
        show_discovery_queue()
    elif action == 'full':
        run_full_discovery()
    else:
        print("Unknown action. Use: init, momentum, sectors, signals, queue, full")

if __name__ == '__main__':
    main()
