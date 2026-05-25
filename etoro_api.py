#!/usr/bin/env python3
"""
eToro API Wrapper for Portfolio Tracking
Fetches real account portfolio, positions, PnL, and mirrors.
"""

import os
import sys
import json
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime


def load_env():
    """Load API keys from ~/.hermes/.env"""
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


def etoro_request(endpoint: str, env: dict) -> dict:
    """Make authenticated request to eToro public API."""
    api_key = env.get("ETORO_API_KEY")
    user_key = env.get("ETORO_USER_KEY")

    if not api_key or not user_key:
        print("❌ ETORO_API_KEY or ETORO_USER_KEY not found in ~/.hermes/.env")
        sys.exit(1)

    url = f"https://public-api.etoro.com/api/v1{endpoint}"
    request_id = str(uuid.uuid4())

    req = urllib.request.Request(url)
    req.add_header("x-api-key", api_key)
    req.add_header("x-user-key", user_key)
    req.add_header("x-request-id", request_id)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
    req.add_header("Origin", "https://etoro.com")
    req.add_header("Referer", "https://etoro.com/")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        try:
            body = json.loads(e.read().decode("utf-8"))
            print(json.dumps(body, indent=2))
        except:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def fetch_portfolio(env: dict) -> dict:
    """Fetch real account portfolio with PnL."""
    return etoro_request("/trading/info/real/pnl", env)


def fetch_identity(env: dict) -> dict:
    """Fetch authenticated user identity."""
    return etoro_request("/identity", env)


def fetch_instruments(env: dict, instrument_ids: list) -> dict:
    """Fetch instrument metadata to map IDs to names."""
    if not instrument_ids:
        return {}

    ids_str = ",".join(map(str, instrument_ids))
    data = etoro_request(f"/market-data/instruments?instrumentIds={ids_str}", env)

    mapping = {}
    for inst in data.get("instrumentDisplayDatas", []):
        iid = inst.get("instrumentID")
        mapping[iid] = {
            "name": inst.get("instrumentDisplayName", "Unknown"),
            "symbol": inst.get("symbolFull", "?"),
            "type": inst.get("instrumentTypeID", 0)
        }
    return mapping


