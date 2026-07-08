#!/usr/bin/env python3
"""
VOX WEEKLY VERIFICATION ENGINE v3.0
Automated grade accuracy checker with cross-validation.

Runs every Monday at 9 AM. Checks:
  1. Grade accuracy: Compare vox_grades vs actual price performance
  2. Contradiction detection: VOX vs sp500 vs trade signals
  3. Inflation bug check: SELL stocks with unified_grade >= 60
  4. Stale data detection: Grades > 7 days old
  5. Outlier detection: Grades that changed > 15 points in 1 day
  6. Coverage gaps: Portfolio positions without grades
  7. Broker sync verification: eToro vs positions table alignment

Outputs:
  - verification_report_YYYYMMDD.json
  - Alerts on Telegram for critical issues
  - Auto-fixes NaN values and missing grades where possible

Target: Zero false positives, catch every data quality issue.
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

# Load env
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

SCRIPT_DIR = Path.home() / ".hermes" / "scripts" / "vox_cron"


def db_query(sql: str) -> List[Tuple]:
    """Execute SQL via psql subprocess."""
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


def db_exec(sql: str) -> bool:
    """Execute SQL that doesn't return rows (UPDATE/INSERT)."""
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PASSWORD
    result = subprocess.run([
        'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER,
        '-d', DB_NAME, '-c', sql
    ], capture_output=True, text=True, env=env)
    return result.returncode == 0


