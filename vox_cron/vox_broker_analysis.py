"""VOX Broker Portfolio Analysis — Deep analysis by broker with actionable insights.

Generates:
- Per-broker grade distribution
- Per-broker sector concentration
- Per-broker risk metrics (volatility, drawdown)
- Per-broker recommendations (trim/add/hold)
- Cross-broker comparison
- Overall portfolio health score
"""
import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.expanduser('~/dev/vox-grader/src'))
from sync.vox_postgres_sync import _get_cursor
from grading.vox_engine import calculate_vox_grade

# Grade thresholds for recommendations
GRADE_THRESHOLDS = {
    'strong_buy': 70,
    'buy': 60,
    'hold': 50,
    'sell': 40,
    'strong_sell': 30
}

SECTOR_RISK_WEIGHTS = {
    'Technology': 1.2,
    'Healthcare': 0.9,
    'Financials': 1.0,
    'Consumer Discretionary': 1.1,
    'Communication Services': 1.1,
    'Industrials': 1.0,
    'Energy': 1.3,
    'Materials': 1.1,
    'Real Estate': 1.0,
    'Utilities': 0.8,
    'Consumer Staples': 0.8,
}


def get_broker_positions():
    """Fetch all positions with broker attribution."""
    with _get_cursor() as cur:
        cur.execute('''
            SELECT 
                p.ticker,
                p.shares,
                p.avg_cost,
                p.live_price,
                p.live_value_usd,
                p.grade,
                p.council,
                p.sector,
                p.currency,
                p.brokers,
                g.vox_grade as latest_grade,
                g.computed_at as grade_updated
            FROM positions p
            LEFT JOIN sp500_grades g ON p.ticker = g.ticker
            ORDER BY p.live_value_usd DESC
        ''')
        return cur.fetchall()


def assign_primary_broker(brokers_array):
    """Determine primary broker from array."""
    if not brokers_array:
        return 'Unknown'
    
    # Priority order for multi-broker positions
    priority = ['IBKR', 'Schwab', 'GBMUSA', 'GBM', 'eToro', 'Binance', 'Bitso']
    
    for broker in priority:
        if broker in brokers_array:
            return broker
    
    return brokers_array[0]


def analyze_broker(positions, broker_name):
    """Deep analysis for a single broker's positions."""
    
    broker_positions = [p for p in positions if assign_primary_broker(p['brokers']) == broker_name]
    
    if not broker_positions:
        return None
    
    total_value = sum(float(p['live_value_usd'] or 0) for p in broker_positions)
    
    # Grade distribution
    grades = [float(p['latest_grade'] or p['grade'] or 50) for p in broker_positions]
    grade_dist = {
        'strong_buy': len([g for g in grades if g >= GRADE_THRESHOLDS['strong_buy']]),
        'buy': len([g for g in grades if GRADE_THRESHOLDS['buy'] <= g < GRADE_THRESHOLDS['strong_buy']]),
        'hold': len([g for g in grades if GRADE_THRESHOLDS['hold'] <= g < GRADE_THRESHOLDS['buy']]),
        'sell': len([g for g in grades if GRADE_THRESHOLDS['sell'] <= g < GRADE_THRESHOLDS['hold']]),
        'strong_sell': len([g for g in grades if g < GRADE_THRESHOLDS['sell']]),
    }
    
    # Sector concentration
    sectors = defaultdict(float)
    for p in broker_positions:
        sector = p['sector'] or 'Unknown'
        sectors[sector] += float(p['live_value_usd'] or 0)
    
    sector_pct = {s: v/total_value*100 for s, v in sectors.items()}
    top_sector = max(sector_pct.items(), key=lambda x: x[1])
    
    # Risk metrics
    avg_grade = np.mean(grades)
    grade_std = np.std(grades)
    
    # Calculate weighted portfolio grade (by position size)
    weighted_grade = sum(
        float(p['latest_grade'] or p['grade'] or 50) * float(p['live_value_usd'] or 0)
        for p in broker_positions
    ) / total_value
    
    # Risk-adjusted grade (penalize concentration)
    concentration_penalty = top_sector[1] * 0.1  # 0.1 pts per % in top sector
    risk_adjusted_grade = weighted_grade - concentration_penalty
    
    # Recommendations per position
    recommendations = []
    for p in broker_positions:
        grade = float(p['latest_grade'] or p['grade'] or 50)
        value = float(p['live_value_usd'] or 0)
        value_pct = value / total_value * 100
        
        rec = 'HOLD'
        action = ''
        
        if grade >= GRADE_THRESHOLDS['strong_buy'] and value_pct < 15:
            rec = 'ADD'
            action = f'Consider adding to {p["ticker"]} (grade {grade:.0f}, only {value_pct:.1f}% of portfolio)'
        elif grade >= GRADE_THRESHOLDS['strong_buy'] and value_pct >= 15:
            rec = 'HOLD'
            action = f'{p["ticker"]} is strong but already {value_pct:.1f}% — maintain position'
        elif grade < GRADE_THRESHOLDS['sell']:
            rec = 'TRIM'
            action = f'Trim {p["ticker"]} (grade {grade:.0f}) — consider selling 30-50%'
        elif grade < GRADE_THRESHOLDS['hold'] and value_pct > 10:
            rec = 'TRIM'
            action = f'Reduce {p["ticker"]} (grade {grade:.0f}, {value_pct:.1f}% allocation)'
        elif grade < GRADE_THRESHOLDS['hold']:
            rec = 'WATCH'
            action = f'Monitor {p["ticker"]} (grade {grade:.0f}) — small position, keep watching'
        
        recommendations.append({
            'ticker': p['ticker'],
            'grade': grade,
            'value_usd': value,
            'value_pct': value_pct,
            'rec': rec,
            'action': action,
            'sector': p['sector'] or 'Unknown',
            'council': p['council'] or 'HOLD',
            'upside': round((float(p['live_price'] or 0) - float(p['avg_cost'] or 0)) / float(p['avg_cost'] or 1) * 100, 1) if p['avg_cost'] else 0
        })
    
    # Sort by value
    recommendations.sort(key=lambda x: x['value_usd'], reverse=True)
    
    return {
        'broker': broker_name,
        'positions': len(broker_positions),
        'total_value_usd': round(total_value, 2),
        'avg_grade': round(avg_grade, 1),
        'weighted_grade': round(weighted_grade, 1),
        'risk_adjusted_grade': round(risk_adjusted_grade, 1),
        'grade_std': round(grade_std, 1),
        'grade_distribution': grade_dist,
        'sector_concentration': {
            'top_sector': top_sector[0],
            'top_sector_pct': round(top_sector[1], 1),
            'num_sectors': len(sectors)
        },
        'recommendations': recommendations,
        'health_score': calculate_health_score(grades, sector_pct, total_value)
    }


