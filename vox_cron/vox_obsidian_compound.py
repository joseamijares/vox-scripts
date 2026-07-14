#!/usr/bin/env python3
"""
VOX Obsidian Compound System v1.0
Populates the daily log with real VOX data, multiple times per day.
"""
import os
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap
from vox_cron.vox_utils import query_db, call_openrouter
from vox_cron.vox_data_health import assess_data_health, health_summary
from vox_cron.vox_hy3_workhorse import hy3_draft

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
    "Brain": Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "brain",
}

SYNC_LABELS = {0: "pre-market", 1: "midday", 2: "post-market"}

VOX_WRITTEN_MARKER = "<!-- vox-written -->"
FIELD_GUIDE_LINK = "[[FieldGuide|VOX Field Guide]]"

THESIS_DIR = OBSIDIAN_VOX / "memory" / "theses"


def ensure_dirs():
    for d in [DAILY_DIR, DECISION_DIR, WEEKLY_DIR, THESIS_DIR] + list(RESEARCH_DIRS.values()):
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
    """Pull real issues: latest-per-ticker stale grades, broker staleness, breaking shocks."""
    lines = []
    # Pattern 7: latest per ticker only
    rows = query_db(
        """
        SELECT COUNT(*) FROM (
          SELECT ticker FROM vox_grades
          GROUP BY ticker
          HAVING MAX(generated_at) < NOW() - INTERVAL '7 days' OR MAX(generated_at) IS NULL
        ) s
        """
    )
    stale = rows[0][0] if rows else 0
    stale = int(stale.strip()) if isinstance(stale, str) else int(stale)
    lines.append(f"- {stale} tickers with latest grade older than 7d")

    rows2 = query_db(
        """
        SELECT broker, MAX(last_sync_at)
        FROM broker_positions
        GROUP BY broker
        HAVING MAX(last_sync_at) < NOW() - INTERVAL '7 days'
        ORDER BY MAX(last_sync_at)
        """
    )
    if rows2:
        stale_brokers = ", ".join(f"{r[0]} ({r[1]})" for r in rows2)
        lines.append(f"- Stale brokers (>7d): {stale_brokers}")

    breaking = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "decisions" / "Breaking-LATEST.md"
    if breaking.exists():
        age_h = (datetime.now().timestamp() - breaking.stat().st_mtime) / 3600
        head = ""
        for line in breaking.read_text().splitlines():
            if line.startswith("**Headline:**") or line.startswith("**Severity:**"):
                head += line + " "
        lines.append(f"- Breaking note ({age_h:.1f}h old): {head.strip()[:180] or 'see [[memory/decisions/Breaking-LATEST]]'}")
    return "\n".join(lines) if lines else "- No open issues"


def get_daily_log_path() -> Path:
    return DAILY_DIR / f"{today_str()}.md"




def generate_llm_sections(sync_idx: int, top_grades: str, alerts: str, open_issues: str, research_links: str) -> dict:
    """Ask deepseek-v4-flash to draft Morning Intentions, Current Issues, Lessons, and Decision Candidates."""
    label = SYNC_LABELS.get(sync_idx, "sync")
    system_prompt = """You are Vox, an aggressive-growth investing assistant. You write concise, specific, actionable notes.
Do not write generic motivational text. Every item must reference a real ticker, signal, or concrete trigger.
Use markdown tables where requested. Be brief."""
    user_prompt = f"""Generate content for the VOX daily log at the **{label}** sync on {today_str()}.

Data available:

**Top grades today:**
{top_grades}

**Alerts:**
{alerts}

**Open issues:**
{open_issues}

**Research links:**
{research_links}

Produce exactly these sections:

## Morning Intentions
- 2-3 bullet points. Only if {label} is pre-market. If not pre-market, write "_Generated at {label} sync — morning intentions already set._".
- Each bullet: ticker, trigger, and invalidation.

## Current Issues
- A markdown table with columns: Issue, Severity, Next Step.
- 2-4 rows from the data or known system blockers. Severity = critical/high/medium/low.

## Lessons Learned
- 1-3 bullet points. Synthesize from grades and alerts. If no actionable lesson, write "_No new lessons from this sync._".

## Decision Candidates
- A markdown table with columns: Ticker, Decision, Source, Reason, Expected Edge.
- Proposed actions only; do NOT state they are executed. Use verbs like: "Consider BUY", "Consider TRIM", "Consider PASS".

Format the entire response as markdown with the four section headers exactly as above."""
    try:
        result = hy3_draft(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1500,
            temperature=0.3,
            script_name="vox_obsidian_compound",
            fallback_model="deepseek/deepseek-v4-flash",
        )
        text = result.get("content", "")
    except Exception as e:
        text = f"""
## Morning Intentions
- _LLM synthesis failed: {e}_

## Current Issues
| Issue | Severity | Next Step |
|-------|----------|-----------|
| LLM synthesis failed | medium | Check API key and cost |

## Lessons Learned
- _No synthesis available._

## Decision Candidates
| Ticker | Decision | Source | Reason | Expected Edge |
|--------|----------|--------|--------|---------------|
"""
    return parse_llm_sections(text)


