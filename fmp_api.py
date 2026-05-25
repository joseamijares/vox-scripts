#!/usr/bin/env python3
"""Financial Modeling Prep API client - simple wrapper for Hermes agent."""
import os, sys, json, urllib.request

API_KEY = os.environ.get("FMP_API_KEY", "")
BASE = "https://financialmodelingprep.com/api/v3"

def fetch(path, params=None):
    url = f"{BASE}{path}?apikey={API_KEY}"
    if params:
        url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "profile":
        print(json.dumps(fetch(f"/profile/{sys.argv[2]}"), indent=2))
    elif cmd == "quote":
        print(json.dumps(fetch(f"/quote/{sys.argv[2]}"), indent=2))
    elif cmd == "income":
        print(json.dumps(fetch(f"/income-statement/{sys.argv[2]}"), indent=2))
    elif cmd == "balance":
        print(json.dumps(fetch(f"/balance-sheet-statement/{sys.argv[2]}"), indent=2))
    elif cmd == "ratios":
        print(json.dumps(fetch(f"/ratios-ttm/{sys.argv[2]}"), indent=2))
    else:
        print("Usage: fmp.py quote|profile|income|balance|ratios <ticker>")
