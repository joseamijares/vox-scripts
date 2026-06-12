#!/usr/bin/env python3
"""
VOX Macro Analyst v1.0
Tracks macroeconomic indicators and their market impact.

Sources:
- Fed policy (rates, statements)
- CPI/PPI inflation data
- Employment (NFP, unemployment)
- Treasury yields (10Y, 2Y)
- Dollar index (DXY)
- Oil prices

Output: vox_macro_report.json
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public"

def get_fed_policy():
    """Get Fed policy stance"""
    # Placeholder - would fetch from FRED API
    return {
        "fed_funds_rate": 5.25,
        "last_change": "HOLD",
        "next_meeting": "2026-06-17",
        "stance": "RESTRICTIVE",
        "dot_plot": "NO_CUTS_2026",
    }

def get_inflation():
    """Get inflation data"""
    return {
        "cpi_yoy": 3.2,
        "cpi_mom": 0.3,
        "core_cpi_yoy": 3.8,
        "ppi_yoy": 2.1,
        "trend": "STICKY",
        "target": 2.0,
        "gap": 1.2,
    }

def get_employment():
    """Get employment data"""
    return {
        "unemployment_rate": 3.9,
        "nfp_last": 175000,
        "nfp_trend": "SLOWING",
        "labor_market": "COOLING",
    }

def get_yields():
    """Get treasury yields"""
    return {
        "ten_year": 4.42,
        "two_year": 4.85,
        "spread": -0.43,
        "curve": "INVERTED",
        "trend": "RISING",
    }

def get_dollar():
    """Get dollar index"""
    return {
        "dxy": 104.5,
        "trend": "FLAT",
        "impact": "NEUTRAL",
    }

def get_commodities():
    """Get commodity prices"""
    return {
        "oil_wti": 78.50,
        "oil_trend": "RISING",
        "gold": 2340,
        "gold_trend": "RISING",
    }

def analyze_macro(fed, inflation, employment, yields, dollar, commodities):
    """Analyze macro environment and generate signals"""
    
    signals = []
    score = 0
    
    # Fed policy
    if fed["stance"] == "RESTRICTIVE":
        signals.append({
            "type": "MONETARY",
            "signal": "HAWKISH",
            "impact": "NEGATIVE",
            "message": "Fed maintaining restrictive policy. Pressure on valuations.",
        })
        score -= 20
    elif fed["stance"] == "ACCOMMODATIVE":
        signals.append({
            "type": "MONETARY",
            "signal": "DOVISH",
            "impact": "POSITIVE",
            "message": "Fed accommodative. Supportive for risk assets.",
        })
        score += 20
    
    # Inflation
    if inflation["cpi_yoy"] > 3.5:
        signals.append({
            "type": "INFLATION",
            "signal": "HIGH",
            "impact": "NEGATIVE",
            "message": f"CPI at {inflation['cpi_yoy']}% > 3.5%. Inflation sticky.",
        })
        score -= 15
    elif inflation["cpi_yoy"] < 2.5:
        signals.append({
            "type": "INFLATION",
            "signal": "LOW",
            "impact": "POSITIVE",
            "message": "Inflation near target. Room for Fed cuts.",
        })
        score += 15
    
    # Employment
    if employment["unemployment_rate"] > 4.5:
        signals.append({
            "type": "EMPLOYMENT",
            "signal": "WEAK",
            "impact": "NEGATIVE",
            "message": f"Unemployment rising to {employment['unemployment_rate']}%.",
        })
        score -= 10
    
    # Yield curve
    if yields["curve"] == "INVERTED":
        signals.append({
            "type": "YIELD_CURVE",
            "signal": "INVERTED",
            "impact": "NEGATIVE",
            "message": f"Yield curve inverted ({yields['spread']:.2f}%). Recession risk.",
        })
        score -= 15
    
    # Dollar
    if dollar["dxy"] > 105:
        signals.append({
            "type": "DOLLAR",
            "signal": "STRONG",
            "impact": "NEGATIVE",
            "message": "Strong dollar pressuring exports and commodities.",
        })
        score -= 10
    elif dollar["dxy"] < 100:
        signals.append({
            "type": "DOLLAR",
            "signal": "WEAK",
            "impact": "POSITIVE",
            "message": "Weak dollar supportive for multinationals.",
        })
        score += 10
    
    # Determine regime
    if score >= 30:
        regime = "GOLDILOCKS"
    elif score >= 10:
        regime = "FAVORABLE"
    elif score >= -10:
        regime = "MIXED"
    elif score >= -30:
        regime = "CHALLENGING"
    else:
        regime = "HOSTILE"
    
    return {
        "score": score,
        "regime": regime,
        "signals": signals,
    }

def generate_macro_report():
    """Generate comprehensive macro report"""
    
    now = datetime.now(timezone.utc)
    
    fed = get_fed_policy()
    inflation = get_inflation()
    employment = get_employment()
    yields = get_yields()
    dollar = get_dollar()
    commodities = get_commodities()
    
    analysis = analyze_macro(fed, inflation, employment, yields, dollar, commodities)
    
    report = {
        "timestamp": now.isoformat(),
        "macro_score": analysis["score"],
        "macro_regime": analysis["regime"],
        "fed": fed,
        "inflation": inflation,
        "employment": employment,
        "yields": yields,
        "dollar": dollar,
        "commodities": commodities,
        "signals": analysis["signals"],
        "alerts": [],
        "sector_implications": {},
    }
    
    # Generate alerts
    for signal in analysis["signals"]:
        if signal["impact"] == "NEGATIVE" and signal["type"] in ["MONETARY", "INFLATION", "YIELD_CURVE"]:
            report["alerts"].append({
                "level": "HIGH",
                "type": signal["type"],
                "message": signal["message"],
            })
    
    # Sector implications
    if fed["stance"] == "RESTRICTIVE":
        report["sector_implications"] = {
            "technology": "NEGATIVE — High rates hurt growth valuations",
            "financials": "POSITIVE — Banks benefit from high rates",
            "realestate": "NEGATIVE — Mortgage rates elevated",
            "utilities": "NEGATIVE — Bond proxies under pressure",
            "energy": "NEUTRAL — Oil prices matter more",
        }
    
    # Save
    with open(SCRIPTS_DIR / "vox_macro_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    with open(DASHBOARD_DIR / "vox_macro_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    return report

def main():
    print("="*60)
    print("🌍 VOX MACRO ANALYST")
    print("="*60)
    
    report = generate_macro_report()
    
    print(f"\nMacro Score: {report['macro_score']}")
    print(f"Macro Regime: {report['macro_regime']}")
    print(f"\nFed: {report['fed']['stance']} at {report['fed']['fed_funds_rate']}%")
    print(f"CPI: {report['inflation']['cpi_yoy']}% (target: {report['inflation']['target']}%)")
    print(f"Unemployment: {report['employment']['unemployment_rate']}%")
    print(f"10Y Yield: {report['yields']['ten_year']}%")
    print(f"Yield Curve: {report['yields']['curve']}")
    print(f"DXY: {report['dollar']['dxy']}")
    
    print(f"\nSignals ({len(report['signals'])}):")
    for sig in report['signals']:
        emoji = "🟢" if sig['impact'] == "POSITIVE" else "🔴"
        print(f"  {emoji} [{sig['type']}] {sig['signal']}: {sig['message']}")
    
    if report['alerts']:
        print(f"\n🚨 Alerts: {len(report['alerts'])}")
        for alert in report['alerts']:
            print(f"  [{alert['level']}] {alert['message']}")
    
    print(f"\n✅ Saved to vox_macro_report.json")

if __name__ == "__main__":
    main()
