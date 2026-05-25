#!/usr/bin/env python3
"""
VOX Daily Briefing Generator
Auto-compiles all signals into morning brief
Run at 8:00 AM before market open
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"
DAILY_DIR = f"{VAULT_PATH}/06-Tracking/Daily"

class DailyBriefing:
    def __init__(self):
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.brief = {}
        
    def gather_macro(self):
        """Gather macro signals"""
        return {
            "fed_funds": 5.25,
            "cpi": 3.2,
            "yield_curve": -0.35,
            "vix": 14.2,
            "market_bias": "CAUTIOUSLY_BULLISH",
            "key_event": "Fed speakers today",
            "sector_rotation": "XLF leading, XLK consolidating"
        }
    
    def gather_alerts(self):
        """Gather active alerts"""
        return [
            {"ticker": "NVDA", "type": "BUY", "trigger": "$215", "reason": "RSI <40, Grade 70"},
            {"ticker": "AMAT", "type": "BUY", "trigger": "$415", "reason": "EMA21 bounce"},
            {"ticker": "OKLO", "type": "SELL", "trigger": "$80", "reason": "Target hit"},
            {"ticker": "CEG", "type": "BUY", "trigger": "$280", "reason": "Any dip"},
        ]
    
    def gather_positions_needing_attention(self):
        """Positions requiring review"""
        return [
            {"ticker": "JMIA", "grade": 40, "action": "SELL TODAY", "urgency": "HIGH"},
            {"ticker": "BILL", "grade": 50, "action": "Evaluate exit", "urgency": "MEDIUM"},
            {"ticker": "AI", "grade": 45, "action": "Cut if grade drops", "urgency": "MEDIUM"},
        ]
    
    def gather_screener_signals(self):
        """Top screener signals"""
        return [
            {"ticker": "NVDA", "screener": "Grade 70+ Pullback", "confidence": "HIGH"},
            {"ticker": "AMAT", "screener": "RSI <40 + Grade >65", "confidence": "HIGH"},
            {"ticker": "CEG", "screener": "Sector Rotation", "confidence": "MEDIUM"},
        ]
    
    def gather_sentiment(self):
        """Contrarian opportunities"""
        return [
            {"ticker": "NVDA", "sentiment": "Bearish", "grade": 70, "signal": "CONTRARIAN_BUY"},
            {"ticker": "CEG", "sentiment": "Mixed", "grade": 60, "signal": "FAVORABLE"},
        ]
    
    def generate_brief(self):
        """Generate the full briefing"""
        macro = self.gather_macro()
        alerts = self.gather_alerts()
        attention = self.gather_positions_needing_attention()
        screener = self.gather_screener_signals()
        sentiment = self.gather_sentiment()
        
        brief = f"""---
tags: [daily-brief, morning, pre-market]
date: {self.date}
---

# 📰 VOX Daily Briefing — {self.date}

> Generated: {datetime.now().strftime("%H:%M")} | Market opens in ~1 hour

---

## 🌍 Macro Snapshot

| Indicator | Value | Signal |
|-----------|-------|--------|
| Fed Funds | {macro['fed_funds']}% | Neutral |
| CPI | {macro['cpi']}% | Cooling |
| Yield Curve | {macro['yield_curve']}% | Inverted (recession watch) |
| VIX | {macro['vix']} | Low — buy dips |
| Market Bias | {macro['market_bias']} | — |

**Key Event:** {macro['key_event']}
**Sector Flow:** {macro['sector_rotation']}

---

## 🚨 Positions Needing Attention

| Ticker | Grade | Action | Urgency |
|--------|-------|--------|---------|
"""
        for pos in attention:
            emoji = "🔴" if pos['urgency'] == "HIGH" else "🟡"
            brief += f"| {pos['ticker']} | {pos['grade']} | {pos['action']} | {emoji} {pos['urgency']} |\n"
        
        brief += """
---

## 🔔 Active Alerts (May Trigger Today)

| Ticker | Action | Trigger | Reason |
|--------|--------|---------|--------|
"""
        for alert in alerts:
            brief += f"| {alert['ticker']} | {alert['type']} | {alert['trigger']} | {alert['reason']} |\n"
        
        brief += """
---

## 🎯 Screener Signals

| Ticker | Screener | Confidence |
|--------|----------|------------|
"""
        for sig in screener:
            stars = "⭐⭐⭐" if sig['confidence'] == "HIGH" else "⭐⭐"
            brief += f"| {sig['ticker']} | {sig['screener']} | {stars} {sig['confidence']} |\n"
        
        brief += """
---

## 🧠 Contrarian Opportunities

| Ticker | Sentiment | Grade | Signal |
|--------|-----------|-------|--------|
"""
        for opp in sentiment:
            brief += f"| {opp['ticker']} | {opp['sentiment']} | {opp['grade']} | {opp['signal']} |\n"
        
        brief += f"""
---

## 📋 Today's Action Checklist

### Must Do (Before Market Open)
- [ ] Review [[Mistake Journal]] — any patterns repeating?
- [ ] Check [[Trade Execution Log]] — log yesterday's trades
- [ ] Set alerts for: NVDA $215, AMAT $415, OKLO $80

### If Alerts Trigger
- [ ] NVDA @ $215 → Buy 27 shares (Schwab)
- [ ] AMAT @ $415 → Buy 9 shares (Schwab)
- [ ] OKLO @ $80 → Sell position (Schwab)

### Watch List
- [ ] JMIA — SELL if any bounce
- [ ] BILL — Evaluate exit if grade <45
- [ ] BTC — Monitor for trim execution

---

## 💡 Key Insight

**{datetime.now().strftime("%A")} Focus:** 
"""
        
        # Day-specific insight
        day = datetime.now().strftime("%A")
        if day == "Monday":
            brief += "Weekly sector rotation check. Rebalance if tech >30%."
        elif day == "Tuesday":
            brief += "Execute planned trades. No new positions without grade >65."
        elif day == "Wednesday":
            brief += "Mid-week review. Cut any position that dropped grade <45."
        elif day == "Thursday":
            brief += "Pre-Friday positioning. Reduce risk if VIX >20."
        elif day == "Friday":
            brief += "Weekend hold review. No new speculative positions."
        else:
            brief += "Weekend analysis. Review screener results, update thesis."
        
        brief += """

---

## 🔗 Related
- [[Daily Checklist]] — Full pre-market routine
- [[Macro Dashboard]] — Detailed macro analysis
- [[Sentiment Tracker]] — Live sentiment data
- [[Trade Execution Log]] — Log today's trades

---

*Generated by VOX Daily Briefing System*
"""
        
        return brief
    
    def save(self):
        """Save briefing to vault"""
        os.makedirs(DAILY_DIR, exist_ok=True)
        filepath = f"{DAILY_DIR}/Briefing — {self.date}.md"
        
        brief = self.generate_brief()
        with open(filepath, "w") as f:
            f.write(brief)
        
        print(f"✅ Daily briefing saved: {filepath}")
        return filepath

if __name__ == "__main__":
    briefing = DailyBriefing()
    briefing.save()
