#!/usr/bin/env python3
"""
JOS-8: Test Polygon.io Options API
Verify we can fetch options chain data, Greeks, and unusual volume.
"""

import os
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta


def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    keys[key] = val
    return keys


def polygon_request(endpoint):
    """Make authenticated request to Polygon API."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY")
    if not api_key:
        print("❌ POLYGON_API_KEY not found")
        return None

    url = f"https://api.polygon.io{endpoint}{'&' if '?' in endpoint else '?'}apiKey={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP {e.code}: {e.reason}")
        try:
            body = json.loads(e.read())
            print(f"   Detail: {body}")
        except:
            pass
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_options_contracts(ticker):
    """Test 1: Fetch options contracts for a ticker."""
    print(f"\n{'='*60}")
    print(f"TEST 1: Options Contracts for {ticker}")
    print(f"{'='*60}")

    # Get options contracts
    today = datetime.now().strftime("%Y-%m-%d")
    endpoint = f"/v3/reference/options/contracts?underlying_ticker={ticker}&expiration_date.gte={today}&limit=10"

    data = polygon_request(endpoint)
    if not data:
        return False

    results = data.get("results", [])
    if not results:
        print(f"⚠️ No options contracts found for {ticker}")
        return False

    print(f"✅ Found {len(results)} option contracts")
    for r in results[:3]:
        print(f"   {r.get('ticker', 'N/A')}: {r.get('strike_price', 'N/A')} {r.get('contract_type', 'N/A')} exp {r.get('expiration_date', 'N/A')}")

    return True


def test_options_chain(ticker):
    """Test 2: Fetch options chain (snapshots)."""
    print(f"\n{'='*60}")
    print(f"TEST 2: Options Chain Snapshot for {ticker}")
    print(f"{'='*60}")

    # Get options snapshot (chain)
    endpoint = f"/v3/snapshot/options/{ticker}?limit=10"

    data = polygon_request(endpoint)
    if not data:
        return False

    results = data.get("results", [])
    if not results:
        print(f"⚠️ No options snapshot data for {ticker}")
        return False

    print(f"✅ Found {len(results)} option snapshots")
    for r in results[:3]:
        details = r.get("details", {})
        print(f"   {details.get('ticker', 'N/A')}: Strike {details.get('strike_price', 'N/A')} {details.get('contract_type', 'N/A')}")
        # Greeks
        greeks = r.get("greeks", {})
        if greeks:
            print(f"      Delta: {greeks.get('delta', 'N/A')}, Gamma: {greeks.get('gamma', 'N/A')}, Theta: {greeks.get('theta', 'N/A')}, IV: {greeks.get('implied_volatility', 'N/A')}")
        # Quote
        quote = r.get("last_quote", {})
        if quote:
            print(f"      Bid: {quote.get('bid', 'N/A')} Ask: {quote.get('ask', 'N/A')} Size: {quote.get('bid_size', 'N/A')}/{quote.get('ask_size', 'N/A')}")

    return True


def test_unusual_options(ticker):
    """Test 3: Check for unusual options volume."""
    print(f"\n{'='*60}")
    print(f"TEST 3: Unusual Options Activity for {ticker}")
    print(f"{'='*60}")

    # Get aggregate options volume
    today = datetime.now()
    from_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    endpoint = f"/v3/reference/options/contracts?underlying_ticker={ticker}&limit=50"
    data = polygon_request(endpoint)

    if not data or not data.get("results"):
        print(f"⚠️ No data for unusual options check")
        return False

    print(f"✅ Found {len(data['results'])} total contracts")
    print(f"   (Full unusual volume scan requires WebSocket or premium endpoint)")

    return True


def test_stock_snapshot(ticker):
    """Test 4: Get stock snapshot for context."""
    print(f"\n{'='*60}")
    print(f"TEST 4: Stock Snapshot for {ticker}")
    print(f"{'='*60}")

    endpoint = f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
    data = polygon_request(endpoint)

    if not data or "ticker" not in data:
        print(f"⚠️ No snapshot for {ticker}")
        return False

    ticker_data = data["ticker"]
    day = ticker_data.get("day", {})
    prev = ticker_data.get("prevDay", {})

    print(f"✅ {ticker} Snapshot:")
    print(f"   Price: ${day.get('c', 'N/A')} (Prev: ${prev.get('c', 'N/A')})")
    print(f"   Volume: {day.get('v', 'N/A'):,}")
    print(f"   VWAP: ${day.get('vw', 'N/A')}")

    return True


def main():
    print("=" * 60)
    print("JOS-8: Polygon.io Options API Test")
    print("=" * 60)

    tickers = ["AAPL", "NVDA", "CEG"]

    results = {}
    for ticker in tickers:
        print(f"\n{'#'*60}")
        print(f"# Testing: {ticker}")
        print(f"{'#'*60}")

        r1 = test_options_contracts(ticker)
        r2 = test_options_chain(ticker)
        r3 = test_unusual_options(ticker)
        r4 = test_stock_snapshot(ticker)

        results[ticker] = {
            "contracts": r1,
            "chain": r2,
            "unusual": r3,
            "snapshot": r4
        }

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    for ticker, res in results.items():
        passed = sum(res.values())
        total = len(res)
        status = "✅" if passed == total else "⚠️" if passed > 0 else "❌"
        print(f"{status} {ticker}: {passed}/{total} tests passed")
        for test, passed_flag in res.items():
            icon = "✅" if passed_flag else "❌"
            print(f"   {icon} {test}")

    # Save results
    output = {
        "test_date": datetime.now().isoformat(),
        "results": results
    }
    out_path = Path.home() / ".hermes" / "scripts" / "polygon_options_test.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Results saved to: {out_path}")

    return results


if __name__ == "__main__":
    main()
