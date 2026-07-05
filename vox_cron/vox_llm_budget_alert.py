#!/usr/bin/env python3
"""
VOX LLM Budget Alert — lightweight guardrail.

Runs hourly during market hours. Checks current month spend against
vox_llm_budget thresholds. If spend exceeds the pause threshold, uses
Hermes cron API (via subprocess) to pause non-essential LLM crons.

Never pauses price feeds, grading, alerts, or monitor.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import subprocess
from datetime import datetime, date
from calendar import monthrange

import psycopg2

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "railway")
DB_PASSWORD = os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", ""))

# Non-essential LLM crons that may be paused under budget pressure.
PAUSEABLE_CRONS = {
    "vox-daily-research-brief",
    "vox-weekly-deep-dive-claude",
    "vox-ai-council",
    "vox-council-daily-doc",
}

PROTECTED_KEYWORDS = ["price", "feed", "grade", "alert", "monitor"]


def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def fetch_budget_and_spend(cur):
    cur.execute(
        "SELECT cap_usd, alert_threshold_usd, pause_threshold_usd FROM vox_llm_budget WHERE month = DATE_TRUNC('month', NOW())::DATE"
    )
    row = cur.fetchone()
    budget = {
        "cap": float(row[0]) if row else 20.0,
        "alert_threshold": float(row[1]) if row else 15.0,
        "pause_threshold": float(row[2]) if row else 18.0,
    }
    cur.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM vox_llm_costs WHERE run_at >= DATE_TRUNC('month', NOW())"
    )
    spend = float(cur.fetchone()[0] or 0)
    return budget, spend


def project_month_spend(spend):
    today = date.today()
    _, days_in_month = monthrange(today.year, today.month)
    days_elapsed = max(1, today.day)
    return spend / days_elapsed * days_in_month


def list_hermes_crons():
    """Return a set of enabled Hermes cron job names."""
    try:
        result = subprocess.run(
            ["hermes", "cron", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"hermes cron list failed: {result.stderr.strip()}")
            return set()
    except Exception as e:
        print(f"Could not run hermes cron list: {e}")
        return set()

    enabled = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("ID", "-", "No cron")):
            continue
        parts = [p.strip() for p in line.split("  ") if p.strip()]
        if len(parts) < 3:
            continue
        # Typical list format: id, name, schedule, enabled
        name = parts[1]
        enabled_flag = parts[-1].lower()
        if enabled_flag in ("enabled", "true", "yes"):
            enabled.add(name)
    return enabled


def pause_cron(name):
    try:
        result = subprocess.run(
            ["hermes", "cron", "pause", name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def main():
    if not DB_PASSWORD:
        print("ERROR: DB_PASSWORD/PGPASSWORD not set.")
        return 1

    conn = get_conn()
    cur = conn.cursor()
    try:
        budget, spend = fetch_budget_and_spend(cur)
    finally:
        cur.close()
        conn.close()

    projected = project_month_spend(spend)
    remaining = budget["cap"] - spend
    pct_used = (spend / budget["cap"] * 100) if budget["cap"] > 0 else 0

    print(f"[VOX Budget Alert] Month MTD spend: ${spend:.4f} / ${budget['cap']:.2f} ({pct_used:.1f}%)")
    print(f"[VOX Budget Alert] Projected spend: ${projected:.4f}")

    if spend <= budget["alert_threshold"] and projected <= budget["alert_threshold"]:
        print("[VOX Budget Alert] ✅ Budget on track.")
        return 0

    alert_level = None
    if spend > budget["pause_threshold"] or projected > budget["pause_threshold"]:
        alert_level = "PAUSE"
    elif spend > budget["alert_threshold"] or projected > budget["alert_threshold"]:
        alert_level = "ALERT"

    if alert_level == "ALERT":
        print(
            f"⚠️ ALERT: Current/projected month spend (${spend:.2f}/${projected:.2f}) exceeds alert threshold ${budget['alert_threshold']:.2f}."
        )
        return 1

    if alert_level == "PAUSE":
        print(
            f"🚨 CRITICAL: Current/projected month spend (${spend:.2f}/${projected:.2f}) exceeds pause threshold ${budget['pause_threshold']:.2f}."
        )
        print("Pausing non-essential LLM crons...")

        enabled_crons = list_hermes_crons()
        paused = []
        failed = []
        for name in PAUSEABLE_CRONS:
            if name not in enabled_crons:
                continue
            ok, stdout, stderr = pause_cron(name)
            if ok:
                paused.append(name)
                print(f"  ⏸️ Paused {name}")
            else:
                failed.append((name, stderr or stdout))
                print(f"  ❌ Failed to pause {name}: {stderr or stdout}")

        if paused:
            print(f"\nPaused {len(paused)} cron(s): {', '.join(paused)}")
        if failed:
            print(f"\nFailed to pause {len(failed)} cron(s): {', '.join(n for n, _ in failed)}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
