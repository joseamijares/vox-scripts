#!/usr/bin/env python3
"""
VOX Macro Factors Monitor
Tracks key macroeconomic indicators and factors them into trade suggestions.
Run daily before market open.
"""

import os
import json
from datetime import datetime

# Load API keys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_macro_summary():
    """Generate macro factor summary for trade suggestions."""
    
    # These would normally come from APIs (FRED, Bloomberg, etc.)
    # For now, using placeholder structure that gets updated manually or via cron
    
    macro = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "federal_reserve": {
            "fed_funds_rate": 5.25,
            "last_change": "hold",
            "next_meeting": "2026-06-18",
            "market_implied_cuts_2026": 2,
            "bias": "neutral",  # hawkish/dovish/neutral
            "impact": "Rates stable. Financials benefit. Growth stocks neutral."
        },
        "inflation": {
            "cpi_yoy": 3.2,
            "core_cpi_yoy": 3.8,
            "trend": "cooling",  # rising/cooling/stable
            "impact": "Inflation cooling but sticky. Real assets (BTC, gold) attractive."
        },
        "employment": {
            "unemployment_rate": 3.9,
            "nfp_last": 185000,
            "trend": "stable",
            "impact": "Labor market resilient. Consumer spending supported."
        },
        "gdp": {
            "q1_2026": 2.1,
            "q2_2026_est": 2.3,
            "trend": "stable",
            "impact": "Soft landing likely. Recession risk low."
        },
        "yield_curve": {
            "10y_2y_spread": -0.35,
            "inverted": True,
            "days_inverted": 180,
            "impact": "Still inverted but steepening. Banks (JPM, BAC) benefit when un-inverts."
        },
        "dollar": {
            "dxy": 104.5,
            "trend": "stable",  # strengthening/weakening/stable
            "impact": "USD stable. EM (INDA, EWZ, FXI) neutral."
        },
        "vix": {
            "current": 14.2,
            "trend": "low",  # low/moderate/high
            "impact": "Low volatility. Good for selling options, buying dips."
        },
        "credit_spreads": {
            "hy_oj_spread": 320,
            "trend": "tight",  # tight/widening
            "impact": "Credit markets healthy. Risk-on environment."
        },
        "commodities": {
            "oil_wti": 78.50,
            "gold": 2350,
            "copper": 4.85,
            "impact": "Oil stable. Gold elevated (inflation hedge). Copper strong (AI infrastructure)."
        },
        "geopolitical": {
            "risk_level": "moderate",  # low/moderate/high
            "hotspots": ["Ukraine", "Middle East", "Taiwan"],
            "impact": "Moderate risk. Defense stocks (LMT, NOC) supported. Energy volatile."
        },
        "ai_cycle": {
            "phase": "infrastructure",  # early/infrastructure/maturity
            "capex_growth": 45,
            "impact": "AI infrastructure build-out continues. NVDA, AMAT, ANET, COHR benefit."
        }
    }
    
    return macro

def generate_trade_bias(macro):
    """Generate trade bias based on macro factors."""
    
    biases = []
    
    # Fed policy
    if macro["federal_reserve"]["bias"] == "dovish":
        biases.append("🟢 GROWTH BIAS: Fed cutting rates. Favor tech, growth, crypto.")
    elif macro["federal_reserve"]["bias"] == "hawkish":
        biases.append("🔴 VALUE BIAS: Fed hiking. Favor financials, staples, cash.")
    else:
        biases.append("🟡 NEUTRAL: Fed on hold. Balanced approach. Quality over speculation.")
    
    # Inflation
    if macro["inflation"]["trend"] == "cooling":
        biases.append("🟢 DISINFLATION: Real assets less urgent. Growth stocks attractive.")
    elif macro["inflation"]["trend"] == "rising":
        biases.append("🔴 INFLATION: Favor commodities, energy, BTC, TIPS.")
    
    # Yield curve
    if macro["yield_curve"]["inverted"] and macro["yield_curve"]["days_inverted"] > 90:
        biases.append("⚠️ RECESSION WATCH: Yield curve inverted 180+ days. Defensive positioning.")
    elif not macro["yield_curve"]["inverted"]:
        biases.append("🟢 STEEPENING: Banks benefit. Add JPM, BAC, XLF.")
    
    # Dollar
    if macro["dollar"]["trend"] == "strengthening":
        biases.append("🔴 STRONG DOLLAR: Avoid EM (INDA, EWZ, FXI). Favor US domestic.")
    elif macro["dollar"]["trend"] == "weakening":
        biases.append("🟢 WEAK DOLLAR: EM attractive. Commodities rally.")
    
    # VIX
    if macro["vix"]["trend"] == "low":
        biases.append("🟢 LOW VOL: Sell options for income. Buy dips aggressively.")
    elif macro["vix"]["trend"] == "high":
        biases.append("🔴 HIGH VOL: Reduce size. Raise cash. Wait for clarity.")
    
    # AI cycle
    if macro["ai_cycle"]["phase"] == "infrastructure":
        biases.append("🟢 AI INFRA: NVDA, AMAT, ANET, COHR, DELL in sweet spot.")
    elif macro["ai_cycle"]["phase"] == "maturity":
        biases.append("🟡 AI MATURITY: Rotate to AI applications. Trim infrastructure.")
    
    # Geopolitical
    if macro["geopolitical"]["risk_level"] == "high":
        biases.append("🔴 HIGH GEOPOLITICAL: Favor defense, energy, gold, USD.")
    
    return biases

