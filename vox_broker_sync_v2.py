#!/usr/bin/env python3
"""
VOX Broker Sync Orchestrator v2.0
Enhanced with retry logic, circuit breaker, and health checks
"""

import json
import os
import sys
import time
import urllib.request
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from functools import wraps

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public" / "data"

# ─── RETRY DECORATOR ────────────────────────────────────────────────────────

def retry(max_attempts=3, delay=2, exceptions=(Exception,)):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait = delay * (2 ** attempt)
                    print(f"  ⚠️  Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
            return None
        return wrapper
    return decorator

# ─── CIRCUIT BREAKER ────────────────────────────────────────────────────────

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=300):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                print("  🔄 Circuit breaker: HALF_OPEN (testing)")
            else:
                print("  ⛔ Circuit breaker: OPEN (skipping)")
                return None
        
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                print("  ✅ Circuit breaker: CLOSED")
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                print(f"  ⛔ Circuit breaker: OPEN ({self.failure_count} failures)")
            raise

# ─── HEALTH CHECK ───────────────────────────────────────────────────────────

class HealthChecker:
    def __init__(self):
        self.checks = {}
    
    def check(self, name, func, *args, **kwargs):
        """Run a health check and store result."""
        try:
            start = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start
            self.checks[name] = {
                "status": "healthy",
                "duration_ms": round(duration * 1000, 2),
                "result": result is not None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return result
        except Exception as e:
            self.checks[name] = {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return None
    
    def report(self):
        """Generate health report."""
        healthy = sum(1 for c in self.checks.values() if c["status"] == "healthy")
        total = len(self.checks)
        return {
            "overall": "healthy" if healthy == total else "degraded" if healthy > 0 else "unhealthy",
            "healthy_count": healthy,
            "total_count": total,
            "checks": self.checks
        }

# ─── ENV LOADING ────────────────────────────────────────────────────────────

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
    "etoro": {"name": "eToro", "type": "api", "enabled": bool(ENV.get("ETORO_API_KEY")), "currency": "USD", "weight": 0.43},
    "binance": {"name": "Binance", "type": "api", "enabled": bool(ENV.get("BINANCE_API_KEY")), "currency": "USD", "weight": 0.10},
    "gbm_main": {"name": "GBM Plus (Main)", "type": "manual", "enabled": True, "currency": "MXN", "weight": 0.38},
    "gbm_usa": {"name": "GBM Plus (USA)", "type": "manual", "enabled": True, "currency": "USD", "weight": 0.07},
    "schwab": {"name": "Charles Schwab", "type": "manual", "enabled": True, "currency": "USD", "weight": 0.01},
    "ibkr": {"name": "Interactive Brokers", "type": "manual", "enabled": True, "currency": "USD", "weight": 0.01},
    "revolut": {"name": "Revolut", "type": "manual", "enabled": True, "currency": "MXN", "weight": 0.00},
    "bitso": {"name": "Bitso", "type": "manual", "enabled": True, "currency": "USD", "weight": 0.00},
}

# ─── CIRCUIT BREAKERS ───────────────────────────────────────────────────────

etoro_breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=300)
binance_breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=300)