def parse_llm_sections(text: str) -> dict:
    """Parse the LLM response into sections."""
    sections = {
        "morning_intentions": "- _No morning intentions generated._",
        "current_issues": "| Issue | Severity | Next Step |\n|-------|----------|-----------|\n",
        "lessons_learned": "- _No lessons generated._",
        "decision_candidates": "| Ticker | Decision | Source | Reason | Expected Edge |\n|--------|----------|--------|--------|---------------|\n",
    }
    current = None
    buffer = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Morning Intentions"):
            current = "morning_intentions"
            buffer = []
        elif stripped.startswith("## Current Issues"):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = "current_issues"
            buffer = []
        elif stripped.startswith("## Lessons Learned"):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = "lessons_learned"
            buffer = []
        elif stripped.startswith("## Decision Candidates"):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = "decision_candidates"
            buffer = []
        elif current and not stripped.startswith("## "):
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    # Fallbacks: ensure key sections are never empty
    default_issues = "| Issue | Severity | Next Step |\n|-------|----------|-----------|\n"
    if not sections.get("current_issues", "").strip() or sections["current_issues"] == default_issues or sections["current_issues"] == default_issues.rstrip("\n"):
        sections["current_issues"] = default_issues + "| Stale grades accumulating | medium | Schedule grade refresh or reduce universe |\n"
    if not sections.get("lessons_learned", "").strip():
        sections["lessons_learned"] = "- _No new lessons generated from this sync._"
    return sections


def normalize_issues_section(section: str) -> str:
    """Remove markdown header/separator from current issues and return just rows."""
    lines = []
    for line in section.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("| Issue") or stripped.startswith("|-------"):
            continue
        lines.append(line)
    return "\n".join(lines)


def normalize_candidates_section(section: str) -> str:
    """Remove markdown header/separator from decision candidates and return just rows."""
    lines = []
    for line in section.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("| Ticker") or stripped.startswith("|--------"):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_table_body(table_text: str) -> str:
    """Remove markdown table header and separator lines."""
    lines = [l for l in table_text.strip().splitlines() if l.strip() and not l.strip().startswith("| Issue") and not l.strip().startswith("| Ticker") and not l.strip().startswith("|-------")]
    return "\n".join(lines)


def section_body_is_empty(body: str) -> bool:
    """Return True if section body has no human-written content."""
    if not body.strip():
        return True
    if VOX_WRITTEN_MARKER in body:
        return True
    # Strip markdown table headers and list markers
    stripped = body.strip()
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    # If all remaining lines are table headers/separators, it's empty
    for line in lines:
        if not line.startswith("|"):
            return False
        # It's a table line; check if it's header or separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and not all(c.replace("-", "") == "" or c in ("Issue", "Severity", "Next Step", "Ticker", "Decision", "Source", "Reason", "Expected Edge") for c in cells):
            return False
    return True


def fill_section(content: str, heading: str, new_body: str) -> str:
    """Replace a section body if it is empty or previously auto-generated."""
    marker = f"## {heading}\n"
    if marker not in content:
        return content
    parts = content.split(marker, 1)
    before = parts[0]
    after_parts = parts[1].split("\n##", 1)
    after = "\n##" + after_parts[1] if len(after_parts) > 1 else ""
    body = after_parts[0]
    # If body is empty, auto-generated, or just a table header, overwrite
    if section_body_is_empty(body):
        new_body = new_body.strip() + "\n" + VOX_WRITTEN_MARKER + "\n"
        return before + marker + "\n" + new_body + "\n" + after
    return content


def update_frontmatter(content: str, source_grade_id: str = "", data_confidence: int = 0) -> str:
    """Update or add YAML frontmatter fields."""
    now = datetime.now().isoformat()
    if content.startswith("---"):
        # Extract existing frontmatter
        parts = content.split("---", 2)
        if len(parts) >= 3:
            _, fm, rest = parts
            fm_lines = [l for l in fm.splitlines() if l.strip() and not l.startswith("source_grade_id:") and not l.startswith("data_confidence:") and not l.startswith("generated_at:")]
            fm_lines += [
                f"source_grade_id: \"{source_grade_id}\"",
                f"data_confidence: {data_confidence}",
                f"generated_at: \"{now}\"",
            ]
            new_fm = "\n".join(fm_lines)
            return f"---\n{new_fm}\n---\n{rest}"
    # No frontmatter; add one
    fm_lines = [
        "---",
        f"source_grade_id: \"{source_grade_id}\"",
        f"data_confidence: {data_confidence}",
        f"generated_at: \"{now}\"",
        "---",
        "",
    ]
    return "\n".join(fm_lines) + content