def sector_bias(macro):
    """Generate sector-specific biases."""
    
    sectors = {
        "technology": {"bias": "neutral", "confidence": 60},
        "financials": {"bias": "bullish", "confidence": 75},
        "healthcare": {"bias": "neutral", "confidence": 55},
        "energy": {"bias": "bullish", "confidence": 70},
        "consumer": {"bias": "neutral", "confidence": 50},
        "utilities": {"bias": "neutral", "confidence": 55},
        "reits": {"bias": "bearish", "confidence": 65},
        "crypto": {"bias": "neutral", "confidence": 60},
        "emerging_markets": {"bias": "bearish", "confidence": 70}
    }
    
    # Adjust based on macro
    if macro["federal_reserve"]["bias"] == "dovish":
        sectors["technology"]["bias"] = "bullish"
        sectors["technology"]["confidence"] = 75
        sectors["crypto"]["bias"] = "bullish"
        sectors["crypto"]["confidence"] = 70
    
    if macro["yield_curve"]["inverted"]:
        sectors["financials"]["bias"] = "neutral"
        sectors["financials"]["confidence"] = 55
    
    if macro["inflation"]["trend"] == "rising":
        sectors["energy"]["bias"] = "bullish"
        sectors["energy"]["confidence"] = 80
        sectors["reits"]["bias"] = "bearish"
        sectors["reits"]["confidence"] = 75
    
    if macro["dollar"]["trend"] == "strengthening":
        sectors["emerging_markets"]["bias"] = "bearish"
        sectors["emerging_markets"]["confidence"] = 80
    
    if macro["ai_cycle"]["phase"] == "infrastructure":
        sectors["technology"]["bias"] = "bullish"
        sectors["technology"]["confidence"] = 80
    
    return sectors

def save_macro_data(macro, biases, sectors):
    """Save macro data for reference."""
    
    data = {
        "macro": macro,
        "biases": biases,
        "sectors": sectors,
        "updated": datetime.now().isoformat()
    }
    
    output_dir = os.path.expanduser("~/.hermes/scripts")
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/vox_macro_data.json", "w") as f:
        json.dump(data, f, indent=2)
    
    return f"{output_dir}/vox_macro_data.json"

def main():
    """Main function."""
    
    print("=" * 60)
    print("VOX MACRO FACTORS MONITOR")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # Get macro data
    macro = get_macro_summary()
    
    print("\n📊 KEY MACRO INDICATORS")
    print("-" * 40)
    print(f"Fed Funds Rate: {macro['federal_reserve']['fed_funds_rate']}%")
    print(f"CPI YoY: {macro['inflation']['cpi_yoy']}%")
    print(f"Unemployment: {macro['employment']['unemployment_rate']}%")
    print(f"GDP Q1: {macro['gdp']['q1_2026']}%")
    print(f"10Y-2Y Spread: {macro['yield_curve']['10y_2y_spread']}%")
    print(f"DXY: {macro['dollar']['dxy']}")
    print(f"VIX: {macro['vix']['current']}")
    print(f"Oil (WTI): ${macro['commodities']['oil_wti']}")
    
    # Generate biases
    biases = generate_trade_bias(macro)
    
    print("\n🎯 TRADE BIASES")
    print("-" * 40)
    for bias in biases:
        print(bias)
    
    # Sector biases
    sectors = sector_bias(macro)
    
    print("\n📈 SECTOR BIASES")
    print("-" * 40)
    for sector, data in sectors.items():
        emoji = "🟢" if data["bias"] == "bullish" else "🔴" if data["bias"] == "bearish" else "🟡"
        print(f"{emoji} {sector.upper()}: {data['bias'].upper()} (confidence: {data['confidence']}%)")
    
    # Save data
    filepath = save_macro_data(macro, biases, sectors)
    print(f"\n💾 Saved to: {filepath}")
    
    print("\n" + "=" * 60)
    print("Use this data to adjust trade suggestions.")
    print("Update daily before market open.")
    print("=" * 60)

if __name__ == "__main__":
    main()
