#!/usr/bin/env python3
"""
VOX Obsidian Compound System v1.0
Populates the daily log with real VOX data, multiple times per day.
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap
from vox_cron.vox_utils import query_db, call_openrouter

OBSIDIAN_VOX = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox"
DAILY_DIR = OBSIDIAN_VOX / "memory" / "daily"
DECISION_DIR = OBSIDIAN_VOX / "memory" / "decisions"
WEEKLY_DIR = OBSIDIAN_VOX / "memory" / "weekly"
RESEARCH_DIRS = {
    "SmartMoney": Path.home() / "Documents" / "Obsidian" / "VOX" / "SmartMoney",
    "SectorRotation": Path.home() / "Documents" / "Obsidian" / "VOX" / "SectorRotation",
    "Discovery": Path.home() / "Documents" / "Obsidian" / "VOX" / "Discovery",
    "SignalQuality": Path.home() / "Documents" / "Obsidian" / "VOX" / "SignalQuality",
    "NewsBriefs": Path.home() / "Documents" / "Obsidian" / "VOX" / "NewsBriefs",
    "Earnings": Path.home() / "Documents" / "Obsidian" / "VOX" / "Earnings",
}

SYNC_LABELS = {0: "pre-market", 1: "midday", 2: "post-market"}


def ensure_dirs():
    for d in [DAILY_DIR, DECISION_DIR, WEEKLY_DIR] + list(RESEARCH_DIRS.values()):
        d.mkdir(parents=True, exist_ok=True)


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def rel_link(path: Path) -> str:
    """Return an Obsidian relative link from the vox daily folder."""
    try:
        rel = path.relative_to(Path.home() / "Documents" / "Obsidian" / "VOX")
    except ValueError:
        rel = path
    return str(rel)


def latest_file(folder: Path, suffix: str = ".md") -> Path:
    files = [f for f in folder.iterdir() if f.is_file() and f.name.endswith(suffix)]
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def tail_lines(path: Path, n: int = 20) -> str:
    if not path or not path.exists():
        return "_No data yet_"
    lines = path.read_text().splitlines()
    return "\n".join(lines[-n:]) if lines else "_Empty_"


def extract_bullets(path: Path, n: int = 10) -> str:
    if not path or not path.exists():
        return "- _No data yet_"
    bullets = [l for l in path.read_text().splitlines() if l.strip().startswith("- ") or l.strip().startswith("|")]
    return "\n".join(bullets[-n:]) if bullets else "- _Empty_"


def db_recent_alerts() -> str:
    """Pull recent grade-swing alerts from the last 24h."""
    rows = query_db("""
        SELECT ticker, alert_type, old_grade, new_grade, old_action, new_action, triggered_at
        FROM grade_alerts
        WHERE triggered_at > NOW() - INTERVAL '24 hours'
        ORDER BY triggered_at DESC
        LIMIT 20
    """)
    if not rows:
        return "- No alerts in last 24h"
    out = []
    for r in rows:
        t, atype, old_g, new_g, old_a, new_a, when = r[:7]
        grade_line = f"grade {old_g} → {new_g}" if old_g and new_g else ""
        action_line = f"action {old_a} → {new_a}" if old_a and new_a else ""
        parts = [p for p in [grade_line, action_line] if p]
        out.append(f"- **{t}** {atype}: {', '.join(parts)} at {when}")
    return "\n".join(out)


def db_recent_grades() -> str:
    """Pull top grade changes and current top opportunities."""
    rows = query_db("""
        SELECT ticker, unified_grade, action
        FROM unified_grades
        WHERE computed_at > NOW() - INTERVAL '24 hours'
        ORDER BY unified_grade DESC
        LIMIT 10
    """)
    if not rows:
        return "- No fresh grades"
    return "\n".join([f"- **{r[0].strip()}** {r[2].strip()} (grade {r[1].strip()})" for r in rows])


def db_cron_runs() -> str:
    """Pull recent Hermes cron job runs."""
    jobs_path = Path.home() / ".hermes" / "cron" / "jobs.json"
    if not jobs_path.exists():
        return "- Could not read cron jobs.json"
    try:
        data = json.loads(jobs_path.read_text())
        out = []
        for job in data.get("jobs", [])[:20]:
            name = job.get("name", "unknown")
            last = job.get("last_run_at", "never")
            status = job.get("last_status", "unknown")
            out.append(f"- {name}: {status} (last {last})")
        return "\n".join(out)
    except Exception as e:
        return f"- Error reading jobs.json: {e}"


def db_cost_summary() -> str:
    """Pull today's LLM cost."""
    rows = query_db("""
        SELECT COALESCE(SUM(total_cost), 0), COUNT(*)
        FROM vox_llm_costs
        WHERE run_at > NOW() - INTERVAL '24 hours'
    """)
    if not rows:
        return "- $0.00 (0 runs)"
    total, count = rows[0]
    total = float(total.strip()) if isinstance(total, str) else float(total)
    count = int(count.strip()) if isinstance(count, str) else int(count)
    return f"- ${total:.4f} ({count} runs)"


