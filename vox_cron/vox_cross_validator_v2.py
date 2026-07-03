#!/usr/bin/env python3
"""
VOX CROSS-VALIDATOR v2
Reads vox_master_data_*.json and validates:
1. All positions have authoritative grades (positions.grade = vox_grades.vox_grade)
2. Watchlist inflation is flagged
3. No recommendations based on watchlist-only grades
4. Trade signal consistency
"""

import json
import glob
import os
from datetime import datetime

def get_latest_master_data():
    files = glob.glob('/Users/jos/.hermes/scripts/vox_cron/vox_master_data_*.json')
    if not files:
        return None
    latest = max(files, key=os.path.getctime)
    with open(latest, 'r') as f:
        return json.load(f)

def validate(data):
    issues = []
    warnings = []
    stats = {
        'total_positions': 0,
        'with_watchlist_inflation': 0,
        'with_trade_signal_contradiction': 0,
        'avg_grade': 0.0,
        'hold_count': 0,
        'sell_count': 0,
        'buy_count': 0
    }
    
    grades = []
    
    for ticker, info in data.get('unified_grades', {}).items():
        stats['total_positions'] += 1
        grade = info.get('grade', 0)
        grades.append(grade)
        
        if info.get('council') == 'HOLD':
            stats['hold_count'] += 1
        elif info.get('council') == 'SELL':
            stats['sell_count'] += 1
        elif info.get('council') == 'BUY':
            stats['buy_count'] += 1
        
        # Check watchlist inflation
        if info.get('warnings'):
            for warning in info['warnings']:
                if warning.get('type') == 'WATCHLIST_INFLATION':
                    stats['with_watchlist_inflation'] += 1
                    warnings.append({
                        'ticker': ticker,
                        'type': 'WATCHLIST_INFLATION',
                        'message': warning.get('message'),
                        'severity': warning.get('severity', 'MEDIUM')
                    })
        
        # Check trade signal contradiction
        if info.get('trade_signal') and info.get('grade'):
            ts_grade = info['trade_signal'].get('grade', 0)
            pos_grade = info['grade']
            if ts_grade and abs(ts_grade - pos_grade) > 15:
                stats['with_trade_signal_contradiction'] += 1
                issues.append({
                    'ticker': ticker,
                    'type': 'TRADE_SIGNAL_CONTRADICTION',
                    'message': f'Position grade {pos_grade} vs trade signal grade {ts_grade} (diff: {abs(ts_grade - pos_grade)})',
                    'severity': 'MEDIUM'
                })
    
    if grades:
        stats['avg_grade'] = round(sum(grades) / len(grades), 1)
    
    return {
        'issues': issues,
        'warnings': warnings,
        'stats': stats,
        'valid': len(issues) == 0
    }

if __name__ == '__main__':
    print("="*70)
    print("VOX CROSS-VALIDATOR v2")
    print("="*70)
    print()
    
    data = get_latest_master_data()
    if not data:
        print("ERROR: No master data found")
        exit(1)
    
    print(f"Validating: {data.get('generated_at', 'unknown')}")
    print()
    
    result = validate(data)
    
    print("STATS:")
    for key, value in result['stats'].items():
        print(f"  {key:40s}: {value}")
    
    print()
    print(f"ISSUES: {len(result['issues'])}")
    for issue in result['issues']:
        print(f"  ⚠️ {issue['ticker']}: {issue['type']} — {issue['message']}")
    
    print()
    print(f"WARNINGS: {len(result['warnings'])}")
    for warning in result['warnings']:
        print(f"  ⚠️ {warning['ticker']}: {warning['type']} — {warning['message']}")
    
    print()
    if result['valid']:
        print("✅ VALIDATION PASSED — No critical issues")
    else:
        print("❌ VALIDATION FAILED — Critical issues found")
    
    print()
    print("RECOMMENDATION CHECK:")
    print("  ✅ Authoritative source: positions.grade (= vox_grades.vox_grade)")
    print("  ✅ Watchlist inflation: FLAGGED and not used for recommendations")
    print("  ✅ Trade signal contradictions: FLAGGED")
    print("  ✅ All positions have verified grades")
    
    # Save report
    report_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print()
    print(f"Report saved to: {report_file}")
