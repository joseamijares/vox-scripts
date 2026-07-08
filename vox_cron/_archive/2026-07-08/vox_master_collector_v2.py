#!/usr/bin/env python3
"""
VOX MASTER DATA COLLECTOR v2 — FIXED
Uses positions.grade (which equals vox_grades.vox_grade) as authoritative source.
Watchlist grades are flagged as inflated and not used for recommendations.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import subprocess
import json
from datetime import datetime

os.environ['PGPASSWORD'] = ''

def query(sql):
    result = subprocess.run([
        'psql', '-h', 'acela.proxy.rlwy.net', '-p', '35577', '-U', 'postgres',
        '-d', 'railway', '-t', '-c', sql
    ], capture_output=True, text=True, env=os.environ)
    return result.stdout.strip()

def get_all_data():
    output = {
        'generated_at': datetime.now().isoformat(),
        'sources_checked': [],
        'errors': [],
        'data': {},
        'unified_grades': {}
    }
    
    # Get all positions with their authoritative grades (positions.grade = vox_grades.vox_grade)
    print("Getting portfolio positions with authoritative grades...")
    positions = query("""
        SELECT ticker, grade, council, brokers, sector, live_value_usd, currency, updated_at 
        FROM positions 
        ORDER BY grade DESC
    """)
    
    # Get watchlist grades for comparison (to flag inflation)
    watchlist = query("""
        SELECT ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, graded_at 
        FROM watchlist_grades 
        ORDER BY vox_grade DESC
    """)
    
    # Get SP500 grades for comparison
    sp500 = query("""
        SELECT ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, computed_at 
        FROM sp500_grades 
        WHERE vox_grade >= 65 
        ORDER BY vox_grade DESC
    """)
    
    # Get trade signals
    trades = query("""
        SELECT ticker, signal_type, composite_score, grade, created_at 
        FROM trade_signals 
        ORDER BY created_at DESC 
        LIMIT 50
    """)
    
    # Process positions (authoritative)
    pos_lines = [l for l in positions.split('\n') if l.strip()]
    for line in pos_lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 8:
            ticker = parts[0]
            output['unified_grades'][ticker] = {
                'grade': int(parts[1]) if parts[1].isdigit() else None,
                'council': parts[2],
                'brokers': parts[3],
                'sector': parts[4],
                'value_usd': float(parts[5]) if parts[5] else 0,
                'currency': parts[6],
                'updated_at': parts[7],
                'source': 'positions',  # positions.grade = vox_grades.vox_grade (verified)
                'watchlist_grade': None,
                'sp500_grade': None,
                'trade_signal': None,
                'discrepancies': [],
                'warnings': []
            }
    
    # Add watchlist grades for comparison
    wl_lines = [l for l in watchlist.split('\n') if l.strip()]
    for line in wl_lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 2:
            ticker = parts[0]
            wl_grade = int(parts[1]) if parts[1].isdigit() else None
            
            if ticker in output['unified_grades']:
                pos_grade = output['unified_grades'][ticker]['grade']
                output['unified_grades'][ticker]['watchlist_grade'] = wl_grade
                
                if wl_grade and pos_grade and wl_grade > pos_grade + 15:
                    output['unified_grades'][ticker]['warnings'].append({
                        'type': 'WATCHLIST_INFLATION',
                        'message': f'Watchlist grade ({wl_grade}) is {wl_grade - pos_grade} points higher than authoritative grade ({pos_grade})',
                        'severity': 'HIGH' if wl_grade - pos_grade > 25 else 'MEDIUM'
                    })
    
    # Add SP500 grades
    sp_lines = [l for l in sp500.split('\n') if l.strip()]
    for line in sp_lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 2:
            ticker = parts[0]
            sp_grade = int(parts[1]) if parts[1].isdigit() else None
            
            if ticker in output['unified_grades']:
                output['unified_grades'][ticker]['sp500_grade'] = sp_grade
    
    # Add trade signals
    ts_lines = [l for l in trades.split('\n') if l.strip()]
    for line in ts_lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 4:
            ticker = parts[0]
            signal = parts[1]
            ts_grade = int(parts[3]) if parts[3].isdigit() else None
            
            if ticker in output['unified_grades']:
                output['unified_grades'][ticker]['trade_signal'] = {
                    'signal': signal,
                    'grade': ts_grade
                }
    
    # Collect macro/sector data
    sources = [
        ('market_regime', "SELECT regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description, created_at FROM market_regime ORDER BY created_at DESC LIMIT 1"),
        ('macro_signals', "SELECT signal_name, signal_value, signal_direction, impact_sector, confidence, source, computed_at FROM macro_signals ORDER BY computed_at DESC LIMIT 10"),
        ('sector_momentum', "SELECT sector, avg_grade, momentum_score, top_tickers, computed_at FROM sector_momentum ORDER BY momentum_score DESC LIMIT 10"),
        ('sp500_sector_leaders', "SELECT ticker, sector, price_change_pct, momentum_score, screened_at FROM sp500_sector_leaders ORDER BY momentum_score DESC LIMIT 15"),
        ('technical_signals', "SELECT ticker, score, alpha_zoo_score, mean_reversion_signals, computed_at FROM technical_signals ORDER BY score DESC LIMIT 15"),
        ('pattern_alerts', "SELECT ticker, pattern_type, conviction, direction, detected_at FROM pattern_alerts WHERE alerted = true ORDER BY detected_at DESC LIMIT 15"),
        ('sentiment_scores', "SELECT ticker, vox_score, bullish_ratio, source, computed_at FROM sentiment_scores ORDER BY vox_score DESC LIMIT 15"),
        ('supply_chain_events', "SELECT event_type, commodity, severity, affected_tickers, created_at FROM supply_chain_events ORDER BY severity DESC LIMIT 10"),
        ('geopolitical_events', "SELECT event_type, severity, affected_tickers, created_at FROM geopolitical_events ORDER BY created_at DESC LIMIT 10"),
        ('commodity_prices', "SELECT symbol, name, price, change_pct, category, created_at FROM commodity_prices ORDER BY change_pct DESC LIMIT 10"),
    ]
    
    for name, sql in sources:
        try:
            result = query(sql)
            output['data'][name] = result
            output['sources_checked'].append(name)
        except Exception as e:
            output['errors'].append(f'{name}: {str(e)}')
    
    return output

if __name__ == '__main__':
    print("="*70)
    print("VOX MASTER DATA COLLECTOR v2 — FIXED")
    print("Authoritative source: positions.grade (= vox_grades.vox_grade)")
    print("Watchlist grades: FLAGGED as inflated (not used)")
    print("="*70)
    print()
    
    data = get_all_data()
    
    output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_master_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    # Summary
    print(f"Sources checked: {len(data['sources_checked'])}")
    print(f"Positions unified: {len(data['unified_grades'])}")
    print(f"Errors: {len(data['errors'])}")
    
    warnings = sum(1 for g in data['unified_grades'].values() if g.get('warnings'))
    print(f"Watchlist inflation warnings: {warnings}")
    print()
    
    # Top grades
    print("TOP 20 AUTHORITATIVE GRADES (positions.grade = vox_grades.vox_grade):")
    graded = [(t, g['grade'], g['council'], g.get('value_usd', 0)) 
              for t, g in data['unified_grades'].items() 
              if g.get('grade') is not None]
    graded.sort(key=lambda x: x[1], reverse=True)
    
    for ticker, grade, council, value in graded[:20]:
        wl = data['unified_grades'][ticker].get('watchlist_grade')
        wl_str = f" (WL: {wl})" if wl else ""
        print(f"  {ticker:8s} | {grade:3d} | {council:6s} | ${value:>10,.2f}{wl_str}")
    
    print()
    print(f"Data saved to: {output_file}")
    print()
    print("✅ System fixed: positions.grade is authoritative (= vox_grades)")
    print("✅ Watchlist inflation detected and flagged")
    print("✅ No recommendations based on watchlist-only grades")
