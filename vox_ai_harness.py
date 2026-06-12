#!/usr/bin/env python3
"""
VOX AI Harness v1.0
Signal Unification Layer — converts all data sources into composite scores

Usage:
    python3 vox_ai_harness.py --ticker NVDA    # Score single ticker
    python3 vox_ai_harness.py --scan           # Scan all positions
    python3 vox_ai_harness.py --plays          # Generate actionable plays
"""

import os
import sys
import json
import argparse
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime, timedelta

# Load API key from .env
def load_api_key(key_name="OPENROUTER_API_KEY"):
    env_paths = [
        os.path.expanduser("~/.hermes/scripts/.env"),
        os.path.expanduser("~/.env"),
        ".env"
    ]
    for path in env_paths:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '=' in line:
                        k, v = line.strip().split('=', 1)
                        if k == key_name:
                            return v.strip().strip('"').strip("'")
    return None

API_KEY = load_api_key()

@dataclass
class Signal:
    name: str
    value: float          # 0-100 normalized
    weight: float         # 0-1
    raw_data: Dict
    confidence: float     # 0-1 how reliable is this signal

@dataclass
class CompositeScore:
    ticker: str
    overall: float        # 0-100 weighted composite
    signals: List[Signal]
    grade: Optional[int]
    action: str
    confidence: float
    catalysts: List[str]
    risks: List[str]

@dataclass
class Play:
    id: str
    ticker: str
    type: str             # BUY, SELL, TRIM, HOLD, WATCH
    confidence: float     # 0-100
    conviction: str       # SPEC, CORE
    thesis: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target_price: Optional[float]
    time_horizon: str     # SWING, POSITION, LONG_TERM
    catalysts: List[str]
    risks: List[str]
    source_signals: List[str]
    status: str           # HYPOTHESIS, ACTIVE, EXECUTED, CLOSED
    created_at: str


