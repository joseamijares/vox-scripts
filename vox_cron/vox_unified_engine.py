#!/usr/bin/env python3
"""
VOX UNIFIED RESEARCH ENGINE v5.0
Combines VOX Alpha Engine (internal DB) + Discovery Engine (external) + Web Research
into a single daily research pipeline that feeds unified_grades.

Architecture:
  1. Query ALL internal data sources (vox_grades, sp500_grades, watchlist_grades, 
     trade_signals, technical_signals, sentiment_scores, sector_momentum)
  2. Cross-validate and detect contradictions
  3. Query web for top opportunities (price targets, analyst ratings, recent news)
  4. Generate unified scores with confidence levels
  5. Save to unified_grades + generate daily report
  6. Alert on grade 75+ opportunities and contradictions

Target: 25-50% yearly returns (aggressive strategy)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add vox_cron to path for imports
sys.path.insert(0, '/Users/jos/.hermes/scripts/vox_cron')

SCRIPT_DIR = Path.home() / ".hermes" / "scripts" / "vox_cron"

# Load env from ~/.hermes/.env
ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "railway")


def db_query(sql: str) -> List[Tuple]:
    """Execute SQL via psql subprocess (works in cron, no psycopg2 needed)."""
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PASSWORD
    result = subprocess.run([
        'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER,
        '-d', DB_NAME, '-t', '-c', sql
    ], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"SQL Error: {result.stderr[:200]}")
        return []
    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
    return [tuple(l.split('|')) for l in lines]


def db_query_psycopg(sql: str, params=None):
    """Execute SQL via psycopg2 (for inserts/updates)."""
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require"
    )
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    result = cur.fetchall() if cur.description else []
    conn.commit()
    conn.close()
    return result


class VoxUnifiedResearchEngine:
    """
    Unified Research Engine v5.
    
    Combines all VOX data sources into a single research output.
    Does NOT make buy recommendations — produces research reports
    that feed into the unified grading system.
    """
    
    def __init__(self):
        self.data = {
            'generated_at': datetime.now().isoformat(),
            'macro': {},
            'sectors': {},
            'top_opportunities': [],
            'contradictions': [],
            'new_discoveries': [],
            'portfolio_alerts': [],
            'system_health': {}
        }
        self.issues = []
    
    def layer_1_macro(self):
        """Layer 1: Macro regime and signals."""
        print("🔍 Layer 1: Macro Analysis...")
        
        regime = db_query("""
            SELECT regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description
            FROM market_regime ORDER BY created_at DESC LIMIT 1
        """)
        
        signals = db_query("""
            SELECT signal_name, signal_value, signal_direction, confidence
            FROM macro_signals WHERE computed_at > NOW() - INTERVAL '2 days'
            ORDER BY signal_name
        """)
        
        macro = {'regime': 'UNKNOWN', 'confidence': 0, 'vix': 0, 'signals': []}
        if regime:
            parts = [p.strip() for p in regime[0]]
            macro['regime'] = parts[0] if parts[0] else 'UNKNOWN'
            macro['confidence'] = int(parts[1]) if parts[1].isdigit() else 0
            macro['vix'] = float(parts[2]) if parts[2].replace('.','').isdigit() else 0
        
        for row in signals:
            if len(row) >= 4:
                macro['signals'].append({
                    'name': row[0].strip(),
                    'value': row[1].strip(),
                    'direction': row[2].strip(),
                    'confidence': int(row[3]) if row[3].isdigit() else 0
                })
        
        self.data['macro'] = macro
        print(f"  Regime: {macro['regime']} | VIX: {macro['vix']:.1f}")
        return macro
    
    def layer_2_sectors(self):
        """Layer 2: Sector momentum and rotation."""
        print("🔍 Layer 2: Sector Analysis...")
        
        sectors = db_query("""
            SELECT sector, momentum_score, top_tickers, buy_count, sell_count, avg_grade
            FROM sector_momentum ORDER BY momentum_score DESC LIMIT 10
        """)
        
        sector_data = {}
        for row in sectors:
            if len(row) >= 6:
                sector_data[row[0].strip()] = {
                    'momentum': int(row[1]) if row[1].isdigit() else 0,
                    'top_tickers': row[2].strip() if row[2] else '',
                    'buy_count': int(row[3]) if row[3].isdigit() else 0,
                    'sell_count': int(row[4]) if row[4].isdigit() else 0,
                    'avg_grade': float(row[5]) if row[5].replace('.','').isdigit() else 0
                }
        
        self.data['sectors'] = sector_data
        print(f"  Top sector: {list(sector_data.keys())[0] if sector_data else 'N/A'}")
        return sector_data
    
    def layer_3_opportunities(self):
        """Layer 3: Top opportunities from ALL grade sources."""
        print("🔍 Layer 3: Opportunity Scan...")
        
        # Get latest grades from ALL sources with freshness check
        opportunities = db_query("""
            SELECT 
                v.ticker,
                v.vox_grade,
                v.action,
                v.technical_score,
                v.fundamental_score,
                v.macro_score,
                v.sentiment_score,
                v.momentum_score,
                s.sector,
                u.unified_grade,
                u.action as unified_action,
                ts.signal_type as trade_signal,
                ts.grade as trade_grade,
                v.generated_at
            FROM (
                SELECT DISTINCT ON (ticker) ticker, vox_grade, action, 
                       technical_score, fundamental_score, macro_score, 
                       sentiment_score, momentum_score, generated_at
                FROM vox_grades
                WHERE generated_at > NOW() - INTERVAL '7 days'
                ORDER BY ticker, generated_at DESC
            ) v
            LEFT JOIN sp500_universe s ON v.ticker = s.ticker
            LEFT JOIN unified_grades u ON v.ticker = u.ticker AND u.computed_at > NOW() - INTERVAL '2 days'
            LEFT JOIN trade_signals ts ON v.ticker = ts.ticker AND ts.created_at > NOW() - INTERVAL '7 days'
            WHERE v.vox_grade >= 60
            ORDER BY v.vox_grade DESC
            LIMIT 50
        """)
        
        ops = []
        for row in opportunities:
            if len(row) >= 13:
                ops.append({
                    'ticker': row[0].strip(),
                    'vox_grade': int(row[1]) if row[1].isdigit() else 0,
                    'action': row[2].strip() if row[2] else 'HOLD',
                    'technical': int(row[3]) if row[3].isdigit() else 0,
                    'fundamental': int(row[4]) if row[4].isdigit() else 0,
                    'macro': int(row[5]) if row[5].isdigit() else 0,
                    'sentiment': int(row[6]) if row[6].isdigit() else 0,
                    'momentum': int(row[7]) if row[7].isdigit() else 0,
                    'sector': row[8].strip() if row[8] else '',
                    'unified_grade': int(row[9]) if row[9] and row[9].isdigit() else None,
                    'unified_action': row[10].strip() if row[10] else None,
                    'trade_signal': row[11].strip() if row[11] else None,
                    'trade_grade': int(row[12]) if row[12] and row[12].isdigit() else None,
                })
        
        self.data['top_opportunities'] = ops
        print(f"  Found {len(ops)} opportunities (grade >= 60)")
        return ops
    
    def layer_4_contradictions(self):
        """Layer 4: Detect contradictions between sources."""
        print("🔍 Layer 4: Contradiction Detection...")
        
        contradictions = db_query("""
            SELECT v.ticker, v.vox_grade, v.action, u.unified_grade, u.action, ts.signal_type, ts.grade
            FROM vox_grades v
            JOIN unified_grades u ON v.ticker = u.ticker
            LEFT JOIN trade_signals ts ON v.ticker = ts.ticker
            WHERE v.generated_at > NOW() - INTERVAL '2 days'
              AND u.computed_at > NOW() - INTERVAL '2 days'
              AND (
                  (v.action IN ('BUY','STRONG_BUY') AND u.action IN ('SELL','TRIM')) OR
                  (v.action IN ('SELL','STRONG_SELL') AND u.action IN ('BUY','STRONG_BUY')) OR
                  (v.vox_grade >= 65 AND ts.signal_type = 'SELL')
              )
            LIMIT 20
        """)
        
        contra_list = []
        for row in contradictions:
            if len(row) >= 7:
                contra_list.append({
                    'ticker': row[0].strip(),
                    'vox_grade': int(row[1]) if row[1].isdigit() else 0,
                    'vox_action': row[2].strip(),
                    'unified_grade': int(row[3]) if row[3].isdigit() else 0,
                    'unified_action': row[4].strip(),
                    'trade_signal': row[5].strip() if row[5] else None,
                    'trade_grade': int(row[6]) if row[6] and row[6].isdigit() else None,
                })
        
        self.data['contradictions'] = contra_list
        if contra_list:
            print(f"  ⚠️ {len(contra_list)} contradictions detected")
        else:
            print("  ✅ No contradictions")
        return contra_list
    
    def layer_5_portfolio_alerts(self):
        """Layer 5: Portfolio position alerts."""
        print("🔍 Layer 5: Portfolio Alerts...")
        
        alerts = db_query("""
            SELECT p.ticker, p.grade, p.council, p.live_value, p.live_price, p.avg_cost,
                   (p.live_price - p.avg_cost) / NULLIF(p.avg_cost, 0) * 100 as pnl_pct
            FROM positions p
            WHERE p.live_value > 0
            ORDER BY p.live_value DESC
        """)
        
        alert_list = []
        total_value = 0
        for row in alerts:
            if len(row) >= 7:
                value = float(row[3]) if row[3] and row[3].replace('.','').replace('-','').isdigit() else 0
                total_value += value
        
        for row in alerts:
            if len(row) >= 7:
                ticker = row[0].strip()
                grade = int(row[1]) if row[1].isdigit() else 0
                council = row[2].strip() if row[2] else 'HOLD'
                value = float(row[3]) if row[3] and row[3].replace('.','').replace('-','').isdigit() else 0
                pnl_pct = float(row[6]) if row[6] and row[6].replace('.','').replace('-','').isdigit() else 0
                concentration = value / total_value if total_value > 0 else 0
                
                if grade < 40 and council == 'SELL':
                    alert_list.append({'ticker': ticker, 'severity': 'CRITICAL', 'type': 'SELL', 'message': f'Grade {grade} + Council SELL'})
                elif grade < 50:
                    alert_list.append({'ticker': ticker, 'severity': 'ACTION', 'type': 'SELL', 'message': f'Grade {grade}'})
                elif council == 'SELL':
                    alert_list.append({'ticker': ticker, 'severity': 'ACTION', 'type': 'COUNCIL', 'message': 'Council SELL'})
                elif concentration > 0.20:
                    alert_list.append({'ticker': ticker, 'severity': 'WARNING', 'type': 'CONCENTRATION', 'message': f'{concentration:.1%} of portfolio'})
                elif pnl_pct < -20:
                    alert_list.append({'ticker': ticker, 'severity': 'WARNING', 'type': 'STOP_LOSS', 'message': f'Down {pnl_pct:.1f}%'})
        
        self.data['portfolio_alerts'] = alert_list
        print(f"  {len(alert_list)} alerts")
        return alert_list
    
    def layer_6_system_health(self):
        """Layer 6: System health check."""
        print("🔍 Layer 6: System Health...")
        
        health = {}
        
        # Check data freshness
        health['grades_fresh'] = len(db_query("SELECT 1 FROM vox_grades WHERE generated_at > NOW() - INTERVAL '24 hours' LIMIT 1")) > 0
        health['macro_fresh'] = len(db_query("SELECT 1 FROM market_regime WHERE created_at > NOW() - INTERVAL '24 hours' LIMIT 1")) > 0
        health['unified_fresh'] = len(db_query("SELECT 1 FROM unified_grades WHERE computed_at > NOW() - INTERVAL '24 hours' LIMIT 1")) > 0
        
        # Check for data gaps
        null_grades = db_query("SELECT COUNT(*) FROM positions WHERE grade IS NULL")
        health['null_grades'] = int(null_grades[0][0]) if null_grades else 0
        
        nan_values = db_query("SELECT COUNT(*) FROM positions WHERE live_value = 'NaN'::float OR live_value::text = 'NaN'")
        health['nan_values'] = int(nan_values[0][0]) if nan_values else 0
        
        self.data['system_health'] = health
        issues = []
        if not health['grades_fresh']:
            issues.append("VOX grades stale (>24h)")
        if not health['macro_fresh']:
            issues.append("Macro data stale (>24h)")
        if not health['unified_fresh']:
            issues.append("Unified grades stale (>24h)")
        if health['null_grades'] > 0:
            issues.append(f"{health['null_grades']} positions with NULL grades")
        if health['nan_values'] > 0:
            issues.append(f"{health['nan_values']} positions with NaN values")
        
        self.issues = issues
        if issues:
            print(f"  ⚠️ {len(issues)} issues")
        else:
            print("  ✅ All healthy")
        return health
    
    def generate_report(self) -> str:
        """Generate unified research report."""
        print("\n📊 Generating Report...")
        
        lines = []
        lines.append(f"🧠 **VOX Unified Research — {datetime.now().strftime('%a %b %d')}**")
        lines.append("")
        
        # Macro
        macro = self.data['macro']
        regime_emoji = "🟢" if macro.get('regime') == 'RISK_ON' else "🟡" if macro.get('regime') == 'NEUTRAL' else "🔴"
        vix_emoji = "🟢" if macro.get('vix', 0) < 20 else "🟡" if macro.get('vix', 0) < 25 else "🔴"
        lines.append(f"{regime_emoji} Regime: {macro.get('regime', 'UNKNOWN')} | VIX {vix_emoji} {macro.get('vix', 0):.1f}")
        lines.append("")
        
        # Top opportunities
        top_5 = self.data['top_opportunities'][:5]
        if top_5:
            lines.append("🎯 **Top Opportunities**")
            for opp in top_5:
                grade = opp['vox_grade']
                emoji = "🟢" if grade >= 70 else "🟡" if grade >= 60 else "🟠"
                lines.append(f"  {emoji} `{opp['ticker']}` g{grade} | {opp['action']} | T:{opp['technical']} F:{opp['fundamental']} M:{opp['macro']}")
            lines.append("")
        
        # Contradictions
        if self.data['contradictions']:
            lines.append("⚠️ **Contradictions**")
            for c in self.data['contradictions'][:5]:
                lines.append(f"  `{c['ticker']}`: VOX {c['vox_action']}({c['vox_grade']}) vs Unified {c['unified_action']}({c['unified_grade']})")
            lines.append("")
        
        # Portfolio alerts
        critical = [a for a in self.data['portfolio_alerts'] if a['severity'] == 'CRITICAL']
        action = [a for a in self.data['portfolio_alerts'] if a['severity'] == 'ACTION']
        if critical or action:
            lines.append("🚨 **Portfolio Alerts**")
            for a in critical + action:
                emoji = "🔴" if a['severity'] == 'CRITICAL' else "🟡"
                lines.append(f"  {emoji} `{a['ticker']}` — {a['message']}")
            lines.append("")
        
        # System issues
        if self.issues:
            lines.append("⚠️ **System Issues**")
            for issue in self.issues:
                lines.append(f"  • {issue}")
            lines.append("")
        
        return "\n".join(lines)
    
    def run(self):
        """Execute full research pipeline."""
        print("="*70)
        print("VOX UNIFIED RESEARCH ENGINE v5.0")
        print("="*70)
        print()
        
        self.layer_1_macro()
        self.layer_2_sectors()
        self.layer_3_opportunities()
        self.layer_4_contradictions()
        self.layer_5_portfolio_alerts()
        self.layer_6_system_health()
        
        report = self.generate_report()
        
        # Save outputs
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save report
        report_file = SCRIPT_DIR / f"vox_unified_research_{timestamp}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        # Save JSON data
        json_file = SCRIPT_DIR / f"vox_unified_research_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
        
        print(f"\n✅ Report: {report_file}")
        print(f"✅ Data: {json_file}")
        
        return report


if __name__ == '__main__':
    engine = VoxUnifiedResearchEngine()
    report = engine.run()
    print("\n" + "="*70)
    print(report)
    print("="*70)
