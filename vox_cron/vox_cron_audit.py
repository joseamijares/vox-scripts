#!/usr/bin/env python3
"""Deep audit of VOX cron jobs"""
import json, os, sys
from datetime import datetime, timedelta

# The full cron list from the API
crons = [
    {"job_id": "3e8f6b99661e", "name": "vox-alert-system", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T12:00:16.192249-06:00", "last_status": "ok", "script": "vox_alert_system_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 9,12,15 * * 1-5"},
    {"job_id": "fe62753d36de", "name": "vox-autonomous-screener", "enabled": False, "state": "paused", "last_run_at": "2026-06-09T18:00:50.600902-06:00", "last_status": "ok", "script": "vox_autonomous_screener_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 18 * * 1-5"},
    {"job_id": "977c8bf0668b", "name": "vox-evening-commander", "enabled": False, "state": "paused", "last_run_at": "2026-06-09T18:00:50.822432-06:00", "last_status": "ok", "script": "vox_evening_commander_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 18 * * 1-5"},
    {"job_id": "9a031b2c663d", "name": "vox-sector-scan-weekly", "enabled": False, "state": "paused", "last_run_at": "2026-06-08T10:00:53.255287-06:00", "last_status": "ok", "script": "vox_sector_scanner_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 10 * * 1"},
    {"job_id": "93b6063af334", "name": "vox-market-regime", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T06:00:26.212902-06:00", "last_status": "ok", "script": "vox_market_regime_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 6 * * 1-5"},
    {"job_id": "312d3b31bf1f", "name": "vox-position-review", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-15T07:00:08.001133-06:00", "last_status": "ok", "script": "vox_position_review_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 7 * * 1-5"},
    {"job_id": "9acf574c02b3", "name": "vox-daily-briefing", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T08:00:43.426996-06:00", "last_status": "ok", "script": "vox_daily_briefing_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 8 * * 1-5"},
    {"job_id": "76e2c19b0d6d", "name": "vox-trade-scorer", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-12T15:00:15.804599-06:00", "last_status": "ok", "script": "vox_trade_scorer_v2.py", "no_agent": True, "deliver": "local", "schedule": "0 9,15 * * 1-5"},
    {"job_id": "a51d1889ceab", "name": "vox-weather-agent", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T12:44:15.018222-06:00", "last_status": "ok", "script": "run_vox_weather.sh", "no_agent": False, "deliver": "origin", "schedule": "every 240m"},
    {"job_id": "30089d4a7953", "name": "vox-geopolitical-agent", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T11:55:35.056862-06:00", "last_status": "ok", "script": "run_vox_geopolitical.sh", "no_agent": False, "deliver": "origin", "schedule": "every 240m"},
    {"job_id": "53cceb22a695", "name": "vox-supply-chain-agent", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T12:31:52.076599-06:00", "last_status": "ok", "script": "run_vox_supply_chain.sh", "no_agent": False, "deliver": "origin", "schedule": "every 240m"},
    {"job_id": "93599576bfa9", "name": "vox-cost-monitor", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T09:01:02.492101-06:00", "last_status": "ok", "script": "run_vox_cost_monitor.sh", "no_agent": False, "deliver": "origin", "schedule": "0 9 * * *"},
    {"job_id": "53d5d19fdc64", "name": "vox-weekly-gbm-import", "enabled": False, "state": "paused", "last_run_at": "2026-06-08T09:01:18.753081-06:00", "last_status": "ok", "script": "scripts/import_gbm.py", "no_agent": False, "deliver": "origin", "schedule": "0 9 * * 1", "workdir": "/Users/jos/dev/vox-python"},
    {"job_id": "6130b5b97467", "name": "vox-premarket-briefing", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T08:37:37.374358-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "origin", "schedule": "30 8 * * 1-5"},
    {"job_id": "e40f1e49eded", "name": "vox-daily-top3-plays", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T07:11:42.576420-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "telegram", "schedule": "0 7 * * *"},
    {"job_id": "c39924caac44", "name": "vox-daily-obsidian-log", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T08:04:51.628582-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 8 * * *"},
    {"job_id": "96c65777c4e1", "name": "vox-weekly-obsidian-summary", "enabled": False, "state": "paused", "last_run_at": "2026-06-08T09:08:20.864701-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 9 * * 1"},
    {"job_id": "f6e6c6fb85c8", "name": "vox-monthly-obsidian-summary", "enabled": False, "state": "paused", "last_run_at": None, "last_status": None, "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 10 1 * *"},
    {"job_id": "023ee243a0c7", "name": "vox-cron-health-monitor", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T07:08:42.880682-06:00", "last_status": "error", "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 7 * * *"},
    {"job_id": "814b11ba86e0", "name": "vox-weekly-harness", "enabled": False, "state": "paused", "last_run_at": "2026-06-08T09:01:05.306407-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 9 * * 1"},
    {"job_id": "18a063132d6c", "name": "vox-monthly-harness", "enabled": False, "state": "paused", "last_run_at": None, "last_status": None, "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 9 1 * *"},
    {"job_id": "376a7c061ca2", "name": "vox-monthly-audit", "enabled": False, "state": "paused", "last_run_at": None, "last_status": None, "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 9 1 * *", "workdir": "/Users/jos/dev/vox-grader"},
    {"job_id": "ea74fd103c0c", "name": "sp500-weekly-grader", "enabled": False, "state": "paused", "last_run_at": "2026-06-08T07:39:43.864715-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "origin", "schedule": "0 18 * * 0", "workdir": "/Users/jos/dev/vox-grader"},
    {"job_id": "2a1efdca6017", "name": "sp500-daily-sector-screen", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-10T09:11:21.476017-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "local", "schedule": "0 9 * * 1-5", "workdir": "/Users/jos/dev/vox-grader"},
    {"job_id": "c533bef02e64", "name": "vox-macro-snapshot", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-15T06:02:41.084543-06:00", "last_status": "ok", "script": "vox_cron/vox_macro_snapshot.py", "no_agent": True, "deliver": "local", "schedule": "0 6 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "8f5666490611", "name": "vox-morning-briefing", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T08:00:44.885415-06:00", "last_status": "ok", "script": "vox_cron/vox_morning_briefing.py", "no_agent": True, "deliver": "origin", "schedule": "0 8 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "c3b0a8be789d", "name": "vox-alert-monitor", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T09:15:05.036911-06:00", "last_status": "ok", "script": "vox_cron/vox_alert_monitor.py", "no_agent": False, "deliver": "origin", "schedule": "0 9,15 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "52727b40dccb", "name": "vox-weekly-opportunities", "enabled": False, "state": "paused", "last_run_at": "2026-06-07T19:02:26.238538-06:00", "last_status": "ok", "script": "vox_cron/vox_weekly_opportunities.py", "no_agent": False, "deliver": "origin", "schedule": "0 19 * * 0", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "77b9f215be49", "name": "vox-daily-grade-sync", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-15T07:00:11.056588-06:00", "last_status": "ok", "script": "vox_cron/vox_daily_grade_sync.py", "no_agent": True, "deliver": "local", "schedule": "0 7 * * *", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "a30e653fb78e", "name": "vox-trump-tracker", "enabled": False, "state": "paused", "last_run_at": "2026-06-10T13:00:33.732386-06:00", "last_status": "ok", "script": None, "no_agent": False, "deliver": "origin", "schedule": "*/15 * * * *"},
    {"job_id": "85a2dece7a0d", "name": "vox-morning-digest", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-15T07:30:20.786703-06:00", "last_status": "ok", "script": "vox_cron/vox_morning_digest.py", "no_agent": True, "deliver": "telegram", "schedule": "30 7 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "cbdb93e40028", "name": "vox-evening-digest", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-12T16:30:29.366033-06:00", "last_status": "ok", "script": "vox_cron/vox_evening_digest.py", "no_agent": True, "deliver": "telegram", "schedule": "30 16 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "ddfd0d35955e", "name": "vox-council-daily-doc", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-12T08:00:29.113112-06:00", "last_status": "ok", "script": "vox_cron/vox_council_doc.py", "no_agent": True, "deliver": "local", "schedule": "0 8 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
    {"job_id": "afc8c8af3b81", "name": "vox-massive-opportunity", "enabled": True, "state": "scheduled", "last_run_at": "2026-06-12T18:54:51.693638-06:00", "last_status": "ok", "script": "vox_cron/vox_massive_opportunity.py", "no_agent": True, "deliver": "telegram", "schedule": "0 10,16 * * 1-5", "workdir": "/Users/jos/.hermes/scripts"},
]

now = datetime.now()
print("=" * 70)
print("VOX CRON AUDIT REPORT")
print("=" * 70)
print(f"Generated: {now.isoformat()}")
print(f"Total jobs: {len(crons)}")
print()

active = [c for c in crons if c["enabled"]]
paused = [c for c in crons if not c["enabled"]]
print(f"ACTIVE: {len(active)} | PAUSED: {len(paused)}")
print()

# Check script existence
script_paths = {
    "vox_cron/vox_macro_snapshot.py": "/Users/jos/.hermes/scripts/vox_cron/vox_macro_snapshot.py",
    "vox_cron/vox_morning_digest.py": "/Users/jos/.hermes/scripts/vox_cron/vox_morning_digest.py",
    "vox_cron/vox_evening_digest.py": "/Users/jos/.hermes/scripts/vox_cron/vox_evening_digest.py",
    "vox_cron/vox_massive_opportunity.py": "/Users/jos/.hermes/scripts/vox_cron/vox_massive_opportunity.py",
    "vox_cron/vox_council_doc.py": "/Users/jos/.hermes/scripts/vox_cron/vox_council_doc.py",
    "vox_cron/vox_daily_grade_sync.py": "/Users/jos/.hermes/scripts/vox_cron/vox_daily_grade_sync.py",
    "vox_cron/vox_alert_monitor.py": "/Users/jos/.hermes/scripts/vox_cron/vox_alert_monitor.py",
    "vox_cron/vox_morning_briefing.py": "/Users/jos/.hermes/scripts/vox_cron/vox_morning_briefing.py",
    "vox_cron/vox_weekly_opportunities.py": "/Users/jos/.hermes/scripts/vox_cron/vox_weekly_opportunities.py",
    "vox_position_review_v2.py": "/Users/jos/.hermes/scripts/vox_position_review_v2.py",
    "vox_trade_scorer_v2.py": "/Users/jos/.hermes/scripts/vox_trade_scorer_v2.py",
    "vox_alert_system_v2.py": "/Users/jos/.hermes/scripts/vox_alert_system_v2.py",
    "vox_autonomous_screener_v2.py": "/Users/jos/.hermes/scripts/vox_autonomous_screener_v2.py",
    "vox_evening_commander_v2.py": "/Users/jos/.hermes/scripts/vox_evening_commander_v2.py",
    "vox_sector_scanner_v2.py": "/Users/jos/.hermes/scripts/vox_sector_scanner_v2.py",
    "vox_market_regime_v2.py": "/Users/jos/.hermes/scripts/vox_market_regime_v2.py",
    "vox_daily_briefing_v2.py": "/Users/jos/.hermes/scripts/vox_daily_briefing_v2.py",
    "run_vox_weather.sh": "/Users/jos/.hermes/scripts/run_vox_weather.sh",
    "run_vox_geopolitical.sh": "/Users/jos/.hermes/scripts/run_vox_geopolitical.sh",
    "run_vox_supply_chain.sh": "/Users/jos/.hermes/scripts/run_vox_supply_chain.sh",
    "run_vox_cost_monitor.sh": "/Users/jos/.hermes/scripts/run_vox_cost_monitor.sh",
    "scripts/import_gbm.py": "/Users/jos/dev/vox-python/scripts/import_gbm.py",
}

print("-" * 70)
print("SCRIPT EXISTENCE CHECK")
print("-" * 70)
for script, path in script_paths.items():
    exists = os.path.exists(path)
    status = "EXISTS" if exists else "MISSING"
    print(f"  [{status}] {script}")
    if not exists:
        alt = f"/Users/jos/.hermes/scripts/{script}"
        if os.path.exists(alt):
            print(f"      -> Found at alternate: {alt}")
print()

# Active jobs deep dive
print("-" * 70)
print("ACTIVE JOBS ANALYSIS")
print("-" * 70)
for c in active:
    last = c.get("last_run_at")
    if last:
        try:
            dt = datetime.fromisoformat(last.replace("-06:00", ""))
            age = (now - dt).total_seconds() / 3600
            age_str = f"{age:.1f}h ago"
        except:
            age_str = "unknown"
    else:
        age_str = "NEVER"
    
    mode = "no_agent" if c.get("no_agent") else "LLM-agent"
    script = c.get("script") or "INLINE-PROMPT"
    print(f"\n  [ACTIVE] {c['name']}")
    print(f"     Job ID: {c['job_id']} | Mode: {mode} | Deliver: {c['deliver']}")
    print(f"     Schedule: {c['schedule']} | Last: {age_str} | Status: {c.get('last_status', 'N/A')}")
    print(f"     Script: {script}")
    if c.get("workdir"):
        print(f"     Workdir: {c['workdir']}")

print()
print("-" * 70)
print("PAUSED JOBS ANALYSIS (all 25)")
print("-" * 70)
for c in paused:
    last = c.get("last_run_at")
    if last:
        try:
            dt = datetime.fromisoformat(last.replace("-06:00", ""))
            age = (now - dt).total_seconds() / 3600
            age_str = f"{age:.1f}h ago"
        except:
            age_str = "unknown"
    else:
        age_str = "NEVER"
    
    mode = "no_agent" if c.get("no_agent") else "LLM-agent"
    script = c.get("script") or "INLINE-PROMPT"
    status = c.get("last_status", "N/A")
    print(f"  [PAUSED] {c['name']} | Last: {age_str} | Status: {status} | Mode: {mode}")

print()
print("-" * 70)
print("DELIVERY TARGET MATRIX")
print("-" * 70)
for target in ["local", "origin", "telegram"]:
    jobs = [c for c in crons if c["deliver"] == target]
    active_count = len([c for c in jobs if c["enabled"]])
    print(f"  {target}: {len(jobs)} total, {active_count} active")
    for c in jobs:
        state = "A" if c["enabled"] else "P"
        print(f"    [{state}] {c['name']}")

print()
print("-" * 70)
print("CRITICAL FINDINGS")
print("-" * 70)

# Find jobs with last_status=error
errors = [c for c in crons if c.get("last_status") == "error"]
if errors:
    print(f"[ERROR] Jobs with last_status=error: {len(errors)}")
    for c in errors:
        print(f"   - {c['name']} (last run: {c.get('last_run_at')})")
else:
    print("[OK] No jobs with last_status=error")

# Find jobs that never ran
never_ran = [c for c in crons if c.get("last_run_at") is None]
if never_ran:
    print(f"[WARN] Jobs that NEVER ran: {len(never_ran)}")
    for c in never_ran:
        print(f"   - {c['name']}")
else:
    print("[OK] All jobs have run at least once")

# Find jobs with stale last_run (>7 days)
stale = []
for c in crons:
    last = c.get("last_run_at")
    if last and c["enabled"]:
        try:
            dt = datetime.fromisoformat(last.replace("-06:00", ""))
            if (now - dt).days > 7:
                stale.append(c)
        except:
            pass
if stale:
    print(f"[WARN] Active jobs stale >7 days: {len(stale)}")
    for c in stale:
        print(f"   - {c['name']} (last: {c['last_run_at']})")
else:
    print("[OK] All active jobs ran within 7 days")

# Check for duplicate scripts
dup_scripts = {}
for c in crons:
    s = c.get("script") or "INLINE"
    if s != "INLINE":
        dup_scripts.setdefault(s, []).append(c["name"])
print()
print("-" * 70)
print("SCRIPT SHARING CHECK")
print("-" * 70)
for script, names in dup_scripts.items():
    if len(names) > 1:
        print(f"[WARN] {script} used by {len(names)} jobs: {', '.join(names)}")

print()
print("=" * 70)
print("END CRON AUDIT")
print("=" * 70)
