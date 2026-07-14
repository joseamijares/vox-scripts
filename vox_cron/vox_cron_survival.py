#!/usr/bin/env python3
"""
Monthly cron survival report: list enabled jobs that haven't impacted decisions.
Writes Obsidian system note; deliver local unless zombies found.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

JOBS = Path.home() / ".hermes" / "cron" / "jobs.json"
OUT = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "system" / "Cron-Survival-LATEST.md"

# Jobs that always count as decision-relevant
CORE = {
    "vox-portfolio-brain-daily",
    "vox-portfolio-brain-weekly",
    "vox-portfolio-weekly-grade",
    "vox-intel-breaking",
    "vox-intel-breaking-weekend",
    "vox-outside-ideas",
    "vox-daily-top10-claude",
    "vox-grade-alerts-claude",
    "vox-cron-monitor",
    "vox-daily-health-check",
    "portfolio-dashboard-update",
    "weekly-portfolio-sync",
    "vox-price-history-sync",
    "vox-hybrid-price-feed-full",
    "vox-etoro-price-sync-v3",
    "vox-master-data-pipeline",
    "vox-unified-grading",
    "vox-checklist-validator",
    "vox-repo-housekeeper",
    "vox-market-regime",
    "vox-regrade-sp500-weekly",
}


def main():
    raw = json.loads(JOBS.read_text())
    jobs = raw["jobs"] if isinstance(raw, dict) else raw
    enabled = [j for j in jobs if j.get("enabled", True)]
    paused = [j for j in jobs if not j.get("enabled", True)]
    zombies = []
    for j in enabled:
        name = j.get("name") or ""
        if name in CORE:
            continue
        # secondary feed jobs
        if j.get("deliver") in ("origin", "telegram") and name not in CORE:
            zombies.append((name, j.get("id"), "origin_but_not_core"))
        elif name.startswith("vox-ai-") or "council" in name or "pattern" in name:
            zombies.append((name, j.get("id"), "candidate_pause"))

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Cron Survival — {day}",
        "",
        f"Enabled: **{len(enabled)}** · Paused: **{len(paused)}** · Target: ≤25",
        "",
        "## Core (keep)",
    ]
    for n in sorted(CORE):
        if any(j.get("name") == n for j in enabled):
            lines.append(f"- `{n}`")
    lines += ["", "## Review / pause candidates"]
    if not zombies:
        lines.append("- _none flagged_")
    for name, jid, why in sorted(zombies):
        lines.append(f"- `{name}` (`{jid}`) — {why}")
    lines += [
        "",
        "## Rule",
        "If a job does not change a Brain decision in 30 days → pause.",
        "See Cron-Kill-List-2026-07-14.md",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")

    print(f"🧹 **Cron survival** — enabled {len(enabled)} / paused {len(paused)}")
    print(f"Candidates: {len(zombies)}")
    for name, jid, why in zombies[:12]:
        print(f"· {name} ({why})")
    print(f"Note: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
