#!/usr/bin/env python3
"""
VOX CROSS-VALIDATOR
Reads vox_master_data_*.json and checks for contradictions across all sources.
Outputs a unified report with discrepancies flagged.
"""

import json
import glob
import os
from datetime import datetime

def get_latest_master_data():
    files = glob.glob('/Users/jos/.hermes/scripts/vox_cron/vox_master_data_*.json')
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    with open(latest) as f:
        return json.load(f)

def cross_validate(data):
    issues = []
    warnings = []
    
    # Extract positions grades
    pos_grades = {}
    if 'positions' in data.get('data', {}):
        for line in data['data']['positions'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                pos_grades[parts[0]] = int(parts[1]) if parts[1].isdigit() else 0
    
    # Extract vox_grades
    vox_grades = {}
    if 'vox_grades' in data.get('data', {}):
        for line in data['data']['vox_grades'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                vox_grades[parts[0]] = int(parts[1]) if parts[1].isdigit() else 0
    
    # Extract watchlist grades
    watch_grades = {}
    if 'watchlist_grades' in data.get('data', {}):
        for line in data['data']['watchlist_grades'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                watch_grades[parts[0]] = int(parts[1]) if parts[1].isdigit() else 0
    
    # Extract sp500 grades
    sp500_grades = {}
    if 'sp500_grades' in data.get('data', {}):
        for line in data['data']['sp500_grades'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                sp500_grades[parts[0]] = int(parts[1]) if parts[1].isdigit() else 0
    
    # Cross-validate: positions vs vox_grades
    for ticker, pos_grade in pos_grades.items():
        if ticker in vox_grades:
            diff = abs(pos_grade - vox_grades[ticker])
            if diff >= 5:
                issues.append(f"GRADE MISMATCH: {ticker} | positions={pos_grade} | vox_grades={vox_grades[ticker]} | diff={diff}")
    
    # Cross-validate: positions vs watchlist
    for ticker, pos_grade in pos_grades.items():
        if ticker in watch_grades:
            diff = abs(pos_grade - watch_grades[ticker])
            if diff >= 5:
                issues.append(f"WATCHLIST MISMATCH: {ticker} | positions={pos_grade} | watchlist={watch_grades[ticker]} | diff={diff}")
    
    # Cross-validate: positions vs sp500
    for ticker, pos_grade in pos_grades.items():
        if ticker in sp500_grades:
            diff = abs(pos_grade - sp500_grades[ticker])
            if diff >= 5:
                issues.append(f"SP500 MISMATCH: {ticker} | positions={pos_grade} | sp500={sp500_grades[ticker]} | diff={diff}")
    
    # Check for stale data
    if 'market_regime' in data.get('data', {}):
        regime_data = data['data']['market_regime'].get('data', [])
        if regime_data:
            # Parse timestamp
            pass
    
    return issues, warnings

def generate_unified_report(data):
    issues, warnings = cross_validate(data)
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'master_data_source': data.get('generated_at', 'unknown'),
        'sources_checked': data.get('sources_checked', []),
        'cross_validation_issues': issues,
        'warnings': warnings,
        'unified_summary': {}
    }
    
    # Build unified ticker list with all grades
    all_tickers = {}
    
    # Positions
    if 'positions' in data.get('data', {}):
        for line in data['data']['positions'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 6:
                ticker = parts[0]
                all_tickers[ticker] = {
                    'position_grade': int(parts[1]) if parts[1].isdigit() else 0,
                    'council': parts[2],
                    'brokers': parts[3],
                    'sector': parts[4],
                    'value': float(parts[5]) if parts[5] else 0,
                    'currency': parts[6] if len(parts) > 6 else 'USD'
                }
    
    # Add vox_grades
    if 'vox_grades' in data.get('data', {}):
        for line in data['data']['vox_grades'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                ticker = parts[0]
                if ticker in all_tickers:
                    all_tickers[ticker]['vox_grade'] = int(parts[1]) if parts[1].isdigit() else 0
                else:
                    all_tickers[ticker] = {'vox_grade': int(parts[1]) if parts[1].isdigit() else 0}
    
    # Add watchlist grades
    if 'watchlist_grades' in data.get('data', {}):
        for line in data['data']['watchlist_grades'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                ticker = parts[0]
                if ticker in all_tickers:
                    all_tickers[ticker]['watchlist_grade'] = int(parts[1]) if parts[1].isdigit() else 0
                else:
                    all_tickers[ticker] = {'watchlist_grade': int(parts[1]) if parts[1].isdigit() else 0}
    
    # Add sp500 grades
    if 'sp500_grades' in data.get('data', {}):
        for line in data['data']['sp500_grades'].get('data', []):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                ticker = parts[0]
                if ticker in all_tickers:
                    all_tickers[ticker]['sp500_grade'] = int(parts[1]) if parts[1].isdigit() else 0
                else:
                    all_tickers[ticker] = {'sp500_grade': int(parts[1]) if parts[1].isdigit() else 0}
    
    report['unified_summary'] = all_tickers
    
    # Save report
    output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_unified_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    return report, output_file

if __name__ == '__main__':
    print("VOX CROSS-VALIDATOR")
    print("="*70)
    
    data = get_latest_master_data()
    if not data:
        print("ERROR: No master data found. Run vox_master_collector.py first.")
        exit(1)
    
    report, output_file = generate_unified_report(data)
    
    print(f"Master data: {data.get('generated_at', 'unknown')}")
    print(f"Sources checked: {len(data.get('sources_checked', []))}")
    print(f"Tickers in unified summary: {len(report['unified_summary'])}")
    print(f"Cross-validation issues: {len(report['cross_validation_issues'])}")
    print()
    
    if report['cross_validation_issues']:
        print("⚠️ ISSUES FOUND:")
        for issue in report['cross_validation_issues'][:10]:
            print(f"  {issue}")
        if len(report['cross_validation_issues']) > 10:
            print(f"  ... and {len(report['cross_validation_issues']) - 10} more")
    else:
        print("✅ No cross-validation issues found.")
    
    print()
    print(f"Report saved to: {output_file}")
    print()
    print("This is your SINGLE SOURCE OF TRUTH.")
    print("Use it for ALL recommendations.")
