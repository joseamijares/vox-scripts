#!/usr/bin/env python3
"""
VOX UNIFIED GRADING SYSTEM v2
Fixes the watchlist vs vox_grades discrepancy by using FRESHEST grade with source tracking.
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

def get_unified_grade(ticker):
    """Get the unified grade for a ticker using the freshest data with full provenance."""
    
    sources = {}
    
    # 1. Portfolio position (most authoritative for current holdings)
    pos = query(f"SELECT grade, council, updated_at FROM positions WHERE ticker = '{ticker}'")
    if pos.strip():
        parts = [p.strip() for p in pos.split('|')]
        sources['positions'] = {
            'grade': int(parts[0]) if parts[0].isdigit() else None,
            'council': parts[1] if len(parts) > 1 else None,
            'timestamp': parts[2] if len(parts) > 2 else None,
            'source': 'positions'
        }
    
    # 2. VOX grades (freshest, most comprehensive)
    vox = query(f"SELECT vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, action, generated_at FROM vox_grades WHERE ticker = '{ticker}' ORDER BY generated_at DESC LIMIT 1")
    if vox.strip():
        parts = [p.strip() for p in vox.split('|')]
        sources['vox_grades'] = {
            'grade': int(parts[0]) if parts[0].isdigit() else None,
            'technical': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
            'fundamental': int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
            'macro': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None,
            'sector': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None,
            'weather': int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None,
            'sentiment': int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None,
            'action': parts[7] if len(parts) > 7 else None,
            'timestamp': parts[8] if len(parts) > 8 else None,
            'source': 'vox_grades'
        }
    
    # 3. Watchlist grades (check but flag if discrepancy)
    wl = query(f"SELECT vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, graded_at FROM watchlist_grades WHERE ticker = '{ticker}' ORDER BY graded_at DESC LIMIT 1")
    if wl.strip():
        parts = [p.strip() for p in wl.split('|')]
        sources['watchlist'] = {
            'grade': int(parts[0]) if parts[0].isdigit() else None,
            'technical': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
            'fundamental': int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
            'macro': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None,
            'sector': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None,
            'weather': int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None,
            'sentiment': int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None,
            'timestamp': parts[7] if len(parts) > 7 else None,
            'source': 'watchlist'
        }
    
    # 4. SP500 grades
    sp = query(f"SELECT vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, computed_at FROM sp500_grades WHERE ticker = '{ticker}' ORDER BY computed_at DESC LIMIT 1")
    if sp.strip():
        parts = [p.strip() for p in sp.split('|')]
        sources['sp500'] = {
            'grade': int(parts[0]) if parts[0].isdigit() else None,
            'technical': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
            'fundamental': int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
            'macro': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None,
            'sector': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None,
            'weather': int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None,
            'sentiment': int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None,
            'timestamp': parts[7] if len(parts) > 7 else None,
            'source': 'sp500'
        }
    
    # 5. Trade signals
    ts = query(f"SELECT signal_type, composite_score, grade, created_at FROM trade_signals WHERE ticker = '{ticker}' ORDER BY created_at DESC LIMIT 1")
    if ts.strip():
        parts = [p.strip() for p in ts.split('|')]
        sources['trade_signals'] = {
            'signal': parts[0] if len(parts) > 0 else None,
            'composite': int(parts[1]) if len(parts) > 1 and parts[1].replace('.', '').isdigit() else None,
            'grade': int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
            'timestamp': parts[3] if len(parts) > 3 else None,
            'source': 'trade_signals'
        }
    
    # Determine unified grade
    # Priority: positions (if exists) > vox_grades (freshest) > sp500 > watchlist (flagged)
    unified = {
        'ticker': ticker,
        'sources': sources,
        'discrepancies': [],
        'warnings': []
    }
    
    # Find all grades
    grades = []
    for source_name, source_data in sources.items():
        if source_data.get('grade') is not None:
            grades.append((source_name, source_data['grade'], source_data.get('timestamp')))
    
    if not grades:
        unified['grade'] = None
        unified['source'] = None
        return unified
    
    # Check for discrepancies > 10 points
    if len(grades) > 1:
        grade_values = [g[1] for g in grades]
        max_diff = max(grade_values) - min(grade_values)
        if max_diff > 10:
            unified['discrepancies'].append({
                'type': 'GRADE_DISCREPANCY',
                'severity': 'HIGH' if max_diff > 20 else 'MEDIUM',
                'max_diff': max_diff,
                'grades': {g[0]: g[1] for g in grades}
            })
    
    # Check for watchlist inflation
    if 'watchlist' in sources and 'vox_grades' in sources:
        wl_grade = sources['watchlist']['grade']
        vox_grade = sources['vox_grades']['grade']
        if wl_grade and vox_grade and wl_grade > vox_grade + 15:
            unified['warnings'].append({
                'type': 'WATCHLIST_INFLATION',
                'message': f'Watchlist grade ({wl_grade}) is {wl_grade - vox_grade} points higher than vox_grades ({vox_grade})',
                'recommendation': 'Use vox_grades as authoritative source'
            })
    
    # Select authoritative grade
    # Priority 1: positions (current holdings)
    if 'positions' in sources:
        unified['grade'] = sources['positions']['grade']
        unified['council'] = sources['positions'].get('council')
        unified['source'] = 'positions'
        unified['timestamp'] = sources['positions'].get('timestamp')
    # Priority 2: vox_grades (most comprehensive, freshest)
    elif 'vox_grades' in sources:
        unified['grade'] = sources['vox_grades']['grade']
        unified['council'] = sources['vox_grades'].get('action')
        unified['source'] = 'vox_grades'
        unified['timestamp'] = sources['vox_grades'].get('timestamp')
    # Priority 3: sp500
    elif 'sp500' in sources:
        unified['grade'] = sources['sp500']['grade']
        unified['council'] = None
        unified['source'] = 'sp500'
        unified['timestamp'] = sources['sp500'].get('timestamp')
    # Priority 4: watchlist (with warning)
    elif 'watchlist' in sources:
        unified['grade'] = sources['watchlist']['grade']
        unified['council'] = None
        unified['source'] = 'watchlist'
        unified['timestamp'] = sources['watchlist'].get('timestamp')
        unified['warnings'].append({
            'type': 'WATCHLIST_ONLY',
            'message': 'Grade from watchlist only — may be inflated'
        })
    else:
        unified['grade'] = grades[0][1]
        unified['source'] = grades[0][0]
    
    return unified

if __name__ == '__main__':
    print("VOX UNIFIED GRADING SYSTEM v2")
    print("Testing grade unification...")
    print()
    
    test_tickers = ['IONQ', 'SE', 'NVO', 'BAC', 'VRT', 'ESTC', 'NOW', 'CEG', 'TSM', 'QQQ', 'AMD', 'CRSP', 'META']
    
    results = {}
    for ticker in test_tickers:
        result = get_unified_grade(ticker)
        results[ticker] = result
        
        print(f"{ticker:>8} | Grade: {result['grade']:>3} | Source: {result['source']:12s} | Council: {result.get('council', 'N/A'):<6}", end="")
        
        if result['discrepancies']:
            print(f" | ⚠️ DISCREPANCY: {result['discrepancies'][0]['max_diff']} points", end="")
        
        if result['warnings']:
            print(f" | ⚠️ {result['warnings'][0]['type']}", end="")
        
        print()
        
        # Show all sources
        for source_name, source_data in result['sources'].items():
            if source_data.get('grade') is not None:
                print(f"           {source_name:15s}: {source_data['grade']:>3} @ {source_data.get('timestamp', 'N/A')}")
        print()
    
    # Save to file
    output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_unified_grades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_file}")
    print("\nSUMMARY:")
    print(f"  Total tested: {len(test_tickers)}")
    print(f"  With discrepancies: {sum(1 for r in results.values() if r['discrepancies'])}")
    print(f"  With warnings: {sum(1 for r in results.values() if r['warnings'])}")
    print(f"  Using positions: {sum(1 for r in results.values() if r['source'] == 'positions')}")
    print(f"  Using vox_grades: {sum(1 for r in results.values() if r['source'] == 'vox_grades')}")
    print(f"  Using watchlist: {sum(1 for r in results.values() if r['source'] == 'watchlist')}")
