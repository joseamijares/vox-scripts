#!/usr/bin/env python3
"""
Vox Monitored Plays
- Tracks active opportunities being watched
- Auto-updates prices daily
- Flags when plays hit entry, stop, or target
- Outputs to Google Sheets '🔍 Monitored Plays' tab
"""
import json, os, sys, urllib.request
from datetime import datetime, date

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_KEY:
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    POLYGON_KEY = line.strip().split("=", 1)[1].strip('"')
                    break

MONITORED_FILE = "vox_monitored_plays.json"

def load_monitored():
    if os.path.exists(MONITORED_FILE):
        with open(MONITORED_FILE) as f:
            return json.load(f)
    return {"plays": []}

def save_monitored(data):
    with open(MONITORED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_price(ticker):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={POLYGON_KEY}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("results", [{}])[0].get("c", 0)
    except:
        return 0

def add_monitored(ticker, trigger, entry_price, target, stop, grade, notes=""):
    data = load_monitored()
    play = {
        "id": f"MON_{ticker}_{datetime.now().strftime('%Y%m%d')}",
        "date": str(date.today()),
        "ticker": ticker,
        "trigger": trigger,
        "entry_price": entry_price,
        "current_price": entry_price,
        "target": target,
        "stop": stop,
        "grade": grade,
        "days_held": 0,
        "unrealized_pnl": 0,
        "status": "WATCHING",
        "action_needed": "Monitor",
        "notes": notes,
        "alerts": []
    }
    data["plays"].append(play)
    save_monitored(data)
    print(f"✅ Added to monitored: {ticker} @ ${entry_price}")
    return play

def update_monitored():
    """Update all monitored plays with current prices."""
    data = load_monitored()
    alerts = []
    
    for play in data["plays"]:
        if play["status"] not in ("WATCHING", "NEAR_ENTRY"):
            continue
        
        current = get_price(play["ticker"])
        if not current:
            continue
        
        play["current_price"] = current
        play["days_held"] = (date.today() - datetime.strptime(play["date"], "%Y-%m-%d").date()).days
        
        if play["entry_price"]:
            play["unrealized_pnl"] = round((current - play["entry_price"]) / play["entry_price"] * 100, 2)
        
        # Check triggers
        if play["stop"] and current <= play["stop"]:
            play["status"] = "STOP_HIT"
            play["action_needed"] = "CLOSE POSITION"
            alerts.append(f"🛑 {play['ticker']} hit stop @ ${play['stop']} (current: ${current})")
        elif play["target"] and current >= play["target"]:
            play["status"] = "TARGET_HIT"
            play["action_needed"] = "TAKE PROFITS"
            alerts.append(f"🎯 {play['ticker']} hit target @ ${play['target']} (current: ${current})")
        elif play["entry_price"] and abs(current - play["entry_price"]) / play["entry_price"] < 0.02:
            play["status"] = "NEAR_ENTRY"
            play["action_needed"] = "READY TO ENTER"
            alerts.append(f"⚡ {play['ticker']} near entry @ ${play['entry_price']} (current: ${current})")
    
    save_monitored(data)
    return alerts

def main():
    print("🔍 Vox Monitored Plays Update")
    print("-" * 50)
    
    alerts = update_monitored()
    data = load_monitored()
    active = [p for p in data["plays"] if p["status"] in ("WATCHING", "NEAR_ENTRY")]
    
    print(f"Active monitored plays: {len(active)}")
    
    if active:
        print(f"\n{'TICKER':<8} {'ENTRY':<10} {'CURRENT':<10} {'TARGET':<10} {'STOP':<10} {'P&L%':<8} {'DAYS':<6} {'STATUS':<15}")
        for p in active:
            print(f"{p['ticker']:<8} ${p['entry_price']:<9.2f} ${p['current_price']:<9.2f} ${p['target']:<9.2f} ${p['stop']:<9.2f} {p['unrealized_pnl']:>+6.1f}%  {p['days_held']:<6} {p['status']:<15}")
    
    if alerts:
        print(f"\n🚨 Alerts ({len(alerts)}):")
        for a in alerts:
            print(f"  {a}")
    
    print("\n✅ Done")

if __name__ == "__main__":
    main()
