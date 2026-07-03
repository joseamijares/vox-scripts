"""VOX Cron Health Monitor — checks all active cron jobs for staleness.

Reports:
- Jobs that haven't run in >48h (stale)
- Jobs with last_status != 'ok' (errors)
- Jobs that have never run (new)
- Summary counts

Exits with code 1 if any critical issues found (for alerting).
"""
import os
import sys
import json
import subprocess
from datetime import datetime, timedelta

# Config
STALE_HOURS = 48
CRITICAL_JOBS = [
    'vox-macro-snapshot',
    'vox-position-review',
    'vox-daily-grade-sync',
    'vox-morning-digest',
]

def run_hermes_cron_list():
    """Run hermes cron list and parse output."""
    try:
        result = subprocess.run(
            ['hermes', 'cron', 'list'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            print(f"ERROR: hermes cron list failed: {result.stderr}")
            return []
        return parse_text_output(result.stdout)
    except Exception as e:
        print(f"ERROR: Failed to run hermes cron list: {e}")
        return []

def parse_text_output(output):
    """Parse text output from hermes cron list."""
    import re
    jobs = []
    lines = output.split('\n')
    current_job = None
    for line in lines:
        # Match job ID line: "  312d3b31bf1f [active]"
        m = re.match(r'^\s+([a-f0-9]+)\s+\[(\w+)\]', line)
        if m:
            if current_job:
                jobs.append(current_job)
            current_job = {
                'job_id': m.group(1),
                'status': m.group(2)
            }
        elif current_job and line.startswith('    Name:'):
            current_job['name'] = line.split(':', 1)[1].strip()
        elif current_job and line.startswith('    Last run:'):
            parts = line.split(':', 1)[1].strip()
            # Format: "2026-06-15T07:00:08.001133-06:00  ok"
            if '  ' in parts:
                current_job['last_run'] = parts.split('  ')[0].strip()
                current_job['last_status'] = parts.split('  ')[1].strip()
            else:
                current_job['last_run'] = parts
    if current_job:
        jobs.append(current_job)
    return jobs

def check_health(jobs):
    """Check health of all jobs."""
    now = datetime.now()
    stale_threshold = now - timedelta(hours=STALE_HOURS)
    
    issues = []
    healthy = []
    
    for job in jobs:
        name = job.get('name', 'unknown')
        status = job.get('status', 'unknown')
        last_status = job.get('last_status', 'unknown')
        last_run_str = job.get('last_run', '')
        
        # Parse last_run
        last_run = None
        if last_run_str and last_run_str != 'Never':
            try:
                # Parse ISO format with timezone
                from datetime import timezone
                # Remove microseconds for cleaner parsing
                clean = last_run_str.replace('+00:00', '').replace('-06:00', '')
                # Try parsing
                for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        last_run = datetime.strptime(clean, fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        # Check for issues
        issue = None
        
        if status == 'paused':
            # Paused is not an issue unless it's a critical job
            if name in CRITICAL_JOBS:
                issue = {'type': 'paused_critical', 'job': name, 'severity': 'warning'}
        elif last_run is None:
            issue = {'type': 'never_run', 'job': name, 'severity': 'warning'}
        elif last_run < stale_threshold:
            issue = {'type': 'stale', 'job': name, 'severity': 'error', 'hours': (now - last_run).total_seconds() / 3600}
        elif last_status != 'ok' and last_status != 'unknown':
            issue = {'type': 'error_status', 'job': name, 'severity': 'error', 'status': last_status}
        
        if issue:
            issues.append(issue)
        else:
            healthy.append(name)
    
    return issues, healthy

def main():
    print("=" * 60)
    print("VOX CRON HEALTH MONITOR")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Stale threshold: {STALE_HOURS} hours")
    print()
    
    jobs = run_hermes_cron_list()
    if not jobs:
        print("ERROR: No jobs found or failed to fetch job list")
        sys.exit(1)
    
    print(f"Total jobs: {len(jobs)}")
    active = [j for j in jobs if j.get('status') == 'active']
    paused = [j for j in jobs if j.get('status') == 'paused']
    print(f"  Active: {len(active)}")
    print(f"  Paused: {len(paused)}")
    print()
    
    issues, healthy = check_health(jobs)
    
    if issues:
        print(f"ISSUES FOUND: {len(issues)}")
        print("-" * 40)
        for issue in issues:
            severity_emoji = "🔴" if issue['severity'] == 'error' else "⚠️"
            print(f"{severity_emoji} {issue['job']}: {issue['type']}")
            if 'hours' in issue:
                print(f"   Last run: {issue['hours']:.1f} hours ago")
            if 'status' in issue:
                print(f"   Status: {issue['status']}")
        print()
    else:
        print("✅ All jobs healthy")
        print()
    
    print(f"Healthy jobs: {len(healthy)}")
    for name in healthy:
        print(f"  ✅ {name}")
    
    # Exit with error if any critical issues
    critical = [i for i in issues if i['severity'] == 'error']
    if critical:
        print(f"\n❌ {len(critical)} critical issues found")
        sys.exit(1)
    else:
        print(f"\n✅ No critical issues")
        sys.exit(0)

if __name__ == '__main__':
    main()
