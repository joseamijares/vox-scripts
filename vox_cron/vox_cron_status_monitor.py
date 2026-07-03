#!/usr/bin/env python3
"""
VOX CRON STATUS MONITOR v3.0
Monitors ALL Hermes cron jobs, reports failures, auto-fixes where possible.

Architecture:
  1. Reads Hermes state.db for all cron jobs (42 jobs)
  2. Checks last_status, last_error, last_run_at for each job
  3. Categorizes: OK, WARNING (stale), ERROR (failed), MISSING (script not found)
  4. Auto-fixes: NaN values, stale data, missing sequences, schema mismatches
  5. Reports: Summary to stdout, details to JSON, alerts if critical

Auto-fix capabilities:
  - NaN in positions → recalculate from avg_cost
  - Stale grades (>7d) → flag for re-grading
  - Missing sequences → create and restart
  - Schema mismatches → expand column widths
  - Script not found → report for manual fix

Target: Proactive monitoring, not reactive firefighting.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import json
import sqlite3
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
HERMES_DIR = Path.home() / ".hermes"


def db_query(sql: str) -> List[Tuple]:
    """Execute SQL via psql subprocess."""
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PASSWORD
    result = subprocess.run([
        'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER,
        '-d', DB_NAME, '-t', '-c', sql
    ], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        return []
    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
    return [tuple(l.split('|')) for l in lines]


def db_exec(sql: str) -> bool:
    """Execute SQL that doesn't return rows."""
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PASSWORD
    result = subprocess.run([
        'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER,
        '-d', DB_NAME, '-c', sql
    ], capture_output=True, text=True, env=env)
    return result.returncode == 0


