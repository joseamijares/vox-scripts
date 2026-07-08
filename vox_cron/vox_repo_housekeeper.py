#!/usr/bin/env python3
"""
VOX Repo Housekeeper v1.0
Runs at midnight CT. Archives (does not delete) repo artifacts and stale cron outputs.
On Sunday, produces a weekly audit summary suggesting what to permanently delete.
"""
import os
import shutil
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path.home() / ".hermes" / "scripts"
ARCHIVE_ROOT = Path.home() / ".hermes" / "archive"
CRON_OUTPUT_DIR = Path.home() / ".hermes" / "cron" / "output"
OBSIDIAN_VOX = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox"
DAILY_LOG_DIR = OBSIDIAN_VOX / "memory" / "daily"
WEEKLY_AUDIT_DIR = OBSIDIAN_VOX / "system" / "audits"

VOX_CRON = REPO_ROOT / "vox_cron"
SCRIPT_ARCHIVE = VOX_CRON / "_archive"

KEEP_DAYS = {
    "pycache": 0,       # always archive to today's bucket
    "logs": 7,
    "cron_output": 30,
    "alert_state": 30,
}


def ensure_dirs():
    for d in [ARCHIVE_ROOT, DAILY_LOG_DIR, WEEKLY_AUDIT_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def today_bucket() -> Path:
    bucket = ARCHIVE_ROOT / datetime.now().strftime("%Y-%m/%d")
    bucket.mkdir(parents=True, exist_ok=True)
    return bucket


def archive_path(bucket: Path, src: Path) -> Path:
    rel = src.relative_to(Path.home()) if str(src).startswith(str(Path.home())) else src
    dest = bucket / str(rel).lstrip("/")
    dest.parent.mkdir(parents=True, exist_ok=True)
    counter = 0
    final_dest = dest
    while final_dest.exists():
        counter += 1
        final_dest = dest.parent / f"{dest.name}.{counter}"
    return final_dest


def move_to_archive(src: Path, bucket: Path) -> Path:
    dest = archive_path(bucket, src)
    if src.is_dir():
        shutil.move(str(src), str(dest))
    else:
        shutil.move(str(src), str(dest))
    return dest


def cleanup_pycache(bucket: Path):
    archived = []
    for pycache in REPO_ROOT.rglob("__pycache__"):
        if not pycache.is_dir():
            continue
        dest = archive_path(bucket, pycache)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pycache), str(dest))
        archived.append(str(pycache.relative_to(REPO_ROOT)))
    return archived


def cleanup_logs(bucket: Path):
    archived = []
    log_files = [
        REPO_ROOT / ".vox_pipeline.log",
        REPO_ROOT / ".grade_regen.log",
    ] + list(REPO_ROOT.glob("*.log"))
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS["logs"])
    for log in log_files:
        if not log.exists():
            continue
        try:
            mtime = datetime.fromtimestamp(log.stat().st_mtime)
            if mtime < cutoff or KEEP_DAYS["logs"] == 0:
                move_to_archive(log, bucket)
                archived.append(str(log.relative_to(REPO_ROOT)))
        except Exception as e:
            print(f"[WARN] Could not archive log {log}: {e}")
    return archived


def cleanup_alert_state(bucket: Path):
    archived = []
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS["alert_state"])
    for state in REPO_ROOT.glob(".vox_alert_state_v*.json"):
        if not state.is_file():
            continue
        # Keep the currently active version; archive old versions
        if "v8" in state.name:
            continue
        try:
            mtime = datetime.fromtimestamp(state.stat().st_mtime)
            if mtime < cutoff:
                move_to_archive(state, bucket)
                archived.append(state.name)
        except Exception as e:
            print(f"[WARN] Could not archive state {state}: {e}")
    return archived


