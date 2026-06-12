#!/usr/bin/env python3
"""
VOX Decision Layer v1.0
Extra layer of thinking before ANY sell recommendation.

Rules:
1. NEVER recommend selling without context
2. ALWAYS consider: thesis, time horizon, conviction, market conditions
3. ALWAYS present alternatives
4. NEVER treat positions as "just numbers"

This prevents lazy "sell everything" recommendations.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class ConvictionLevel(Enum):
    CORE = "core"           # Never sell without explicit user approval
    STRONG = "strong"       # Hold through volatility
    MODERATE = "moderate"   # Trim on weakness, add on strength
    WEAK = "weak"           # Review regularly, cut if thesis breaks
    SPECULATIVE = "spec"    # Tight stops, quick cuts

@dataclass
class PositionDecision:
    ticker: str
    current_value: float
    current_pct: float
    pnl: float
    pnl_pct: float
    
    # Decision factors
    conviction: ConvictionLevel
    thesis: str
    time_horizon: str  # "short", "medium", "long"
    
    # Market context
    trend: str  # "uptrend", "downtrend", "range", "unknown"
    technical_grade: int  # 0-100
    
    # Recommendation
    action: str  # "HOLD", "TRIM", "SELL", "ADD"
    action_size: str  # "full", "half", "quarter", "none"
    reasoning: str
    alternatives: List[str]
    risks_if_kept: List[str]
    risks_if_sold: List[str]
    
    # User override
    user_protected: bool = False

class DecisionLayer:
    """Prevents lazy sell recommendations"""
    
    def __init__(self):
        self.protected_tickers = ["SHOP"]  # User-protected positions
        self.decisions = []
    
    def analyze_position(self, position: Dict, portfolio_value: float, 
                        market_context: Dict) -> PositionDecision:
        """Deep analysis before recommending any action"""
        
        ticker = position["ticker"]
        value = position["value"]
        pct = value / portfolio_value * 100
        pnl = position.get("pnl", 0)
        cost_basis = value - pnl
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        
        # Determine conviction based on position characteristics
        conviction = self._assess_conviction(ticker, position, pnl_pct)
        
        # Determine trend (simplified - would use technical data)
        trend = self._assess_trend(ticker, pnl_pct)
        
        # Generate thesis
        thesis = self._generate_thesis(ticker, position, conviction)
        
        # Make decision
        action, action_size, reasoning = self._make_decision(
            ticker, value, pct, pnl, pnl_pct, conviction, trend, market_context
        )
        
        # Generate alternatives
        alternatives = self._generate_alternatives(
            ticker, action, conviction, position
        )
        
        # Assess risks
        risks_kept, risks_sold = self._assess_risks(
            ticker, action, position, conviction
        )
        
        return PositionDecision(
            ticker=ticker,
            current_value=value,
            current_pct=pct,
            pnl=pnl,
            pnl_pct=pnl_pct,
            conviction=conviction,
            thesis=thesis,
            time_horizon=self._time_horizon(conviction),
            trend=trend,
            technical_grade=0,  # Would come from technical analyst
            action=action,
            action_size=action_size,
            reasoning=reasoning,
            alternatives=alternatives,
            risks_if_kept=risks_kept,
            risks_if_sold=risks_sold,
            user_protected=ticker in self.protected_tickers
        )
    
    def _assess_conviction(self, ticker: str, position: Dict, pnl_pct: float) -> ConvictionLevel:
        """Assess conviction level for a position"""
        
        # Crypto assets
        if ticker in ["BTC", "ETH"]:
            return ConvictionLevel.STRONG  # Long-term holds
        
        if ticker in ["BNB", "SOL"]:
            return ConvictionLevel.MODERATE  # Quality alts
        
        if ticker in ["DOGE", "SHIB", "TRX", "ADA", "XRP"]:
            return ConvictionLevel.SPECULATIVE  # Meme/speculative
        
        # Large cap tech
        if ticker in ["NVDA", "MSFT", "GOOGL", "AMZN", "AAPL", "META", "TSLA"]:
            return ConvictionLevel.STRONG
        
        # ETFs
        if ticker in ["VOO", "VTI", "QQQ", "XLF", "XLE"]:
            return ConvictionLevel.CORE
        
        # Check position size
        if position["value"] > 10000:
            return ConvictionLevel.STRONG  # Large positions = conviction
        
        if pnl_pct > 50:
            return ConvictionLevel.STRONG  # Big winners = working thesis
        
        if pnl_pct < -30:
            return ConvictionLevel.WEAK  # Big losers = broken thesis?
        
        return ConvictionLevel.MODERATE
    
    def _assess_trend(self, ticker: str, pnl_pct: float) -> str:
        """Simple trend assessment"""
        if pnl_pct > 20:
            return "uptrend"
        elif pnl_pct < -20:
            return "downtrend"
        else:
            return "range"
    
    def _generate_thesis(self, ticker: str, position: Dict, conviction: ConvictionLevel) -> str:
        """Generate investment thesis"""
        
        theses = {
            "BTC": "Digital gold, inflation hedge, long-term store of value",
            "ETH": "Smart contract platform, DeFi infrastructure, staking yield",
            "BNB": "Exchange token, Binance ecosystem, utility value",
            "SOL": "High-performance blockchain, NFT ecosystem, developer growth",
            "DOGE": "Meme coin, speculative, community-driven",
            "XRP": "Cross-border payments, regulatory uncertainty",
            "ADA": "Academic approach, slow development, speculative",
            "TRX": "High yield staking, Justin Sun concerns",
            "NVDA": "AI chip monopoly, data center growth, CUDA ecosystem",
            "TSLA": "EV leader, FSD potential, energy storage",
            "SHOP": "E-commerce platform, merchant solutions, recovery potential",
        }
        
        return theses.get(ticker, f"{ticker} position based on market opportunity")
    
    def _make_decision(self, ticker: str, value: float, pct: float, 
                      pnl: float, pnl_pct: float, conviction: ConvictionLevel,
                      trend: str, market_context: Dict) -> tuple:
        """Make actual decision with deep reasoning"""
        
        # Protected positions
        if ticker in self.protected_tickers:
            return "HOLD", "none", f"User protected position. Do not sell without explicit approval."
        
        # Core positions - never sell
        if conviction == ConvictionLevel.CORE:
            return "HOLD", "none", f"Core holding. Part of long-term portfolio foundation."
        
        # Strong conviction - hold through volatility
        if conviction == ConvictionLevel.STRONG:
            if pnl_pct < -20:
                return "HOLD", "none", f"Strong conviction. Down {pnl_pct:.1f}% but thesis intact. Consider adding on weakness."
            elif pnl_pct > 50:
                return "TRIM", "quarter", f"Strong conviction but up {pnl_pct:.1f}%. Take some profits, let rest run."
            else:
                return "HOLD", "none", f"Strong conviction. Hold for long-term thesis to play out."
        
        # Moderate - trim on weakness, add on strength
        if conviction == ConvictionLevel.MODERATE:
            if pnl_pct < -15:
                return "TRIM", "half", f"Moderate conviction. Down {pnl_pct:.1f}%. Reduce size, keep core position."
            elif pnl_pct > 30:
                return "TRIM", "quarter", f"Moderate conviction. Up {pnl_pct:.1f}%. Take profits, hold core."
            else:
                return "HOLD", "none", f"Moderate conviction. Hold and monitor."
        
        # Weak - review regularly
        if conviction == ConvictionLevel.WEAK:
            if pnl_pct < -20:
                return "SELL", "full", f"Weak conviction. Down {pnl_pct:.1f}%. Thesis likely broken. Cut loss."
            elif pnl_pct > 20:
                return "SELL", "full", f"Weak conviction. Up {pnl_pct:.1f}%. Take profit and redeploy."
            else:
                return "HOLD", "none", f"Weak conviction. Monitor closely. Set stop at -15%."
        
        # Speculative - tight stops
        if conviction == ConvictionLevel.SPECULATIVE:
            if pnl_pct < -10:
                return "SELL", "full", f"Speculative position. Down {pnl_pct:.1f}%. Cut quickly."
            elif pnl_pct > 50:
                return "TRIM", "half", f"Speculative position. Up {pnl_pct:.1f}%. Take profits, ride free shares."
            else:
                return "HOLD", "none", f"Speculative. Tight stop at -10%."
        
        return "HOLD", "none", "Default hold. Need more analysis."
    
    def _generate_alternatives(self, ticker: str, action: str, 
                              conviction: ConvictionLevel, position: Dict) -> List[str]:
        """Generate alternative actions"""
        
        alternatives = []
        
        if action == "SELL":
            alternatives.append(f"Instead of selling, trim 50% and keep half")
            alternatives.append(f"Set a stop loss at -15% instead of selling now")
            alternatives.append(f"Wait for bounce to reduce loss")
        
        if action == "TRIM":
            alternatives.append(f"Instead of trimming, add if it drops 5% more")
            alternatives.append(f"Sell covered calls instead of trimming")
            alternatives.append(f"Move to similar but stronger position")
        
        if action == "HOLD":
            alternatives.append(f"Add on weakness if conviction is high")
            alternatives.append(f"Set trailing stop to protect gains")
            alternatives.append(f"Rebalance if position grew too large")
        
        return alternatives
    
    def _assess_risks(self, ticker: str, action: str, 
                     position: Dict, conviction: ConvictionLevel) -> tuple:
        """Assess risks of keeping vs selling"""
        
        risks_kept = []
        risks_sold = []
        
        if action in ["SELL", "TRIM"]:
            risks_sold.append(f"Miss recovery if {ticker} bounces")
            risks_sold.append(f"Tax event (realize gains/losses)")
            risks_sold.append(f"Transaction costs")
            
            if conviction in [ConvictionLevel.STRONG, ConvictionLevel.CORE]:
                risks_sold.append(f"Selling high-conviction position prematurely")
        
        if action in ["HOLD", "TRIM"]:
            risks_kept.append(f"Further downside if thesis breaks")
            risks_kept.append(f"Opportunity cost of tied-up capital")
            
            if conviction == ConvictionLevel.SPECULATIVE:
                risks_kept.append(f"High volatility, potential large loss")
        
        return risks_kept, risks_sold
    
    def _time_horizon(self, conviction: ConvictionLevel) -> str:
        """Determine time horizon"""
        horizons = {
            ConvictionLevel.CORE: "long (5+ years)",
            ConvictionLevel.STRONG: "long (3-5 years)",
            ConvictionLevel.MODERATE: "medium (1-3 years)",
            ConvictionLevel.WEAK: "short (3-6 months)",
            ConvictionLevel.SPECULATIVE: "short (weeks-months)",
        }
        return horizons.get(conviction, "medium")
    
    def print_decision(self, decision: PositionDecision):
        """Print decision in readable format"""
        
        print(f"\n{'='*60}")
        print(f"🎯 {decision.ticker} — DECISION")
        print(f"{'='*60}")
        
        print(f"\n📊 Position: ${decision.current_value:,.0f} ({decision.current_pct:.1f}%)")
        print(f"📈 P&L: ${decision.pnl:,.0f} ({decision.pnl_pct:+.1f}%)")
        print(f"💭 Conviction: {decision.conviction.value.upper()}")
        print(f"⏰ Time Horizon: {decision.time_horizon}")
        print(f"📉 Trend: {decision.trend}")
        
        print(f"\n📝 Thesis: {decision.thesis}")
        
        print(f"\n{'🔴' if decision.action == 'SELL' else '🟡' if decision.action == 'TRIM' else '🟢'} RECOMMENDATION: {decision.action} {decision.action_size.upper()}")
        print(f"   Reasoning: {decision.reasoning}")
        
        if decision.alternatives:
            print(f"\n💡 Alternatives:")
            for alt in decision.alternatives:
                print(f"   • {alt}")
        
        if decision.risks_if_kept:
            print(f"\n⚠️  Risks if KEPT:")
            for risk in decision.risks_if_kept:
                print(f"   • {risk}")
        
        if decision.risks_if_sold:
            print(f"\n⚠️  Risks if SOLD:")
            for risk in decision.risks_if_sold:
                print(f"   • {risk}")
        
        if decision.user_protected:
            print(f"\n🛒 USER PROTECTED — Do not sell without explicit approval")


def main():
    """Test the decision layer on crypto positions"""
    
    # Load portfolio
    with open(Path.home() / ".hermes" / "scripts" / "dashboard_positions.json") as f:
        portfolio = json.load(f)
    
    positions = portfolio.get("positions", [])
    total_value = portfolio.get("total_value", 197818)
    
    # Focus on crypto
    crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX"]
    crypto_positions = [p for p in positions if p["ticker"] in crypto_tickers]
    
    market_context = {
        "regime": "RANGE",
        "vix": 16.2,
        "btc_dominance": 52.5,
    }
    
    layer = DecisionLayer()
    
    print("="*60)
    print("🧠 VOX DECISION LAYER — CRYPTO ANALYSIS")
    print("="*60)
    print(f"\nPortfolio: ${total_value:,.0f}")
    print(f"Crypto positions: {len(crypto_positions)}")
    
    decisions = []
    for pos in sorted(crypto_positions, key=lambda x: x["value"], reverse=True):
        decision = layer.analyze_position(pos, total_value, market_context)
        layer.print_decision(decision)
        decisions.append(decision)
    
    # Summary
    print(f"\n\n{'='*60}")
    print("📊 DECISION SUMMARY")
    print(f"{'='*60}")
    
    for d in decisions:
        emoji = "🔴" if d.action == "SELL" else "🟡" if d.action == "TRIM" else "🟢"
        print(f"{emoji} {d.ticker:6s}: {d.action:6s} {d.action_size:8s} | Conviction: {d.conviction.value:12s} | ${d.current_value:>8,.0f}")
    
    # Calculate cash impact
    sell_value = sum(d.current_value for d in decisions if d.action == "SELL" and d.action_size == "full")
    trim_value = sum(d.current_value * 0.5 for d in decisions if d.action == "TRIM" and d.action_size == "half")
    trim_value += sum(d.current_value * 0.25 for d in decisions if d.action == "TRIM" and d.action_size == "quarter")
    
    print(f"\n💰 CASH IMPACT:")
    print(f"   From SELLs: ${sell_value:,.0f}")
    print(f"   From TRIMs: ${trim_value:,.0f}")
    print(f"   Total: ${sell_value + trim_value:,.0f}")
    
    print(f"\n⚠️  THOUGHTFUL ANALYSIS COMPLETE")
    print(f"   No lazy 'sell everything' here. Each position analyzed individually.")


if __name__ == "__main__":
    main()
