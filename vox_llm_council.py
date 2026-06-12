#!/usr/bin/env python3
"""
VOX LLM Council v1.0
Multi-model deliberation before ANY recommendation.

Every play/decision goes through:
1. Data Analyst (facts)
2. Risk Manager (downside)  
3. Contrarian (why this might be wrong)
4. Portfolio Context (fit with overall strategy)
5. Chairman (final vote)

No recommendation without council approval.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass
class CouncilVote:
    agent: str
    role: str
    vote: str  # "APPROVE", "REJECT", "CONDITIONAL"
    confidence: int  # 0-100
    reasoning: str
    concerns: List[str]
    conditions: List[str]  # Must be met for approval

@dataclass
class CouncilDecision:
    timestamp: str
    ticker: str
    proposed_action: str
    votes: List[CouncilVote]
    consensus: str  # "APPROVE", "REJECT", "CONDITIONAL"
    consensus_confidence: int
    final_recommendation: str
    execution_conditions: List[str]
    dissent_notes: List[str]
    requires_human_approval: bool

class LLMCouncil:
    """Simulated LLM council - in production, calls multiple models"""
    
    def __init__(self):
        self.agents = {
            "data_analyst": self._data_analyst,
            "risk_manager": self._risk_manager,
            "contrarian": self._contrarian,
            "portfolio_context": self._portfolio_context,
            "chairman": self._chairman,
        }
    
    def deliberate(self, ticker: str, action: str, position: Dict, 
                   portfolio: Dict, market_context: Dict) -> CouncilDecision:
        """Full council deliberation on a proposed action"""
        
        votes = []
        
        # Each agent votes
        for agent_name, agent_func in self.agents.items():
            if agent_name != "chairman":
                vote = agent_func(ticker, action, position, portfolio, market_context)
                votes.append(vote)
        
        # Chairman reviews all votes and decides
        chairman_vote = self._chairman(ticker, action, position, portfolio, market_context, votes)
        votes.append(chairman_vote)
        
        # Calculate consensus
        approve_count = sum(1 for v in votes if v.vote == "APPROVE")
        reject_count = sum(1 for v in votes if v.vote == "REJECT")
        conditional_count = sum(1 for v in votes if v.vote == "CONDITIONAL")
        
        if reject_count >= 2:
            consensus = "REJECT"
            consensus_confidence = int((reject_count / len(votes)) * 100)
        elif approve_count >= 3 and reject_count == 0:
            consensus = "APPROVE"
            consensus_confidence = int((approve_count / len(votes)) * 100)
        else:
            consensus = "CONDITIONAL"
            consensus_confidence = int((conditional_count / len(votes)) * 100)
        
        # Collect execution conditions
        execution_conditions = []
        for v in votes:
            execution_conditions.extend(v.conditions)
        
        # Collect dissent
        dissent_notes = []
        for v in votes:
            if v.vote == "REJECT" or v.confidence < 60:
                dissent_notes.append(f"{v.agent}: {v.reasoning}")
        
        # Determine if human approval required
        requires_human = (
            consensus == "REJECT" or
            consensus == "CONDITIONAL" or
            consensus_confidence < 70 or
            position.get("value", 0) > 10000 or  # Large positions
            ticker in ["SHOP"]  # Protected
        )
        
        # Final recommendation
        if consensus == "REJECT":
            final_rec = f"REJECTED: Council rejects {action} {ticker}. See dissent notes."
        elif consensus == "CONDITIONAL":
            final_rec = f"CONDITIONAL: {action} {ticker} only if conditions met."
        else:
            final_rec = f"APPROVED: {action} {ticker} with confidence {consensus_confidence}%"
        
        return CouncilDecision(
            timestamp=datetime.now(timezone.utc).isoformat(),
            ticker=ticker,
            proposed_action=action,
            votes=votes,
            consensus=consensus,
            consensus_confidence=consensus_confidence,
            final_recommendation=final_rec,
            execution_conditions=list(set(execution_conditions)),
            dissent_notes=dissent_notes,
            requires_human_approval=requires_human,
        )
    
    def _data_analyst(self, ticker, action, position, portfolio, market_context) -> CouncilVote:
        """Analyzes data quality and facts"""
        
        value = position.get("value", 0)
        pnl = position.get("pnl", 0)
        pnl_pct = (pnl / (value - pnl) * 100) if value != pnl else 0
        
        concerns = []
        conditions = []
        
        # Check data freshness
        if market_context.get("data_stale", False):
            concerns.append("Data is stale - prices may have changed")
            conditions.append("Verify current price before execution")
        
        # Check for missing data
        if not position.get("price"):
            concerns.append("Missing price data")
            conditions.append("Get live price quote")
        
        # Check position size
        portfolio_value = portfolio.get("total_value", 197818)
        if value > portfolio_value * 0.10:
            concerns.append(f"Large position: ${value:,.0f} ({value/portfolio_value*100:.1f}%)")
        
        if concerns:
            vote = "CONDITIONAL"
            confidence = 60
        else:
            vote = "APPROVE"
            confidence = 85
        
        return CouncilVote(
            agent="data_analyst",
            role="Data Quality & Facts",
            vote=vote,
            confidence=confidence,
            reasoning=f"Position: ${value:,.0f}, P&L: {pnl_pct:+.1f}%. Data quality: {'good' if not concerns else 'concerns'}",
            concerns=concerns,
            conditions=conditions,
        )
    
    def _risk_manager(self, ticker, action, position, portfolio, market_context) -> CouncilVote:
        """Analyzes downside and risk"""
        
        value = position.get("value", 0)
        pnl = position.get("pnl", 0)
        pnl_pct = (pnl / (value - pnl) * 100) if value != pnl else 0
        
        concerns = []
        conditions = []
        
        # Selling losers - tax loss harvesting
        if action in ["SELL", "TRIM"] and pnl < -500:
            concerns.append(f"Realizing ${abs(pnl):,.0f} loss")
            # In Mexico no tax loss harvesting, so this is just a loss
        
        # Concentration risk
        portfolio_value = portfolio.get("total_value", 197818)
        if value > portfolio_value * 0.08:
            concerns.append(f"Concentration risk: {value/portfolio_value*100:.1f}% of portfolio")
        
        # Market regime
        regime = market_context.get("regime", "UNKNOWN")
        if regime == "BEAR" and action == "BUY":
            concerns.append("Buying in bear market - high risk")
            conditions.append("Wait for trend reversal confirmation")
        
        # Crypto specific
        if ticker in ["BTC", "ETH", "BNB", "SOL"]:
            if action == "SELL":
                concerns.append("Selling core crypto assets - may miss long-term upside")
                conditions.append("Ensure this is rebalancing, not panic selling")
        
        if concerns:
            vote = "CONDITIONAL"
            confidence = 55
        else:
            vote = "APPROVE"
            confidence = 75
        
        return CouncilVote(
            agent="risk_manager",
            role="Risk & Downside Analysis",
            vote=vote,
            confidence=confidence,
            reasoning=f"Risk assessment: {'concerns found' if concerns else 'acceptable'}. Regime: {regime}",
            concerns=concerns,
            conditions=conditions,
        )
    
    def _contrarian(self, ticker, action, position, portfolio, market_context) -> CouncilVote:
        """Argues against the proposed action"""
        
        value = position.get("value", 0)
        pnl = position.get("pnl", 0)
        
        concerns = []
        conditions = []
        
        # Why selling might be wrong
        if action in ["SELL", "TRIM"]:
            if pnl < -1000:
                concerns.append(f"Selling at loss - could bounce back")
                conditions.append("Wait 48h for potential bounce")
            
            if ticker in ["BTC", "ETH"]:
                concerns.append("Institutional adoption increasing - selling now may be premature")
            
            if value < 500:
                concerns.append("Small position - transaction costs may exceed benefit")
        
        # Why buying might be wrong
        if action == "BUY":
            concerns.append("Could be catching a falling knife")
            conditions.append("Wait for confirmation of trend reversal")
        
        # Why holding might be wrong
        if action == "HOLD":
            if pnl < -2000:
                concerns.append("Holding big loser - opportunity cost of dead money")
        
        if concerns:
            vote = "CONDITIONAL" if len(concerns) < 3 else "REJECT"
            confidence = 50 if vote == "REJECT" else 65
        else:
            vote = "APPROVE"
            confidence = 70
        
        return CouncilVote(
            agent="contrarian",
            role="Devil's Advocate",
            vote=vote,
            confidence=confidence,
            reasoning=f"Contrarian view: {'strong objections' if vote == 'REJECT' else 'some concerns' if concerns else 'no major objections'}",
            concerns=concerns,
            conditions=conditions,
        )
    
    def _portfolio_context(self, ticker, action, position, portfolio, market_context) -> CouncilVote:
        """Analyzes fit with overall portfolio strategy"""
        
        value = position.get("value", 0)
        portfolio_value = portfolio.get("total_value", 197818)
        
        concerns = []
        conditions = []
        
        # Sector balance
        # Would need sector data
        
        # Cash position
        # Would need cash data
        
        # Correlation
        if ticker in ["BTC", "ETH"]:
            concerns.append("Crypto correlation with tech stocks - may not provide diversification")
        
        # User preferences
        if ticker == "SHOP":
            concerns.append("User has explicitly protected this position")
            vote = "REJECT"
            confidence = 95
            return CouncilVote(
                agent="portfolio_context",
                role="Portfolio Strategy & User Preferences",
                vote=vote,
                confidence=confidence,
                reasoning="User explicitly protected SHOP - do not sell without approval",
                concerns=concerns,
                conditions=["Get explicit user approval before any action on SHOP"],
            )
        
        if concerns:
            vote = "CONDITIONAL"
            confidence = 70
        else:
            vote = "APPROVE"
            confidence = 80
        
        return CouncilVote(
            agent="portfolio_context",
            role="Portfolio Strategy & User Preferences",
            vote=vote,
            confidence=confidence,
            reasoning="Portfolio fit: acceptable. No major conflicts with strategy.",
            concerns=concerns,
            conditions=conditions,
        )
    
    def _chairman(self, ticker, action, position, portfolio, market_context, prior_votes) -> CouncilVote:
        """Reviews all votes and makes final decision"""
        
        approve_count = sum(1 for v in prior_votes if v.vote == "APPROVE")
        reject_count = sum(1 for v in prior_votes if v.vote == "REJECT")
        conditional_count = sum(1 for v in prior_votes if v.vote == "CONDITIONAL")
        
        all_concerns = []
        all_conditions = []
        for v in prior_votes:
            all_concerns.extend(v.concerns)
            all_conditions.extend(v.conditions)
        
        # Chairman logic
        if reject_count >= 2:
            vote = "REJECT"
            confidence = 70
            reasoning = f"Council strongly divided. {reject_count} rejections. Action blocked pending review."
        elif conditional_count >= 2:
            vote = "CONDITIONAL"
            confidence = 65
            reasoning = "Multiple conditions required. Proceed only if all conditions met."
        elif approve_count >= 3:
            vote = "APPROVE"
            confidence = 80
            reasoning = "Strong consensus for approval. Proceed with standard precautions."
        else:
            vote = "CONDITIONAL"
            confidence = 60
            reasoning = "Mixed signals. Require additional analysis before execution."
        
        # Special cases
        value = position.get("value", 0)
        if value > 15000:
            vote = "CONDITIONAL"
            confidence = 50
            reasoning += " Large position - requires human confirmation."
            all_conditions.append("Get explicit user approval for positions >$15K")
        
        return CouncilVote(
            agent="chairman",
            role="Final Authority",
            vote=vote,
            confidence=confidence,
            reasoning=reasoning,
            concerns=all_concerns[:5],  # Top 5 concerns
            conditions=all_conditions,
        )
    
    def print_decision(self, decision: CouncilDecision):
        """Print council decision in readable format"""
        
        print(f"\n{'='*70}")
        print(f"🗳️  LLM COUNCIL DECISION: {decision.ticker}")
        print(f"{'='*70}")
        print(f"Proposed Action: {decision.proposed_action}")
        print(f"Consensus: {decision.consensus} ({decision.consensus_confidence}% confidence)")
        print(f"Requires Human Approval: {'YES' if decision.requires_human_approval else 'NO'}")
        
        print(f"\n📊 Council Votes:")
        for vote in decision.votes:
            emoji = "🟢" if vote.vote == "APPROVE" else "🔴" if vote.vote == "REJECT" else "🟡"
            print(f"   {emoji} {vote.agent:20s} | {vote.vote:12s} | {vote.confidence:3d}% | {vote.role}")
        
        if decision.dissent_notes:
            print(f"\n⚠️  Dissent:")
            for note in decision.dissent_notes:
                print(f"   • {note}")
        
        if decision.execution_conditions:
            print(f"\n✅ Execution Conditions:")
            for condition in decision.execution_conditions:
                print(f"   • {condition}")
        
        print(f"\n📝 Final: {decision.final_recommendation}")
        print(f"{'='*70}")


def main():
    """Test the LLM council on crypto decisions"""
    
    # Load portfolio
    with open(Path.home() / ".hermes" / "scripts" / "dashboard_positions.json") as f:
        portfolio = json.load(f)
    
    positions = portfolio.get("positions", [])
    
    market_context = {
        "regime": "RANGE",
        "vix": 16.2,
        "data_stale": True,
    }
    
    council = LLMCouncil()
    
    print("="*70)
    print("🗳️  LLM COUNCIL DELIBERATION")
    print("="*70)
    print("\nEvery decision reviewed by 5 agents before recommendation")
    
    # Test on key positions
    test_cases = [
        ("BTC", "SELL", 16812),
        ("ETH", "SELL", 8396),
        ("SHOP", "SELL", 6877),
        ("NVDA", "TRIM", 10150),
    ]
    
    all_decisions = []
    
    for ticker, action, _ in test_cases:
        position = next((p for p in positions if p["ticker"] == ticker), {"ticker": ticker, "value": 0, "pnl": 0})
        decision = council.deliberate(ticker, action, position, portfolio, market_context)
        council.print_decision(decision)
        all_decisions.append(decision)
    
    # Summary
    print(f"\n\n{'='*70}")
    print("📊 COUNCIL SUMMARY")
    print(f"{'='*70}")
    
    approved = sum(1 for d in all_decisions if d.consensus == "APPROVE")
    rejected = sum(1 for d in all_decisions if d.consensus == "REJECT")
    conditional = sum(1 for d in all_decisions if d.consensus == "CONDITIONAL")
    
    print(f"Approved:     {approved}")
    print(f"Rejected:     {rejected}")
    print(f"Conditional:  {conditional}")
    print(f"Need Human:   {sum(1 for d in all_decisions if d.requires_human_approval)}")
    
    # Save decisions
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decisions": [asdict(d) for d in all_decisions],
    }
    
    with open(Path.home() / ".hermes" / "scripts" / "vox_council_decisions.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Council decisions saved")


if __name__ == "__main__":
    main()
