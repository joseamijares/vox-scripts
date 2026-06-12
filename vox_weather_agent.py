#!/usr/bin/env python3
"""
VOX Weather & Agriculture Agent
Monitors: US drought, extreme weather, crop-growing regions
Impacts: Agricultural stocks (ADM, DE, MOS, NTR), food prices, energy demand
Free data: OpenWeatherMap (current + 5-day forecast)
"""

import json, urllib.request
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Key agricultural regions (lat, lon) + major cities for weather
AG_REGIONS = {
    "US Corn Belt (IA)": (42.0, -93.6),
    "US Corn Belt (IL)": (40.1, -89.4),
    "US Wheat Belt (KS)": (38.0, -97.0),
    "US Wheat Belt (ND)": (47.5, -100.5),
    "US Soy Belt (MN)": (45.0, -93.2),
    "Brazil Soy (Mato Grosso)": (-13.0, -55.9),
    "Argentina Soy (Buenos Aires)": (-34.6, -58.4),
    "Ukraine Wheat (Kyiv)": (50.4, 30.5),
    "India Rice (Punjab)": (31.1, 75.3),
    "Gulf Coast (Houston)": (29.8, -95.4),  # Hurricane risk
}

# Portfolio tickers sensitive to weather
WEATHER_SENSITIVE = {
    "DE": "equipment", "ADM": "grain", "MOS": "fertilizer", "NTR": "fertilizer",
    "CF": "fertilizer", "BG": "grain", "CTVA": "seeds", "AGCO": "equipment",
    "XOM": "energy_demand", "CVX": "energy_demand", "NG": "natgas_heating",
    "UNG": "natgas", "D": "utility", "NEE": "utility"
}

DROUGHT_THRESHOLDS = {
    "extreme_heat": 35,  # °C
    "frost_risk": 0,     # °C
    "drought_rain": 5,   # mm in 5 days = dry
    "flood_rain": 50,    # mm in 5 days = wet
}

def fetch_weather(lat, lon):
    """Fetch 5-day forecast from OpenWeatherMap (free tier, no key needed for some endpoints)."""
    # Using Open-Meteo — completely free, no API key
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto&forecast_days=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def analyze_weather_risk(region_name, data):
    """Analyze weather data for agricultural risk."""
    if "error" in data or "daily" not in data:
        return None
    
    daily = data["daily"]
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    
    risks = []
    
    # Check extreme heat
    if max_temps and max(max_temps) >= DROUGHT_THRESHOLDS["extreme_heat"]:
        risks.append({
            "type": "EXTREME_HEAT",
            "severity": max(max_temps),
            "days": sum(1 for t in max_temps if t >= DROUGHT_THRESHOLDS["extreme_heat"]),
            "impact": "Crop stress, lower yields, higher irrigation demand"
        })
    
    # Check frost risk
    if min_temps and min(min_temps) <= DROUGHT_THRESHOLDS["frost_risk"]:
        risks.append({
            "type": "FROST_RISK",
            "severity": min(min_temps),
            "days": sum(1 for t in min_temps if t <= DROUGHT_THRESHOLDS["frost_risk"]),
            "impact": "Crop damage, planting delays"
        })
    
    # Check drought
    total_rain = sum(precip) if precip else 0
    if total_rain <= DROUGHT_THRESHOLDS["drought_rain"]:
        risks.append({
            "type": "DROUGHT",
            "severity": total_rain,
            "impact": "Low soil moisture, yield reduction risk"
        })
    
    # Check flood
    if total_rain >= DROUGHT_THRESHOLDS["flood_rain"]:
        risks.append({
            "type": "FLOOD_RISK",
            "severity": total_rain,
            "impact": "Field flooding, planting delays, crop loss"
        })
    
    return risks if risks else None

def run_weather_agent():
    """Main weather tracking loop."""
    all_risks = []
    
    for region, (lat, lon) in AG_REGIONS.items():
        data = fetch_weather(lat, lon)
        risks = analyze_weather_risk(region, data)
        if risks:
            all_risks.append({"region": region, "risks": risks})
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regions_checked": len(AG_REGIONS),
        "regions_at_risk": len(all_risks),
        "risks": all_risks,
        "affected_tickers": list(WEATHER_SENSITIVE.keys())
    }
    
    with open(SCRIPT_DIR / "vox_weather_analysis.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Only print if there are risks
    if all_risks:
        print(f"🌡️ WEATHER ALERT — {len(all_risks)} regions at risk")
        for item in all_risks:
            for risk in item["risks"]:
                emoji = "🔥" if risk["type"] == "EXTREME_HEAT" else "❄️" if risk["type"] == "FROST_RISK" else "🌵" if risk["type"] == "DROUGHT" else "🌊"
                print(f"   {emoji} {item['region']}: {risk['type']} ({risk.get('severity', 'N/A')})")
    
    return output

if __name__ == "__main__":
    run_weather_agent()
