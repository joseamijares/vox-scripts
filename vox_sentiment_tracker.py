#!/usr/bin/env python3
"""
VOX Sentiment Tracker
Combines social sentiment + news sentiment + price alerts + grade alerts
Updates Sentiment Tracker.md in Obsidian vault
"""

import json
import os
from datetime import datetime

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"
SENTIMENT_FILE = f"{VAULT_PATH}/10-Strategy/Sentiment Tracker.md"

class SentimentTracker:
    def __init__(self):
        self.alerts = []
        self.sentiment_data = {}
    
    def add_alert(self, ticker, alert_type, condition, trigger_price, grade=0):
        """Add a price or grade alert"""
        alert = {
            "ticker": ticker,
            "type": alert_type,  # PRICE or GRADE
            "condition": condition,
            "trigger": trigger_price,
            "grade": grade,
            "status": "ACTIVE",
            "created": datetime.now().strftime("%Y-%m-%d")
        }
        self.alerts.append(alert)
        return alert
    
    def update_sentiment(self, ticker, social_score, news_score, grade, price, rsi):
        """Update sentiment data for a ticker"""
        # social_score: -100 (very bearish) to +100 (very bullish)
        # news_score: -100 to +100
        
        combined = (social_score * 0.4) + (news_score * 0.4) + ((grade - 50) * 0.2)
        
        signal = "NEUTRAL"
        if combined > 60 and grade > 70 and rsi < 40:
            signal = "🟢 STRONG BUY"
        elif combined > 40 and grade > 65:
            signal = "🟢 BUY"
        elif combined < -60 and grade < 45:
            signal = "🔴 AVOID"
        elif combined < -40 and grade > 70:
            signal = "🟢 CONTRARIAN BUY"
        elif abs(combined) < 20:
            signal = "🟡 NEUTRAL"
        
        self.sentiment_data[ticker] = {
            "social": social_score,
            "news": news_score,
            "combined": combined,
            "grade": grade,
            "price": price,
            "rsi": rsi,
            "signal": signal,
            "updated": datetime.now().strftime("%Y-%m-%d")
        }
        
        return self.sentiment_data[ticker]
    
    def get_contrarian_opportunities(self):
        """Find tickers where sentiment disagrees with grade"""
        opportunities = []
        for ticker, data in self.sentiment_data.items():
            if data["signal"] in ["🟢 CONTRARIAN BUY", "🟢 STRONG BUY"]:
                opportunities.append({
                    "ticker": ticker,
                    "signal": data["signal"],
                    "grade": data["grade"],
                    "sentiment": data["combined"],
                    "rsi": data["rsi"]
                })
        return opportunities
    
    def generate_markdown(self):
        """Generate updated Sentiment Tracker markdown"""
        md = f"""---
tags: [sentiment, alerts, social, news, combined]
date: {datetime.now().strftime("%Y-%m-%d")}
---

# 📣 Sentiment & Alert Tracker

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## 📊 Current Sentiment Dashboard

| Ticker | Grade | Price | RSI | Social | News | Combined | Signal |
|--------|-------|-------|-----|--------|------|----------|--------|
"""
        for ticker, data in self.sentiment_data.items():
            social_emoji = "🟢" if data["social"] > 20 else "🔴" if data["social"] < -20 else "🟡"
            news_emoji = "🟢" if data["news"] > 20 else "🔴" if data["news"] < -20 else "🟡"
            md += f"| {ticker} | {data['grade']} | ${data['price']} | {data['rsi']:.1f} | {social_emoji} {data['social']:.0f} | {news_emoji} {data['news']:.0f} | {data['combined']:.0f} | {data['signal']} |\n"
        
        md += """
---

## 🔔 Active Alerts

### Price Alerts
| Ticker | Condition | Trigger | Status |
|--------|-----------|---------|--------|
"""
        for alert in self.alerts:
            if alert["type"] == "PRICE":
                md += f"| {alert['ticker']} | {alert['condition']} | ${alert['trigger']} | {alert['status']} |\n"
        
        md += """
### Grade Alerts
| Ticker | Grade | Alert If | Action |
|--------|-------|----------|--------|
"""
        for alert in self.alerts:
            if alert["type"] == "GRADE":
                md += f"| {alert['ticker']} | {alert['grade']} | {alert['condition']} | {alert['status']} |\n"
        
        # Contrarian opportunities
        opportunities = self.get_contrarian_opportunities()
        if opportunities:
            md += """
---

## 🎯 Contrarian Opportunities

| Ticker | Signal | Grade | Why |
|--------|--------|-------|-----|
"""
            for opp in opportunities:
                md += f"| {opp['ticker']} | {opp['signal']} | {opp['grade']} | Sentiment {opp['sentiment']:.0f}, Grade {opp['grade']} |\n"
        
        return md
    
    def save(self):
        """Save to vault"""
        md = self.generate_markdown()
        with open(SENTIMENT_FILE, "w") as f:
            f.write(md)
        print(f"✅ Sentiment Tracker updated: {SENTIMENT_FILE}")

if __name__ == "__main__":
    tracker = SentimentTracker()
    
    # Example data
    tracker.update_sentiment("NVDA", 65, 45, 70, 256, 53.6)
    tracker.update_sentiment("AMAT", 60, 50, 70, 415, 57.6)
    tracker.update_sentiment("CEG", 30, 40, 60, 294, 48.2)
    tracker.update_sentiment("JMIA", -80, -70, 40, 2.40, 35.0)
    
    tracker.add_alert("NVDA", "PRICE", "Buy — RSI <40", 215, 70)
    tracker.add_alert("OKLO", "PRICE", "Sell — Target", 80, 55)
    
    tracker.save()
    
    opportunities = tracker.get_contrarian_opportunities()
    print(f"\n🎯 Contrarian opportunities: {len(opportunities)}")
    for opp in opportunities:
        print(f"   {opp['ticker']}: {opp['signal']}")
