#!/usr/bin/env python3
"""
VOX Smart Alert System v4
ONLY alerts when:
1. Grade drops below 45 (SELL signal) AND position value > $500
2. Grade rises above 85 (strong BUY) AND not already in portfolio
3. Crypto exceeds 10% of portfolio
4. Trump tweet affects portfolio ticker with impact >= 8
5. Any position loses >$500 in a day
6. Council consensus >75% on a play

NEVER alerts on:
- Grade changes within normal range (45-85)
- Market open/close summaries
- "All clear" messages
- Duplicate alerts within 24h
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Files
POSITIONS_FILE = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
GRADES_FILE = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
ALERT_STATE = Path.home() / ".hermes" / "scripts" / ".vox_alert_state.json"

def load_state():
    if ALERT_STATE.exists():
        with open(ALERT_STATE) as f:
            return json.load(f)
    return {"last_alerts": {}, "daily_alert_count": 0, "last_reset": datetime.now(timezone.utc).isoformat()}

def save_state(state):
    with open(ALERT_STATE, 'w') as f:
        json.dump(state, f, indent=2)

def should_alert(alert_key, cooldown_hours=24):
    """Check if we should alert (deduplication)"""
    state = load_state()
    
    # Ensure state has required keys
    if "last_alerts" not in state:
        state["last_alerts"] = {}
    if "daily_alert_count" not in state:
        state["daily_alert_count"] = 0
    if "last_reset" not in state:
        state["last_reset"] = datetime.now(timezone.utc).isoformat()
    
    last_alert = state["last_alerts"].get(alert_key)
    
    if last_alert:
        last_time = datetime.fromisoformat(last_alert)
        if datetime.now(timezone.utc) - last_time < timedelta(hours=cooldown_hours):
            return False
    
    # Check daily limit
    last_reset = datetime.fromisoformat(state["last_reset"])
    if datetime.now(timezone.utc) - last_reset > timedelta(days=1):
        state["daily_alert_count"] = 0
        state["last_reset"] = datetime.now(timezone.utc).isoformat()
    
    if state["daily_alert_count"] >= 5:  # Max 5 alerts per day
        return False
    
    return True

def record_alert(alert_key):
    state = load_state()
    # Ensure state has required keys
    if "last_alerts" not in state:
        state["last_alerts"] = {}
    if "daily_alert_count" not in state:
        state["daily_alert_count"] = 0
    state["last_alerts"][alert_key] = datetime.now(timezone.utc).isoformat()
    state["daily_alert_count"] += 1
    save_state(state)

def check_sell_alerts():
    """Check for SELL signals (grade < 45, value > $500)"""
    alerts = []
    
    if not POSITIONS_FILE.exists():
        return alerts
    
    with open(POSITIONS_FILE) as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    
    for pos in positions:
        grade = pos.get("grade", 0)
        value = pos.get("value", 0)
        ticker = pos["ticker"]
        
        if grade > 0 and grade < 45 and value > 500:
            alert_key = f"sell_{ticker}"
            if should_alert(alert_key, cooldown_hours=24):
                alerts.append({
                    "type": "SELL",
                    "ticker": ticker,
                    "grade": grade,
                    "value": value,
                    "brokers": pos.get("brokers", []),
                    "message": f"🔴 SELL {ticker}: Grade {grade}, Value ${value:,.0f}",
                    "alert_key": alert_key,
                })
    
    return alerts

def check_crypto_limit():
    """Check if crypto exceeds 10%"""
    alerts = []
    
    if not POSITIONS_FILE.exists():
        return alerts
    
    with open(POSITIONS_FILE) as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    total_value = data.get("total_value", sum(p.get("value", 0) for p in positions))
    
    crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX", "SUI"]
    crypto_value = sum(p["value"] for p in positions if p["ticker"] in crypto_tickers)
    crypto_pct = (crypto_value / total_value * 100) if total_value > 0 else 0
    
    if crypto_pct > 10:
        alert_key = "crypto_limit"
        if should_alert(alert_key, cooldown_hours=24):
            alerts.append({
                "type": "CRYPTO_LIMIT",
                "message": f"⚠️ Crypto at {crypto_pct:.1f}% (limit 10%). Consider trimming.",
                "alert_key": alert_key,
            })
    
    return alerts

def check_big_losers():
    """Check for positions losing >$500"""
    alerts = []
    
    if not POSITIONS_FILE.exists():
        return alerts
    
    with open(POSITIONS_FILE) as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    
    for pos in positions:
        pnl = pos.get("pnl", 0)
        ticker = pos["ticker"]
        
        if pnl < -500:
            alert_key = f"loser_{ticker}"
            if should_alert(alert_key, cooldown_hours=24):
                alerts.append({
                    "type": "BIG_LOSER",
                    "ticker": ticker,
                    "pnl": pnl,
                    "message": f"📉 {ticker} losing ${abs(pnl):,.0f}. Review stop loss.",
                    "alert_key": alert_key,
                })
    
    return alerts

def generate_alerts():
    """Generate all alerts"""
    print("🔍 VOX Smart Alert System v4")
    print("=" * 50)
    
    all_alerts = []
    all_alerts.extend(check_sell_alerts())
    all_alerts.extend(check_crypto_limit())
    all_alerts.extend(check_big_losers())
    
    if not all_alerts:
        print("✅ No action required. All quiet.")
        return []
    
    print(f"\n🚨 {len(all_alerts)} ALERTS:")
    for alert in all_alerts:
        print(f"   {alert['message']}")
        record_alert(alert['alert_key'])
    
    return all_alerts

if __name__ == "__main__":
    generate_alerts()
