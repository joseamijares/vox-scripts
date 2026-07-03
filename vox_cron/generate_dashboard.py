import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, psycopg2, json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_unified_grades():
    """Load unified grades from single source of truth"""
    unified_path = SCRIPT_DIR / "vox_unified_grades.json"
    if not unified_path.exists():
        return {}
    with open(unified_path) as f:
        return json.load(f)

def get_unified_grade(ticker, unified_grades):
    """Get grade from unified source"""
    if ticker in unified_grades.get("grades", {}):
        return unified_grades["grades"][ticker].get("grade", 0)
    return 0


def get_db_password():
    return os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))

def get_db_connection():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net',
        port=35577,
        database='railway',
        user='postgres',
        password=get_db_password()
    )

def generate_dashboard_data():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all positions from unified positions table (not broker_positions)
    cur.execute("""
        SELECT 
            ticker,
            shares,
            live_price,
            live_value,
            grade,
            council,
            sector,
            brokers,
            updated_at
        FROM positions
        WHERE live_value > 0
        ORDER BY live_value DESC
    """)
    
    broker_data = defaultdict(list)
    for row in cur.fetchall():
        ticker, shares, price, value, grade, council, sector, brokers, updated_at = row
        # Group by first broker for display purposes
        broker = brokers[0] if brokers else 'Unknown'
        broker_data[broker].append({
            'ticker': ticker,
            'shares': float(shares) if shares else 0,
            'price': float(price) if price else 0,
            'value_usd': float(value) if value else 0,
            'grade': grade,
            'council': council,
            'sector': sector,
            'brokers': brokers,
            'last_sync': updated_at.isoformat() if updated_at else None
        })
    
    # Calculate summary metrics
    summary = {}
    grand_total = 0
    
    for broker, positions in broker_data.items():
        total = sum(p['value_usd'] for p in positions)
        grand_total += total
        
        grades = [p['grade'] for p in positions if p['grade'] is not None]
        avg_grade = sum(grades) / len(grades) if grades else 0
        
        councils = defaultdict(float)
        for p in positions:
            if p['council'] and p['value_usd'] > 0:
                councils[p['council']] += p['value_usd']
        
        summary[broker] = {
            'positions': len(positions),
            'total_usd': total,
            'avg_grade': avg_grade,
            'councils': dict(councils),
            'top_positions': sorted(positions, key=lambda x: x['value_usd'], reverse=True)[:10]
        }
    
    # Overall metrics
    all_positions = []
    for positions in broker_data.values():
        all_positions.extend(positions)
    
    all_grades = [p['grade'] for p in all_positions if p['grade'] is not None]
    all_councils = defaultdict(float)
    for p in all_positions:
        if p['council'] and p['value_usd'] > 0:
            all_councils[p['council']] += p['value_usd']
    
    dashboard_data = {
        'generated_at': datetime.now().isoformat(),
        'grand_total': grand_total,
        'total_positions': len(all_positions),
        'avg_grade': sum(all_grades) / len(all_grades) if all_grades else 0,
        'grade_distribution': {
            'A (80-100)': len([g for g in all_grades if g >= 80]),
            'B (60-79)': len([g for g in all_grades if 60 <= g < 80]),
            'C (40-59)': len([g for g in all_grades if 40 <= g < 60]),
            'D (0-39)': len([g for g in all_grades if g < 40])
        },
        'council_distribution': dict(all_councils),
        'broker_summary': summary,
        'all_positions': sorted(all_positions, key=lambda x: x['value_usd'], reverse=True)[:50]
    }
    
    # Save to JSON
    output_path = os.path.expanduser('~/.hermes/scripts/vox_cron/portfolio_dashboard.json')
    with open(output_path, 'w') as f:
        json.dump(dashboard_data, f, indent=2)
    
    print(f"✅ Dashboard data saved to {output_path}")
    
    conn.close()
    return dashboard_data

if __name__ == "__main__":
    data = generate_dashboard_data()
    print(f"\n📊 Portfolio Dashboard Generated")
    print(f"Grand Total: ${data['grand_total']:,.2f}")
    print(f"Total Positions: {data['total_positions']}")
    print(f"Average Grade: {data['avg_grade']:.1f}")