def fallback_sections(health: dict) -> dict:
    """When data confidence is LOW, produce conservative fallback sections."""
    blocking_str = "; ".join(health["blocking"]) or "Data quality below threshold"
    return {
        "morning_intentions": f"- _Data confidence is LOW ({health['score']}/100). Morning intentions require fresh unified_grades. Blocking: {blocking_str}_",
        "current_issues": f"| Data confidence gate | critical | Resolve: {blocking_str} |\n| Data quality too low for LLM synthesis | high | Refresh grades, price history, or required tables |",
        "lessons_learned": f"- _When data confidence is below 50, do not generate new decision candidates. Wait for the next refresh cycle._",
        "decision_candidates": "| Ticker | Decision | Source | Reason | Expected Edge |\n|--------|----------|--------|--------|---------------|\n| _NONE_ | Consider PASS | data_health | Low confidence | Preserve capital |",
    }


def generate_decision_candidates(section_text: str) -> str:
    """Return candidate rows for the decision log table, with thesis links."""
    body = normalize_candidates_section(section_text)
    return add_thesis_links_to_rows(body)


def add_thesis_links_to_rows(rows_text: str) -> str:
    """Add [[memory/theses/TICKER|TICKER]] links to candidate rows."""
    lines = []
    for line in rows_text.strip().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Accept 5-column daily-candidate table or 6-column with Time
        if len(cells) >= 5:
            offset = 0 if len(cells) == 5 else 1
            ticker = cells[offset]
            if ticker and ticker not in ("_NONE_", "Ticker", ""):
                ensure_thesis(ticker)
                cells[offset] = f"[[memory/theses/{ticker}|{ticker}]]"
            lines.append("| " + " | ".join(cells) + " |")
        elif line.strip() and not line.strip().startswith("| Ticker") and not line.strip().startswith("|--------"):
            lines.append(line)
    return "\n".join(lines)


def ticker_candidates_to_thesis_links(rows_text: str) -> str:
    """Convert candidate rows into a list of thesis links for the daily note."""
    links = []
    for line in rows_text.strip().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 5:
            offset = 0 if len(cells) == 5 else 1
            ticker_raw = cells[offset]
            # Strip any existing markdown link
            ticker = ticker_raw.replace("[[", "").replace("]]", "").split("|")[-1]
            if ticker and ticker not in ("_NONE_", "Ticker"):
                links.append(f"- [[memory/theses/{ticker}|{ticker}]]")
    return "\n".join(links) if links else "- _No candidates generated."


def ensure_thesis(ticker: str) -> Path:
    """Create a ticker thesis page if missing, with links to decision log and research notes."""
    path = THESIS_DIR / f"{ticker}.md"
    if path.exists():
        return path
    today = today_str()
    template = f"""---
ticker: "{ticker}"
status: "watch"
data_confidence: 0
source_grade_id: ""
generated_at: "{datetime.now().isoformat()}"
---

# Thesis — {ticker}

**Status:** watch  
**Why here:** Decision candidate from VOX daily compound on {today}.

## Links
- [[memory/decisions/{today}|Decision Log]]
- [[SmartMoney/{latest_file_name(RESEARCH_DIRS['SmartMoney'])}|SmartMoney]]
- [[SectorRotation/{latest_file_name(RESEARCH_DIRS['SectorRotation'])}|SectorRotation]]
- [[Discovery/{latest_file_name(RESEARCH_DIRS['Discovery'])}|Discovery]]
- [[Earnings/{latest_file_name(RESEARCH_DIRS['Earnings'])}|Earnings]]

## Setup
- _To be filled from daily log and research notes._

## Trigger
- _To be filled from Morning Intentions / Decision Candidates._

## Invalidation
- _To be filled._

## Notes
- Created by `vox_obsidian_compound.py` on {today}.
"""
    path.write_text(template)
    return path


def latest_file_name(folder: Path) -> str:
    """Return latest filename in folder, or empty string."""
    f = latest_file(folder)
    return f.name if f else ""


