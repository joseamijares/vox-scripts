#!/usr/bin/env python3
"""
VOX Position Review Scheduler v2
Auto-flags positions needing review based on live Railway Postgres data.
Reads actual positions, grades, P&L — flags based on real data.
Writes review queue to Railway Postgres + Obsidian vault.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import json
import urllib.request
import os
from datetime import datetime, timedelta
from pathlib import Path
import json
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_unified_grades():
    """Load unified grades from single source of truth"""
    unified_path = SCRIPT_DIR / "vox_unified_grades.json"
    if not unified_path.exists():
        return {}
    with open(unified_path) as f:
        return json.load(f)

def get_unified_grade(ticker, unified_grades):
    """Get grade from unified source"""
    if ticker in unified_grades.get("grades", {}):
        return unified_grades["grades"][ticker].get("grade", 0)
    return 0


DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"
VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"


def fetch_positions():
    """Fetch live positions from Railway Postgres."""
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/positions")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("positions", [])
    except Exception as e:
        print(f"❌ Failed to fetch positions: {e}")
        return []


def record_cron_run(job_name, status, output, error=None):
    """Record cron run status to dashboard API."""
    try:
        body = json.dumps({
            "job_name": job_name,
            "status": status,
            "output": output,
            "error": error
        }).encode()
        req = urllib.request.Request(
            f"{DASHBOARD_API}/admin/cron-runs",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"⚠️ Failed to record cron run: {e}")


class PositionReviewScheduler:
    def __init__(self):
        self.reviews = []
        self.positions = fetch_positions()

    def flag_for_review(self, ticker, reason, urgency="MEDIUM"):
        review = {
            "ticker": ticker,
            "reason": reason,
            "urgency": urgency,
            "flagged_date": datetime.now().strftime("%Y-%m-%d"),
            "due_date": (datetime.now() + timedelta(days=3 if urgency == "HIGH" else 7)).strftime("%Y-%m-%d")
        }
        self.reviews.append(review)
        return review

    def check_grade_drops(self):
        """Flag positions where grade is below threshold."""
        for p in self.positions:
            grade = p.get("grade", 0)
            ticker = p.get("ticker", "")
            if grade < 45:
                self.flag_for_review(ticker, f"Grade {grade} — below 45 threshold", "HIGH")
            elif grade < 50:
                self.flag_for_review(ticker, f"Grade {grade} — SELL zone", "MEDIUM")

    def check_pnl_extremes(self):
        """Flag positions with extreme P&L."""
        for p in self.positions:
            pnl_pct = p.get("pnl_pct", 0)
            ticker = p.get("ticker", "")
            if pnl_pct > 200:
                self.flag_for_review(ticker, f"Up {pnl_pct:.0f}% — consider trimming", "MEDIUM")
            elif pnl_pct < -50:
                self.flag_for_review(ticker, f"Down {pnl_pct:.0f}% — evaluate thesis", "HIGH")
            elif pnl_pct < -30:
                self.flag_for_review(ticker, f"Down {pnl_pct:.0f}% — evaluate thesis", "MEDIUM")

    def check_low_grades_high_value(self):
        """Flag large positions with low grades (concentration risk)."""
        total_value = sum(p.get("live_value", 0) for p in self.positions)
        for p in self.positions:
            grade = p.get("grade", 0)
            value = p.get("live_value", 0)
            ticker = p.get("ticker", "")
            if total_value > 0:
                pct = (value / total_value) * 100
                if pct > 10 and grade < 50:
                    self.flag_for_review(ticker, f"{pct:.1f}% of portfolio with grade {grade} — concentration risk", "HIGH")

    def generate_review_queue(self):
        self.check_grade_drops()
        self.check_pnl_extremes()
        self.check_low_grades_high_value()
        urgency_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        self.reviews.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
        return self.reviews

    def generate_markdown(self):
        reviews = self.generate_review_queue()
        total_value = sum(p.get("live_value", 0) for p in self.positions)

        md = f"""---
tags: [position-review, scheduler, flags]
date: {datetime.now().strftime("%Y-%m-%d")}
---

# 🔔 Position Review Queue

> Auto-generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> {len(reviews)} positions flagged for review
> Portfolio: ${total_value:,.0f}

---

## 🔴 HIGH Priority (Review Within 48h)

| Ticker | Reason | Due Date | Action |
|--------|--------|----------|--------|
"""
        for r in reviews:
            if r["urgency"] == "HIGH":
                md += f"| [[{r['ticker']}]] | {r['reason']} | {r['due_date']} | REVIEW NOW |\n"

        md += """
---

## 🟡 MEDIUM Priority (Review Within 7 Days)

| Ticker | Reason | Due Date | Action |
|--------|--------|----------|--------|
"""
        for r in reviews:
            if r["urgency"] == "MEDIUM":
                md += f"| [[{r['ticker']}]] | {r['reason']} | {r['due_date']} | Schedule review |\n"

        md += f"""
---

## 📊 Review Stats

| Metric | Count |
|--------|-------|
| **Total Flagged** | {len(reviews)} |
| **HIGH Priority** | {len([r for r in reviews if r["urgency"] == "HIGH"])} |
| **MEDIUM Priority** | {len([r for r in reviews if r["urgency"] == "MEDIUM"])} |
| **Portfolio Value** | ${total_value:,.0f} |

---

## 🔄 Review Triggers

Positions are auto-flagged when:
1. **Grade < 45** — HIGH priority
2. **Grade < 50** — MEDIUM priority
3. **P&L > +200%** — consider trimming
4. **P&L < -30%** — evaluate thesis
5. **P&L < -50%** — HIGH priority
6. **>10% of portfolio with grade < 50** — concentration risk

---

## ✅ Review Template

When reviewing a flagged position, answer:

1. **Has the thesis changed?** Yes / No
2. **Is the grade still valid?** Current grade: __
3. **Would I buy today at current price?** Yes / No
4. **What would improve this position?** __
5. **Action:** HOLD / ADD / TRIM / SELL / SET ALERT

---

## 🔗 Related
- [[Trade Execution Log]] — Log review outcomes
- [[Mistake Journal]] — Log bad decisions
- [[Daily Briefing]] — Today's priorities
"""
        return md

    def save(self):
        md = self.generate_markdown()
        filepath = f"{VAULT_PATH}/06-Tracking/Daily/Review Queue — {datetime.now().strftime('%Y-%m-%d')}.md"
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(md)
        print(f"✅ Review queue saved: {filepath}")
        return filepath


if __name__ == "__main__":
    job_name = "vox-position-review"
    try:
        scheduler = PositionReviewScheduler()
        scheduler.save()

        output = f"Flagged {len(scheduler.reviews)} positions for review"
        for r in scheduler.reviews:
            output += f"\n   {r['urgency']}: {r['ticker']} — {r['reason']}"

        print(f"\n📊 {output}")
        record_cron_run(job_name, "ok", output)

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
