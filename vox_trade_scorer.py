#!/usr/bin/env python3
"""
VOX Trade Idea Scorer
Ranks opportunities by signal strength across all systems
Outputs ranked list with composite score
"""

import json
from datetime import datetime
from dataclasses import dataclass
from typing import List

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"

@dataclass
class TradeSignal:
    ticker: str
    grade: int
    rsi: float
    sentiment: str
    screener: str
    macro_aligned: bool
    correlation_risk: float
    broker_cash: float
    target_price: float
    stop_price: float
    
    @property
    def composite_score(self):
        """Calculate composite score 0-100"""
        score = 0
        
        # Grade (0-30 points)
        score += min(self.grade / 100 * 30, 30)
        
        # RSI setup (0-15 points)
        if self.rsi < 30:
            score += 15  # Oversold
        elif self.rsi < 40:
            score += 12
        elif self.rsi < 50:
            score += 8
        elif self.rsi < 60:
            score += 5
        else:
            score += 2
        
        # Sentiment (0-15 points)
        if self.sentiment == "CONTRARIAN":
            score += 15  # Crowd wrong, we right
        elif self.sentiment == "FAVORABLE":
            score += 10
        elif self.sentiment == "NEUTRAL":
            score += 5
        else:
            score += 2
        
        # Screener track record (0-15 points)
        screener_scores = {
            "Grade 70+ Pullback": 15,
            "RSI <40 + Grade >65": 14,
            "Sector Rotation": 10,
            "Earnings Surprise": 8,
            "52-Week High": 3,
            "Insider Buying": 2
        }
        score += screener_scores.get(self.screener, 5)
        
        # Macro alignment (0-10 points)
        score += 10 if self.macro_aligned else 3
        
        # Correlation risk (0-10 points)
        score += max(0, 10 - self.correlation_risk * 10)
        
        # Broker cash available (0-5 points)
        score += 5 if self.broker_cash > 5000 else 3 if self.broker_cash > 2000 else 1
        
        return min(score, 100)
    
    @property
    def risk_reward(self):
        """Calculate risk/reward ratio"""
        if self.stop_price and self.target_price:
            risk = abs(self.stop_price - self.target_price)  # Simplified
            reward = abs(self.target_price - self.stop_price)
            return reward / risk if risk > 0 else 0
        return 0
    
    @property
    def conviction(self):
        """Human-readable conviction level"""
        s = self.composite_score
        if s >= 85:
            return "STRONG BUY"
        elif s >= 70:
            return "BUY"
        elif s >= 55:
            return "WEAK BUY"
        elif s >= 40:
            return "HOLD"
        else:
            return "AVOID"
    
    @property
    def position_size(self):
        """Suggested position size based on conviction"""
        s = self.composite_score
        if s >= 85:
            return "6-8%"
        elif s >= 70:
            return "4-6%"
        elif s >= 55:
            return "2-4%"
        else:
            return "0-2%"

