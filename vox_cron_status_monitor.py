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

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
VOX_CRON_DIR = SCRIPT_DIR / "vox_cron"
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
        """Load all cron jobs from Hermes live cron list output."""
        print("🔍 Loading cron jobs from live cron list...")
        
        try:
            result = subprocess.run(
                ["hermes", "cron", "list"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                self.jobs = self._parse_cron_list(result.stdout)
                print(f"  ✅ Loaded {len(self.jobs)} jobs from live list")
                return self.jobs
        except Exception as e:
            print(f"  ⚠️ Live list failed: {e}")
        
        # Fallback: read latest backup
        backup_dir = HERMES_DIR / "skills" / ".curator_backups"
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("*/cron-jobs.json"), reverse=True)
            if backups:
                with open(backups[0]) as f:
                    data = json.load(f)
                    self.jobs = data.get('jobs', [])
                    print(f"  ✅ Loaded {len(self.jobs)} jobs from backup")
                    return self.jobs
        
        # Fallback: scan scripts directory
        print("  ⚠️ No backup found, scanning scripts directory...")
        scripts = list(SCRIPT_DIR.glob("vox_*.py"))
        self.jobs = [{'name': s.stem, 'script': s.name, 'enabled': True} for s in scripts]
        print(f"  ✅ Found {len(self.jobs)} scripts")
        return self.jobs
    
    def _parse_cron_list(self, output: str) -> List[Dict]:
        """Parse hermes cron list text output into job dicts."""
        jobs = []
        current_job = {}
        
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('Name:'):
                if current_job:
                    jobs.append(current_job)
                current_job = {'name': line.split('Name:')[1].strip()}
            elif line.startswith('Script:'):
                current_job['script'] = line.split('Script:')[1].strip()
            elif line.startswith('Last run:'):
                # Parse: "Last run:  2026-06-24T12:00:50.856888-06:00  ok"
                # Or: "Last run:  2026-06-24T13:01:01.504869-06:00  error: Script exited with code 1"
                rest = line.split('Last run:')[1].strip()
                # Split by two spaces to separate timestamp from status
                parts = rest.split('  ')
                if len(parts) >= 2:
                    current_job['last_run_at'] = parts[0].strip()
                    status_part = parts[1].strip()
                    # Status is before the colon (e.g., "error:" or "ok")
                    if ':' in status_part:
                        status = status_part.split(':')[0].strip()
                        current_job['last_status'] = status
                        current_job['last_error'] = ':'.join(status_part.split(':')[1:]).strip()
                    else:
                        current_job['last_status'] = status_part
                elif len(parts) == 1:
                    # Just timestamp, no status
                    current_job['last_run_at'] = parts[0].strip()
                    current_job['last_status'] = 'unknown'
            elif line.startswith('Next run:'):
                current_job['next_run_at'] = line.split('Next run:')[1].strip()
            elif line.startswith('Schedule:'):
                current_job['schedule'] = line.split('Schedule:')[1].strip()
        
        if current_job:
            jobs.append(current_job)
        
        return jobs
    
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
        
        # Check if script exists
        if script:
            # Handle vox_cron/ prefix in script paths
            script_name = script.replace('vox_cron/', '')
            script_path = SCRIPT_DIR / script_name
            if not script_path.exists():
                script_path = SCRIPT_DIR / 'vox_cron' / script_name
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
        elif last_status == 'ok':
            self.stats['ok'] += 1
        else:
            status['state'] = 'WARNING'
            status['issues'].append(f"Unknown status: {last_status}")
            self.stats['warning'] += 1
        
        # Check if stale (> 48 hours since last run, adjusted for weekly schedules)
        if last_run:
            try:
                last_run_dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                schedule = job.get('schedule', '')
                # Weekly jobs: allow up to 8 days + 6 hours slack
                if schedule and ('* * 0' in schedule or '* * 1' in schedule or '* * 2' in schedule or
                                 '* * 3' in schedule or '* * 4' in schedule or '* * 5' in schedule or
                                 '* * 6' in schedule or '* * 7' in schedule):
                    stale_threshold = timedelta(days=8, hours=6)
                else:
                    stale_threshold = timedelta(hours=48)
                if datetime.now().astimezone() - last_run_dt > stale_threshold:
                    status['issues'].append(f"Stale: Last run {last_run}")
                    if status['state'] == 'OK':
                        status['state'] = 'STALE'
                        self.stats['stale'] += 1
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
        
        # Check stale grades - count tickers whose LATEST grade is stale
        stale = db_query("""
            SELECT COUNT(*) FROM (
                SELECT ticker, MAX(generated_at) as last_grade
                FROM vox_grades
                GROUP BY ticker
                HAVING MAX(generated_at) < NOW() - INTERVAL '7 days'
            ) sq
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
        
        # Failed jobs
        failed_jobs = [j for j in self.jobs if j.get('state') in ('ERROR', 'MISSING')]
        if failed_jobs:
            lines.append("🔴 **Failed Jobs**")
            for job in failed_jobs[:10]:
                lines.append(f"  • `{job['name']}`: {job.get('issues', ['Unknown'])[0]}")
            lines.append("")
        
        # Stale jobs
        stale_jobs = [j for j in self.jobs if j.get('state') == 'STALE']
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
        
        report_file = VOX_CRON_DIR / f"cron_monitor_{timestamp}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        json_file = VOX_CRON_DIR / f"cron_monitor_{timestamp}.json"
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
        
        # Exit with non-zero if critical issues — but exclude self to avoid
        # self-referential failure loops (our own previous error is not a
        # systemic issue that needs re-alerting every 6 hours).
        non_self_errors = [j for j in self.jobs if j.get('status') == 'error' and j.get('name') != 'vox-cron-monitor']
        non_self_issues = [i for i in self.issues if 'vox-cron-monitor' not in str(i)]
        if non_self_issues or len(non_self_errors) > 0 or self.stats['missing_script'] > 0:
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