# ─── FETCH FUNCTIONS WITH RETRY ─────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def get_fx_rate():
    """Get USD/MXN rate with retry."""
    result = subprocess.run(
        ["python3", "vox_fx_rate.py"],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        timeout=30
    )
    for line in result.stdout.split("\n"):
        if "USD/MXN:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                rate_str = parts[1].split("(")[0].strip()
                return float(rate_str)
    raise ValueError("Could not parse FX rate")

@retry(max_attempts=3, delay=2)
def fetch_etoro():
    """Fetch eToro portfolio via API with retry and circuit breaker."""
    def _fetch():
        result = subprocess.run(
            ["python3", "etoro_api.py"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"eToro API error: {result.stderr[:200]}")
        
        with open(SCRIPT_DIR / "etoro_portfolio.json") as f:
            data = json.load(f)
        
        cp = data.get("clientPortfolio", {})
        positions = cp.get("positions", [])
        
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
                    "ticker": ticker, "shares": 0, "exposure": 0,
                    "pnl": 0, "cost_basis": 0, "broker": "eToro"
                }
            aggregated[ticker]["shares"] += pos["shares"]
            aggregated[ticker]["exposure"] += pos["exposure"]
            aggregated[ticker]["pnl"] += pos["pnl"]
        
        for ticker, agg in aggregated.items():
            if agg["shares"] > 0:
                agg["cost_basis"] = (agg["exposure"] - agg["pnl"]) / agg["shares"]
        
        mirrors = cp.get("mirrors", [])
        mirror_value = sum(m.get("initialInvestment", 0) - m.get("availableAmount", 0) for m in mirrors)
        mirror_pnl = sum(m.get("closedPositionsNetProfit", 0) for m in mirrors)
        
        total_exposure = sum(p.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0) for p in positions)
        total_pnl = sum(p.get("unrealizedPnL", {}).get("pnL", 0) for p in positions)
        
        credit_raw = cp.get("credit", 0)
        cash = credit_raw if isinstance(credit_raw, (int, float)) else credit_raw.get("balance", 0)
        
        return {
            "broker": "etoro", "broker_name": "eToro", "status": "connected",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "currency": "USD", "total_value": total_exposure + mirror_value,
            "total_pnl": total_pnl + mirror_pnl, "cash": cash,
            "positions": list(aggregated.values()),
            "position_count": len(aggregated),
            "mirror_value": mirror_value, "mirror_pnl": mirror_pnl,
            "mirror_count": len(mirrors), "data_source": "api_live"
        }
    
    return etoro_breaker.call(_fetch)

@retry(max_attempts=2, delay=1)
def fetch_binance():
    """Fetch Binance portfolio with retry."""
    def _fetch():
        with open(SCRIPT_DIR / "binance_portfolio.json") as f:
            data = json.load(f)
        
        positions = []
        for bal in data.get("balances", []):
            if bal.get("value_usd", 0) > 10:
                positions.append({
                    "ticker": bal["asset"], "shares": bal["total"],
                    "exposure": bal["value_usd"], "pnl": 0,
                    "avg_cost": bal.get("price_usd", 0), "broker": "binance"
                })
        
        return {
            "broker": "binance", "broker_name": "Binance", "status": "manual",
            "last_updated": data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            "currency": "USD", "total_value": data.get("total_usd", 0),
            "total_pnl": 0, "cash": 0, "positions": positions,
            "position_count": len(positions), "data_source": "manual_export"
        }
    
    return binance_breaker.call(_fetch)