def db_open_issues() -> str:
    """Pull stale grades and any known issues."""
    rows = query_db("""
        SELECT COUNT(*) FROM vox_grades WHERE generated_at < NOW() - INTERVAL '7 days' OR generated_at IS NULL
    """)
    stale = rows[0][0] if rows else 0
    stale = int(stale.strip()) if isinstance(stale, str) else int(stale)
    return f"- {stale} stale grades (>7 days)"


def get_daily_log_path() -> Path:
    return DAILY_DIR / f"{today_str()}.md"


def ensure_daily_log():
    """Create the daily log if missing."""
    path = get_daily_log_path()
    if path.exists():
        return path
    template = f"""# Daily Log — {today_str()}

**Status:** active  
**Owner:** Vox

## Morning Intentions

## What We Did

## Decisions
- [[memory/decisions/{today_str()}|Decision Log]]

## Research Links

## Current Issues
| Issue | Severity | Next Step |
|-------|----------|-----------|

## Lessons Learned

## Handoff Needed?
- No.
"""
    path.write_text(template)
    return path


def sync_daily_log(sync_idx: int):
    """Populate the daily log with current data, replacing the same sync block if it exists."""
    ensure_dirs()
    path = ensure_daily_log()
    content = path.read_text()
    label = SYNC_LABELS.get(sync_idx, "sync")
    now = datetime.now().strftime("%H:%M")

    # Collect data
    smart = latest_file(RESEARCH_DIRS["SmartMoney"])
    sector = latest_file(RESEARCH_DIRS["SectorRotation"])
    discovery = latest_file(RESEARCH_DIRS["Discovery"])
    news = latest_file(RESEARCH_DIRS["NewsBriefs"])
    earnings = latest_file(RESEARCH_DIRS["Earnings"])

    smart_link = f"[[{rel_link(smart)}|SmartMoney]]" if smart else "SmartMoney"
    sector_link = f"[[{rel_link(sector)}|SectorRotation]]" if sector else "SectorRotation"
    discovery_link = f"[[{rel_link(discovery)}|Discovery]]" if discovery else "Discovery"
    news_link = f"[[{rel_link(news)}|NewsBrief]]" if news else "NewsBrief"
    earnings_link = f"[[{rel_link(earnings)}|Earnings]]" if earnings else "Earnings"

    block = f"""<!-- vox-sync: {label} -->
### {label} sync ({now} CT)

**Top grades today:**
{db_recent_grades()}

**Alerts:**
{db_recent_alerts()}

**Cost:**
{db_cost_summary()}

**Cron health:**
{db_cron_runs()}

**Open issues:**
{db_open_issues()}
<!-- vox-sync-end: {label} -->

"""

    # Idempotent insertion: replace existing sync block, or append after "## What We Did"
    start_marker = f"<!-- vox-sync: {label} -->"
    end_marker = f"<!-- vox-sync-end: {label} -->"
    if start_marker in content and end_marker in content:
        before = content.split(start_marker, 1)[0]
        after = content.split(end_marker, 1)[1]
        content = before + block + after
    else:
        marker = "## What We Did\n"
        if marker in content:
            before, after = content.split(marker, 1)
            content = before + marker + "\n" + block + after
        else:
            content += "\n\n" + block

    # Update research links section once per day (replace placeholder)
    research_links = f"\n**Research today:** {smart_link} | {sector_link} | {discovery_link} | {news_link} | {earnings_link}\n"
    if "## Research Links" in content:
        parts = content.split("## Research Links", 1)
        after_section = parts[1].split("\n##", 1)
        content = parts[0] + "## Research Links" + research_links + "\n##" + after_section[1]

    path.write_text(content)
    return path