def ensure_daily_log():
    """Create the daily log if missing, with YAML frontmatter."""
    path = get_daily_log_path()
    if path.exists():
        return path
    template = f"""---
source_grade_id: ""
data_confidence: 0
generated_at: "{datetime.now().isoformat()}"
---

# Daily Log — {today_str()}

**Status:** active  
**Owner:** Vox | Manual fields explained in {FIELD_GUIDE_LINK}

## Morning Intentions

## What We Did

## Decisions
- [[memory/decisions/{today_str()}|Decision Log]]
- [[memory/theses|All Theses]]

## Decision Candidates
| Ticker | Decision | Source | Reason | Expected Edge |
|--------|----------|--------|--------|---------------|

## Active Theses
- _Links to theses generated today will appear here._

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
    research_links = f"\n**Research today:** {smart_link} | {sector_link} | {discovery_link} | {news_link} | {earnings_link} | [[memory/brain/Brain-LATEST|Portfolio Brain]] | [[memory/decisions/Breaking-LATEST|Breaking Shock]]\n"
    if "## Research Links" in content:
        parts = content.split("## Research Links", 1)
        after_section = parts[1].split("\n##", 1)
        content = parts[0] + "## Research Links" + research_links + "\n##" + after_section[1]

    # Assess data health before using any data for LLM synthesis
    health = assess_data_health()
    health_md = health_summary(health)
    confidence = health["score"]

    # Stamp frontmatter on the daily note
    content = update_frontmatter(content, source_grade_id="unified_grades", data_confidence=confidence)

    # Insert health summary into What We Did block
    actual_end_marker = f"<!-- vox-sync-end: {label} -->"
    block = block.replace(
        actual_end_marker,
        f"**Data Health:**\n{health_md}\n\n{actual_end_marker}"
    )
    # Re-apply the replacement since `block` may have changed
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

    # Generate LLM-drafted manual sections only if confidence >= 50 (MEDIUM)
    top_grades = db_recent_grades()
    alerts = db_recent_alerts()
    open_issues = db_open_issues()
    research_links_text = f"{smart_link} | {sector_link} | {discovery_link} | {news_link} | {earnings_link}"
    if confidence >= 50:
        sections = generate_llm_sections(sync_idx, top_grades, alerts, open_issues + "\n- " + "\n- ".join(health["blocking"] + health["warnings"]), research_links_text)
    else:
        sections = fallback_sections(health)

    content = fill_section(content, "Morning Intentions", sections["morning_intentions"])
    # Reconstruct current issues table from the row-only section
    issues_body = normalize_issues_section(sections["current_issues"])
    if issues_body.strip():
        issues_table = "| Issue | Severity | Next Step |\n|-------|----------|-----------|\n" + issues_body + "\n"
    else:
        issues_table = "| Issue | Severity | Next Step |\n|-------|----------|-----------|\n| Stale grades accumulating | medium | Schedule grade refresh or reduce universe |\n"
    content = fill_section(content, "Current Issues", issues_table)
    content = fill_section(content, "Lessons Learned", sections["lessons_learned"])
    content = fill_section(content, "Decision Candidates", sections["decision_candidates"])
    content = fill_section(content, "Active Theses", ticker_candidates_to_thesis_links(sections["decision_candidates"]))

    # Generate decision candidates into the dedicated decision log
    candidate_rows = generate_decision_candidates(sections["decision_candidates"])
    ensure_decision_candidates(candidate_rows)

    path.write_text(content)
    return path


def ensure_decision_candidates(candidate_rows: str):
    """Append or overwrite machine-generated decision candidates to today's decision log."""
    path = DECISION_DIR / f"{today_str()}.md"
    ensure_decision_log()
    content = path.read_text()
    # If candidates already written by machine, replace that block
    marker = "\n<!-- vox-candidates -->\n"
    end_marker = "\n<!-- vox-candidates-end -->\n"
    # Transform candidate rows into decision-log rows with time and empty outcome
    time_str = datetime.now().strftime("%H:%M")
    log_rows = []
    for line in candidate_rows.strip().splitlines():
        if line.strip() and not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 5 and cells[0] not in ("Ticker", "_NONE_"):
            # 5-column daily format: Ticker, Decision, Source, Reason, Expected Edge
            log_rows.append(f"| {time_str} | " + " | ".join(cells[:5]) + " | |")
    if not log_rows:
        log_rows.append(f"| {time_str} | _NONE_ | Consider PASS | data_health | Low confidence | Preserve capital | |")
    block = marker + "\n".join(log_rows) + end_marker
    if marker in content and end_marker in content:
        before = content.split(marker, 1)[0]
        after = content.split(end_marker, 1)[1]
        content = before + block + after
    else:
        content = content.rstrip() + block
    path.write_text(content)


def ensure_decision_log():
    """Create today's decision registry if missing, with YAML frontmatter."""
    path = DECISION_DIR / f"{today_str()}.md"
    if path.exists():
        return path
    template = f"""---
source_grade_id: ""
data_confidence: 0
generated_at: "{datetime.now().isoformat()}"
---

# Decision Log — {today_str()}

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
