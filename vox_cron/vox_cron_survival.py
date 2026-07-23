#!/usr/bin/env python3
"""
VOX Cron Survival (Phase 4) — monthly anti-slop audit.

Rules:
  1) Enabled set must match ALLOWLIST only (no surprise re-enables)
  2) Telegram deliver only for DECISION_TG
  3) Flag erroring jobs, origin-not-TG-allowlist, unknown names
  4) Exit 1 if zombies found (so compound/ops can surface)

Writes: Obsidian system/Cron-Survival-LATEST.md
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

JOBS = Path.home() / ".hermes" / "cron" / "jobs.json"
OUT = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "system" / "Cron-Survival-LATEST.md"

# Single source of truth — Phase 4 allowlist
ALLOWLIST = {
    # Telegram decision
    "vox-daily-ops-card",
    "vox-intel-breaking",
    "vox-intel-breaking-weekend",
    # Context → Ops
    "vox-morning-context",
    "vox-outside-ideas",
    "vox-portfolio-brain-daily",
    "vox-obsidian-compound-pre",
    # Prices (single owner + adapters)
    "vox-pricing-held-intraday",
    "vox-pricing-eod",
    "vox-etoro-price-sync-v3",
    "vox-crypto-broker-sync",  # Binance + Bitso API → broker_positions
    # Fund free
    "vox-fmp-fund-enrich",
    # Hygiene refresh
    "vox-portfolio-weekly-grade",
    # Meta
    "vox-daily-health-check",
    "vox-repo-housekeeper",
    "vox-compound-weekly",
    "vox-cron-survival-monthly",
    "vox-k3-advisor",
    # Broadcast bot (self-send; Hermes deliver=local)
    "vox-weekly-monitor",
    # Radar Board panels A–E (feeds weekly + Ops EVENT; not a council)
    "vox-radar-board",
    # Intel Spine Phase 1+2 (JOS-267)
    "vox-intel-ingest",
    "vox-intel-distill",
    "vox-earnings-desk",
    # AUM daily track (WTD/WoW snaps)
    "vox-aum-track",
}

DECISION_TG = {
    "vox-daily-ops-card",
    "vox-intel-breaking",
    "vox-intel-breaking-weekend",
}
# Note: vox-weekly-monitor uses TELEGRAM_BROADCAST_* self-send, not Hermes origin.

# Explicitly dead forever (if re-enabled → zombie)
NEVER = {
    "vox-daily-top10-claude",
    "vox-grade-alerts-claude",
    "vox-master-data-pipeline",
    "vox-unified-grading",
    "vox-market-regime",
    "vox-regrade-sp500-weekly",
    "vox-price-history-sync",
    "vox-ai-council",
    "llm_council",
}


def _deliver_origin(j) -> bool:
    d = j.get("deliver")
    if d == "origin":
        return True
    if isinstance(d, str) and "origin" in d:
        return True
    if isinstance(d, list) and "origin" in d:
        return True
    return False


def main() -> int:
    raw = json.loads(JOBS.read_text())
    jobs = raw["jobs"] if isinstance(raw, dict) else raw
    enabled = [j for j in jobs if j.get("enabled", True)]
    paused = [j for j in jobs if not j.get("enabled", True)]

    zombies = []
    for j in enabled:
        name = j.get("name") or ""
        jid = j.get("id")
        status = j.get("last_status")

        if name in NEVER:
            zombies.append((name, jid, "NEVER_reenabled"))
            continue
        if name not in ALLOWLIST:
            zombies.append((name, jid, "not_on_allowlist"))
            continue
        if _deliver_origin(j) and name not in DECISION_TG:
            zombies.append((name, jid, "telegram_not_decision_surface"))
        if status == "error":
            zombies.append((name, jid, "last_status=error"))

    missing = sorted(ALLOWLIST - {j.get("name") for j in enabled})

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Cron Survival — {day}",
        "",
        f"**Phase 4 allowlist.** Enabled: **{len(enabled)}** · Paused: **{len(paused)}** · Target: ≤{len(ALLOWLIST)}",
        "",
        "## Allowlist (keep)",
    ]
    for n in sorted(ALLOWLIST):
        mark = "✅" if any(j.get("name") == n for j in enabled) else "❌ missing"
        lines.append(f"- {mark} `{n}`")

    lines += ["", "## Zombies / violations"]
    if not zombies:
        lines.append("- _none — fleet clean_")
    for name, jid, why in sorted(zombies):
        lines.append(f"- `{name}` (`{jid}`) — **{why}**")

    if missing:
        lines += ["", "## Missing allowlist jobs (should enable)"]
        for n in missing:
            lines.append(f"- `{n}`")

    lines += [
        "",
        "## Anti-slop rules",
        "1. Do **not** re-enable NEVER list (councils, master-data, top10-claude, price-history-sync…)",
        "2. Hermes Telegram only: Ops Card + Breaking (+ weekend). Weekly monitor = broadcast bot (local deliver).",
        "3. Price owner = `pricing_refresh` only; eToro = adapter",
        "4. If a job does not feed Ops/Decision for 30 days → pause",
        "5. New cron requires: allowlist edit + AGENTS.md note",
        "",
        "## Cadence (final)",
        "| CT | Job |",
        "|----|-----|",
        "| 05:00 | health · FMP fund |",
        "| 06:15 | morning context |",
        "| 06:30 | obsidian compound |",
        "| 07:00 | outside ideas |",
        "| 07:45 | **Ops Card (TG)** |",
        "| 08:00 | brain daily (local) |",
        "| 09–15 :15 | pricing held |",
        "| 09/12/16 | breaking (TG if material) |",
        "| 15:45 | pricing EOD |",
        "| Sun | weekly grade · **weekly monitor (broadcast bot)** · compound · survival monthly (1st) |",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")

    print(f"🧹 Cron survival Phase4 — enabled {len(enabled)} / paused {len(paused)}")
    print(f"Allowlist {len(ALLOWLIST)} · zombies {len(zombies)} · missing {len(missing)}")
    for name, jid, why in zombies[:20]:
        print(f"  ! {name}: {why}")
    for n in missing:
        print(f"  ? missing {n}")
    print(f"Note: {OUT}")
    return 1 if zombies else 0


if __name__ == "__main__":
    raise SystemExit(main())