def cleanup_cron_output(bucket: Path):
    archived = []
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS["cron_output"])
    if not CRON_OUTPUT_DIR.exists():
        return archived
    for f in CRON_OUTPUT_DIR.rglob("*"):
        if not f.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                move_to_archive(f, bucket)
                archived.append(str(f.relative_to(CRON_OUTPUT_DIR)))
        except Exception as e:
            print(f"[WARN] Could not archive cron output {f}: {e}")
    return archived


def ensure_daily_log():
    """Create a minimal daily Obsidian log stub if missing; compound system owns content."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = DAILY_LOG_DIR / f"{today}.md"
    if log_path.exists():
        return None
    template = f"""# Daily Log — {today}

**Status:** active  
**Owner:** Vox

## Morning Intentions

## What We Did

## Decisions
- [[memory/decisions/{today}|Decision Log]]

## Research Links

## Current Issues
| Issue | Severity | Next Step |
|-------|----------|-----------|

## Lessons Learned

## Handoff Needed?
- No.
"""
    log_path.write_text(template)
    return str(log_path)


def weekly_audit():
    """On Sunday, produce a summary of archived files and suggest deletions/organization."""
    if datetime.now().weekday() != 6:
        return None
    week_start = datetime.now() - timedelta(days=7)
    week_str = week_start.strftime("%Y-%m-%d")
    audit_path = WEEKLY_AUDIT_DIR / f"archive-audit-{week_str}.md"
    lines = [
        f"# Weekly Archive Audit — {week_str}",
        "",
        "Archives are grouped by date under `~/.hermes/archive/YYYY-MM/DD`.",
        "Review each bucket and either delete permanently or promote to cold storage.",
        "",
        "| Archive Bucket | Suggested Action |",
        "|----------------|------------------|",
    ]
    if ARCHIVE_ROOT.exists():
        for month_dir in sorted(ARCHIVE_ROOT.iterdir()):
            if not month_dir.is_dir():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                size_mb = sum(f.stat().st_size for f in day_dir.rglob("*") if f.is_file()) / (1024 * 1024)
                lines.append(f"| `{month_dir.name}/{day_dir.name}` | Review ({size_mb:.1f} MB) |")
    lines.extend([
        "",
        "## Cleanup rules",
        "- `__pycache__` archives: safe to delete after 30 days.",
        "- `.log` archives: safe to delete after 7 days.",
        "- Cron output archives: keep for 90 days, then delete unless flagged.",
    ])
    audit_path.write_text("\n".join(lines))
    return str(audit_path)


def flag_version_creep():
    """Detect new _vN.py duplicate scripts in vox_cron/ and emit an audit note."""
    flagged = []
    v_pattern = re.compile(r"_v\d+\.py$")
    # Only scan top-level vox_cron/ scripts, not _archive/ or subdirectories
    for p in VOX_CRON.glob("*.py"):
        if p.is_file() and v_pattern.search(p.name):
            flagged.append(str(p.relative_to(REPO_ROOT)))
    if not flagged:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = OBSIDIAN_VOX / "system" / "audits" / f"version-creep-{today}.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Version Creep Alert — {today}",
        "",
        "New `_vN.py` scripts detected in `vox_cron/`. These are candidates for consolidation or archiving.",
        "",
        "| Script | Action |",
        "|--------|--------|",
    ]
    for f in sorted(flagged):
        lines.append(f"| `{f}` | Review / consolidate |")
    lines.extend([
        "",
        "Run `python3 vox_cron/audit_active_scripts.py` to determine if the old version is still referenced.",
    ])
    note_path.write_text("\n".join(lines))
    return str(note_path)


def main():
    ensure_dirs()
    bucket = today_bucket()
    report = {
        "archived_pycache": cleanup_pycache(bucket),
        "archived_logs": cleanup_logs(bucket),
        "archived_alert_state": cleanup_alert_state(bucket),
        "archived_cron_output": cleanup_cron_output(bucket),
        "daily_log_created": ensure_daily_log(),
        "weekly_audit": weekly_audit(),
        "version_creep_note": flag_version_creep(),
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