class VoxHarness:
    """AI Harness — unifies all signals into composite scores"""
    
    # Signal weights (sum to 1.0)
    DEFAULT_WEIGHTS = {
        "grade": 0.40,        # Increased from 0.25 — grade is most reliable
        "technical": 0.15,
        "fundamental": 0.15,
        "sentiment": 0.10,
        "earnings": 0.10,
        "macro": 0.05,        # Decreased — too generic
        "llm_council": 0.00,  # Not implemented yet
        "trump": 0.05,
    }
    
    def __init__(self, weights=None):
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.scripts_dir = os.path.expanduser("~/.hermes/scripts")
        self.data = self._load_all_data()
    
    def _load_all_data(self) -> Dict:
        """Load all data sources"""
        data = {
            "positions": [],
            "grades": {},
            "macro": {},
            "screener": [],
            "trump": {},
            "journal": [],
        }
        
        # Load positions
        pos_file = f"{self.scripts_dir}/dashboard_positions.json"
        if os.path.exists(pos_file):
            with open(pos_file) as f:
                pos_data = json.load(f)
            # Handle both dict with 'positions' key and direct list
            if isinstance(pos_data, dict):
                data["positions"] = pos_data.get("positions", [])
            else:
                data["positions"] = pos_data
        
        # Load grades
        grades_file = f"{self.scripts_dir}/portfolio_grades.json"
        if os.path.exists(grades_file):
            with open(grades_file) as f:
                grades_data = json.load(f)
            # Handle nested format (strong_buy/moderate_buy/avoid)
            if isinstance(grades_data, dict):
                if any(k in grades_data for k in ['strong_buy', 'moderate_buy', 'avoid']):
                    # Flatten nested format
                    flat_grades = {}
                    for cat in ['strong_buy', 'moderate_buy', 'avoid']:
                        for item in grades_data.get(cat, []):
                            if 'ticker' in item:
                                flat_grades[item['ticker']] = item
                    data["grades"] = flat_grades
                else:
                    data["grades"] = grades_data
            elif isinstance(grades_data, list):
                data["grades"] = {g.get("ticker", "UNKNOWN"): g for g in grades_data}
        
        print(f"Harness loaded: {len(data['positions'])} positions, {len(data['grades'])} grades")
        macro_file = f"{self.scripts_dir}/vox_macro_data.json"
        if os.path.exists(macro_file):
            with open(macro_file) as f:
                macro_data = json.load(f)
            if isinstance(macro_data, dict):
                data["macro"] = macro_data
            else:
                data["macro"] = {}
        
        # Load screener
        screener_file = f"{self.scripts_dir}/screener_results.json"
        if os.path.exists(screener_file):
            with open(screener_file) as f:
                data["screener"] = json.load(f)
        
        # Load trump tracker
        trump_file = f"{self.scripts_dir}/trump_tracker_results.json"
        if os.path.exists(trump_file):
            with open(trump_file) as f:
                data["trump"] = json.load(f)
        
        print(f"Harness loaded: {len(data['positions'])} positions, {len(data['grades'])} grades")
        return data
    
    def _get_grade_signal(self, ticker: str) -> Optional[Signal]:
        """Extract grade signal"""
        grade_data = self.data["grades"].get(ticker)
        if not grade_data:
            return None
        
        grade = grade_data.get("grade", 0)
        return Signal(
            name="grade",
            value=min(grade, 100),
            weight=self.weights["grade"],
            raw_data=grade_data,
            confidence=0.8 if grade > 0 else 0.3
        )
    
    def _get_technical_signal(self, ticker: str) -> Optional[Signal]:
        """Extract technical signal from position data"""
        positions = [p for p in self.data["positions"] if p["ticker"] == ticker]
        if not positions:
            return None
        
        # Use unrealized P&L % as proxy for momentum
        pnl_pcts = [p.get("unrealized_pnl_pct", 0) for p in positions]
        avg_pnl = sum(pnl_pcts) / len(pnl_pcts)
        
        # Normalize -50% to +100% → 0-100, but center at 50 for neutral
        # A stock that's flat (0% P&L) should score 50, not 33
        normalized = max(0, min(100, 50 + avg_pnl * 0.5))
        
        return Signal(
            name="technical",
            value=normalized,
            weight=self.weights["technical"],
            raw_data={"avg_pnl_pct": avg_pnl},
            confidence=0.6
        )
    
    def _get_sentiment_signal(self, ticker: str) -> Optional[Signal]:
        """Extract sentiment signal"""
        screener = self.data.get("screener", {})
        results = screener.get("results", []) if isinstance(screener, dict) else []
        
        for item in results:
            if isinstance(item, dict) and item.get("ticker") == ticker:
                sentiment = item.get("sentiment", "neutral")
                score = 70 if sentiment == "bullish" else 30 if sentiment == "bearish" else 50
                return Signal(
                    name="sentiment",
                    value=score,
                    weight=self.weights["sentiment"],
                    raw_data=item,
                    confidence=0.5
                )
        return None
    
    def _get_macro_signal(self, ticker: str) -> Optional[Signal]:
        """Extract macro signal"""
        regime = self.data["macro"].get("regime", "NEUTRAL")
        
        # Map regime to score
        regime_scores = {
            "EARLY_BULL": 75,
            "BULL": 85,
            "LATE_BULL": 60,
            "BEAR": 25,
            "RECOVERY": 55,
            "NEUTRAL": 50,
        }
        
        return Signal(
            name="macro",
            value=regime_scores.get(regime, 50),
            weight=self.weights["macro"],
            raw_data={"regime": regime},
            confidence=0.7
        )
    
    def _get_trump_signal(self, ticker: str) -> Optional[Signal]:
        """Extract Trump policy signal"""
        trump_data = self.data["trump"]
        
        # Check if ticker is in affected list
        affected = trump_data.get("affected_tickers", [])
        if ticker in affected:
            impact = trump_data.get("impact_score", 0)
            return Signal(
                name="trump",
                value=max(0, min(100, 50 + impact)),
                weight=self.weights["trump"],
                raw_data=trump_data,
                confidence=0.4
            )
        return None
    
    def score_ticker(self, ticker: str) -> CompositeScore:
        """Calculate composite score for a ticker"""
        signals = []
        
        # Collect all available signals
        for getter in [
            self._get_grade_signal,
            self._get_technical_signal,
            self._get_sentiment_signal,
            self._get_macro_signal,
            self._get_trump_signal,
        ]:
            signal = getter(ticker)
            if signal:
                signals.append(signal)
        
        # Calculate weighted composite
        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            overall = 50
        else:
            overall = sum(s.value * s.weight for s in signals) / total_weight
        
        # Get grade
        grade_data = self.data["grades"].get(ticker, {})
        grade = grade_data.get("grade")
        
        # Determine action
        if overall >= 75:
            action = "STRONG_BUY"
        elif overall >= 65:
            action = "BUY"
        elif overall >= 50:
            action = "HOLD"
        elif overall >= 40:
            action = "WEAK_HOLD"
        else:
            action = "SELL"
        
        # Calculate confidence
        avg_confidence = sum(s.confidence for s in signals) / len(signals) if signals else 0.5
        
        # Identify catalysts and risks
        catalysts = []
        risks = []
        
        for s in signals:
            if s.name == "grade" and s.value >= 60:
                catalysts.append(f"Strong grade ({s.value:.0f})")
            elif s.name == "grade" and s.value < 40:
                risks.append(f"Weak grade ({s.value:.0f})")
            elif s.name == "technical" and s.value >= 70:
                catalysts.append("Strong momentum")
            elif s.name == "trump":
                risks.append("Policy risk")
        
        return CompositeScore(
            ticker=ticker,
            overall=overall,
            signals=signals,
            grade=grade,
            action=action,
            confidence=avg_confidence,
            catalysts=catalysts,
            risks=risks
        )
    
    def scan_all(self) -> List[CompositeScore]:
        """Score all unique tickers in portfolio"""
        tickers = list(set(p["ticker"] for p in self.data["positions"]))
        
        results = []
        for ticker in sorted(tickers):
            score = self.score_ticker(ticker)
            results.append(score)
        
        # Sort by overall score
        results.sort(key=lambda x: x.overall, reverse=True)
        return results
    
    def generate_plays(self) -> List[Play]:
        """Generate actionable plays from composite scores"""
        scores = self.scan_all()
        plays = []
        
        for score in scores:
            # Skip if not enough confidence
            if score.confidence < 0.4:
                continue
            
            # Determine play type
            if score.overall >= 70 and score.action in ["STRONG_BUY", "BUY"]:
                play_type = "BUY"
                conviction = "CORE"
            elif score.overall >= 60 and score.action == "BUY":
                play_type = "BUY"
                conviction = "SPEC"
            elif score.overall < 35 and score.action in ["SELL", "WEAK_HOLD"]:
                play_type = "SELL"
                conviction = "SPEC"
            elif score.overall < 45 and score.grade and score.grade < 40:
                play_type = "TRIM"
                conviction = "SPEC"
            else:
                play_type = "HOLD"
                conviction = "SPEC"
            
            # Only generate plays for actionable items
            if play_type in ["BUY", "SELL", "TRIM"] and score.confidence >= 0.5:
                # Get position data for price targets
                positions = [p for p in self.data["positions"] if p["ticker"] == score.ticker]
                avg_price = sum(p.get("price", 0) for p in positions) / len(positions) if positions else 0
                
                play = Play(
                    id=f"play_{score.ticker}_{datetime.now().strftime('%Y%m%d')}",
                    ticker=score.ticker,
                    type=play_type,
                    confidence=score.overall,
                    conviction=conviction,
                    thesis=f"Composite score {score.overall:.0f}/100. {', '.join(score.catalysts)}. Risks: {', '.join(score.risks)}",
                    entry_price=avg_price if play_type == "BUY" else None,
                    stop_loss=avg_price * 0.85 if play_type == "BUY" else None,
                    target_price=avg_price * 1.3 if play_type == "BUY" else None,
                    time_horizon="POSITION",
                    catalysts=score.catalysts,
                    risks=score.risks,
                    source_signals=[s.name for s in score.signals],
                    status="HYPOTHESIS",
                    created_at=datetime.now().isoformat()
                )
                plays.append(play)
        
        # Sort by confidence
        plays.sort(key=lambda x: x.confidence, reverse=True)
        return plays
    
    def export_plays(self, plays: List[Play], filepath: str):
        """Export plays to JSON"""
        plays_data = [asdict(p) for p in plays]
        with open(filepath, 'w') as f:
            json.dump(plays_data, f, indent=2)
        print(f"Exported {len(plays)} plays to {filepath}")


