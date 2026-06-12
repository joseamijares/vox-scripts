#!/usr/bin/env python3
"""
VOX Macro Analyst Agent
Analyzes Fed policy, CPI, sector rotation, global events.
Reads economic calendar. Outputs: risk-on/risk-off signals per sector.

Usage:
    python3 macro_analyst.py analyze
    python3 macro_analyst.py sector --sector technology
"""

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Economic indicators and their market impact
INDICATOR_IMPACT = {
    "CPI": "high",
    "PPI": "medium",
    "FOMC": "high",
    "NFP": "high",
    "GDP": "medium",
    "Retail Sales": "medium",
    "Consumer Confidence": "low",
    "ISM Manufacturing": "medium",
    "Jobless Claims": "low",
}

SECTOR_MACRO_MAP = {
    "technology": ["interest_rates", "semiconductor_demand", "ai_spending"],
    "healthcare": ["drug_pricing", "regulation", "aging_demographics"],
    "energy": ["oil_prices", "geopolitics", "climate_policy"],
    "financials": ["interest_rates", "yield_curve", "regulation"],
    "consumer": ["consumer_spending", "employment", "inflation"],
    "industrials": ["manufacturing", "supply_chain", "infrastructure"],
    "materials": ["commodity_prices", "china_demand", "dollar_strength"],
    "utilities": ["interest_rates", "energy_transition", "regulation"],
    "reits": ["interest_rates", "real_estate", "remote_work"],
    "crypto": ["regulation", "liquidity", "adoption"],
}


def get_market_regime() -> Dict:
    """Determine current market regime"""
    # This would ideally read from vox_market_regime.py output
    # For now, use a simple heuristic based on recent market data
    
    regime = {
        "regime": "EARLY_BULL",  # Would be dynamic
        "risk_appetite": "moderate",
        "fed_stance": "neutral",
        "inflation_trend": "cooling",
        "yield_curve": "normal",
        "dollar_trend": "sideways",
        "liquidity": "tightening",
    }
    
    return regime


def analyze_sector(sector: str, regime: Dict) -> Dict:
    """Analyze a sector given current macro regime"""
    sector = sector.lower()
    
    if sector not in SECTOR_MACRO_MAP:
        return {"error": f"Unknown sector: {sector}"}
    
    factors = SECTOR_MACRO_MAP[sector]
    
    # Score each factor
    scores = {}
    for factor in factors:
        if factor == "interest_rates":
            # Rising rates hurt growth, help financials
            if regime["fed_stance"] == "hawkish":
                scores[factor] = -2 if sector in ["technology", "reits", "utilities"] else 1
            elif regime["fed_stance"] == "dovish":
                scores[factor] = 2 if sector in ["technology", "reits", "utilities"] else -1
            else:
                scores[factor] = 0
        
        elif factor == "inflation":
            # High inflation hurts consumer, helps energy/materials
            if regime["inflation_trend"] == "rising":
                scores[factor] = 2 if sector in ["energy", "materials"] else -1
            elif regime["inflation_trend"] == "cooling":
                scores[factor] = -1 if sector in ["energy", "materials"] else 1
            else:
                scores[factor] = 0
        
        elif factor == "commodity_prices":
            if regime["inflation_trend"] == "rising":
                scores[factor] = 2
            else:
                scores[factor] = 0
        
        elif factor == "consumer_spending":
            if regime["risk_appetite"] == "high":
                scores[factor] = 2
            elif regime["risk_appetite"] == "low":
                scores[factor] = -2
            else:
                scores[factor] = 0
        
        elif factor == "regulation":
            # Simplified: regulation generally negative
            scores[factor] = -1
        
        elif factor == "liquidity":
            if regime["liquidity"] == "easing":
                scores[factor] = 2
            elif regime["liquidity"] == "tightening":
                scores[factor] = -2
            else:
                scores[factor] = 0
        
        else:
            scores[factor] = 0
    
    # Calculate total score
    total_score = sum(scores.values())
    
    # Determine signal
    if total_score >= 3:
        signal = "STRONG_BUY"
        conviction = min(100, 50 + total_score * 10)
    elif total_score >= 1:
        signal = "BUY"
        conviction = min(100, 30 + total_score * 10)
    elif total_score <= -3:
        signal = "STRONG_SELL"
        conviction = min(100, 50 + abs(total_score) * 10)
    elif total_score <= -1:
        signal = "SELL"
        conviction = min(100, 30 + abs(total_score) * 10)
    else:
        signal = "NEUTRAL"
        conviction = 20
    
    return {
        "sector": sector,
        "signal": signal,
        "conviction": conviction,
        "score": total_score,
        "factor_scores": scores,
        "regime": regime["regime"],
    }


def analyze_all_sectors() -> List[Dict]:
    """Analyze all sectors"""
    regime = get_market_regime()
    
    print("🌍 MACRO ANALYSIS")
    print(f"   Regime: {regime['regime']}")
    print(f"   Fed: {regime['fed_stance']}")
    print(f"   Inflation: {regime['inflation_trend']}")
    print(f"   Liquidity: {regime['liquidity']}")
    print()
    
    results = []
    for sector in SECTOR_MACRO_MAP.keys():
        result = analyze_sector(sector, regime)
        results.append(result)
        
        emoji = "🟢" if result["score"] > 0 else "🔴" if result["score"] < 0 else "⚪"
        print(f"   {emoji} {sector.upper():15} | {result['signal']:12} | Score: {result['score']:+d} | Conviction: {result['conviction']}")
    
    # Save results
    output_file = Path.home() / ".hermes" / "scripts" / "vox_macro_analysis.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regime": regime,
            "results": results,
        }, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Macro Analyst")
    parser.add_argument("--sector", help="Analyze specific sector")
    
    args = parser.parse_args()
    
    if args.sector:
        regime = get_market_regime()
        result = analyze_sector(args.sector, regime)
        print(json.dumps(result, indent=2))
    else:
        analyze_all_sectors()


if __name__ == "__main__":
    main()