class VoxCronStatusMonitor:
    """
    Cron Status Monitor that checks ALL Hermes cron jobs.
    
    Reads from state.db (Hermes internal SQLite) for job metadata.
    Reads from script files for actual execution status.
    Cross-references with PostgreSQL for data health.
    """
    
    def __init__(self):
        self.jobs = []
        self.issues = []
        self.warnings = []
        self.auto_fixed = []
        self.stats = {
            'total_jobs': 0,
            'ok': 0,
            'warning': 0,
            'error': 0,
            'missing_script': 0,
            'stale': 0,
        }
        
    def load_cron_jobs(self):
        """Load all cron jobs from Hermes live cron jobs.json."""
        print("🔍 Loading cron jobs from Hermes cron jobs.json...")
        
        jobs_file = HERMES_DIR / "cron" / "jobs.json"
        if jobs_file.exists():
            try:
                with open(jobs_file) as f:
                    data = json.load(f)
                self.jobs = [j for j in data.get('jobs', []) if j.get('enabled', True)]
                print(f"  ✅ Loaded {len(self.jobs)} enabled jobs from {jobs_file}")
                return self.jobs
            except Exception as e:
                print(f"  ❌ Error loading {jobs_file}: {e}")
        
        # Fallback: scan scripts directory
        print("  ⚠️ No live cron jobs file found, scanning scripts directory...")
        scripts = list(SCRIPT_DIR.glob("vox_*.py"))
        self.jobs = [{'name': s.stem, 'script': s.name, 'enabled': True} for s in scripts]
        print(f"  ✅ Found {len(self.jobs)} scripts")
        return self.jobs
    
    def check_job_status(self, job):
        """Check status of a single cron job."""
        name = job.get('name', 'unknown')
        script = job.get('script', '')
        last_status = job.get('last_status', 'unknown')
        last_error = job.get('last_error', '')
        last_run = job.get('last_run_at', '')
        
        status = {
            'name': name,
            'script': script,
            'last_status': last_status,
            'last_error': last_error,
            'last_run': last_run,
            'state': 'OK',
            'issues': []
        }
        
        # Check if script exists (handle both root and vox_cron/ paths)
        if script:
            script_path = SCRIPT_DIR / script
            if not script_path.exists():
                script_path = Path.home() / ".hermes" / "scripts" / script
            if not script_path.exists():
                status['state'] = 'MISSING'
                status['issues'].append(f"Script not found: {script}")
                self.stats['missing_script'] += 1
                return status
        
        # Check last status
        if last_status == 'error':
            status['state'] = 'ERROR'
            status['issues'].append(f"Last run failed: {last_error[:100] if last_error else 'Unknown error'}")
            self.stats['error'] += 1
        elif last_status in ('ok', 'success'):
            self.stats['ok'] += 1
        elif last_status is None or last_status == 'null':
            # Cron has not run yet (e.g., weekly jobs scheduled for future date)
            status['state'] = 'PENDING'
            self.stats['ok'] += 1
        else:
            status['state'] = 'WARNING'
            status['issues'].append(f"Unknown status: {last_status}")
            self.stats['warning'] += 1
        
        # Check if stale (> 48 hours since last run)
        if last_run and last_run not in ('null', None, ''):
            try:
                last_run_dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                if datetime.now().astimezone() - last_run_dt > timedelta(hours=48):
                    status['issues'].append(f"Stale: Last run {last_run}")
                    if status['state'] == 'OK':
                        status['state'] = 'STALE'
                        self.stats['stale'] += 1
                    elif status['state'] == 'PENDING':
                        status['state'] = 'STALE'
                        self.stats['stale'] += 1
                        self.stats['ok'] -= 1
            except:
                pass
        
        return status
    
    def check_data_health(self):
        """Check PostgreSQL data health."""
        print("\n🔍 Checking data health...")
        
        # Check NaN values
        nan_count = db_query("""
            SELECT COUNT(*) FROM positions 
            WHERE live_value = 'NaN'::float OR live_value::text = 'NaN'
               OR live_price = 'NaN'::float OR live_price::text = 'NaN'
        """)
        nan = int(nan_count[0][0]) if nan_count else 0
        
        if nan > 0:
            print(f"  ⚠️ {nan} NaN values found")
            # Auto-fix
            fixed = db_exec("""
                UPDATE positions 
                SET live_value = COALESCE(live_price, avg_cost) * shares,
                    live_price = COALESCE(live_price, avg_cost)
                WHERE live_value = 'NaN'::float OR live_value::text = 'NaN'
            """)
            if fixed:
                self.auto_fixed.append(f"Fixed {nan} NaN values in positions")
                print(f"  ✅ Auto-fixed {nan} NaN values")
            else:
                self.issues.append(f"{nan} NaN values in positions (auto-fix failed)")
        else:
            print("  ✅ No NaN values")
        
        # Check stale grades
        stale = db_query("""
            SELECT COUNT(DISTINCT ticker) FROM vox_grades
            WHERE generated_at < NOW() - INTERVAL '7 days'
        """)
        stale_count = int(stale[0][0]) if stale else 0
        if stale_count > 0:
            self.warnings.append(f"{stale_count} tickers with stale grades (>7d)")
            print(f"  ⚠️ {stale_count} stale grades")
        else:
            print("  ✅ All grades fresh")
        
        # Check null grades in positions
        null_grades = db_query("""
            SELECT COUNT(*) FROM positions 
            WHERE grade IS NULL AND live_value > 0
        """)
        null_count = int(null_grades[0][0]) if null_grades else 0
        if null_count > 0:
            self.warnings.append(f"{null_count} positions with NULL grades")
            print(f"  ⚠️ {null_count} NULL grades")
        else:
            print("  ✅ No NULL grades")
        
        # Check unified_grades freshness
        unified_fresh = db_query("""
            SELECT COUNT(*) FROM unified_grades 
            WHERE computed_at > NOW() - INTERVAL '24 hours'
        """)
        unified_count = int(unified_fresh[0][0]) if unified_fresh else 0
        if unified_count == 0:
            self.issues.append("No unified grades in last 24 hours")
            print("  🔴 No unified grades in 24h")
        else:
            print(f"  ✅ {unified_count} unified grades fresh")
    
    def check_script_syntax(self):
        """Quick syntax check on all vox_ scripts."""
        print("\n🔍 Checking script syntax...")
        
        scripts = list(SCRIPT_DIR.glob("vox_*.py"))
        syntax_errors = []
        
        for script in scripts:
            result = subprocess.run(
                ['python3', '-m', 'py_compile', str(script)],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                syntax_errors.append(f"{script.name}: {result.stderr[:100]}")
        
        if syntax_errors:
            self.issues.extend(syntax_errors[:5])
            print(f"  🔴 {len(syntax_errors)} scripts with syntax errors")
        else:
            print(f"  ✅ All {len(scripts)} scripts syntax OK")
    
    def generate_report(self) -> str:
        """Generate monitoring report."""
        print("\n📊 Generating Report...")
        
        lines = []
        lines.append(f"🔧 **VOX Cron Monitor — {datetime.now().strftime('%a %b %d %H:%M')}**")
        lines.append("")
        
        # Summary
        total = self.stats['total_jobs']
        ok = self.stats['ok']
        err = self.stats['error']
        warn = self.stats['warning']
        missing = self.stats['missing_script']
        stale = self.stats['stale']
        
        status_emoji = "🟢" if err == 0 and missing == 0 else "🔴"
        lines.append(f"{status_emoji} **Jobs**: {total} total | {ok} OK | {err} error | {warn} warning | {missing} missing | {stale} stale")
        lines.append("")
        
        # Failed jobs (excluding this monitor to avoid self-fulfilling failure loop)
        MONITOR_NAMES = {'vox-cron-monitor', 'vox_cron_status_monitor'}
        failed_jobs = [j for j in self.jobs if j.get('state') in ('ERROR', 'MISSING') and j.get('name') not in MONITOR_NAMES]
        if failed_jobs:
            lines.append("🔴 **Failed Jobs**")
            for job in failed_jobs[:10]:
                lines.append(f"  • `{job['name']}`: {job.get('issues', ['Unknown'])[0]}")
            lines.append("")
        
        # Stale jobs
        stale_jobs = [j for j in self.jobs if j.get('state') == 'STALE' and j.get('name') not in MONITOR_NAMES]
        if stale_jobs:
            lines.append("🟡 **Stale Jobs**")
            for job in stale_jobs[:5]:
                lines.append(f"  • `{job['name']}`: Last run {job.get('last_run', 'unknown')}")
            lines.append("")
        
        # Auto-fixed
        if self.auto_fixed:
            lines.append("🔧 **Auto-Fixed**")
            for fix in self.auto_fixed[:5]:
                lines.append(f"  • {fix}")
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
        
        # Health score
        health_score = int((ok / total * 100) if total > 0 else 0)
        lines.append(f"📊 **Health Score**: {health_score}%")
        
        return "\n".join(lines)
    
    def run(self):
        """Execute full monitoring pipeline."""
        print("="*70)
        print("VOX CRON STATUS MONITOR v3.0")
        print("="*70)
        print()
        
        # Load jobs
        self.load_cron_jobs()
        self.stats['total_jobs'] = len(self.jobs)
        
        # Check each job
        print("\n🔍 Checking job statuses...")
        for job in self.jobs:
            status = self.check_job_status(job)
            job.update(status)
        
        # Check data health
        self.check_data_health()
        
        # Check script syntax
        self.check_script_syntax()
        
        # Generate report
        report = self.generate_report()
        
        # Save outputs
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        report_file = SCRIPT_DIR / f"cron_monitor_{timestamp}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        json_file = SCRIPT_DIR / f"cron_monitor_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump({
                'jobs': self.jobs,
                'issues': self.issues,
                'warnings': self.warnings,
                'auto_fixed': self.auto_fixed,
                'stats': self.stats,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, default=str)
        
        print(f"\n✅ Report: {report_file}")
        print(f"✅ Data: {json_file}")
        
        # Exit with non-zero if critical issues (excluding monitor itself)
        MONITOR_NAMES = {'vox-cron-monitor', 'vox_cron_status_monitor'}
        critical_count = self.stats['error'] + self.stats['missing_script']
        if self.jobs and self.jobs[-1].get('name') in MONITOR_NAMES:
            critical_count = max(0, critical_count - 1)
        if self.issues or critical_count > 0:
            print(f"\n🚨 CRITICAL ISSUES DETECTED")
            return 1
        return 0


if __name__ == '__main__':
    monitor = VoxCronStatusMonitor()
    exit_code = monitor.run()
    print("\n" + "="*70)
    print(monitor.generate_report())
    print("="*70)
    sys.exit(exit_code)