class TradeScorer:
    def __init__(self):
        self.signals: List[TradeSignal] = []
    
    def add_signal(self, **kwargs):
        """Add a trade signal"""
        signal = TradeSignal(**kwargs)
        self.signals.append(signal)
        return signal
    
    def rank_signals(self):
        """Rank signals by composite score"""
        return sorted(self.signals, key=lambda x: x.composite_score, reverse=True)
    
    def generate_report(self):
        """Generate ranked trade ideas report"""
        ranked = self.rank_signals()
        
        md = f"""---
tags: [trade-ideas, scorer, ranked, signals]
date: {datetime.now().strftime("%Y-%m-%d")}
---

# 🎯 VOX Trade Idea Scorer

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> {len(ranked)} ideas scored and ranked

---

## 🏆 Top Opportunities

| Rank | Ticker | Score | Conviction | Position Size | Grade | RSI | Setup |
|------|--------|-------|------------|---------------|-------|-----|-------|
"""
        for i, s in enumerate(ranked[:10], 1):
            emoji = "🟢" if s.composite_score >= 70 else "🟡" if s.composite_score >= 55 else "🔴"
            md += f"| {i} | {s.ticker} | {s.composite_score:.0f} | {emoji} {s.conviction} | {s.position_size} | {s.grade} | {s.rsi:.1f} | {s.screener} |\n"
        
        md += """
---

## 📊 Detailed Analysis

"""
        for i, s in enumerate(ranked[:5], 1):
            md += f"""### {i}. {s.ticker} — {s.conviction} (Score: {s.composite_score:.0f}/100)

**Setup:** {s.screener}
**Grade:** {s.grade}/100
**RSI:** {s.rsi:.1f}
**Sentiment:** {s.sentiment}
**Macro Aligned:** {"Yes" if s.macro_aligned else "No"}
**Correlation Risk:** {s.correlation_risk:.2f}
**Broker Cash:** ${s.broker_cash:,.0f}

**Suggested Action:**
- Position size: {s.position_size} of portfolio
- Entry: Current price
- Stop: ${s.stop_price:.2f}
- Target: ${s.target_price:.2f}

**Score Breakdown:**
- Grade: {min(s.grade / 100 * 30, 30):.0f}/30
- RSI Setup: {15 if s.rsi < 30 else 12 if s.rsi < 40 else 8 if s.rsi < 50 else 5 if s.rsi < 60 else 2}/15
- Sentiment: {15 if s.sentiment == 'CONTRARIAN' else 10 if s.sentiment == 'FAVORABLE' else 5}/15
- Screener: {15 if 'Grade 70+' in s.screener else 14 if 'RSI' in s.screener else 10}/15
- Macro: {10 if s.macro_aligned else 3}/10
- Correlation: {max(0, 10 - s.correlation_risk * 10):.0f}/10
- Cash: {5 if s.broker_cash > 5000 else 3 if s.broker_cash > 2000 else 1}/5

---

"""
        
        md += """## 🎯 How to Use This

**STRONG BUY (85+):** Execute immediately. Full position size.
**BUY (70-84):** Execute today. Standard position size.
**WEAK BUY (55-69):** Small position or wait for better entry.
**HOLD (40-54):** On watchlist. No action yet.
**AVOID (<40):** Skip. Not worth the risk.

---

## 🔗 Related
- [[Daily Briefing]] — Today's context
- [[Market Regime]] — Strategy adjustments
- [[Screener Results Database]] — Screener track record
- [[Sentiment Tracker]] — Crowd positioning
- [[Position Sizer]] — Exact share calculation

---

*Generated by VOX Trade Scorer*
"""
        
        return md
    
    def save(self):
        """Save trade ideas"""
        md = self.generate_report()
        filepath = f"{VAULT_PATH}/09-Actions/Trade Ideas — {datetime.now().strftime('%Y-%m-%d')}.md"
        
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(md)
        
        print(f"✅ Trade ideas saved: {filepath}")
        return filepath

if __name__ == "__main__":
    scorer = TradeScorer()
    
    # Example signals
    scorer.add_signal(
        ticker="NVDA", grade=70, rsi=38,
        sentiment="CONTRARIAN", screener="Grade 70+ Pullback",
        macro_aligned=True, correlation_risk=0.3,
        broker_cash=12000, target_price=300, stop_price=195
    )
    
    scorer.add_signal(
        ticker="AMAT", grade=70, rsi=42,
        sentiment="FAVORABLE", screener="RSI <40 + Grade >65",
        macro_aligned=True, correlation_risk=0.4,
        broker_cash=12000, target_price=480, stop_price=370
    )
    
    scorer.add_signal(
        ticker="CEG", grade=60, rsi=48,
        sentiment="FAVORABLE", screener="Sector Rotation",
        macro_aligned=True, correlation_risk=0.2,
        broker_cash=12000, target_price=350, stop_price=250
    )
    
    scorer.add_signal(
        ticker="JMIA", grade=40, rsi=35,
        sentiment="BEARISH", screener="Grade <45 Cut List",
        macro_aligned=False, correlation_risk=0.1,
        broker_cash=3500, target_price=3, stop_price=2
    )
    
    ranked = scorer.rank_signals()
    print("🎯 Ranked Trade Ideas:")
    for s in ranked:
        print(f"   {s.ticker}: {s.composite_score:.0f} — {s.conviction} ({s.position_size})")
    
    scorer.save()
