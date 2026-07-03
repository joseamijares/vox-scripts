#!/usr/bin/env python3
"""
VOX Unified Grades Rebuilder
Rebuilds unified_grades table from vox_grades, watchlist_grades, and sp500_grades.
Runs daily to ensure unified grades stay synchronized.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
from psycopg2.extras import execute_values
import os
import sys

DB_HOST = os.environ.get('PGHOST', 'acela.proxy.rlwy.net')
DB_PORT = os.environ.get('PGPORT', '35577')
DB_USER = os.environ.get('PGUSER', 'postgres')
DB_PASS = os.environ.get('PGPASSWORD', '')
DB_NAME = os.environ.get('PGDATABASE', 'railway')

def rebuild_unified():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASS, dbname=DB_NAME, sslmode='require'
    )
    cur = conn.cursor()
    
    # Truncate unified_grades
    cur.execute('TRUNCATE TABLE unified_grades RESTART IDENTITY')
    
    # Get all latest vox_grades
    cur.execute('''
        SELECT v.ticker, v.vox_grade, v.action, v.technical_score, v.fundamental_score, v.macro_score, v.sentiment_score
        FROM vox_grades v
        WHERE v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
    ''')
    vox_rows = {row[0]: row for row in cur.fetchall()}
    
    # Get all sp500 grades
    cur.execute('SELECT DISTINCT ON (ticker) ticker, vox_grade FROM sp500_grades ORDER BY ticker, computed_at DESC')
    sp500_rows = {row[0]: row[1] for row in cur.fetchall()}
    
    # Get all watchlist grades
    cur.execute('SELECT DISTINCT ON (ticker) ticker, vox_grade FROM watchlist_grades ORDER BY ticker, graded_at DESC')
    watch_rows = {row[0]: row[1] for row in cur.fetchall()}
    
    records = []
    for ticker, row in vox_rows.items():
        _, vox_grade, vox_action, tech, fund, macro, sent = row
        
        sp500_grade = sp500_rows.get(ticker)
        watch_grade = watch_rows.get(ticker)
        
        # Determine source and base grade
        if watch_grade and watch_grade >= vox_grade:
            base_grade = watch_grade
            source = 'watchlist'
        else:
            base_grade = vox_grade
            source = 'vox_grades'
        
        # Compute unified grade with weights
        weights = []
        grades = []
        
        weights.append(0.4)
        grades.append(base_grade)
        
        if sp500_grade:
            weights.append(0.3)
            grades.append(sp500_grade)
        
        if watch_grade and watch_grade != base_grade:
            weights.append(0.2)
            grades.append(watch_grade)
        
        layer_scores = [s for s in [tech, fund, macro, sent] if s is not None]
        if layer_scores:
            avg_layer = sum(layer_scores) / len(layer_scores)
            weights.append(0.1)
            grades.append(avg_layer)
        
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        unified_grade = int(round(sum(g * w for g, w in zip(grades, normalized_weights))))
        
        # INFLATION BUG FIX: Cap unified grade when VOX says SELL
        if vox_action in ('SELL', 'STRONG_SELL'):
            unified_grade = min(unified_grade, 59)
        
        # Determine action
        if unified_grade >= 80:
            action = 'STRONG_BUY'
        elif unified_grade >= 65:
            action = 'BUY'
        elif unified_grade >= 50:
            action = 'HOLD'
        elif unified_grade >= 35:
            action = 'TRIM'
        else:
            action = 'SELL'
        
        # Check for contradiction
        contradiction = None
        if vox_action in ('BUY', 'STRONG_BUY') and action in ('SELL', 'TRIM'):
            contradiction = f'VOX says {vox_action} but unified says {action}'
        elif vox_action in ('SELL', 'TRIM') and action in ('BUY', 'STRONG_BUY'):
            contradiction = f'VOX says {vox_action} but unified says {action}'
        
        records.append((ticker, unified_grade, action, vox_grade, sp500_grade, None, tech, contradiction, source))
    
    # Batch insert
    execute_values(cur, """
        INSERT INTO unified_grades (ticker, unified_grade, action, vox_grade, sp500_grade, trade_grade, tech_score, contradiction, computed_at, vox_source)
        VALUES %s
    """, [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], 'NOW()', r[8]) for r in records], page_size=500)
    
    # Verify no inflation bug
    cur.execute('''
        SELECT COUNT(*) 
        FROM unified_grades u
        JOIN vox_grades v ON u.ticker = v.ticker
        WHERE v.action IN ('SELL', 'STRONG_SELL')
          AND u.unified_grade >= 60
          AND v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
    ''')
    inflation_count = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f'Rebuilt {len(records)} unified records')
    print(f'Inflation bug tickers: {inflation_count}')
    print('SUCCESS' if inflation_count == 0 else 'FAILED')
    return inflation_count == 0

if __name__ == '__main__':
    success = rebuild_unified()
    sys.exit(0 if success else 1)
