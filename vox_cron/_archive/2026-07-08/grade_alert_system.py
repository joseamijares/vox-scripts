import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, psycopg2, json
from datetime import datetime, timedelta
from collections import defaultdict
from decimal import Decimal

def get_db_connection():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net',
        port=35577,
        database='railway',
        user='postgres',
        pwd = os.environ.get('PGPASSWORD', os.environ.get('DB_PASSWORD', ''))
    )

def check_grade_changes():
    """Check for significant grade changes and generate alerts"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("🔍 Checking for grade changes...")
    
    # Get current grades from positions table
    cur.execute("""
        SELECT ticker, grade, council, sector
        FROM positions
        WHERE grade IS NOT NULL
    """)
    
    current_grades = {row[0]: {'grade': row[1], 'council': row[2], 'sector': row[3]} for row in cur.fetchall()}
    
    # Get previous grades from broker_positions (last sync)
    cur.execute("""
        SELECT DISTINCT ON (ticker)
            ticker, grade, council
        FROM broker_positions
        WHERE grade IS NOT NULL
        ORDER BY ticker, last_sync_at DESC
    """)
    
    previous_grades = {row[0]: {'grade': row[1], 'council': row[2]} for row in cur.fetchall()}
    
    alerts = []
    
    # Check for grade changes
    for ticker, current in current_grades.items():
        if ticker in previous_grades:
            prev = previous_grades[ticker]
            grade_change = current['grade'] - prev['grade']
            
            # Alert if grade changed by 5+ points or council changed
            if abs(grade_change) >= 5 or current['council'] != prev['council']:
                alerts.append({
                    'ticker': ticker,
                    'previous_grade': prev['grade'],
                    'current_grade': current['grade'],
                    'grade_change': grade_change,
                    'previous_council': prev['council'],
                    'current_council': current['council'],
                    'severity': 'HIGH' if abs(grade_change) >= 10 or current['council'] != prev['council'] else 'MEDIUM'
                })
    
    # Check for new positions without grades
    cur.execute("""
        SELECT bp.ticker, bp.broker, bp.live_value_usd
        FROM broker_positions bp
        LEFT JOIN positions p ON bp.ticker = p.ticker
        WHERE p.grade IS NULL AND bp.live_value_usd > 100
    """)
    
    for row in cur.fetchall():
        ticker, broker, value = row
        alerts.append({
            'ticker': ticker,
            'broker': broker,
            'value_usd': float(value),
            'severity': 'LOW',
            'message': f'New position without grade: {ticker} in {broker}'
        })
    
    conn.close()
    
    return alerts

def generate_alert_report(alerts):
    """Generate alert report"""
    if not alerts:
        print("✅ No significant grade changes detected")
        return
    
    print(f"\n🚨 ALERTS: {len(alerts)} detected")
    print("=" * 80)
    
    high_alerts = [a for a in alerts if a.get('severity') == 'HIGH']
    medium_alerts = [a for a in alerts if a.get('severity') == 'MEDIUM']
    low_alerts = [a for a in alerts if a.get('severity') == 'LOW']
    
    if high_alerts:
        print(f"\n🔴 HIGH SEVERITY ({len(high_alerts)}):")
        for alert in high_alerts:
            if 'grade_change' in alert:
                direction = "📈 UP" if alert['grade_change'] > 0 else "📉 DOWN"
                print(f"  {alert['ticker']}: Grade {alert['previous_grade']} → {alert['current_grade']} ({direction} {abs(alert['grade_change'])})")
                if alert['previous_council'] != alert['current_council']:
                    print(f"    Council changed: {alert['previous_council']} → {alert['current_council']}")
    
    if medium_alerts:
        print(f"\n🟡 MEDIUM SEVERITY ({len(medium_alerts)}):")
        for alert in medium_alerts:
            direction = "📈 UP" if alert['grade_change'] > 0 else "📉 DOWN"
            print(f"  {alert['ticker']}: Grade {alert['previous_grade']} → {alert['current_grade']} ({direction} {abs(alert['grade_change'])})")
    
    if low_alerts:
        print(f"\n🟢 LOW SEVERITY ({len(low_alerts)}):")
        for alert in low_alerts:
            print(f"  {alert['message']} (${alert['value_usd']:,.2f})")
    
    # Save alerts to JSON
    output = {
        'generated_at': datetime.now().isoformat(),
        'alert_count': len(alerts),
        'high': high_alerts,
        'medium': medium_alerts,
        'low': low_alerts
    }
    
    output_path = os.path.expanduser('~/.hermes/scripts/vox_cron/grade_alerts.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Alerts saved to {output_path}")

def main():
    print("=" * 80)
    print("GRADE CHANGE ALERT SYSTEM")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    alerts = check_grade_changes()
    generate_alert_report(alerts)
    
    print("\n✅ Alert check complete")

if __name__ == "__main__":
    main()
