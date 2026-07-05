#!/usr/bin/env python3
"""
VOX LLM Cost Dashboard

Daily cron that reads vox_llm_costs and vox_llm_budget, computes spend
over 24h/7d/30d/current month, breaks it down by model and script,
writes an Obsidian note, and prints a summary.

No LLM calls. Uses SQL/psycopg2 only.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

from datetime import datetime, date
from calendar import monthrange
from pathlib import Path

import psycopg2

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "railway")
DB_PASSWORD = os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", ""))

OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian" / "VOX" / "LLMCosts"


def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def fetch_summary(cur):
    # Time-bucketed totals
    cur.execute(
        """
        SELECT
            COALESCE(SUM(total_cost) FILTER (WHERE run_at > NOW() - INTERVAL '24 hours'), 0) AS cost_24h,
            COALESCE(SUM(total_cost) FILTER (WHERE run_at > NOW() - INTERVAL '7 days'), 0) AS cost_7d,
            COALESCE(SUM(total_cost) FILTER (WHERE run_at > NOW() - INTERVAL '30 days'), 0) AS cost_30d,
            COALESCE(SUM(total_cost) FILTER (WHERE run_at >= DATE_TRUNC('month', NOW())), 0) AS cost_month,
            COALESCE(SUM(total_tokens) FILTER (WHERE run_at > NOW() - INTERVAL '24 hours'), 0) AS tokens_24h,
            COALESCE(SUM(total_tokens) FILTER (WHERE run_at >= DATE_TRUNC('month', NOW())), 0) AS tokens_month
        FROM vox_llm_costs
        """
    )
    row = cur.fetchone()
    summary = {
        "24h": float(row[0] or 0),
        "7d": float(row[1] or 0),
        "30d": float(row[2] or 0),
        "month": float(row[3] or 0),
        "tokens_24h": int(row[4] or 0),
        "tokens_month": int(row[5] or 0),
    }

    # By model (current month)
    cur.execute(
        """
        SELECT model, COUNT(*), SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), SUM(total_cost)
        FROM vox_llm_costs
        WHERE run_at >= DATE_TRUNC('month', NOW())
        GROUP BY model
        ORDER BY SUM(total_cost) DESC
        """
    )
    by_model = [
        {
            "model": r[0],
            "calls": int(r[1] or 0),
            "prompt_tokens": int(r[2] or 0),
            "completion_tokens": int(r[3] or 0),
            "total_tokens": int(r[4] or 0),
            "cost": float(r[5] or 0),
        }
        for r in cur.fetchall()
    ]

    # By script (current month)
    cur.execute(
        """
        SELECT script_name, COUNT(*), SUM(total_tokens), SUM(total_cost)
        FROM vox_llm_costs
        WHERE run_at >= DATE_TRUNC('month', NOW())
        GROUP BY script_name
        ORDER BY SUM(total_cost) DESC
        """
    )
    by_script = [
        {
            "script": r[0] or "unknown",
            "calls": int(r[1] or 0),
            "tokens": int(r[2] or 0),
            "cost": float(r[3] or 0),
        }
        for r in cur.fetchall()
    ]

    # Budget row
    cur.execute(
        "SELECT cap_usd, alert_threshold_usd, pause_threshold_usd FROM vox_llm_budget WHERE month = DATE_TRUNC('month', NOW())::DATE"
    )
    budget_row = cur.fetchone()
    budget = {
        "cap": float(budget_row[0]) if budget_row else 20.0,
        "alert_threshold": float(budget_row[1]) if budget_row else 15.0,
        "pause_threshold": float(budget_row[2]) if budget_row else 18.0,
    }

    return summary, by_model, by_script, budget


def project_month_spend(summary):
    """Linear projection: actual month spend so far / days elapsed * days in month."""
    today = date.today()
    _, days_in_month = monthrange(today.year, today.month)
    days_elapsed = max(1, today.day)
    return summary["month"] / days_elapsed * days_in_month


def build_obsidian_note(summary, by_model, by_script, budget, projected):
    today_str = datetime.now().strftime("%Y-%m-%d")
    remaining = budget["cap"] - summary["month"]
    pct_used = (summary["month"] / budget["cap"] * 100) if budget["cap"] > 0 else 0

    lines = [
        f"# VOX LLM Costs — {today_str}",
        "",
        "## Summary",
        f"- **24h spend:** ${summary['24h']:.4f}",
        f"- **7d spend:** ${summary['7d']:.4f}",
        f"- **30d spend:** ${summary['30d']:.4f}",
        f"- **Current month spend:** ${summary['month']:.4f}",
        f"- **Monthly budget cap:** ${budget['cap']:.2f}",
        f"- **Remaining budget:** ${remaining:.4f} ({pct_used:.1f}% used)",
        f"- **Projected month spend:** ${projected:.4f}",
        f"- **Tokens (24h / month):** {summary['tokens_24h']:,} / {summary['tokens_month']:,}",
        "",
    ]

    if projected > budget["pause_threshold"]:
        lines.append(f"> ⚠️ **BUDGET WARNING:** Projected spend ${projected:.2f} exceeds pause threshold ${budget['pause_threshold']:.2f}.")
    elif projected > budget["alert_threshold"]:
        lines.append(f"> ⚠️ **Budget alert:** Projected spend ${projected:.2f} exceeds alert threshold ${budget['alert_threshold']:.2f}.")
    else:
        lines.append(f"> ✅ Budget on track.")
    lines.append("")

    lines.append("## Spend by Model (current month)")
    lines.append("| Model | Calls | Prompt Tokens | Completion Tokens | Total Tokens | Cost |")
    lines.append("|-------|-------|---------------|-------------------|--------------|------|")
    for m in by_model:
        lines.append(f"| {m['model']} | {m['calls']} | {m['prompt_tokens']:,} | {m['completion_tokens']:,} | {m['total_tokens']:,} | ${m['cost']:.4f} |")
    lines.append("")

    lines.append("## Spend by Script (current month)")
    lines.append("| Script | Calls | Total Tokens | Cost |")
    lines.append("|--------|-------|--------------|------|")
    for s in by_script:
        lines.append(f"| {s['script']} | {s['calls']} | {s['tokens']:,} | ${s['cost']:.4f} |")
    lines.append("")

    return "\n".join(lines)


def main():
    if not DB_PASSWORD:
        print("ERROR: DB_PASSWORD/PGPASSWORD not set.")
        return 1

    conn = get_conn()
    cur = conn.cursor()
    try:
        summary, by_model, by_script, budget = fetch_summary(cur)
    finally:
        cur.close()
        conn.close()

    projected = project_month_spend(summary)

    # Write Obsidian note
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    note_path = OBSIDIAN_DIR / f"LLMCosts-{datetime.now().strftime('%Y-%m-%d')}.md"
    note_path.write_text(build_obsidian_note(summary, by_model, by_script, budget, projected))

    # Print summary
    print("=" * 60)
    print("VOX LLM Cost Dashboard")
    print("=" * 60)
    print(f"24h spend:  ${summary['24h']:.4f}")
    print(f"7d spend:   ${summary['7d']:.4f}")
    print(f"30d spend:  ${summary['30d']:.4f}")
    print(f"Month MTD:  ${summary['month']:.4f} / ${budget['cap']:.2f}")
    print(f"Remaining:  ${budget['cap'] - summary['month']:.4f}")
    print(f"Projected:  ${projected:.4f}")
    print(f"Tokens:     {summary['tokens_24h']:,} (24h) / {summary['tokens_month']:,} (month)")
    print(f"Models:     {len(by_model)} distinct")
    print(f"Scripts:    {len(by_script)} distinct")
    print(f"Obsidian:   {note_path}")
    print("=" * 60)

    if projected > budget["pause_threshold"]:
        print(f"\n⚠️ WARNING: Projected monthly spend ${projected:.2f} exceeds pause threshold ${budget['pause_threshold']:.2f}.")
        return 2
    if projected > budget["alert_threshold"]:
        print(f"\n⚠️ Alert: Projected monthly spend ${projected:.2f} exceeds alert threshold ${budget['alert_threshold']:.2f}.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
