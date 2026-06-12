#!/usr/bin/env python3
"""
VOX Data Validation Harness v3 — DYNAMIC SYSTEM

This script:
1. Reads REAL broker API files
2. Compares with user-confirmed values
3. Flags stale/discrepant data
4. Produces dashboard_positions.json with both API and confirmed values
5. Shows data freshness for each broker

CRITICAL: Never use hardcoded values. Always read from source files.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# CONFIG
BROKER_FILES = {
    'eToro': '/Users/jos/.hermes/scripts/etoro_portfolio.json',
    'GBM Main': '/Users/jos/.hermes/scripts/gbm_main_portfolio.json',
    'GBM USA': '/Users/jos/.hermes/scripts/gbm_usa_portfolio.json',
    'Binance': '/Users/jos/.hermes/scripts/binance_portfolio.json',
    'Schwab': '/Users/jos/.hermes/scripts/schwab_portfolio.json',
    'IBKR': '/Users/jos/.hermes/scripts/ibkr_portfolio.json',
    'Bitso': '/Users/jos/.hermes/scripts/bitso_portfolio.json',
}

SOURCE_OF_TRUTH = '/Users/jos/.hermes/scripts/unified_portfolio_current.json'
DASHBOARD_DATA = '/Users/jos/.hermes/scripts/dashboard_positions.json'
DASHBOARD_PUBLIC = '/Users/jos/dev/vox-dashboard/public/dashboard_positions.json'
VALIDATION_LOG = '/Users/jos/.hermes/scripts/.vox_validation_log.json'
MXN_TO_USD = 1 / 17.31

def get_file_age_hours(filepath):
    """Get file age in hours."""
    if not os.path.exists(filepath):
        return float('inf')
    mtime = os.path.getmtime(filepath)
    return (datetime.now().timestamp() - mtime) / 3600

def read_etoro_value():
    """Read eToro total from API file."""
    with open(BROKER_FILES['eToro']) as f:
        data = json.load(f)
    positions = data['clientPortfolio']['positions']
    # Use exposure (current market value)
    total = 0
    for p in positions:
        pnl = p.get('unrealizedPnL', {})
        if isinstance(pnl, dict):
            total += pnl.get('exposureInAccountCurrency', 0)
    return total

def read_gbm_main_value():
    """Read GBM Main total from API file."""
    with open(BROKER_FILES['GBM Main']) as f:
        data = json.load(f)
    mxn = data.get('portfolio_summary', {}).get('total_value_mxn', 0)
    return mxn * MXN_TO_USD

def read_gbm_usa_value():
    """Read GBM USA total from API file."""
    with open(BROKER_FILES['GBM USA']) as f:
        data = json.load(f)
    return data.get('portfolio_summary', {}).get('total_value_usd', 0)

def read_binance_value():
    """Read Binance total from API file."""
    with open(BROKER_FILES['Binance']) as f:
        data = json.load(f)
    return data.get('total_usd', 0)

def read_schwab_value():
    """Read Schwab total from API file."""
    with open(BROKER_FILES['Schwab']) as f:
        data = json.load(f)
    if isinstance(data, dict) and 'portfolio_summary' in data:
        return data['portfolio_summary'].get('total_value', 0)
    return 0

def read_ibkr_value():
    """Read IBKR total from API file."""
    with open(BROKER_FILES['IBKR']) as f:
        data = json.load(f)
    if isinstance(data, dict) and 'portfolio_summary' in data:
        return data['portfolio_summary'].get('total_value', 0)
    return 0

def read_bitso_value():
    """Read Bitso total from API file."""
    with open(BROKER_FILES['Bitso']) as f:
        data = json.load(f)
    return data.get('total_usd', 0)

def get_api_values():
    """Get all broker values from API files."""
    return {
        'eToro': read_etoro_value(),
        'GBM Main': read_gbm_main_value(),
        'GBM USA': read_gbm_usa_value(),
        'Binance': read_binance_value(),
        'Schwab': read_schwab_value(),
        'IBKR': read_ibkr_value(),
        'Bitso': read_bitso_value(),
    }

def get_user_confirmed_values():
    """Get user-confirmed values from unified file."""
    if not os.path.exists(SOURCE_OF_TRUTH):
        return {}
    with open(SOURCE_OF_TRUTH) as f:
        data = json.load(f)
    by_broker = data.get('by_broker', {})
    result = {}
    for b, v in by_broker.items():
        if isinstance(v, dict):
            result[b] = v.get('value_usd', 0)
        else:
            result[b] = v
    return result

def main():
    print("=" * 70)
    print("VOX DATA VALIDATION HARNESS v3 — DYNAMIC BROKER READ")
    print("=" * 70)
    
    # Read API values
    api_values = get_api_values()
    user_values = get_user_confirmed_values()
    
    print("\n📊 BROKER VALUE COMPARISON")
    print(f"{'Broker':<15} {'API Value':>12} {'Confirmed':>12} {'Diff':>12} {'Age':>8} {'Status'}")
    print("-" * 75)
    
    discrepancies = []
    stale_brokers = []
    
    for broker in BROKER_FILES.keys():
        api_val = api_values.get(broker, 0)
        user_val = user_values.get(broker, 0)
        diff = user_val - api_val
        diff_pct = (diff / user_val * 100) if user_val > 0 else 0
        
        age_hours = get_file_age_hours(BROKER_FILES[broker])
        age_str = f"{age_hours:.0f}h" if age_hours < 100 else "OLD"
        
        if abs(diff_pct) > 15:
            status = "❌ CHECK"
            discrepancies.append(f"{broker}: API=${api_val:,.0f} vs Confirmed=${user_val:,.0f}")
        elif age_hours > 48:
            status = "⚠️ STALE"
            stale_brokers.append(broker)
        else:
            status = "✅ OK"
        
        print(f"{broker:<15} ${api_val:>10,.0f} ${user_val:>10,.0f} ${diff:>10,.0f} {age_str:>8} {status}")
    
    # Use USER CONFIRMED values for the dashboard (they're more accurate)
    # But flag which ones are stale
    final_values = user_values.copy()
    
    total = sum(final_values.values())
    print("-" * 75)
    print(f"{'TOTAL':<15} ${sum(api_values.values()):>10,.0f} ${total:>10,.0f}")
    
    if discrepancies:
        print(f"\n❌ DISCREPANCIES ({len(discrepancies)}):")
        for d in discrepancies:
            print(f"   • {d}")
    
    if stale_brokers:
        print(f"\n⚠️  STALE DATA ({len(stale_brokers)}):")
        for b in stale_brokers:
            print(f"   • {b}")
    
    # Read positions from unified file
    with open(SOURCE_OF_TRUTH) as f:
        unified = json.load(f)
    
    positions = unified.get('positions', [])
    
    # Build output
    output = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_value': round(total, 2),
        'total_pnl': round(sum(p.get('pnl', 0) for p in positions), 2),
        'total_positions': len(positions),
        'broker_breakdown': {k: round(v, 2) for k, v in final_values.items()},
        'broker_status': {
            k: {
                'api_value': round(api_values.get(k, 0), 2),
                'confirmed_value': round(user_values.get(k, 0), 2),
                'diff_pct': round((user_values.get(k, 0) - api_values.get(k, 0)) / user_values.get(k, 0) * 100, 1) if user_values.get(k, 0) > 0 else 0,
                'file_age_hours': round(get_file_age_hours(BROKER_FILES[k]), 1),
                'stale': get_file_age_hours(BROKER_FILES[k]) > 48,
            }
            for k in BROKER_FILES.keys()
        },
        'positions': positions,
    }
    
    # Merge grades into positions
    grade_map = {}
    grades_path = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
    if grades_path.exists():
        with open(grades_path) as f:
            grades_data = json.load(f)
        for cat in ['strong_buy', 'moderate_buy', 'avoid']:
            for item in grades_data.get(cat, []):
                grade_map[item['ticker']] = item['grade']
    
    for p in positions:
        p['grade'] = grade_map.get(p['ticker'], 0)

    # Write files
    with open(DASHBOARD_DATA, 'w') as f:
        json.dump(output, f, indent=2)
    
    if os.path.exists(os.path.dirname(DASHBOARD_PUBLIC)):
        shutil.copy(DASHBOARD_DATA, DASHBOARD_PUBLIC)
    
    # Log
    log = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'total_value': round(total, 2),
        'total_positions': len(positions),
        'discrepancies': discrepancies,
        'stale_brokers': stale_brokers,
    }
    with open(VALIDATION_LOG, 'w') as f:
        json.dump(log, f, indent=2)
    
    print(f"\n✅ DATA WRITTEN — Total: ${total:,.2f}")
    print(f"   Brokers: {len(final_values)}")
    print(f"   Positions: {len(positions)}")
    
    return True

if __name__ == '__main__':
    main()