def ensure_decision_log():
    """Create today's decision registry if missing."""
    path = DECISION_DIR / f"{today_str()}.md"
    if path.exists():
        return path
    template = f"""# Decision Log — {today_str()}

| Time | Ticker | Decision | Source | Reason | Expected Edge | Outcome (later) |
|------|--------|----------|--------|--------|---------------|-----------------|

"""
    path.write_text(template)
    return path


def weekly_compounding():
    """Generate Sunday compounding review."""
    if datetime.now().weekday() != 6:
        return None
    today = today_str()
    path = WEEKLY_DIR / f"compounding-{today}.md"
    if path.exists():
        return path

    # Pull last 7 days of daily logs and decisions
    week_days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7, 0, -1)]
    log_links = [f"- [[../daily/{d}|{d}]]" for d in week_days if (DAILY_DIR / f"{d}.md").exists()]
    decision_links = [f"- [[../decisions/{d}|{d}]]" for d in week_days if (DECISION_DIR / f"{d}.md").exists()]

    # LLM synthesis
    system_prompt = "You are Vox, an aggressive-growth investing assistant. Synthesize the week into 3 lessons, 2 corrected actions, and 1 priority for next week. Be direct, no fluff."
    user_prompt = f"""Weekly VOX data:
- Daily logs: {len(log_links)} days
- Decision logs: {len(decision_links)} days

Review the daily logs and decision logs (linked) and produce:
1. What worked this week (patterns that produced edge)
2. What failed (sources/grades/alerts that were wrong)
3. Top 3 lessons to encode into vox/memory/lessons.md
4. One priority action for next week
"""
    try:
        result = call_openrouter(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="deepseek/deepseek-v4-flash",
            max_tokens=1500,
            script_name="vox_obsidian_compound",
            notes="weekly compounding review",
        )
        synthesis = result["content"]
    except Exception as e:
        synthesis = f"_LLM synthesis failed: {e}_"

    template = f"""# Weekly Compounding Review — {today}

## Daily Logs This Week
{chr(10).join(log_links) if log_links else "- No daily logs found"}

## Decision Logs This Week
{chr(10).join(decision_links) if decision_links else "- No decisions recorded"}

## Synthesis
{synthesis}

## Action Items
- [ ] Review synthesis with Jose
- [ ] Promote confirmed lessons to `vox/memory/lessons.md`
- [ ] Tag repeated mistakes for automation
"""
    path.write_text(template)
    return path


def infer_sync_from_time() -> int:
    """Map current local time to sync label: pre-market before 10, midday 10-15, post-market 15+."""
    hour = datetime.now().hour
    if hour < 10:
        return 0  # pre-market
    elif hour < 15:
        return 1  # midday
    else:
        return 2  # post-market


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", type=int, default=None, choices=[0, 1, 2], help="0=pre-market, 1=midday, 2=post-market")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly compounding review")
    args = parser.parse_args()

    sync_idx = args.sync if args.sync is not None else infer_sync_from_time()

    ensure_dirs()
    ensure_decision_log()
    log_path = sync_daily_log(sync_idx)
    print(f"Synced daily log: {log_path}")

    if args.weekly or datetime.now().weekday() == 6:
        weekly_path = weekly_compounding()
        if weekly_path:
            print(f"Weekly compounding: {weekly_path}")
        else:
            print("Weekly review already exists or skipped")


if __name__ == "__main__":
    main()