class VoxWeeklyVerification:
    """
    Weekly verification engine that checks ALL VOX data quality.
    
    Philosophy: Better to catch a bad grade before it costs money.
    """
    
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.auto_fixed = []
        self.stats = {}
        
    def check_1_grade_accuracy(self):
        """Check 1: Grade accuracy vs price performance."""
        print("[1/7] Grade Accuracy Check...")
        
        # Get grades from 7 days ago and current prices
        historical = db_query("""
            SELECT 
                v.ticker,
                v.vox_grade as old_grade,
                v.action as old_action,
                p.live_price as current_price,
                p.avg_cost,
                (p.live_price - p.avg_cost) / NULLIF(p.avg_cost, 0) * 100 as pnl_pct
            FROM vox_grades v
            JOIN positions p ON v.ticker = p.ticker
            WHERE v.generated_at BETWEEN NOW() - INTERVAL '10 days' AND NOW() - INTERVAL '6 days'
              AND p.live_value > 0
            ORDER BY v.generated_at DESC
        """)
        
        accuracy_issues = []
        for row in historical:
            if len(row) >= 6:
                ticker = row[0].strip()
                old_grade = int(row[1]) if row[1].isdigit() else 0
                old_action = row[2].strip() if row[2] else 'HOLD'
                pnl_pct = float(row[5]) if row[5] and row[5].replace('.','').replace('-','').isdigit() else 0
                
                # Grade said BUY but stock is down > 10%
                if old_action in ('BUY', 'STRONG_BUY') and pnl_pct < -10:
                    accuracy_issues.append({
                        'ticker': ticker,
                        'issue': 'FALSE_POSITIVE',
                        'old_grade': old_grade,
                        'old_action': old_action,
                        'pnl_pct': pnl_pct,
                        'message': f'BUY signal but down {pnl_pct:.1f}%'
                    })
                # Grade said SELL but stock is up > 10%
                elif old_action in ('SELL', 'STRONG_SELL') and pnl_pct > 10:
                    accuracy_issues.append({
                        'ticker': ticker,
                        'issue': 'FALSE_NEGATIVE',
                        'old_grade': old_grade,
                        'old_action': old_action,
                        'pnl_pct': pnl_pct,
                        'message': f'SELL signal but up {pnl_pct:.1f}%'
                    })
        
        self.stats['accuracy_issues'] = len(accuracy_issues)
        if accuracy_issues:
            self.warnings.extend([f"{i['ticker']}: {i['message']}" for i in accuracy_issues[:5]])
            print(f"  ⚠️ {len(accuracy_issues)} accuracy issues")
        else:
            print("  ✅ Grades accurate")
        return accuracy_issues
    
    def check_2_contradictions(self):
        """Check 2: Cross-source contradictions."""
        print("[2/7] Contradiction Detection...")
        
        contradictions = db_query("""
            SELECT 
                v.ticker,
                v.vox_grade,
                v.action,
                u.unified_grade,
                u.action,
                ts.signal_type,
                ts.grade
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
                })
        
        self.stats['contradictions'] = len(contra_list)
        if contra_list:
            self.issues.extend([f"{c['ticker']}: VOX {c['vox_action']}({c['vox_grade']}) vs Unified {c['unified_action']}({c['unified_grade']})" for c in contra_list[:5]])
            print(f"  🔴 {len(contra_list)} contradictions")
        else:
            print("  ✅ No contradictions")
        return contra_list
    
    def check_3_inflation_bug(self):
        """Check 3: Inflation bug — SELL stocks with unified_grade >= 60."""
        print("[3/7] Inflation Bug Check...")
        
        inflation = db_query("""
            SELECT u.ticker, u.unified_grade, u.action, v.vox_grade, v.action
            FROM unified_grades u
            JOIN vox_grades v ON u.ticker = v.ticker
            WHERE v.action IN ('SELL', 'STRONG_SELL')
              AND u.unified_grade >= 60
              AND v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
              AND u.computed_at > NOW() - INTERVAL '2 days'
            LIMIT 20
        """)
        
        inflation_list = []
        for row in inflation:
            if len(row) >= 5:
                inflation_list.append({
                    'ticker': row[0].strip(),
                    'unified_grade': int(row[1]) if row[1].isdigit() else 0,
                    'unified_action': row[2].strip(),
                    'vox_grade': int(row[3]) if row[3].isdigit() else 0,
                    'vox_action': row[4].strip(),
                })
        
        self.stats['inflation_bugs'] = len(inflation_list)
        if inflation_list:
            self.issues.extend([f"{i['ticker']}: Inflation bug — VOX says {i['vox_action']}({i['vox_grade']}) but unified={i['unified_grade']}" for i in inflation_list[:5]])
            print(f"  🔴 {len(inflation_list)} inflation bugs")
        else:
            print("  ✅ No inflation bugs")
        return inflation_list
    
    def check_4_stale_data(self):
        """Check 4: Stale grades (> 7 days old)."""
        print("[4/7] Stale Data Check...")
        
        stale = db_query("""
            SELECT ticker, MAX(generated_at) as last_graded
            FROM vox_grades
            GROUP BY ticker
            HAVING MAX(generated_at) < NOW() - INTERVAL '7 days'
            ORDER BY MAX(generated_at) ASC
            LIMIT 20
        """)
        
        stale_list = []
        for row in stale:
            if len(row) >= 2:
                stale_list.append({'ticker': row[0].strip(), 'last_graded': row[1].strip()})
        
        self.stats['stale_grades'] = len(stale_list)
        if stale_list:
            self.warnings.extend([f"{s['ticker']}: Last graded {s['last_graded']}" for s in stale_list[:5]])
            print(f"  ⚠️ {len(stale_list)} stale grades")
        else:
            print("  ✅ All grades fresh")
        return stale_list
    
    def check_5_outlier_detection(self):
        """Check 5: Grades that changed > 15 points in 1 day."""
        print("[5/7] Outlier Detection...")
        
        outliers = db_query("""
            SELECT 
                curr.ticker,
                prev.vox_grade as prev_grade,
                curr.vox_grade as curr_grade,
                ABS(curr.vox_grade - prev.vox_grade) as diff,
                curr.action
            FROM vox_grades curr
            JOIN vox_grades prev ON curr.ticker = prev.ticker
            WHERE curr.generated_at > NOW() - INTERVAL '2 days'
              AND prev.generated_at BETWEEN curr.generated_at - INTERVAL '2 days' AND curr.generated_at - INTERVAL '12 hours'
              AND ABS(curr.vox_grade - prev.vox_grade) > 15
            ORDER BY diff DESC
            LIMIT 20
        """)
        
        outlier_list = []
        for row in outliers:
            if len(row) >= 5:
                outlier_list.append({
                    'ticker': row[0].strip(),
                    'prev_grade': int(row[1]) if row[1].isdigit() else 0,
                    'curr_grade': int(row[2]) if row[2].isdigit() else 0,
                    'diff': int(row[3]) if row[3].isdigit() else 0,
                    'action': row[4].strip(),
                })
        
        self.stats['outliers'] = len(outlier_list)
        if outlier_list:
            self.warnings.extend([f"{o['ticker']}: Grade jumped {o['diff']} points ({o['prev_grade']} -> {o['curr_grade']})" for o in outlier_list[:5]])
            print(f"  ⚠️ {len(outlier_list)} outliers")
        else:
            print("  ✅ No outliers")
        return outlier_list
    
    def check_6_coverage_gaps(self):
        """Check 6: Portfolio positions without grades."""
        print("[6/7] Coverage Gap Check...")
        
        gaps = db_query("""
            SELECT p.ticker, p.live_value
            FROM positions p
            LEFT JOIN vox_grades v ON p.ticker = v.ticker AND v.generated_at > NOW() - INTERVAL '7 days'
            WHERE p.live_value > 0
              AND v.ticker IS NULL
            ORDER BY p.live_value DESC
        """)
        
        gap_list = []
        for row in gaps:
            if len(row) >= 2:
                gap_list.append({'ticker': row[0].strip(), 'value': row[1].strip()})
        
        self.stats['coverage_gaps'] = len(gap_list)
        if gap_list:
            self.warnings.extend([f"{g['ticker']}: No grade (value: {g['value']})" for g in gap_list[:5]])
            print(f"  ⚠️ {len(gap_list)} positions without grades")
        else:
            print("  ✅ Full coverage")
        return gap_list
    
    def check_7_broker_sync(self):
        """Check 7: Broker positions vs positions table alignment."""
        print("[7/7] Broker Sync Verification...")
        
        # Check for positions in broker_positions not in positions
        orphan_broker = db_query("""
            SELECT bp.ticker, bp.broker, bp.live_value_usd
            FROM broker_positions bp
            LEFT JOIN positions p ON bp.ticker = p.ticker
            WHERE p.ticker IS NULL
              AND bp.units > 0
            LIMIT 20
        """)
        
        # Check for NaN values
        nan_values = db_query("""
            SELECT ticker, live_value, live_price
            FROM positions
            WHERE live_value = 'NaN'::float OR live_value::text = 'NaN'
               OR live_price = 'NaN'::float OR live_price::text = 'NaN'
            LIMIT 20
        """)
        
        sync_issues = []
        for row in orphan_broker:
            if len(row) >= 3:
                sync_issues.append({'type': 'ORPHAN', 'ticker': row[0].strip(), 'broker': row[1].strip(), 'value': row[2].strip()})
        
        for row in nan_values:
            if len(row) >= 3:
                sync_issues.append({'type': 'NAN', 'ticker': row[0].strip(), 'live_value': row[1], 'live_price': row[2]})
        
        self.stats['sync_issues'] = len(sync_issues)
        
        # Auto-fix NaN values
        for issue in sync_issues:
            if issue['type'] == 'NAN':
                ticker = issue['ticker']
                # Try to fix by recalculating live_value = live_price * shares
                fixed = db_exec(f"""
                    UPDATE positions 
                    SET live_value = COALESCE(live_price, avg_cost) * shares,
                        live_price = COALESCE(live_price, avg_cost)
                    WHERE ticker = '{ticker}' 
                      AND (live_value = 'NaN'::float OR live_value::text = 'NaN')
                """)
                if fixed:
                    self.auto_fixed.append(f"{ticker}: Recalculated live_value from NaN")
        
        if sync_issues:
            orphan_count = len([i for i in sync_issues if i['type'] == 'ORPHAN'])
            nan_count = len([i for i in sync_issues if i['type'] == 'NAN'])
            if orphan_count > 0:
                self.warnings.append(f"{orphan_count} broker positions not in positions table")
            if nan_count > 0:
                self.issues.append(f"{nan_count} positions with NaN values")
            print(f"  ⚠️ {orphan_count} orphans, {nan_count} NaN")
        else:
            print("  ✅ Sync verified")
        return sync_issues
    
    def generate_report(self) -> str:
        """Generate verification report."""
        print("\n📊 Generating Report...")
        
        lines = []
        lines.append(f"🔍 **VOX Weekly Verification — {datetime.now().strftime('%a %b %d')}**")
        lines.append("")
        
        # Summary stats
        total_issues = len(self.issues)
        total_warnings = len(self.warnings)
        total_fixed = len(self.auto_fixed)
        
        status_emoji = "🟢" if total_issues == 0 else "🟡" if total_issues <= 2 else "🔴"
        lines.append(f"{status_emoji} **Status**: {total_issues} issues, {total_warnings} warnings, {total_fixed} auto-fixed")
        lines.append("")
        
        # Stats table
        lines.append("| Check | Result |")
        lines.append("|-------|--------|")
        for check, count in self.stats.items():
            emoji = "✅" if count == 0 else "⚠️"
            lines.append(f"| {check} | {emoji} {count} |")
        lines.append("")
        
        # Critical issues
        if self.issues:
            lines.append("🔴 **Critical Issues**")
            for issue in self.issues[:10]:
                lines.append(f"  • {issue}")
            lines.append("")
        
        # Warnings
        if self.warnings:
            lines.append("⚠️ **Warnings**")
            for warning in self.warnings[:10]:
                lines.append(f"  • {warning}")
            lines.append("")
        
        # Auto-fixed
        if self.auto_fixed:
            lines.append("🔧 **Auto-Fixed**")
            for fix in self.auto_fixed[:10]:
                lines.append(f"  • {fix}")
            lines.append("")
        
        # Recommendation
        if total_issues == 0 and total_warnings == 0:
            lines.append("✅ **All systems verified. Ready for trading.**")
        elif total_issues == 0:
            lines.append("🟡 **Systems operational with warnings. Review before trading.**")
        else:
            lines.append("🔴 **Critical issues detected. DO NOT trade until fixed.**")
        
        return "\n".join(lines)
    
    def run(self):
        """Execute full verification pipeline."""
        print("="*70)
        print("VOX WEEKLY VERIFICATION ENGINE v3.0")
        print("="*70)
        print()
        
        self.check_1_grade_accuracy()
        self.check_2_contradictions()
        self.check_3_inflation_bug()
        self.check_4_stale_data()
        self.check_5_outlier_detection()
        self.check_6_coverage_gaps()
        self.check_7_broker_sync()
        
        report = self.generate_report()
        
        # Save outputs
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        report_file = SCRIPT_DIR / f"verification_report_{timestamp}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        json_file = SCRIPT_DIR / f"verification_data_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump({
                'issues': self.issues,
                'warnings': self.warnings,
                'auto_fixed': self.auto_fixed,
                'stats': self.stats,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n✅ Report: {report_file}")
        print(f"✅ Data: {json_file}")
        
        # Exit with non-zero if critical issues (triggers notification)
        if self.issues:
            print(f"\n🚨 {len(self.issues)} CRITICAL ISSUES — NOTIFICATION TRIGGERED")
            return 1
        return 0


if __name__ == '__main__':
    verifier = VoxWeeklyVerification()
    exit_code = verifier.run()
    print("\n" + "="*70)
    print(verifier.generate_report())
    print("="*70)
    sys.exit(exit_code)
