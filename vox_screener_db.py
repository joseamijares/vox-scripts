#!/usr/bin/env python3
"""
VOX Screener Results Database
Tracks every screener run: what worked, what didn't, why
Updates Screener Results Database.md in Obsidian vault
"""

import json
import os
from datetime import datetime
from collections import defaultdict

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"
DB_FILE = f"{VAULT_PATH}/10-Strategy/Screener Results Database.md"

class ScreenerDatabase:
    def __init__(self):
        self.runs = []
        self.screeners = defaultdict(lambda: {"runs": 0, "winners": 0, "total_return": 0, "best_find": None})
    
    def log_run(self, screener_name, tickers_found, market_condition=""):
        """Log a screener run"""
        run = {
            "id": f"RUN-{len(self.runs)+1:03d}",
            "screener": screener_name,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "market_condition": market_condition,
            "tickers": tickers_found,
            "results": []
        }
        self.runs.append(run)
        self.screeners[screener_name]["runs"] += 1
        return run
    
    def log_result(self, run_id, ticker, entry_price, current_price, status="OPEN"):
        """Log result for a specific ticker from a run"""
        for run in self.runs:
            if run["id"] == run_id:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                result = {
                    "ticker": ticker,
                    "entry": entry_price,
                    "current": current_price,
                    "pnl_pct": pnl_pct,
                    "status": status
                }
                run["results"].append(result)
                
                # Update screener stats
                screener = self.screeners[run["screener"]]
                if pnl_pct > 0:
                    screener["winners"] += 1
                screener["total_return"] += pnl_pct
                
                if not screener["best_find"] or pnl_pct > screener["best_find"]["pnl_pct"]:
                    screener["best_find"] = {"ticker": ticker, "pnl_pct": pnl_pct}
                
                return result
        return None
    
    def get_screener_stats(self, screener_name):
        """Get stats for a specific screener"""
        s = self.screeners[screener_name]
        if s["runs"] == 0:
            return None
        
        total_trades = sum(len(r["results"]) for r in self.runs if r["screener"] == screener_name)
        
        return {
            "name": screener_name,
            "runs": s["runs"],
            "total_trades": total_trades,
            "win_rate": (s["winners"] / total_trades * 100) if total_trades > 0 else 0,
            "avg_return": s["total_return"] / total_trades if total_trades > 0 else 0,
            "best_find": s["best_find"]
        }
    
    def get_top_screeners(self, min_runs=3):
        """Get top performing screeners"""
        stats = []
        for name in self.screeners:
            s = self.get_screener_stats(name)
            if s and s["runs"] >= min_runs:
                stats.append(s)
        
        # Sort by win rate, then avg return
        stats.sort(key=lambda x: (x["win_rate"], x["avg_return"]), reverse=True)
        return stats
    
    def generate_markdown(self):
        """Generate updated Screener Database markdown"""
        md = f"""---
tags: [screener, database, results, backtest, track-record]
date: {datetime.now().strftime("%Y-%m-%d")}
---

# 🔍 Screener Results Database

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> Total runs logged: {len(self.runs)}

---

## 📊 Screener Performance Dashboard

| Screener | Runs | Trades | Win Rate | Avg Return | Best Find |
|----------|------|--------|----------|------------|-----------|
"""
        for name in sorted(self.screeners.keys()):
            s = self.get_screener_stats(name)
            if s:
                best = f"{s['best_find']['ticker']} (+{s['best_find']['pnl_pct']:.0f}%)" if s["best_find"] else "—"
                md += f"| {name} | {s['runs']} | {s['total_trades']} | {s['win_rate']:.0f}% | +{s['avg_return']:.1f}% | {best} |\n"
        
        md += """
---

## 🏆 Top Performing Screeners

"""
        top = self.get_top_screeners(min_runs=1)
        for i, s in enumerate(top[:5], 1):
            md += f"""### {i}. {s['name']} (⭐{"⭐" * int(s['win_rate']/20)})
- **Win Rate:** {s['win_rate']:.0f}%
- **Avg Return:** +{s['avg_return']:.1f}%
- **Best Find:** {s['best_find']['ticker'] if s['best_find'] else 'None'} (+{s['best_find']['pnl_pct']:.0f}%)
- **Confidence:** {"HIGH" if s['win_rate'] > 70 else "MEDIUM" if s['win_rate'] > 50 else "LOW"}

"""
        
        md += """---

## 📋 Recent Run Log

"""
        for run in reversed(self.runs[-10:]):  # Last 10 runs
            md += f"""### {run['id']}: {run['screener']} — {run['date']}
**Market:** {run['market_condition']}

| Ticker | Entry | Current | Return | Status |
|--------|-------|---------|--------|--------|
"""
            for r in run["results"]:
                emoji = "🟢" if r["pnl_pct"] > 0 else "🔴" if r["pnl_pct"] < 0 else "🟡"
                md += f"| {r['ticker']} | ${r['entry']:.2f} | ${r['current']:.2f} | {r['pnl_pct']:+.1f}% | {emoji} {r['status']} |\n"
            md += "\n"
        
        return md
    
    def save(self):
        """Save to vault"""
        md = self.generate_markdown()
        with open(DB_FILE, "w") as f:
            f.write(md)
        print(f"✅ Screener Database updated: {DB_FILE}")

if __name__ == "__main__":
    db = ScreenerDatabase()
    
    # Example: Log some historical runs
    run1 = db.log_run("Grade 70+ Pullback", ["NVDA", "AMAT", "NET"], "Bullish, VIX 14")
    db.log_result(run1["id"], "NVDA", 215, 256, "HOLD")
    db.log_result(run1["id"], "AMAT", 380, 415, "HOLD")
    db.log_result(run1["id"], "NET", 175, 200, "HOLD")
    
    run2 = db.log_run("RSI <40 + Grade >65", ["AMD", "COHR", "INTC"], "Mixed")
    db.log_result(run2["id"], "AMD", 95, 120, "HOLD")
    db.log_result(run2["id"], "COHR", 60, 78, "HOLD")
    db.log_result(run2["id"], "INTC", 22, 20, "CUT")
    
    db.save()
    
    print("\n🏆 Top screeners:")
    for s in db.get_top_screeners(min_runs=1):
        print(f"   {s['name']}: {s['win_rate']:.0f}% win rate, +{s['avg_return']:.1f}% avg")