def main():
    parser = argparse.ArgumentParser(description="VOX AI Harness")
    parser.add_argument("--ticker", help="Score single ticker")
    parser.add_argument("--scan", action="store_true", help="Scan all positions")
    parser.add_argument("--plays", action="store_true", help="Generate plays")
    parser.add_argument("--top", type=int, default=20, help="Show top N results")
    parser.add_argument("--output", help="Output file for plays")
    
    args = parser.parse_args()
    
    harness = VoxHarness()
    
    if args.ticker:
        print(f"\n=== Scoring {args.ticker} ===\n")
        score = harness.score_ticker(args.ticker)
        
        print(f"Ticker: {score.ticker}")
        print(f"Overall Score: {score.overall:.1f}/100")
        print(f"Grade: {score.grade or 'N/A'}")
        print(f"Action: {score.action}")
        print(f"Confidence: {score.confidence:.1%}")
        print(f"\nSignals:")
        for s in score.signals:
            print(f"  {s.name:12} | {s.value:5.1f} | weight {s.weight:.2f} | conf {s.confidence:.1%}")
        print(f"\nCatalysts: {', '.join(score.catalysts) or 'None'}")
        print(f"Risks: {', '.join(score.risks) or 'None'}")
    
    elif args.scan:
        print("\n=== Scanning All Positions ===\n")
        results = harness.scan_all()
        
        print(f"{'Ticker':<10} {'Score':>6} {'Grade':>6} {'Action':<12} {'Conf':>6}")
        print("-" * 50)
        for r in results[:args.top]:
            print(f"{r.ticker:<10} {r.overall:>6.1f} {r.grade or 'N/A':>6} {r.action:<12} {r.confidence:>6.1%}")
    
    elif args.plays:
        print("\n=== Generating Plays ===\n")
        plays = harness.generate_plays()
        
        print(f"Generated {len(plays)} actionable plays:\n")
        print(f"{'Type':<6} {'Ticker':<8} {'Conf':>5} {'Conv':<6} {'Thesis'}")
        print("-" * 80)
        for p in plays[:args.top]:
            thesis_short = p.thesis[:50] + "..." if len(p.thesis) > 50 else p.thesis
            print(f"{p.type:<6} {p.ticker:<8} {p.confidence:>5.0f} {p.conviction:<6} {thesis_short}")
        
        if args.output:
            harness.export_plays(plays, args.output)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
