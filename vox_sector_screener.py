#!/usr/bin/env python3
"""
VOX Sector Screener v1.0
Tracks sector momentum, rotation, relative strength.

Usage:
    python3 vox_sector_screener.py scan
    python3 vox_sector_screener.py rotation
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Sector ETFs for tracking
SECTOR_ETFS = {
    "technology": "XLK",
    "healthcare": "XLV",
    "energy": "XLE",
    "financials": "XLF",
    "consumer": "XLY",
    "industrials": "XLI",
    "materials": "XLB",
    "utilities": "XLU",
    "reits": "XLRE",
}

# Mock sector performance (would use real ETF data)
SECTOR_PERFORMANCE = {
    "technology": {"1w": 2.5, "1m": 5.2, "3m": 8.1, "ytd": 12.3},
    "healthcare": {"1w": -0.5, "1m": 1.2, "3m": 3.5, "ytd": 5.1},
    "energy": {"1w": 1.8, "1m": 3.5, "3m": 6.2, "ytd": 9.8},
    "financials": {"1w": 0.8, "1m": 2.1, "3m": 4.5, "ytd": 7.2},
    "consumer": {"1w": 1.2, "1m": 3.8, "3m": 5.5, "ytd": 8.9},
    "industrials": {"1w": 0.5, "1m": 1.8, "3m": 3.2, "ytd": 5.5},
    "materials": {"1w": -0.2, "1m": 0.8, "3m": 2.1, "ytd": 3.8},
    "utilities": {"1w": -1.2, "1m": -0.5, "3m": 1.2, "ytd": 2.1},
    "reits": {"1w": -0.8, "1m": 0.2, "3m": 1.8, "ytd": 3.2},
}

def analyze_sector_momentum() -> List[Dict]:
    """Analyze sector momentum"""
    results = []
    
    for sector, performance in SECTOR_PERFORMANCE.items():
        # Calculate momentum score
        momentum = (
            performance["1w"] * 0.4 +
            performance["1m"] * 0.35 +
            performance["3m"] * 0.25
        )
        
        # Determine trend
        if momentum > 3:
            trend = "STRONG_UP"
        elif momentum > 1:
            trend = "UP"
        elif momentum < -3:
            trend = "STRONG_DOWN"
        elif momentum < -1:
            trend = "DOWN"
        else:
            trend = "NEUTRAL"
        
        results.append({
            "sector": sector,
            "etf": SECTOR_ETFS.get(sector, ""),
            "momentum": round(momentum, 2),
            "trend": trend,
            "performance": performance,
        })
    
    return sorted(results, key=lambda x: x["momentum"], reverse=True)

def detect_rotation() -> Dict:
    """Detect sector rotation"""
    sectors = analyze_sector_momentum()
    
    # Find leaders and laggards
    leaders = [s for s in sectors if s["trend"] in ["STRONG_UP", "UP"]]
    laggards = [s for s in sectors if s["trend"] in ["STRONG_DOWN", "DOWN"]]
    
    # Detect rotation patterns
    rotation = {
        "from": [],
        "to": [],
        "strength": "NONE",
    }
    
    if len(leaders) >= 3 and len(laggards) >= 3:
        # Check if tech/consumer leading (risk-on)
        risk_on = any(s["sector"] in ["technology", "consumer"] for s in leaders[:2])
        # Check if utilities/healthcare leading (risk-off)
        risk_off = any(s["sector"] in ["utilities", "healthcare"] for s in leaders[:2])
        
        if risk_on:
            rotation["to"] = ["technology", "consumer"]
            rotation["from"] = ["utilities", "healthcare"]
            rotation["strength"] = "RISK_ON"
        elif risk_off:
            rotation["to"] = ["utilities", "healthcare"]
            rotation["from"] = ["technology", "consumer"]
            rotation["strength"] = "RISK_OFF"
    
    return rotation

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Sector Screener")
    parser.add_argument("command", choices=["scan", "rotation"])
    
    args = parser.parse_args()
    
    if args.command == "scan":
        print("\n📊 SECTOR MOMENTUM")
        print("=" * 70)
        
        sectors = analyze_sector_momentum()
        for sector in sectors:
            emoji = "🟢" if sector["momentum"] > 1 else "🔴" if sector["momentum"] < -1 else "⚪"
            print(f"   {emoji} {sector['sector']:15} | {sector['trend']:12} | Momentum: {sector['momentum']:+.2f}")
            print(f"      1W: {sector['performance']['1w']:+.1f}% | 1M: {sector['performance']['1m']:+.1f}% | 3M: {sector['performance']['3m']:+.1f}% | YTD: {sector['performance']['ytd']:+.1f}%")
        
        # Save
        output_file = Path.home() / ".hermes" / "scripts" / "vox_sector_momentum.json"
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sectors": sectors,
            }, f, indent=2)
        
        print(f"\n✅ Saved to {output_file}")
    
    elif args.command == "rotation":
        print("\n🔄 SECTOR ROTATION")
        print("=" * 70)
        
        rotation = detect_rotation()
        
        if rotation["strength"] == "NONE":
            print("   ⚪ No clear rotation detected")
        else:
            emoji = "🟢" if rotation["strength"] == "RISK_ON" else "🔴"
            print(f"   {emoji} {rotation['strength']}")
            print(f"   Money flowing TO: {', '.join(rotation['to'])}")
            print(f"   Money flowing FROM: {', '.join(rotation['from'])}")
        
        # Save
        output_file = Path.home() / ".hermes" / "scripts" / "vox_sector_rotation.json"
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "rotation": rotation,
            }, f, indent=2)
        
        print(f"\n✅ Saved to {output_file}")

if __name__ == "__main__":
    main()
