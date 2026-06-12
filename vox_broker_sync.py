#!/usr/bin/env python3
"""
VOX Broker Sync Orchestrator v1.0
Fetches portfolio data from all brokers, unifies, and saves.
Runs 2x daily: 7 AM (pre-market) and 12 PM (midday)
"""

import json
import os
import sys
import urllib.request
import subprocess
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public" / "data"

def get_fx_rate():
    """Get USD/MXN rate."""
    try:
        result = subprocess.run(
            ["python3", "vox_fx_rate.py"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        # Parse rate from output: "USD/MXN: 17.2924 (source: polygon)"
        for line in result.stdout.split("\n"):
            if "USD/MXN:" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    rate_str = parts[1].split("(")[0].strip()
                    return float(rate_str)
    except Exception as e:
        print(f"  ⚠️ FX rate fetch failed: {e}")
    return 17.31  # Fallback

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

ENV = load_env()

# ─── BROKER CONFIG ──────────────────────────────────────────────────────────

BROKERS = {
    "etoro": {
        "name": "eToro",
        "type": "api",
        "enabled": bool(ENV.get("ETORO_API_KEY")),
        "currency": "USD",
        "weight": 0.43,
    },
    "binance": {
        "name": "Binance",
        "type": "api",
        "enabled": bool(ENV.get("BINANCE_API_KEY")),
        "currency": "USD",
        "weight": 0.10,
    },
    "gbm_main": {
        "name": "GBM Plus (Main)",
        "type": "manual",
        "enabled": True,
        "currency": "MXN",
        "weight": 0.38,
    },
    "gbm_usa": {
        "name": "GBM Plus (USA)",
        "type": "manual",
        "enabled": True,
        "currency": "USD",
        "weight": 0.07,
    },
    "schwab": {
        "name": "Charles Schwab",
        "type": "manual",
        "enabled": True,
        "currency": "USD",
        "weight": 0.01,
    },
    "ibkr": {
        "name": "Interactive Brokers",
        "type": "manual",
        "enabled": True,
        "currency": "USD",
        "weight": 0.01,
    },
    "revolut": {
        "name": "Revolut",
        "type": "manual",
        "enabled": True,
        "currency": "MXN",
        "weight": 0.00,
    },
    "bitso": {
        "name": "Bitso",
        "type": "manual",
        "enabled": True,
        "currency": "USD",
        "weight": 0.00,
    },
}

# ─── FETCH FUNCTIONS ────────────────────────────────────────────────────────

def fetch_etoro():
    """Fetch eToro portfolio via API."""
    try:
        result = subprocess.run(
            ["python3", "etoro_api.py"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            print(f"  ⚠️ eToro API error: {result.stderr[:200]}")
            return None
        
        with open(SCRIPT_DIR / "etoro_portfolio.json") as f:
            data = json.load(f)
        
        cp = data.get("clientPortfolio", {})
        positions = cp.get("positions", [])
        
        # Extract positions with symbol mapping
        extracted = []
        for pos in positions:
            symbol = pos.get("_instrumentSymbol", "?")
            if symbol == "?":
                symbol = pos.get("instrumentID", "UNKNOWN")
            
            pnl_data = pos.get("unrealizedPnL", {})
            extracted.append({
                "ticker": symbol,
                "shares": pos.get("units", 0),
                "exposure": pnl_data.get("exposureInAccountCurrency", 0),
                "pnl": pnl_data.get("pnL", 0),
                "open_price": pos.get("openRate", 0),
                "current_price": pnl_data.get("closeRate", 0),
                "is_buy": pos.get("isBuy", True),
                "leverage": pos.get("leverage", 1),
            })
        
        # Aggregate by ticker
        aggregated = {}
        for pos in extracted:
            ticker = pos["ticker"]
            if ticker not in aggregated:
                aggregated[ticker] = {
                    "ticker": ticker,
                    "shares": 0,
                    "exposure": 0,
                    "pnl": 0,
                    "cost_basis": 0,
                    "broker": "eToro"
                }
            aggregated[ticker]["shares"] += pos["shares"]
            aggregated[ticker]["exposure"] += pos["exposure"]
            aggregated[ticker]["pnl"] += pos["pnl"]
        
        # Calculate avg cost (cost basis = exposure - pnl)
        for ticker, agg in aggregated.items():
            if agg["shares"] > 0:
                agg["cost_basis"] = (agg["exposure"] - agg["pnl"]) / agg["shares"]
            else:
                agg["cost_basis"] = 0
        
        mirrors = cp.get("mirrors", [])
        mirror_value = sum(m.get("initialInvestment", 0) - m.get("availableAmount", 0) for m in mirrors)
        mirror_pnl = sum(m.get("closedPositionsNetProfit", 0) for m in mirrors)
        
        # Calculate totals from positions
        total_exposure = sum(p.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0) for p in positions)
        total_pnl = sum(p.get("unrealizedPnL", {}).get("pnL", 0) for p in positions)
        
        mirrors = cp.get("mirrors", [])
        mirror_value = sum(m.get("initialInvestment", 0) - m.get("availableAmount", 0) for m in mirrors)
        mirror_pnl = sum(m.get("closedPositionsNetProfit", 0) for m in mirrors)
        
        # Cash handling - credit can be float or dict
        credit_raw = cp.get("credit", 0)
        cash = credit_raw if isinstance(credit_raw, (int, float)) else credit_raw.get("balance", 0)
        
        return {
            "broker": "etoro",
            "broker_name": "eToro",
            "status": "connected",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "currency": "USD",
            "total_value": total_exposure + mirror_value,
            "total_pnl": total_pnl + mirror_pnl,
            "cash": cash,
            "positions": list(aggregated.values()),
            "position_count": len(aggregated),
            "mirror_value": mirror_value,
            "mirror_pnl": mirror_pnl,
            "mirror_count": len(mirrors),
            "data_source": "api_live"
        }
    except Exception as e:
        print(f"  ⚠️ eToro fetch failed: {e}")
        return None


def fetch_binance():
    """Fetch Binance portfolio (manual for now)."""
    try:
        with open(SCRIPT_DIR / "binance_portfolio.json") as f:
            data = json.load(f)
        
        positions = []
        for bal in data.get("balances", []):
            if bal.get("value_usd", 0) > 10:  # Filter dust
                positions.append({
                    "ticker": bal["asset"],
                    "shares": bal["total"],
                    "exposure": bal["value_usd"],
                    "pnl": 0,  # Binance doesn't provide PnL in this export
                    "avg_cost": bal.get("price_usd", 0),
                    "broker": "binance"
                })
        
        return {
            "broker": "binance",
            "broker_name": "Binance",
            "status": "manual",
            "last_updated": data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            "currency": "USD",
            "total_value": data.get("total_usd", 0),
            "total_pnl": 0,
            "cash": 0,
            "positions": positions,
            "position_count": len(positions),
            "data_source": "manual_export"
        }
    except Exception as e:
        print(f"  ⚠️ Binance fetch failed: {e}")
        return None


def fetch_manual_broker(broker_key, filename):
    """Fetch manual broker data from JSON file."""
    try:
        with open(SCRIPT_DIR / filename) as f:
            data = json.load(f)
        
        positions = []
        summary = data.get("portfolio_summary", {})
        
        # GBM Main format (sic_positions + national_positions)
        if broker_key == "gbm_main":
            fx_rate = get_fx_rate()
            print(f"  💱 Using USD/MXN rate: {fx_rate}")
            
            sic_positions = data.get("sic_positions", [])
            national_positions = data.get("national_positions", [])
            all_positions = sic_positions + national_positions
            
            for pos in all_positions:
                ticker = pos.get("ticker", "UNKNOWN")
                ticker = ticker.replace("GBM ", "").replace(" ISHRS", "").strip()
                
                # Convert MXN to USD
                market_value_mxn = pos.get("market_value_mxn", 0)
                pnl_mxn = pos.get("pnl_mxn", 0)
                cost_avg_mxn = pos.get("cost_avg_mxn", 0)
                
                positions.append({
                    "ticker": ticker,
                    "shares": pos.get("qty", 0),
                    "exposure": market_value_mxn / fx_rate,
                    "pnl": pnl_mxn / fx_rate,
                    "avg_cost": cost_avg_mxn / fx_rate,
                    "broker": broker_key,
                    "currency": "USD"  # Converted
                })
            
            total_value = summary.get("total_value_mxn", 0) / fx_rate
            cash = 0
        
        # GBM USA format (positions array)
        elif broker_key == "gbm_usa":
            for pos in data.get("positions", []):
                positions.append({
                    "ticker": pos.get("ticker", "UNKNOWN"),
                    "shares": pos.get("qty", 0),
                    "exposure": pos.get("market_value_usd", 0),
                    "pnl": pos.get("pnl_usd", 0),
                    "avg_cost": pos.get("cost_avg_usd", 0),
                    "broker": broker_key,
                    "currency": "USD"
                })
            
            total_value = summary.get("total_value_usd", summary.get("total_value_mxn", 0))
            cash = 0
        
        # Schwab/IBKR format (portfolio_summary.holdings)
        elif broker_key in ["schwab", "ibkr"]:
            holdings = summary.get("holdings", [])
            for pos in holdings:
                positions.append({
                    "ticker": pos.get("ticker", "UNKNOWN"),
                    "shares": pos.get("shares", 0),
                    "exposure": pos.get("market_value", 0),
                    "pnl": pos.get("unrealized_pnl", 0),
                    "avg_cost": pos.get("cost_basis", 0),
                    "broker": broker_key,
                    "currency": "USD"
                })
            
            total_value = summary.get("total_value", 0)
            cash = summary.get("cash", 0)
        
        # Binance format (balances)
        elif broker_key == "binance":
            for bal in data.get("balances", []):
                if bal.get("value_usd", 0) > 10:
                    positions.append({
                        "ticker": bal["asset"],
                        "shares": bal["total"],
                        "exposure": bal["value_usd"],
                        "pnl": 0,
                        "avg_cost": bal.get("price_usd", 0),
                        "broker": broker_key,
                        "currency": "USD"
                    })
            total_value = data.get("total_usd", 0)
            cash = 0
        
        # Revolut format
        elif broker_key == "revolut":
            total_value = summary.get("total_value_mxn", summary.get("total_value_usd", 0))
            cash = summary.get("cash_mxn", summary.get("cash_usd", 0))
        
        # Bitso format
        elif broker_key == "bitso":
            total_value = summary.get("total_value_usd", 0)
            cash = 0
        
        else:
            print(f"  ⚠️ Unknown broker format: {broker_key}")
            return None
        
        return {
            "broker": broker_key,
            "broker_name": BROKERS[broker_key]["name"],
            "status": "manual",
            "last_updated": data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            "currency": BROKERS[broker_key]["currency"],
            "total_value": total_value,
            "total_pnl": sum(p.get("pnl", 0) for p in positions),
            "cash": cash,
            "positions": positions,
            "position_count": len(positions),
            "data_source": data.get("data_source", "manual")
        }
    except Exception as e:
        print(f"  ⚠️ {broker_key} fetch failed: {e}")
        return None


# ─── UNIFY ──────────────────────────────────────────────────────────────────

def unify_portfolios(broker_data):
    """Merge all broker portfolios into unified view."""
    
    # Aggregate positions across brokers
    unified_positions = {}
    broker_breakdown = {}
    total_aum = 0
    total_pnl = 0
    
    for broker_key, data in broker_data.items():
        if not data:
            broker_breakdown[broker_key] = {
                "value": 0,
                "status": "error",
                "stale": True,
                "error": "Failed to fetch"
            }
            continue
        
        broker_value = data.get("total_value", 0)
        broker_pnl = data.get("total_pnl", 0)
        total_aum += broker_value
        total_pnl += broker_pnl
        
        # Check stale status
        last_updated = data.get("last_updated", "")
        is_stale = False
        try:
            if last_updated:
                if isinstance(last_updated, str):
                    if 'T' in last_updated:
                        if '+' in last_updated or 'Z' in last_updated:
                            last_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                        else:
                            last_dt = datetime.fromisoformat(last_updated).replace(tzinfo=timezone.utc)
                    else:
                        last_dt = datetime.strptime(last_updated, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - last_dt
                    is_stale = age.days > 7
        except Exception:
            is_stale = True
        
        broker_breakdown[broker_key] = {
            "value": broker_value,
            "status": data.get("status", "unknown"),
            "stale": is_stale,
            "currency": data.get("currency", "USD"),
            "last_updated": data.get("last_updated"),
            "position_count": data.get("position_count", 0)
        }
        
        # Merge positions
        for pos in data.get("positions", []):
            ticker = pos["ticker"]
            if ticker not in unified_positions:
                unified_positions[ticker] = {
                    "ticker": ticker,
                    "shares": 0,
                    "value": 0,
                    "pnl": 0,
                    "cost_basis": 0,
                    "brokers": [],
                    "price": 0
                }
            
            up = unified_positions[ticker]
            up["shares"] += pos.get("shares", 0)
            up["value"] += pos.get("exposure", 0)
            up["pnl"] += pos.get("pnl", 0)
            if pos.get("broker") not in up["brokers"]:
                up["brokers"].append(pos.get("broker"))
    
    # Calculate derived fields
    positions_list = []
    for ticker, pos in unified_positions.items():
        if pos["shares"] > 0:
            pos["cost_basis"] = (pos["value"] - pos["pnl"]) / pos["shares"]
            pos["price"] = pos["value"] / pos["shares"]
            pos["pnl_pct"] = (pos["pnl"] / (pos["value"] - pos["pnl"]) * 100) if (pos["value"] - pos["pnl"]) > 0 else 0
            pos["pct"] = (pos["value"] / total_aum * 100) if total_aum > 0 else 0
        positions_list.append(pos)
    
    positions_list.sort(key=lambda x: x["value"], reverse=True)
    
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_aum": total_aum,
        "total_pnl": total_pnl,
        "total_positions": len(positions_list),
        "by_broker": broker_breakdown,
        "positions": positions_list,
        "data_source": "broker_sync"
    }


# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("🏦 VOX BROKER SYNC ORCHESTRATOR")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    broker_data = {}
    
    # 1. eToro (API)
    print("📡 Fetching eToro...")
    if BROKERS["etoro"]["enabled"]:
        broker_data["etoro"] = fetch_etoro()
        if broker_data["etoro"]:
            print(f"  ✅ eToro: ${broker_data['etoro']['total_value']:,.2f} | {broker_data['etoro']['position_count']} positions")
        else:
            print("  ❌ eToro failed")
    else:
        print("  ⏭️ eToro disabled (no API key)")
    
    # 2. Binance (manual)
    print("\n📡 Fetching Binance...")
    broker_data["binance"] = fetch_binance()
    if broker_data["binance"]:
        print(f"  ✅ Binance: ${broker_data['binance']['total_value']:,.2f} | {broker_data['binance']['position_count']} positions")
    else:
        print("  ❌ Binance failed")
    
    # 3. GBM Main (manual)
    print("\n📡 Fetching GBM Main...")
    broker_data["gbm_main"] = fetch_manual_broker("gbm_main", "gbm_main_portfolio.json")
    if broker_data["gbm_main"]:
        print(f"  ✅ GBM Main: ${broker_data['gbm_main']['total_value']:,.2f} MXN | {broker_data['gbm_main']['position_count']} positions")
    else:
        print("  ❌ GBM Main failed")
    
    # 4. GBM USA (manual)
    print("\n📡 Fetching GBM USA...")
    broker_data["gbm_usa"] = fetch_manual_broker("gbm_usa", "gbm_usa_portfolio.json")
    if broker_data["gbm_usa"]:
        print(f"  ✅ GBM USA: ${broker_data['gbm_usa']['total_value']:,.2f} | {broker_data['gbm_usa']['position_count']} positions")
    else:
        print("  ❌ GBM USA failed")
    
    # 5. Schwab (manual)
    print("\n📡 Fetching Schwab...")
    broker_data["schwab"] = fetch_manual_broker("schwab", "schwab_portfolio.json")
    if broker_data["schwab"]:
        print(f"  ✅ Schwab: ${broker_data['schwab']['total_value']:,.2f} | {broker_data['schwab']['position_count']} positions")
    else:
        print("  ❌ Schwab failed")
    
    # 6. IBKR (manual)
    print("\n📡 Fetching IBKR...")
    broker_data["ibkr"] = fetch_manual_broker("ibkr", "ibkr_portfolio.json")
    if broker_data["ibkr"]:
        print(f"  ✅ IBKR: ${broker_data['ibkr']['total_value']:,.2f} | {broker_data['ibkr']['position_count']} positions")
    else:
        print("  ❌ IBKR failed")
    
    # 7. Revolut (manual)
    print("\n📡 Fetching Revolut...")
    broker_data["revolut"] = fetch_manual_broker("revolut", "revolut_portfolio.json")
    if broker_data["revolut"]:
        print(f"  ✅ Revolut: ${broker_data['revolut']['total_value']:,.2f} MXN")
    else:
        print("  ❌ Revolut failed")
    
    # 8. Bitso (manual)
    print("\n📡 Fetching Bitso...")
    broker_data["bitso"] = fetch_manual_broker("bitso", "bitso_portfolio.json")
    if broker_data["bitso"]:
        print(f"  ✅ Bitso: ${broker_data['bitso']['total_value']:,.2f}")
    else:
        print("  ❌ Bitso failed")
    
    # Unify
    print("\n" + "=" * 70)
    print("🔄 UNIFYING PORTFOLIOS")
    print("=" * 70)
    
    unified = unify_portfolios(broker_data)
    
    print(f"\n📊 UNIFIED PORTFOLIO")
    print(f"   Total AUM:    ${unified['total_aum']:,.2f}")
    print(f"   Total PnL:    ${unified['total_pnl']:,.2f}")
    print(f"   Positions:    {unified['total_positions']}")
    print(f"\n   By Broker:")
    for broker, info in unified['by_broker'].items():
        status_icon = "🟢" if info['status'] == 'connected' else "🟡" if info['status'] == 'manual' else "🔴"
        stale_icon = "⚠️" if info.get('stale') else ""
        print(f"   {status_icon} {broker:12} | ${info['value']:>12,.2f} | {info['status']:10} {stale_icon}")
    
    # Save unified
    unified_path = SCRIPT_DIR / "unified_portfolio_current.json"
    with open(unified_path, "w") as f:
        json.dump(unified, f, indent=2, default=str)
    print(f"\n💾 Saved unified portfolio to: {unified_path}")
    
    # Save dashboard positions format
    dashboard_positions = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions": unified["positions"],
        "total_value": unified["total_aum"],
        "total_pnl": unified["total_pnl"],
        "broker_breakdown": {k: v["value"] for k, v in unified["by_broker"].items()},
        "broker_status": unified["by_broker"]
    }
    
    dashboard_path = SCRIPT_DIR / "dashboard_positions_live.json"
    with open(dashboard_path, "w") as f:
        json.dump(dashboard_positions, f, indent=2, default=str)
    print(f"💾 Saved dashboard positions to: {dashboard_path}")
    
    # Copy to dashboard
    if DASHBOARD_DIR.exists():
        with open(DASHBOARD_DIR / "dashboard_positions_live.json", "w") as f:
            json.dump(dashboard_positions, f, indent=2, default=str)
        print(f"💾 Copied to dashboard: {DASHBOARD_DIR / 'dashboard_positions_live.json'}")
    
    print("\n" + "=" * 70)
    print("✅ BROKER SYNC COMPLETE")
    print("=" * 70)
    
    return unified


if __name__ == "__main__":
    main()
