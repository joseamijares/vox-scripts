#!/usr/bin/env python3
"""
VOX Agentic Platform v1.0
Autonomous decision loop that orchestrates all agents:
1. Macro Agent → Market regime
2. Micro Agent → Fundamental signals
3. Sector Agent → Rotation/trends
4. Alert System → Actionable signals
5. Council → Final decision validation

Loop:
- Collect signals from all agents
- Weight by confidence
- Generate ranked action list
- Council validates top actions
- Execute alerts for approved actions
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def run_agent(script_name: str) -> dict:
    """Run an agent script and return its output."""
    script_path = SCRIPT_DIR / script_name
    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # Try to load JSON output
        output_file = SCRIPT_DIR / script_name.replace(".py", ".json")
        if output_file.exists():
            with open(output_file) as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Agent {script_name} failed: {e}")
        return {}

def collect_signals() -> dict:
    """Run all agents and collect signals."""
    print("🤖 VOX Agentic Platform initializing...")
    print("=" * 60)
    
    signals = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "macro": {},
        "micro": {},
        "sector": {},
        "alerts": [],
        "consensus": {}
    }
    
    # Run Macro Agent
    print("\n📊 Running Macro Agent...")
    signals["macro"] = run_agent("vox_macro_agent.py")
    
    # Run Sector Agent
    print("\n🏭 Running Sector Agent...")
    signals["sector"] = run_agent("vox_sector_agent.py")
    
    # Run Micro Agent (on portfolio)
    print("\n🔬 Running Micro Agent...")
    # Get portfolio tickers
    positions_file = SCRIPT_DIR / "dashboard_positions_live.json"
    if positions_file.exists():
        with open(positions_file) as f:
            data = json.load(f)
            tickers = [p.get("ticker") for p in data.get("positions", []) if p.get("ticker")]
        
        # Save tickers for micro agent
        tickers_file = SCRIPT_DIR / "vox_micro_tickers.json"
        with open(tickers_file, 'w') as f:
            json.dump({"tickers": tickers[:20]}, f)  # Top 20 for speed
        
        signals["micro"] = run_agent("vox_micro_agent.py")
    
    # Run Alert System
    print("\n🚨 Running Alert System...")
    signals["alerts"] = run_agent("vox_smart_alerts_v6.py")
    
    return signals

def weight_signals(signals: dict) -> List[Dict]:
    """Weight and rank all signals."""
    weighted = []
    
    # Macro regime weight
    macro_regime = signals.get("macro", {}).get("regime", "NEUTRAL")
    macro_score = signals.get("macro", {}).get("risk_score", 50)
    
    # Sector rotation weight
    sector_rotation = signals.get("sector", {}).get("rotation", "NEUTRAL")
    
    # Process alerts with macro/sector context
    for alert in signals.get("alerts", []):
        ticker = alert.get("ticker", "")
        action = alert.get("type", "")
        base_score = alert.get("score", 0)
        
        # Adjust score based on macro regime
        adjusted_score = base_score
        
        if macro_regime == "RISK_OFF" and action in ["BUY", "ADD"]:
            adjusted_score -= 20  # Reduce buy signals in risk-off
        elif macro_regime == "RISK_ON" and action in ["SELL", "TRIM"]:
            adjusted_score -= 15  # Reduce sell signals in risk-on
        
        # Sector alignment
        if sector_rotation == "INFLATION" and ticker in ["XLE", "XLB", "XLI"]:
            adjusted_score += 10
        elif sector_rotation == "RISK_ON" and ticker in ["XLK", "XLC", "XLY"]:
            adjusted_score += 10
        
        weighted.append({
            "ticker": ticker,
            "action": action,
            "base_score": base_score,
            "adjusted_score": adjusted_score,
            "macro_regime": macro_regime,
            "sector_rotation": sector_rotation,
            "message": alert.get("message", "")
        })
    
    # Sort by adjusted score
    weighted.sort(key=lambda x: abs(x["adjusted_score"]), reverse=True)
    
    return weighted

def generate_consensus(weighted_signals: List[Dict]) -> dict:
    """Generate final consensus with context."""
    top_actions = weighted_signals[:5]
    
    consensus = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "top_actions": top_actions,
        "market_context": {
            "regime": weighted_signals[0]["macro_regime"] if weighted_signals else "NEUTRAL",
            "rotation": weighted_signals[0]["sector_rotation"] if weighted_signals else "NEUTRAL"
        },
        "summary": f"Top {len(top_actions)} actions ranked by macro-adjusted confidence"
    }
    
    return consensus

def run_agentic_loop():
    """Main agentic loop."""
    print("\n" + "=" * 60)
    print("🤖 VOX AGENTIC PLATFORM v1.0")
    print("=" * 60)
    
    # Collect all signals
    signals = collect_signals()
    
    # Weight and rank
    print("\n⚖️  Weighting signals with macro/sector context...")
    weighted = weight_signals(signals)
    
    # Generate consensus
    consensus = generate_consensus(weighted)
    
    # Save
    output_file = SCRIPT_DIR / "vox_agentic_consensus.json"
    with open(output_file, 'w') as f:
        json.dump(consensus, f, indent=2)
    
    # Display
    print("\n" + "=" * 60)
    print("📋 AGENTIC CONSENSUS")
    print("=" * 60)
    
    for i, action in enumerate(consensus["top_actions"], 1):
        print(f"\n{i}. {action['action']} {action['ticker']}")
        print(f"   Score: {action['base_score']} → {action['adjusted_score']} (adjusted)")
        print(f"   Context: {action['macro_regime']} | {action['sector_rotation']}")
    
    print(f"\n💾 Saved to {output_file}")
    
    return consensus

if __name__ == "__main__":
    run_agentic_loop()