def format_portfolio(data: dict, env: dict):
    """Pretty-print portfolio summary with instrument names and correct totals."""
    cp = data.get("clientPortfolio", {})

    print("=" * 75)
    print("📊 eTORO PORTFOLIO SUMMARY")
    print("=" * 75)

    # Calculate correct totals
    positions = cp.get("positions", [])
    mirrors = cp.get("mirrors", [])

    # Direct positions
    direct_exposure = sum(p.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0) for p in positions)
    direct_pnl = sum(p.get("unrealizedPnL", {}).get("pnL", 0) for p in positions)
    direct_initial = sum(p.get("initialAmountInDollars", 0) for p in positions)

    # Mirror positions
    mirror_exposure = 0
    mirror_pnl = 0
    mirror_initial = 0
    for m in mirrors:
        for p in m.get("positions", []):
            mirror_exposure += p.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0)
            mirror_pnl += p.get("unrealizedPnL", {}).get("pnL", 0)
            mirror_initial += p.get("initialAmountInDollars", 0)

    mirror_available = sum(m.get("availableAmount", 0) for m in mirrors)
    mirror_closed_pnl = sum(m.get("closedPositionsNetProfit", 0) for m in mirrors)
    mirror_investment = sum(m.get("initialInvestment", 0) for m in mirrors)

    cash = cp.get("credit", 0)
    total_value = direct_exposure + mirror_exposure + mirror_available + cash
    total_pnl = direct_pnl + mirror_pnl
    total_initial = direct_initial + mirror_initial

    print(f"\n💰 TOTAL PORTFOLIO VALUE:  ${total_value:,.2f}")
    print(f"📈 Total Unrealized PnL:   ${total_pnl:,.2f}")
    print(f"💵 Total Invested:         ${total_initial:,.2f}")
    print(f"🏦 Cash Available:         ${cash + mirror_available:,.2f}")

    print(f"\n📋 Direct Positions: {len(positions)} | Value: ${direct_exposure:,.2f} | PnL: ${direct_pnl:,.2f}")

    if positions:
        instrument_ids = sorted(set(p.get("instrumentID") for p in positions if p.get("instrumentID")))
        print(f"   Fetching {len(instrument_ids)} instrument names...")
        inst_map = fetch_instruments(env, instrument_ids)

        print("-" * 75)
        print(f"{'Type':5} | {'Symbol':10} | {'Name':22} | {'Exposure':>12} | {'PnL':>12}")
        print("-" * 75)

        def position_value(pos):
            return pos.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0)

        sorted_positions = sorted(positions, key=position_value, reverse=True)

        for pos in sorted_positions[:15]:
            iid = pos.get("instrumentID", 0)
            info = inst_map.get(iid, {"name": f"ID:{iid}", "symbol": "?"})
            is_buy = "BUY" if pos.get("isBuy") else "SELL"
            pnl_data = pos.get("unrealizedPnL", {})
            exposure = pnl_data.get("exposureInAccountCurrency", 0)
            pnl = pnl_data.get("pnL", 0)
            symbol = info.get("symbol", "?")
            name = info.get("name", "?")[:22]

            print(f"{is_buy:5} | {symbol:10} | {name:22} | ${exposure:>10,.2f} | ${pnl:>10,.2f}")

        if len(positions) > 15:
            print(f"\n   ... and {len(positions) - 15} more positions")

    # Mirrors
    print(f"\n🪞 Copy Trading Mirrors: {len(mirrors)} | Value: ${mirror_exposure:,.2f} | PnL: ${mirror_pnl:,.2f}")

    if mirrors:
        print("-" * 75)
        for mirror in mirrors[:5]:
            parent = mirror.get("parentUsername", "Unknown")
            investment = mirror.get("initialInvestment", 0)
            available = mirror.get("availableAmount", 0)
            closed_pnl = mirror.get("closedPositionsNetProfit", 0)
            status = "PAUSED" if mirror.get("isPaused") else "ACTIVE"

            print(f"  {status:6} | {parent:20} | Allocated: ${investment:,.2f} | "
                  f"Available: ${available:,.2f} | Closed PnL: ${closed_pnl:,.2f}")

            mirror_positions = mirror.get("positions", [])
            if mirror_positions:
                print(f"         └─ {len(mirror_positions)} open positions")

    print("\n" + "=" * 75)


def main():
    env = load_env()

    print("🔑 Loading eToro credentials...")

    # Fetch portfolio directly
    print("\n📊 Fetching portfolio...")
    portfolio = fetch_portfolio(env)
    format_portfolio(portfolio, env)

    # Save enriched data with instrument names
    output_path = Path.home() / ".hermes" / "scripts" / "etoro_portfolio.json"
    
    # Fetch instrument names for all positions
    cp = portfolio.get("clientPortfolio", {})
    positions = cp.get("positions", [])
    instrument_ids = sorted(set(p.get("instrumentID") for p in positions if p.get("instrumentID")))
    inst_map = fetch_instruments(env, instrument_ids)
    
    # Add instrument names to each position before saving
    enriched_portfolio = portfolio.copy()
    enriched_cp = cp.copy()
    enriched_positions = []
    for pos in positions:
        enriched_pos = pos.copy()
        iid = pos.get("instrumentID", 0)
        info = inst_map.get(iid, {"name": f"ID:{iid}", "symbol": "?", "type": 0})
        enriched_pos["_instrumentName"] = info.get("name", "Unknown")
        enriched_pos["_instrumentSymbol"] = info.get("symbol", "?")
        enriched_positions.append(enriched_pos)
    enriched_cp["positions"] = enriched_positions
    enriched_portfolio["clientPortfolio"] = enriched_cp
    
    # Also save instrument mapping separately for easy lookup
    enriched_portfolio["_instrumentMapping"] = inst_map
    enriched_portfolio["_lastFetched"] = datetime.now().isoformat()
    
    with open(output_path, "w") as f:
        json.dump(enriched_portfolio, f, indent=2)
    print(f"\n💾 Enriched data saved to: {output_path}")
    print(f"   Includes {len(inst_map)} instrument names")


if __name__ == "__main__":
    main()
