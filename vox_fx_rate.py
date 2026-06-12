#!/usr/bin/env python3
"""
VOX FX Rate Fetcher
Gets USD/MXN rate from Polygon.io or fallback
"""

import json
import urllib.request
from pathlib import Path

def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v.strip('"').strip("'")
    return keys

def get_usd_mxn_rate():
    """Fetch USD/MXN rate from Polygon or use cached."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    
    # Try Polygon first
    if api_key:
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/C:USDMXN/prev?apiKey={api_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                results = data.get("results", [])
                if results:
                    rate = results[0].get("c", 0)
                    if rate > 0:
                        return {
                            "rate": rate,
                            "source": "polygon",
                            "timestamp": data.get("results", [{}])[0].get("t", "")
                        }
        except Exception as e:
            print(f"Polygon FX failed: {e}")
    
    # Fallback: hardcoded recent rate
    return {
        "rate": 17.31,
        "source": "fallback",
        "timestamp": ""
    }

if __name__ == "__main__":
    rate_data = get_usd_mxn_rate()
    print(f"USD/MXN: {rate_data['rate']} (source: {rate_data['source']})")
