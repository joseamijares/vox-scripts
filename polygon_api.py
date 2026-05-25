#!/usr/bin/env python3
"""Polygon.io API client - simple wrapper for Hermes agent."""
import os, sys, json, urllib.request

API_KEY = os.environ.get("POLYGON_API_KEY", "pr8kk0jyBvNjZlja3Ln58uTwGVbJqotG")
BASE = "https://api.polygon.io"

def fetch(path, params=None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "quote":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
        print(json.dumps(fetch(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"), indent=2))
    elif cmd == "agg":
        ticker, mult, timespan, from_date, to_date = sys.argv[2:7]
        print(json.dumps(fetch(f"/v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from_date}/{to_date}", {"adjusted":"true"}), indent=2))
    elif cmd == "daily":
        date = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
        print(json.dumps(fetch(f"/v2/aggs/grouped/locale/us/market/stocks/{date}"), indent=2))
    elif cmd == "ticker":
        print(json.dumps(fetch(f"/v3/reference/tickers/{sys.argv[2]}"), indent=2))
    else:
        print("Usage: polygon.py quote <ticker> | agg <ticker> <mult> <timespan> <from> <to> | ticker <ticker>")
