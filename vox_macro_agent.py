#!/usr/bin/env python3
"""
VOX Macro Analysis Agent
Monitors: Fed policy, interest rates, VIX, USD, global events, yield curve
Generates: Macro regime signal (risk-on/risk-off/neutral)
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v
    return keys

def fetch_polygon(path: str) -> dict:
    """Fetch from Polygon.io API."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {}
    
    url = f"https://api.polygon.io/v2/{path}?apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"Polygon error: {e}")
        return {}

def get_vix() -> dict:
    """Get VIX level and change."""
    data = fetch_polygon("aggs/ticker/I:VIX/prev")
    if data.get("results"):
        r = data["results"][0]
        return {
            "level": r.get("c", 0),
            "change_pct": ((r.get("c", 0) - r.get("o", 0)) / r.get("o", 1)) * 100 if r.get("o") else 0
        }
    return {"level": 0, "change_pct": 0}

def get_10y_yield() -> dict:
    """Get 10-year Treasury yield."""
    data = fetch_polygon("aggs/ticker/I:TNX/prev")
    if data.get("results"):
        r = data["results"][0]
        return {"yield": r.get("c", 0) / 10}  # TNX is in tenths
    return {"yield": 0}

def get_dxy() -> dict:
    """Get DXY (USD index)."""
    data = fetch_polygon("aggs/ticker/I:DXY/prev")
    if data.get("results"):
        r = data["results"][0]
        return {
            "level": r.get("c", 0),
            "change_pct": ((r.get("c", 0) - r.get("o", 0)) / r.get("o", 1)) * 100 if r.get("o") else 0
        }
    return {"level": 0, "change_pct": 0}

def analyze_macro() -> dict:
    """Analyze macro conditions and return regime signal."""
    
    vix = get_vix()
    yield_10y = get_10y_yield()
    dxy = get_dxy()
    
    # Regime scoring
    risk_score = 50  # Neutral base
    
    # VIX interpretation
    if vix["level"] > 30:
        risk_score -= 30  # High fear
    elif vix["level"] > 25:
        risk_score -= 20
    elif vix["level"] > 20:
        risk_score -= 10
    elif vix["level"] < 15:
        risk_score += 15  # Complacency
    
    # Yield curve (simplified)
    if yield_10y["yield"] > 4.5:
        risk_score -= 10  # Tightening
    elif yield_10y["yield"] < 3.5:
        risk_score += 10  # Easy money
    
    # USD strength
    if dxy["level"] > 105:
        risk_score -= 10  # Strong USD hurts emerging markets
    elif dxy["level"] < 100:
        risk_score += 5
    
    # Determine regime
    if risk_score >= 60:
        regime = "RISK_ON"
        emoji = "🟢"
    elif risk_score <= 40:
        regime = "RISK_OFF"
        emoji = "🔴"
    else:
        regime = "NEUTRAL"
        emoji = "⚪"
    
    analysis = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "risk_score": risk_score,
        "vix": vix,
        "yield_10y": yield_10y,
        "dxy": dxy,
        "implications": {
            "RISK_ON": "Favor growth, tech, crypto, international",
            "RISK_OFF": "Favor cash, bonds, defensive, USD",
            "NEUTRAL": "Balanced approach, stock-picking matters"
        }[regime]
    }
    
    # Save
    output_file = SCRIPT_DIR / "vox_macro_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    # Only print if regime is not neutral or VIX is elevated
    if regime != "NEUTRAL" or vix["level"] > 25:
        print(f"{emoji} Macro: {regime} | VIX {vix['level']:.1f} | 10Y {yield_10y['yield']:.2f}%")
    
    return analysis

if __name__ == "__main__":
    analyze_macro()
