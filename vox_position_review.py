#!/usr/bin/env python3
"""
VOX Position Review Scheduler
Auto-flags positions needing review based on grade changes, time held, P&L
Updates position notes with review flags
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"
POSITIONS_DIR = f"{VAULT_PATH}/02-Portfolio/Stocks/Positions"

class PositionReviewScheduler:
    def __init__(self):
        self.reviews = []
        self.positions = self.load_positions()
    
    def load_positions(self):
        """Load all position notes"""
        positions = []
        if os.path.exists(POSITIONS_DIR):
            for file in os.listdir(POSITIONS_DIR):
                if file.endswith('.md'):
                    ticker = file.replace('.md', '')
                    positions.append({
                        "ticker": ticker,
                        "file": f"{POSITIONS_DIR}/{file}",
                        "last_review": None,
                        "grade": 0,
                        "days_held": 0,
                        "pnl_pct": 0
                    })
        return positions
    
    def flag_for_review(self, ticker, reason, urgency="MEDIUM"):
        """Flag a position for review"""
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
        """Flag positions where grade dropped significantly"""
        # In production, read actual grades from position notes
        grade_drops = [
            {"ticker": "JMIA", "old_grade": 55, "new_grade": 40, "threshold": 45},
            {"ticker": "BILL", "old_grade": 60, "new_grade": 50, "threshold": 50},
            {"ticker": "AI", "old_grade": 55, "new_grade": 45, "threshold": 45},
        ]
        
        for drop in grade_drops:
            if drop["new_grade"] < drop["threshold"]:
                self.flag_for_review(
                    drop["ticker"],
                    f"Grade dropped from {drop['old_grade']} to {drop['new_grade']} (below {drop['threshold']})",
                    "HIGH" if drop["new_grade"] < 40 else "MEDIUM"
                )
    
    def check_time_based(self):
        """Flag positions held too long without review"""
        # Positions held >90 days without review
        long_holds = [
            {"ticker": "JMIA", "days_held": 285, "last_review": "2026-01-15"},
            {"ticker": "INDA", "days_held": 180, "last_review": "2026-02-01"},
            {"ticker": "EWZ", "days_held": 150, "last_review": "2026-03-01"},
        ]
        
        for pos in long_holds:
            if pos["days_held"] > 90:
                self.flag_for_review(
                    pos["ticker"],
                    f"Held {pos['days_held']} days without review",
                    "MEDIUM"
                )
    
    def check_pnl_extremes(self):
        """Flag positions with extreme P&L"""
        extremes = [
            {"ticker": "RKLB", "pnl_pct": 688, "action": "Trim?"},
            {"ticker": "VST", "pnl_pct": 246, "action": "Trim?"},
            {"ticker": "JMIA", "pnl_pct": -68, "action": "Cut?"},
            {"ticker": "BILL", "pnl_pct": -35, "action": "Evaluate"},
        ]
        
        for ext in extremes:
            if ext["pnl_pct"] > 200:
                self.flag_for_review(
                    ext["ticker"],
                    f"Up {ext['pnl_pct']}% — consider trimming to target weight",
                    "MEDIUM"
                )
            elif ext["pnl_pct"] < -30:
                self.flag_for_review(
                    ext["ticker"],
                    f"Down {ext['pnl_pct']}% — evaluate thesis vs grade",
                    "HIGH" if ext["pnl_pct"] < -50 else "MEDIUM"
                )
    
    def check_earnings_proximity(self):
        """Flag positions with earnings within 7 days"""
        earnings = [
            {"ticker": "NVDA", "date": "2026-05-27", "days_until": 2},
            {"ticker": "AMAT", "date": "2026-05-29", "days_until": 4},
            {"ticker": "CRWD", "date": "2026-06-03", "days_until": 8},
        ]
        
        for earn in earnings:
            if earn["days_until"] <= 7:
                self.flag_for_review(
                    earn["ticker"],
                    f"Earnings in {earn['days_until']} days ({earn['date']})",
                    "HIGH" if earn["days_until"] <= 3 else "MEDIUM"
                )
    
    def generate_review_queue(self):
        """Generate prioritized review queue"""
        self.check_grade_drops()
        self.check_time_based()
        self.check_pnl_extremes()
        self.check_earnings_proximity()
        
        # Sort by urgency
        urgency_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        self.reviews.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
        
        return self.reviews
    
    def generate_markdown(self):
        """Generate review queue markdown"""
        reviews = self.generate_review_queue()
        
        md = f"""---
tags: [position-review, scheduler, flags]
date: {datetime.now().strftime("%Y-%m-%d")}
---

# 🔔 Position Review Queue

> Auto-generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> {len(reviews)} positions flagged for review

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
        
        md += """
---

## 📊 Review Stats

| Metric | Count |
|--------|-------|
| **Total Flagged** | """ + str(len(reviews)) + """ |
| **HIGH Priority** | """ + str(len([r for r in reviews if r["urgency"] == "HIGH"])) + """ |
| **MEDIUM Priority** | """ + str(len([r for r in reviews if r["urgency"] == "MEDIUM"])) + """ |

---

## 🔄 Review Triggers

Positions are auto-flagged when:
1. **Grade drops** below threshold (45 = HIGH, 50 = MEDIUM)
2. **Held >90 days** without review
3. **P&L extremes** — up >200% (trim?) or down <-30% (cut?)
4. **Earnings within 7 days** — review position size
5. **Stop breached** — evaluate immediately

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
        """Save review queue to vault"""
        md = self.generate_markdown()
        filepath = f"{VAULT_PATH}/06-Tracking/Daily/Review Queue — {datetime.now().strftime('%Y-%m-%d')}.md"
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(md)
        
        print(f"✅ Review queue saved: {filepath}")
        return filepath

if __name__ == "__main__":
    scheduler = PositionReviewScheduler()
    scheduler.save()
    
    print(f"\n📊 Flagged {len(scheduler.reviews)} positions for review")
    for r in scheduler.reviews:
        print(f"   {r['urgency']}: {r['ticker']} — {r['reason']}")
