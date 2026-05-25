#!/usr/bin/env python3
"""
Binance API Wrapper for Portfolio Tracking
Fetches spot + simple earn (flexible + locked) and correctly prices all assets.
"""

import os, sys, json, time, hashlib, hmac
from pathlib import Path


def load_env():
    """Load API keys from ~/.hermes/.env or ~/.env"""
    for p in [Path.home() / ".hermes" / ".env", Path.home() / ".env"]:
        if p.exists():
            keys = {}
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        keys[key] = val.strip('"').strip("'")
            return keys
    return {}


def resolve_price(asset, prices):
    """Resolve USD price for any asset."""
    if asset.startswith("LD"):
        asset = asset[2:]
    if asset in ("USDT", "FDUSD", "BUSD", "USDC", "TUSD", "DAI", "USD1", "USDS",
                 "USDE", "EURI", "AEUR", "RLUSD", "XUSD", "BFUSD"):
        return 1.0
    if asset in ("BETH", "WBETH"):
        return prices.get("ETH", 0)
    if asset == "WBTC":
        return prices.get("BTC", 0)
    if asset.startswith("1000"):
        base = asset[4:]
        return prices.get(base, 0) / 1000.0
    if asset in prices:
        return prices[asset]
    return 0


def fetch_binance_portfolio():
    """Fetch all Binance wallets: Spot + Flexible Earn + Locked Earn."""
    try:
        from binance.client import Client
    except ImportError:
        print("❌ python-binance not installed. Run: pip3 install python-binance")
        sys.exit(1)

    env = load_env()
    api_key = env.get("BINANCE_API_KEY")
    api_secret = env.get("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        print("❌ BINANCE_API_KEY or BINANCE_API_SECRET not found")
        sys.exit(1)

    client = Client(api_key, api_secret)
    BASE = "https://api.binance.com"

    # ---- 1. Get prices ----
    prices = {}
    for t in client.get_symbol_ticker():
        s = t["symbol"]
        if s.endswith("USDT"):
            prices[s.replace("USDT", "")] = float(t["price"])
    print(f"📊 Loaded {len(prices)} prices")

    # ---- 2. Spot account (includes LD* flexible earn tokens) ----
    account = client.get_account()
    spot = {}
    for b in account["balances"]:
        free = float(b["free"])
        locked = float(b["locked"])
        total = free + locked
        if total > 0:
            spot[b["asset"]] = total

    # ---- 3. Simple Earn Flexible via API (some newer positions) ----
    def signed_get(endpoint, params=None):
        if params is None:
            params = {}
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{BASE}{endpoint}?{query}&signature={sig}"
        import requests
        r = requests.get(url, headers={"X-MBX-APIKEY": api_key})
        return r.json()

    flex_earn = {}
    try:
        resp = signed_get("/sapi/v1/simple-earn/flexible/position")
        for row in resp.get("rows", []):
            asset = row["asset"]
            amt = float(row.get("totalAmount", 0))
            if amt > 0:
                flex_earn[asset] = flex_earn.get(asset, 0) + amt
    except Exception as e:
        print(f"⚠️ Flexible earn error: {e}")

    # ---- 4. Simple Earn Locked via API ----
    locked_earn = {}
    try:
        resp = signed_get("/sapi/v1/simple-earn/locked/position")
        for row in resp.get("rows", []):
            asset = row.get("asset", "")
            amt = 0
            for field in ["amount", "totalAmount", "rewards", "principal"]:
                if field in row and row[field] is not None:
                    try:
                        amt = float(row[field])
                        break
                    except:
                        pass
            if amt > 0:
                locked_earn[asset] = locked_earn.get(asset, 0) + amt
    except Exception as e:
        print(f"⚠️ Locked earn error: {e}")

    # ---- 5. Merge all three wallets ----
    # Strategy: sum all sources. An asset can exist in spot, flex, locked.
    all_assets = {}

    def add(source, asset, qty):
        if qty <= 0:
            return
        if asset not in all_assets:
            all_assets[asset] = {"total": 0.0, "sources": []}
        all_assets[asset]["total"] += qty
        all_assets[asset]["sources"].append((source, qty))

    # Spot (non-LD = actual spot; LD* = old flexible earn)
    for asset, qty in spot.items():
        if asset.startswith("LD"):
            real = asset[2:]
            add("SpotEarn(LD)", real, qty)
        else:
            add("Spot", asset, qty)

    for asset, qty in flex_earn.items():
        add("FlexEarn", asset, qty)

    for asset, qty in locked_earn.items():
        add("LockedEarn", asset, qty)

    # ---- 6. Build output ----
    total_usd = 0.0
    balances = []
    for asset, data in all_assets.items():
        qty = data["total"]
        price = resolve_price(asset, prices)
        value = qty * price
        total_usd += value
        balances.append({
            "asset": asset,
            "total": qty,
            "price_usd": price,
            "value_usd": value,
            "sources": data["sources"]
        })

    balances.sort(key=lambda x: x["value_usd"], reverse=True)

    # ---- 7. Print ----
    print("\n" + "="*80)
    print("📊 BINANCE PORTFOLIO (Spot + Flexible Earn + Locked Earn)")
    print("="*80)
    print(f"\n💰 TOTAL: ${total_usd:,.2f} USD")
    print(f"📋 Assets: {len(balances)}")

    # Top holdings
    top = [b for b in balances if b["value_usd"] > 1]
    if top:
        print(f"\n📈 TOP HOLDINGS:")
        print("-" * 80)
        print(f"{'Asset':10} | {'Qty':>18} | {'Price':>14} | {'Value USD':>14} | {'Sources'}")
        print("-" * 80)
        for b in top[:15]:
            srcs = ", ".join(f"{s}:{q:.3f}" for s, q in b["sources"])
            print(f"{b['asset']:10} | {b['total']:18.6f} | ${b['price_usd']:>12.4f} | ${b['value_usd']:>12.2f} | {srcs}")

    # Unpriced assets
    dust = [b for b in balances if b["price_usd"] == 0 and b["total"] > 0.01]
    if dust:
        dust_val = sum(b["total"] for b in dust)  # qty only, no price
        print(f"\n⚠️  UNPRICED ASSETS: {len(dust)} assets (no USDT pair yet)")

    print("\n" + "="*80)

    # ---- 8. Save ----
    output = Path.home() / ".hermes" / "scripts" / "binance_portfolio.json"
    with open(output, "w") as f:
        json.dump({
            "balances": [{"asset": b["asset"], "total": b["total"],
                          "price_usd": b["price_usd"], "value_usd": b["value_usd"]}
                         for b in balances],
            "total_usd": total_usd,
            "prices": prices
        }, f, indent=2)
    print(f"💾 Saved to: {output}")
    return balances, total_usd, prices


if __name__ == "__main__":
    fetch_binance_portfolio()
