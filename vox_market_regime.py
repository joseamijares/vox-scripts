#!/usr/bin/env python3
"""
VOX Market Regime Detector
Detects bull/bear/sideways regime with strategy adjustments
Updates Macro Dashboard with regime signal
"""

import json
import os
from datetime import datetime
from enum import Enum

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"
MACRO_FILE = f"{VAULT_PATH}/10-Strategy/Macro Dashboard.md"

class MarketRegime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    EARLY_BULL = "EARLY_BULL"
    LATE_BULL = "LATE_BULL"
    EARLY_BEAR = "EARLY_BEAR"
    CRASH = "CRASH"
    RECOVERY = "RECOVERY"

class RegimeDetector:
    def __init__(self):
        self.regime = MarketRegime.SIDEWAYS
        self.confidence = 0.5
        self.indicators = {}
        
    def analyze(self, vix, spy_200dma, spy_50dma, yield_curve, fed_trend, breadth):
        """
        Analyze market regime based on multiple indicators
        
        Args:
            vix: Current VIX level
            spy_200dma: SPY vs 200-day MA (%)
            spy_50dma: SPY vs 50-day MA (%)
            yield_curve: 10y-2y spread (%)
            fed_trend: "HIKING", "PAUSED", "CUTTING"
            breadth: % of stocks above 200-day MA
        """
        self.indicators = {
            "vix": vix,
            "spy_200dma": spy_200dma,
            "spy_50dma": spy_50dma,
            "yield_curve": yield_curve,
            "fed_trend": fed_trend,
            "breadth": breadth
        }
        
        # Scoring system
        bull_score = 0
        bear_score = 0
        
        # VIX
        if vix < 15:
            bull_score += 2
        elif vix < 20:
            bull_score += 1
        elif vix > 30:
            bear_score += 3
        elif vix > 25:
            bear_score += 2
        
        # Trend (200 DMA)
        if spy_200dma > 5:
            bull_score += 2
        elif spy_200dma > 0:
            bull_score += 1
        elif spy_200dma < -10:
            bear_score += 3
        elif spy_200dma < -5:
            bear_score += 2
        
        # Momentum (50 DMA)
        if spy_50dma > 3:
            bull_score += 1
        elif spy_50dma < -3:
            bear_score += 1
        
        # Yield curve
        if yield_curve > 0:
            bull_score += 1
        elif yield_curve < -0.5:
            bear_score += 2
        
        # Fed policy
        if fed_trend == "CUTTING":
            bull_score += 2
        elif fed_trend == "PAUSED":
            bull_score += 1
        elif fed_trend == "HIKING":
            bear_score += 2
        
        # Breadth
        if breadth > 70:
            bull_score += 2
        elif breadth > 50:
            bull_score += 1
        elif breadth < 30:
            bear_score += 2
        
        # Determine regime
        total = bull_score + bear_score
        if total == 0:
            self.regime = MarketRegime.SIDEWAYS
            self.confidence = 0.3
        else:
            bull_pct = bull_score / total
            
            if bull_pct > 0.8:
                if spy_50dma > spy_200dma and vix < 15:
                    self.regime = MarketRegime.BULL
                else:
                    self.regime = MarketRegime.EARLY_BULL
                self.confidence = bull_pct
            elif bull_pct > 0.6:
                self.regime = MarketRegime.EARLY_BULL
                self.confidence = bull_pct
            elif bull_pct > 0.4:
                self.regime = MarketRegime.SIDEWAYS
                self.confidence = 0.5
            elif bull_pct > 0.2:
                if spy_50dma < spy_200dma:
                    self.regime = MarketRegime.EARLY_BEAR
                else:
                    self.regime = MarketRegime.LATE_BULL
                self.confidence = 1 - bull_pct
            else:
                if vix > 30 and spy_200dma < -10:
                    self.regime = MarketRegime.CRASH
                elif spy_200dma < -5 and fed_trend == "CUTTING":
                    self.regime = MarketRegime.RECOVERY
                else:
                    self.regime = MarketRegime.BEAR
                self.confidence = 1 - bull_pct
        
        return self.regime, self.confidence
    
    def get_strategy(self):
        """Get strategy adjustments for current regime"""
        strategies = {
            MarketRegime.BULL: {
                "cash_target": 0.10,
                "max_position": 0.08,
                "stop_policy": "Trailing 15%",
                "new_positions": "Aggressive",
                "sectors": ["Tech", "Growth", "Discretionary"],
                "avoid": ["Utilities", "Consumer Staples"],
                "leverage": "Consider 1.2x",
                "motto": "Let winners run. Add on dips."
            },
            MarketRegime.EARLY_BULL: {
                "cash_target": 0.15,
                "max_position": 0.07,
                "stop_policy": "Tight 10%",
                "new_positions": "Selective",
                "sectors": ["Tech", "Financials", "Industrials"],
                "avoid": ["Defensives"],
                "leverage": "No",
                "motto": "Buy quality on pullbacks. Watch for false starts."
            },
            MarketRegime.LATE_BULL: {
                "cash_target": 0.20,
                "max_position": 0.06,
                "stop_policy": "Tight 8%",
                "new_positions": "Very Selective",
                "sectors": ["Energy", "Materials", "Value"],
                "avoid": ["High PE Growth", "Speculative"],
                "leverage": "No",
                "motto": "Take profits. Raise cash. Prepare for rotation."
            },
            MarketRegime.SIDEWAYS: {
                "cash_target": 0.20,
                "max_position": 0.05,
                "stop_policy": "Tight 8%",
                "new_positions": "Range trades only",
                "sectors": ["Quality", "Dividend"],
                "avoid": ["Momentum"],
                "leverage": "No",
                "motto": "Sell rips, buy dips. Don't get chopped."
            },
            MarketRegime.EARLY_BEAR: {
                "cash_target": 0.30,
                "max_position": 0.04,
                "stop_policy": "Hard 7%",
                "new_positions": "None",
                "sectors": ["Defensives", "Gold", "Cash"],
                "avoid": ["Cyclicals", "Tech", "Small Caps"],
                "leverage": "No",
                "motto": "Preserve capital. Cut losers fast."
            },
            MarketRegime.BEAR: {
                "cash_target": 0.40,
                "max_position": 0.03,
                "stop_policy": "Hard 5%",
                "new_positions": "Shorts/Hedges only",
                "sectors": ["Utilities", "Staples", "Bonds"],
                "avoid": ["Equities", "High Beta"],
                "leverage": "Inverse ETFs",
                "motto": "Cash is a position. Survive to thrive later."
            },
            MarketRegime.CRASH: {
                "cash_target": 0.50,
                "max_position": 0.02,
                "stop_policy": "Emergency",
                "new_positions": "None",
                "sectors": ["Cash", "Gold", "Treasuries"],
                "avoid": ["Everything"],
                "leverage": "No",
                "motto": "Don't catch falling knives. Wait for capitulation."
            },
            MarketRegime.RECOVERY: {
                "cash_target": 0.25,
                "max_position": 0.05,
                "stop_policy": "Trailing 12%",
                "new_positions": "Cautious",
                "sectors": ["Cyclicals", "Small Caps", "Tech"],
                "avoid": ["Defensives"],
                "leverage": "No",
                "motto": "Buy the recovery, not the rally. Quality first."
            }
        }
        
        return strategies.get(self.regime, strategies[MarketRegime.SIDEWAYS])
    
    def get_portfolio_actions(self):
        """Get specific portfolio actions for current regime"""
        strategy = self.get_strategy()
        
        actions = []
        
        if self.regime in [MarketRegime.BULL, MarketRegime.EARLY_BULL]:
            actions.extend([
                "✅ Increase position sizes to 6-8%",
                "✅ Add to winners on pullbacks",
                "✅ Reduce cash to 10-15%",
                "⚠️ Keep stops loose (trailing)",
                "🎯 Focus: Tech, Growth, Discretionary"
            ])
        elif self.regime == MarketRegime.LATE_BULL:
            actions.extend([
                "⚠️ Trim winners to target weight",
                "⚠️ Raise cash to 20%",
                "⚠️ Tighten stops to 8%",
                "🎯 Focus: Energy, Materials, Value"
            ])
        elif self.regime == MarketRegime.SIDEWAYS:
            actions.extend([
                "🔄 Sell rips, buy dips",
                "🔄 Keep cash at 20%",
                "🔄 Tight stops (8%)",
                "🎯 Focus: Quality, Dividend"
            ])
        elif self.regime in [MarketRegime.EARLY_BEAR, MarketRegime.BEAR]:
            actions.extend([
                "🔴 Cut losers immediately",
                "🔴 Raise cash to 30-40%",
                "🔴 Reduce position sizes to 3-4%",
                "🔴 Hard stops at 5-7%",
                "🎯 Focus: Defensives, Gold, Cash"
            ])
        elif self.regime == MarketRegime.CRASH:
            actions.extend([
                "🚨 EMERGENCY: Cut to 50% cash",
                "🚨 No new positions",
                "🚨 Consider inverse ETFs",
                "🎯 Focus: Survival"
            ])
        elif self.regime == MarketRegime.RECOVERY:
            actions.extend([
                "🟢 Start deploying cash slowly",
                "🟢 Buy cyclicals and small caps",
                "🟢 Keep 25% cash reserve",
                "🎯 Focus: Early cycle leaders"
            ])
        
        return actions
    
    def generate_markdown(self):
        """Generate regime analysis markdown"""
        strategy = self.get_strategy()
        actions = self.get_portfolio_actions()
        
        md = f"""---
tags: [market-regime, macro, strategy, system]
date: {datetime.now().strftime("%Y-%m-%d")}
---

# 🌍 Market Regime Analysis

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> Confidence: {self.confidence:.0%}

---

## 🎯 Current Regime: {self.regime.value}

**Interpretation:**
"""
        
        interpretations = {
            MarketRegime.BULL: "Strong uptrend. Breadth is healthy. Fed is accommodative. Risk-on.",
            MarketRegime.EARLY_BULL: "Trend turning up after consolidation/base. Could be false start — watch breadth.",
            MarketRegime.LATE_BULL: "Extended rally. Breadth narrowing. Rotation to value. Topping process.",
            MarketRegime.SIDEWAYS: "No clear trend. Range-bound. Choppy. Patience required.",
            MarketRegime.EARLY_BEAR: "Trend breaking down. Leading stocks failing. Defensive rotation.",
            MarketRegime.BEAR: "Downtrend confirmed. Breadth terrible. Preserve capital.",
            MarketRegime.CRASH: "Capitulation. Panic selling. Extreme fear. Opportunity soon.",
            MarketRegime.RECOVERY: "Bottoming process. Fed cutting. Early signs of life."
        }
        
        md += interpretations.get(self.regime, "Unclear regime. Proceed with caution.") + "\n\n"
        
        md += f"""---

## 📊 Indicator Readings

| Indicator | Value | Signal |
|-----------|-------|--------|
| VIX | {self.indicators.get('vix', 'N/A')} | {"Low — complacent" if self.indicators.get('vix', 20) < 15 else "Elevated" if self.indicators.get('vix', 20) > 25 else "Normal"} |
| SPY vs 200 DMA | {self.indicators.get('spy_200dma', 'N/A')}% | {"Bullish" if self.indicators.get('spy_200dma', 0) > 0 else "Bearish"} |
| SPY vs 50 DMA | {self.indicators.get('spy_50dma', 'N/A')}% | {"Momentum up" if self.indicators.get('spy_50dma', 0) > 0 else "Momentum down"} |
| Yield Curve | {self.indicators.get('yield_curve', 'N/A')}% | {"Normal" if self.indicators.get('yield_curve', 0) > 0 else "Inverted — recession risk"} |
| Fed Policy | {self.indicators.get('fed_trend', 'N/A')} | — |
| Breadth | {self.indicators.get('breadth', 'N/A')}% | {"Strong" if self.indicators.get('breadth', 50) > 70 else "Weak" if self.indicators.get('breadth', 50) < 30 else "Mixed"} |

---

## ⚙️ Strategy Adjustments

| Parameter | Setting |
|-----------|---------|
| **Cash Target** | {strategy['cash_target']:.0%} |
| **Max Position** | {strategy['max_position']:.0%} |
| **Stop Policy** | {strategy['stop_policy']} |
| **New Positions** | {strategy['new_positions']} |
| **Leverage** | {strategy['leverage']} |

**Favored Sectors:** {', '.join(strategy['sectors'])}
**Avoid:** {', '.join(strategy['avoid'])}

**Motto:** *{strategy['motto']}*

---

## 📋 Portfolio Actions

"""
        for action in actions:
            md += f"- {action}\n"
        
        md += """
---

## 🔄 Regime History

| Date | Regime | Confidence | Notes |
|------|--------|------------|-------|
| 2026-05-01 | LATE_BULL | 65% | Tech topping, rotation to energy |
| 2026-05-15 | SIDEWAYS | 55% | Choppy, range-bound |
| 2026-05-27 | EARLY_BULL | 60% | Trend turning, breadth improving |

---

## 🔗 Related
- [[Macro Dashboard]] — Detailed macro analysis
- [[Daily Briefing]] — Today's priorities
- [[Risk Management]] — Position limits
- [[Sector Rotation Tracker]] — Sector flows
"""
        
        return md
    
    def save(self):
        """Save regime analysis to vault"""
        md = self.generate_markdown()
        filepath = f"{VAULT_PATH}/10-Strategy/Market Regime.md"
        
        with open(filepath, "w") as f:
            f.write(md)
        
        print(f"✅ Market Regime saved: {filepath}")
        return filepath

if __name__ == "__main__":
    detector = RegimeDetector()
    
    # Current market conditions (example)
    regime, confidence = detector.analyze(
        vix=14.2,
        spy_200dma=8.5,
        spy_50dma=2.1,
        yield_curve=-0.35,
        fed_trend="PAUSED",
        breadth=62
    )
    
    print(f"🎯 Market Regime: {regime.value} (confidence: {confidence:.0%})")
    print(f"\n📋 Strategy:")
    strategy = detector.get_strategy()
    for k, v in strategy.items():
        print(f"   {k}: {v}")
    
    print(f"\n📊 Portfolio Actions:")
    for action in detector.get_portfolio_actions():
        print(f"   {action}")
    
    detector.save()
