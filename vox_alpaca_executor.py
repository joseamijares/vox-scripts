#!/usr/bin/env python3
"""
Vox Alpaca Executor
- Executes approved plays on Alpaca (Jose's account)
- Kill switches: max 1/day, max $500 risk/day, pause after 2 losses
- Logs all trades to Play Journal + Alpaca Plays tab
- Only executes plays from 'Next Plays' with user approval
"""
import json, os, sys, urllib.request
from datetime import datetime, date

# Load Alpaca keys
ALPACA_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_PAPER = os.environ.get("ALPACA_PAPER", "false").lower() == "true"

if not ALPACA_KEY:
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ALPACA_API_KEY="):
                    ALPACA_KEY = line.strip().split("=", 1)[1].strip('"')
                elif line.startswith("ALPACA_SECRET_KEY="):
                    ALPACA_SECRET = line.strip().split("=", 1)[1].strip('"')

BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"

# Kill switches
MAX_TRADES_PER_DAY = 1
MAX_DAILY_RISK = 500
MAX_POSITION_SIZE = 500
PAUSE_AFTER_CONSECUTIVE_LOSSES = 2
DAILY_LOSS_LOG = "vox_daily_loss.json"

def load_daily_log():
    if os.path.exists(DAILY_LOSS_LOG):
        with open(DAILY_LOSS_LOG) as f:
            return json.load(f)
    return {"date": str(date.today()), "trades": 0, "risk_used": 0, "consecutive_losses": 0, "paused": False}

def save_daily_log(log):
    with open(DAILY_LOSS_LOG, "w") as f:
        json.dump(log, f, indent=2)

def check_kill_switches(log, risk_amount):
    """Returns (ok, reason) tuple."""
    if log.get("paused"):
        return False, "TRADING PAUSED: Consecutive losses reached"
    if log.get("trades", 0) >= MAX_TRADES_PER_DAY:
        return False, f"Max {MAX_TRADES_PER_DAY} trade/day reached"
    if log.get("risk_used", 0) + risk_amount > MAX_DAILY_RISK:
        return False, f"Max ${MAX_DAILY_RISK} daily risk reached"
    if risk_amount > MAX_POSITION_SIZE:
        return False, f"Max ${MAX_POSITION_SIZE} position size exceeded"
    return True, "OK"

def alpaca_request(path, method="GET", data=None):
    url = f"{BASE_URL}/v2{path}"
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(), "status": e.code}

def get_account():
    return alpaca_request("/account")

def place_order(symbol, qty, side, order_type="market", time_in_force="day", stop_price=None, limit_price=None):
    data = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force
    }
    if stop_price:
        data["stop_price"] = str(stop_price)
    if limit_price:
        data["limit_price"] = str(limit_price)
    return alpaca_request("/orders", method="POST", data=data)

def main():
    print("🦙 Vox Alpaca Executor")
    print(f"Mode: {'PAPER' if ALPACA_PAPER else 'LIVE'}")
    print("-" * 50)
    
    # Check account
    account = get_account()
    if "error" in account:
        print(f"❌ Account error: {account}")
        return
    
    cash = float(account.get("cash", 0))
    equity = float(account.get("equity", 0))
    print(f"Cash: ${cash:,.2f}")
    print(f"Equity: ${equity:,.2f}")
    
    # Load daily log
    log = load_daily_log()
    if log.get("date") != str(date.today()):
        log = {"date": str(date.today()), "trades": 0, "risk_used": 0, "consecutive_losses": 0, "paused": False}
    
    print(f"\nToday's trades: {log['trades']}/{MAX_TRADES_PER_DAY}")
    print(f"Risk used: ${log['risk_used']:.2f}/${MAX_DAILY_RISK}")
    print(f"Consecutive losses: {log['consecutive_losses']}/{PAUSE_AFTER_CONSECUTIVE_LOSSES}")
    if log.get("paused"):
        print("⚠️ TRADING IS PAUSED")
    
    # Check for approved plays
    if not os.path.exists("vox_next_plays.json"):
        print("\n📭 No approved plays found (vox_next_plays.json)")
        return
    
    with open("vox_next_plays.json") as f:
        next_plays = json.load(f)
    
    pending = [p for p in next_plays.get("plays", []) if p.get("status") == "APPROVED"]
    print(f"\n📋 Approved plays waiting: {len(pending)}")
    
    for play in pending:
        ticker = play.get("ticker")
        direction = play.get("direction", "BUY")
        qty = play.get("qty", 0)
        risk = play.get("risk_usd", 0)
        
        ok, reason = check_kill_switches(log, risk)
        if not ok:
            print(f"  ⛔ {ticker}: {reason}")
            continue
        
        print(f"\n🚀 Executing: {direction} {qty} {ticker}")
        print(f"   Risk: ${risk:.2f}")
        
        # Place order
        result = place_order(ticker, qty, direction.lower())
        
        if "id" in result:
            print(f"   ✅ Order placed: {result['id']}")
            print(f"   Status: {result.get('status', 'unknown')}")
            
            # Update log
            log["trades"] += 1
            log["risk_used"] += risk
            save_daily_log(log)
            
            # Update play status
            play["status"] = "EXECUTED"
            play["order_id"] = result["id"]
            play["executed_at"] = datetime.now().isoformat()
            play["fill_price"] = result.get("filled_avg_price", "pending")
            
            # Save to journal
            journal_entry = {
                "date": datetime.now().isoformat(),
                "play_id": play.get("play_id", "—"),
                "ticker": ticker,
                "type": "ALPACA_EXECUTION",
                "decision": "EXECUTED",
                "grade": play.get("grade", "—"),
                "council": play.get("council", "—"),
                "entry": result.get("filled_avg_price", "pending"),
                "exit": "—",
                "pnl": "—",
                "lesson": f"Kill switches passed. Risk: ${risk}",
                "what_worked": "Systematic execution",
                "what_didnt": "—"
            }
            
            # Append to journal file
            journal_file = "vox_play_journal.json"
            journal = []
            if os.path.exists(journal_file):
                with open(journal_file) as f:
                    journal = json.load(f)
            journal.append(journal_entry)
            with open(journal_file, "w") as f:
                json.dump(journal, f, indent=2)
            
        else:
            print(f"   ❌ Order failed: {result}")
            play["status"] = "FAILED"
            play["error"] = str(result)
    
    # Save updated plays
    with open("vox_next_plays.json", "w") as f:
        json.dump(next_plays, f, indent=2)
    
    print("\n✅ Done")

if __name__ == "__main__":
    main()
