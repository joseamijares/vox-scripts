#!/usr/bin/env python3
"""
Vox Options Tracker
- Tracks options positions across Schwab, IBKR, Alpaca
- Manual entry for Greeks (until paid API)
- Alerts on expiry, delta changes, profit targets
- Outputs to Google Sheets '📜 Options Trading' tab
"""
import json, os
from datetime import datetime, date

OPTIONS_FILE = "vox_options_positions.json"

def load_positions():
    if os.path.exists(OPTIONS_FILE):
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    return {"positions": []}

def save_positions(data):
    with open(OPTIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def days_to_expiry(expiry_str):
    try:
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return (expiry - date.today()).days
    except:
        return "—"

def add_position(ticker, strategy, opt_type, strike, expiry, premium, broker, notes=""):
    data = load_positions()
    position = {
        "id": f"{ticker}_{strike}_{expiry}_{opt_type}_{datetime.now().strftime('%H%M%S')}",
        "date_opened": str(date.today()),
        "ticker": ticker,
        "strategy": strategy,
        "type": opt_type,
        "strike": strike,
        "expiry": expiry,
        "premium": premium,
        "current_premium": premium,
        "delta": "—",
        "theta": "—",
        "iv": "—",
        "pnl": 0,
        "pnl_pct": 0,
        "broker": broker,
        "status": "OPEN",
        "days_remaining": days_to_expiry(expiry),
        "notes": notes,
        "alerts": []
    }
    data["positions"].append(position)
    save_positions(data)
    print(f"✅ Added: {ticker} {opt_type} ${strike} {expiry} @ ${premium} ({broker})")
    return position

def update_greeks(position_id, delta=None, theta=None, iv=None, current_premium=None):
    data = load_positions()
    for p in data["positions"]:
        if p["id"] == position_id and p["status"] == "OPEN":
            if delta is not None:
                p["delta"] = delta
            if theta is not None:
                p["theta"] = theta
            if iv is not None:
                p["iv"] = iv
            if current_premium is not None:
                p["current_premium"] = current_premium
                p["pnl"] = round(current_premium - p["premium"], 2)
                p["pnl_pct"] = round((current_premium - p["premium"]) / p["premium"] * 100, 1) if p["premium"] else 0
            p["days_remaining"] = days_to_expiry(p["expiry"])
            save_positions(data)
            print(f"✅ Updated: {position_id}")
            return p
    print(f"❌ Position not found: {position_id}")
    return None

def close_position(position_id, exit_premium, notes=""):
    data = load_positions()
    for p in data["positions"]:
        if p["id"] == position_id and p["status"] == "OPEN":
            p["status"] = "CLOSED"
            p["current_premium"] = exit_premium
            p["pnl"] = round(exit_premium - p["premium"], 2)
            p["pnl_pct"] = round((exit_premium - p["premium"]) / p["premium"] * 100, 1) if p["premium"] else 0
            p["date_closed"] = str(date.today())
            p["notes"] += f" | Closed: {notes}"
            save_positions(data)
            print(f"✅ Closed: {position_id} | P&L: ${p['pnl']} ({p['pnl_pct']}%)")
            return p
    print(f"❌ Position not found: {position_id}")
    return None

def check_alerts():
    """Check for expiry warnings, profit targets, stop losses."""
    data = load_positions()
    alerts = []
    for p in data["positions"]:
        if p["status"] != "OPEN":
            continue
        
        days = days_to_expiry(p["expiry"])
        if isinstance(days, int) and days <= 7:
            alerts.append(f"⏰ {p['ticker']} {p['type']} ${p['strike']} expires in {days} days!")
        
        if p["pnl_pct"] >= 50:
            alerts.append(f"🎯 {p['ticker']} {p['type']} ${p['strike']} up {p['pnl_pct']}% — consider taking profits")
        
        if p["pnl_pct"] <= -50:
            alerts.append(f"🛑 {p['ticker']} {p['type']} ${p['strike']} down {p['pnl_pct']}% — stop loss hit")
    
    return alerts

def main():
    print("📜 Vox Options Tracker")
    print("-" * 50)
    
    data = load_positions()
    open_pos = [p for p in data["positions"] if p["status"] == "OPEN"]
    closed_pos = [p for p in data["positions"] if p["status"] == "CLOSED"]
    
    print(f"Open positions: {len(open_pos)}")
    print(f"Closed positions: {len(closed_pos)}")
    
    if open_pos:
        print("\n📊 Open Positions:")
        print(f"{'TICKER':<8} {'TYPE':<6} {'STRIKE':<8} {'EXPIRY':<12} {'PREM':<8} {'P&L':<10} {'DTE':<6} {'BROKER':<10}")
        for p in open_pos:
            print(f"{p['ticker']:<8} {p['type']:<6} ${p['strike']:<7} {p['expiry']:<12} ${p['premium']:<7} {p['pnl_pct']:>+5.1f}%    {str(p['days_remaining']):<6} {p['broker']:<10}")
    
    alerts = check_alerts()
    if alerts:
        print("\n🚨 Alerts:")
        for a in alerts:
            print(f"  {a}")
    
    print("\n✅ Done")

if __name__ == "__main__":
    main()