@retry(max_attempts=2, delay=1)
def fetch_manual_broker(broker_key, filename):
    """Fetch manual broker data with retry."""
    with open(SCRIPT_DIR / filename) as f:
        data = json.load(f)
    
    positions = []
    summary = data.get("portfolio_summary", {})
    
    if broker_key == "gbm_main":
        fx_rate = get_fx_rate()
        print(f"  💱 Using USD/MXN rate: {fx_rate}")
        
        all_positions = data.get("sic_positions", []) + data.get("national_positions", [])
        for pos in all_positions:
            ticker = pos.get("ticker", "UNKNOWN").replace("GBM ", "").replace(" ISHRS", "").strip()
            positions.append({
                "ticker": ticker, "shares": pos.get("qty", 0),
                "exposure": pos.get("market_value_mxn", 0) / fx_rate,
                "pnl": pos.get("pnl_mxn", 0) / fx_rate,
                "avg_cost": pos.get("cost_avg_mxn", 0) / fx_rate,
                "broker": broker_key, "currency": "USD"
            })
        total_value = summary.get("total_value_mxn", 0) / fx_rate
        cash = 0
    
    elif broker_key == "gbm_usa":
        for pos in data.get("positions", []):
            positions.append({
                "ticker": pos.get("ticker", "UNKNOWN"), "shares": pos.get("qty", 0),
                "exposure": pos.get("market_value_usd", 0), "pnl": pos.get("pnl_usd", 0),
                "avg_cost": pos.get("cost_avg_usd", 0), "broker": broker_key, "currency": "USD"
            })
        total_value = summary.get("total_value_usd", summary.get("total_value_mxn", 0))
        cash = 0
    
    elif broker_key in ["schwab", "ibkr"]:
        for pos in summary.get("holdings", []):
            positions.append({
                "ticker": pos.get("ticker", "UNKNOWN"), "shares": pos.get("shares", 0),
                "exposure": pos.get("market_value", 0), "pnl": pos.get("unrealized_pnl", 0),
                "avg_cost": pos.get("cost_basis", 0), "broker": broker_key, "currency": "USD"
            })
        total_value = summary.get("total_value", 0)
        cash = summary.get("cash", 0)
    
    elif broker_key == "binance":
        for bal in data.get("balances", []):
            if bal.get("value_usd", 0) > 10:
                positions.append({
                    "ticker": bal["asset"], "shares": bal["total"],
                    "exposure": bal["value_usd"], "pnl": 0,
                    "avg_cost": bal.get("price_usd", 0), "broker": broker_key, "currency": "USD"
                })
        total_value = data.get("total_usd", 0)
        cash = 0
    
    elif broker_key == "revolut":
        total_value = summary.get("total_value_mxn", summary.get("total_value_usd", 0))
        cash = summary.get("cash_mxn", summary.get("cash_usd", 0))
    
    elif broker_key == "bitso":
        total_value = summary.get("total_value_usd", 0)
        cash = 0
    
    else:
        raise ValueError(f"Unknown broker format: {broker_key}")
    
    return {
        "broker": broker_key, "broker_name": BROKERS[broker_key]["name"],
        "status": "manual", "last_updated": data.get("last_updated", datetime.now(timezone.utc).isoformat()),
        "currency": BROKERS[broker_key]["currency"], "total_value": total_value,
        "total_pnl": sum(p.get("pnl", 0) for p in positions), "cash": cash,
        "positions": positions, "position_count": len(positions),
        "data_source": data.get("data_source", "manual")
    }

# ─── UNIFY ──────────────────────────────────────────────────────────────────

def unify_portfolios(broker_data):
    """Merge all broker portfolios into unified view."""
    unified_positions = {}
    broker_breakdown = {}
    total_aum = 0
    total_pnl = 0
    
    for broker_key, data in broker_data.items():
        if not data:
            broker_breakdown[broker_key] = {
                "value": 0, "status": "error", "stale": True,
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
            "value": broker_value, "status": data.get("status", "unknown"),
            "stale": is_stale, "currency": data.get("currency", "USD"),
            "last_updated": data.get("last_updated"),
            "position_count": data.get("position_count", 0)
        }
        
        for pos in data.get("positions", []):
            ticker = pos["ticker"]
            if ticker not in unified_positions:
                unified_positions[ticker] = {
                    "ticker": ticker, "shares": 0, "value": 0,
                    "pnl": 0, "cost_basis": 0, "brokers": [], "price": 0
                }
            
            up = unified_positions[ticker]
            up["shares"] += pos.get("shares", 0)
            up["value"] += pos.get("exposure", 0)
            up["pnl"] += pos.get("pnl", 0)
            if pos.get("broker") not in up["brokers"]:
                up["brokers"].append(pos.get("broker"))
    
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
        "total_aum": total_aum, "total_pnl": total_pnl,
        "total_positions": len(positions_list),
        "by_broker": broker_breakdown, "positions": positions_list,
        "data_source": "broker_sync"
    }

# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("🏦 VOX BROKER SYNC ORCHESTRATOR v2.0")
    print("   Enhanced: retry logic, circuit breaker, health checks")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    health = HealthChecker()
    broker_data = {}
    
    # Fetch all brokers with health checks
    print("📡 Fetching eToro...")
    if BROKERS["etoro"]["enabled"]:
        broker_data["etoro"] = health.check("etoro", fetch_etoro)
        if broker_data["etoro"]:
            print(f"  ✅ eToro: ${broker_data['etoro']['total_value']:,.2f} | {broker_data['etoro']['position_count']} positions")
        else:
            print("  ❌ eToro failed")
    else:
        print("  ⏭️ eToro disabled (no API key)")
    
    print("\n📡 Fetching Binance...")
    broker_data["binance"] = health.check("binance", fetch_binance)
    if broker_data["binance"]:
        print(f"  ✅ Binance: ${broker_data['binance']['total_value']:,.2f} | {broker_data['binance']['position_count']} positions")
    else:
        print("  ❌ Binance failed")
    
    print("\n📡 Fetching GBM Main...")
    broker_data["gbm_main"] = health.check("gbm_main", fetch_manual_broker, "gbm_main", "gbm_main_portfolio.json")
    if broker_data["gbm_main"]:
        print(f"  ✅ GBM Main: ${broker_data['gbm_main']['total_value']:,.2f} | {broker_data['gbm_main']['position_count']} positions")
    else:
        print("  ❌ GBM Main failed")
    
    print("\n📡 Fetching GBM USA...")
    broker_data["gbm_usa"] = health.check("gbm_usa", fetch_manual_broker, "gbm_usa", "gbm_usa_portfolio.json")
    if broker_data["gbm_usa"]:
        print(f"  ✅ GBM USA: ${broker_data['gbm_usa']['total_value']:,.2f} | {broker_data['gbm_usa']['position_count']} positions")
    else:
        print("  ❌ GBM USA failed")
    
    print("\n📡 Fetching Schwab...")
    broker_data["schwab"] = health.check("schwab", fetch_manual_broker, "schwab", "schwab_portfolio.json")
    if broker_data["schwab"]:
        print(f"  ✅ Schwab: ${broker_data['schwab']['total_value']:,.2f} | {broker_data['schwab']['position_count']} positions")
    else:
        print("  ❌ Schwab failed")
    
    print("\n📡 Fetching IBKR...")
    broker_data["ibkr"] = health.check("ibkr", fetch_manual_broker, "ibkr", "ibkr_portfolio.json")
    if broker_data["ibkr"]:
        print(f"  ✅ IBKR: ${broker_data['ibkr']['total_value']:,.2f} | {broker_data['ibkr']['position_count']} positions")
    else:
        print("  ❌ IBKR failed")
    
    print("\n📡 Fetching Revolut...")
    broker_data["revolut"] = health.check("revolut", fetch_manual_broker, "revolut", "revolut_portfolio.json")
    if broker_data["revolut"]:
        print(f"  ✅ Revolut: ${broker_data['revolut']['total_value']:,.2f}")
    else:
        print("  ❌ Revolut failed")
    
    print("\n📡 Fetching Bitso...")
    broker_data["bitso"] = health.check("bitso", fetch_manual_broker, "bitso", "bitso_portfolio.json")
    if broker_data["bitso"]:
        print(f"  ✅ Bitso: ${broker_data['bitso']['total_value']:,.2f}")
    else:
        print("  ❌ Bitso failed")
    
    # Health report
    print("\n" + "=" * 70)
    print("🏥 HEALTH CHECK REPORT")
    print("=" * 70)
    health_report = health.report()
    print(f"Overall: {health_report['overall'].upper()}")
    print(f"Healthy: {health_report['healthy_count']}/{health_report['total_count']}")
    for name, check in health_report['checks'].items():
        icon = "✅" if check['status'] == 'healthy' else "❌"
        duration = check.get('duration_ms', 'N/A')
        print(f"  {icon} {name:12} | {check['status']:10} | {duration}ms")
    
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
        "broker_status": unified["by_broker"],
        "health": health_report
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
    
    # Save health report
    health_path = SCRIPT_DIR / "broker_health.json"
    with open(health_path, "w") as f:
        json.dump(health_report, f, indent=2)
    print(f"💾 Saved health report to: {health_path}")
    
    print("\n" + "=" * 70)
    print("✅ BROKER SYNC COMPLETE")
    print("=" * 70)
    
    return unified

if __name__ == "__main__":
    main()