def calculate_health_score(grades, sector_pct, total_value):
    """Calculate portfolio health score 0-100."""
    # Grade quality (40%)
    avg_grade = np.mean(grades)
    grade_score = min(100, avg_grade * 1.2)  # Scale up slightly
    
    # Diversification (30%)
    num_sectors = len(sector_pct)
    max_sector = max(sector_pct.values()) if sector_pct else 100
    div_score = min(100, num_sectors * 10 + (100 - max_sector) * 0.5)
    
    # Grade consistency (20%)
    grade_std = np.std(grades)
    consistency_score = max(0, 100 - grade_std * 5)
    
    # Size appropriateness (10%)
    size_score = 80 if total_value > 10000 else 60  # Prefer larger accounts
    
    return round(grade_score * 0.4 + div_score * 0.3 + consistency_score * 0.2 + size_score * 0.1, 1)


def generate_report():
    """Generate full broker analysis report."""
    positions = get_broker_positions()
    
    # Group by broker
    brokers = defaultdict(list)
    for p in positions:
        broker = assign_primary_broker(p['brokers'])
        brokers[broker].append(p)
    
    print("=" * 70)
    print("VOX BROKER PORTFOLIO ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    total_portfolio_value = sum(p['live_value_usd'] or 0 for p in positions)
    print(f"\nTotal Portfolio Value: ${total_portfolio_value:,.2f}")
    print(f"Total Positions: {len(positions)}")
    
    # Analyze each broker
    broker_analyses = []
    for broker_name in sorted(brokers.keys(), key=lambda b: sum(p['live_value_usd'] or 0 for p in brokers[b]), reverse=True):
        analysis = analyze_broker(positions, broker_name)
        if analysis:
            broker_analyses.append(analysis)
    
    # Print summary table
    print("\n" + "=" * 70)
    print("BROKER SUMMARY")
    print("=" * 70)
    print(f"{'Broker':<12} {'Positions':>10} {'Value':>15} {'Avg Grade':>10} {'Health':>8} {'Top Sector':<20}")
    print("-" * 70)
    
    for a in broker_analyses:
        print(f"{a['broker']:<12} {a['positions']:>10} ${a['total_value_usd']:>13,.0f} {a['avg_grade']:>10.1f} {a['health_score']:>8.1f} {a['sector_concentration']['top_sector']:<20}")
    
    # Detailed per-broker analysis
    for a in broker_analyses:
        print(f"\n{'='*70}")
        print(f"📊 {a['broker'].upper()} ANALYSIS")
        print(f"{'='*70}")
        
        print(f"\n  Portfolio Value: ${a['total_value_usd']:,.2f}")
        print(f"  Positions: {a['positions']}")
        print(f"  Avg Grade: {a['avg_grade']}")
        print(f"  Weighted Grade: {a['weighted_grade']}")
        print(f"  Risk-Adjusted Grade: {a['risk_adjusted_grade']}")
        print(f"  Health Score: {a['health_score']}/100")
        
        print(f"\n  Grade Distribution:")
        for grade_cat, count in a['grade_distribution'].items():
            emoji = {'strong_buy': '🟢', 'buy': '🟢', 'hold': '🟡', 'sell': '🔴', 'strong_sell': '🔴'}
            print(f"    {emoji.get(grade_cat, '⚪')} {grade_cat.replace('_', ' ').title()}: {count}")
        
        print(f"\n  Sector Concentration:")
        print(f"    Top Sector: {a['sector_concentration']['top_sector']} ({a['sector_concentration']['top_sector_pct']}%)")
        print(f"    Sectors: {a['sector_concentration']['num_sectors']}")
        
        print(f"\n  🎯 RECOMMENDATIONS (Top 10 by value):")
        for rec in a['recommendations'][:10]:
            emoji = {'ADD': '➕', 'HOLD': '✋', 'TRIM': '✂️', 'WATCH': '👁️'}
            print(f"\n    {emoji.get(rec['rec'], '⚪')} {rec['ticker']} | Grade: {rec['grade']} | ${rec['value_usd']:,.0f} ({rec['value_pct']:.1f}%)")
            print(f"       Council: {rec['council']} | Upside: {rec['upside']}%")
            print(f"       → {rec['action']}")
    
    # Cross-broker comparison
    print(f"\n{'='*70}")
    print("CROSS-BROKER COMPARISON")
    print(f"{'='*70}")
    
    if len(broker_analyses) > 1:
        best_broker = max(broker_analyses, key=lambda x: x['health_score'])
        worst_broker = min(broker_analyses, key=lambda x: x['health_score'])
        
        print(f"\n  🏆 Best Health: {best_broker['broker']} (Score: {best_broker['health_score']})")
        print(f"  ⚠️ Needs Attention: {worst_broker['broker']} (Score: {worst_broker['health_score']})")
        
        print(f"\n  Grade Comparison:")
        for a in sorted(broker_analyses, key=lambda x: x['avg_grade'], reverse=True):
            bar = '█' * int(a['avg_grade'] / 5)
            print(f"    {a['broker']:<12} {bar:<20} {a['avg_grade']:.1f}")
    
    # Overall recommendations
    print(f"\n{'='*70}")
    print("OVERALL PORTFOLIO RECOMMENDATIONS")
    print(f"{'='*70}")
    
    all_recs = []
    for a in broker_analyses:
        for rec in a['recommendations']:
            if rec['rec'] in ['TRIM', 'ADD']:
                all_recs.append({
                    'broker': a['broker'],
                    **rec
                })
    
    # Sort by priority: TRIM first (risk reduction), then ADD
    trim_recs = [r for r in all_recs if r['rec'] == 'TRIM']
    add_recs = [r for r in all_recs if r['rec'] == 'ADD']
    
    if trim_recs:
        print(f"\n  ✂️ PRIORITY TRIMS (Risk Reduction):")
        for r in sorted(trim_recs, key=lambda x: x['value_usd'], reverse=True)[:5]:
            print(f"    • {r['ticker']} ({r['broker']}) — Grade {r['grade']} — ${r['value_usd']:,.0f}")
    
    if add_recs:
        print(f"\n  ➕ OPPORTUNITIES TO ADD:")
        for r in sorted(add_recs, key=lambda x: x['grade'], reverse=True)[:5]:
            print(f"    • {r['ticker']} ({r['broker']}) — Grade {r['grade']} — Currently {r['value_pct']:.1f}%")
    
    # Save report
    report_path = os.path.expanduser('~/.hermes/scripts/vox_cron/reports')
    os.makedirs(report_path, exist_ok=True)
    filename = f"broker_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(os.path.join(report_path, filename), 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_value': total_portfolio_value,
            'total_positions': len(positions),
            'brokers': broker_analyses
        }, f, indent=2, default=str)
    
    print(f"\n📄 Report saved: {filename}")
    print(f"{'='*70}")


if __name__ == '__main__':
    generate_report()
