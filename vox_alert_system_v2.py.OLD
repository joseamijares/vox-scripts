#!/usr/bin/env python3
"""
Vox Alert System v2 — JOS-26 Enhanced
Price-based alerts + Grade-based alerts + Auto-execution prep
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


def polygon_get(path, params=""):
    """Polygon.io API GET."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {"error": "POLYGON_API_KEY not set"}
    url = f"https://api.polygon.io{path}?apiKey={api_key}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_current_price(ticker):
    """Fetch current price from Polygon."""
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/prev")
    if "error" in result:
        return None
    results = result.get("results", [])
    if results:
        return results[0].get("c", None)
    return None


def send_telegram_message(message):
    """Send a message via Telegram bot."""
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        print(f"⚠️ Telegram not configured. Message:\n{message}")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


# ============ ALERT CONFIGURATION ============
# These are YOUR specific alerts based on our analysis

ALERT_CONFIG = {
    # SELL ALERTS — Positions to exit
    "JMIA": {
        "action": "SELL_ALL",
        "trigger": "grade_below_50",
        "current_grade": 41,
        "shares": 200,
        "broker": "eToro",
        "reason": "Thesis broken, -68% loss, no path to profitability",
        "urgency": "HIGH"
    },
    "OKLO": {
        "action": "SELL_ON_BOUNCE",
        "trigger": "price_above",
        "target_price": 18.00,
        "current_grade": 49,
        "shares": 25,
        "broker": "Schwab",
        "reason": "Grade 49, nuclear theme valid but better alternative (CEG)",
        "urgency": "MEDIUM"
    },
    
    # BUY ALERTS — Pullback entries
    "DELL": {
        "action": "BUY_ON_PULLBACK",
        "trigger": "price_below",
        "target_price": 280.00,
        "current_grade": 67,
        "position_size_pct": 2.0,
        "broker": "Schwab",
        "reason": "Grade 67, AI server demand, wait for RSI cooldown from 76",
        "urgency": "MEDIUM"
    },
    "AMAT": {
        "action": "BUY_ON_PULLBACK",
        "trigger": "price_below",
        "target_price": 415.00,
        "current_grade": 63,
        "position_size_pct": 2.0,
        "broker": "Schwab",
        "reason": "Grade 63, semiconductor equipment, buy at EMA21 support",
        "urgency": "MEDIUM"
    },
    "LLY": {
        "action": "BUY_ON_PULLBACK",
        "trigger": "price_below",
        "target_price": 960.00,
        "current_grade": 66,
        "position_size_pct": 1.5,
        "broker": "Schwab",
        "reason": "Grade 66, GLP-1 leader, 10% pullback entry",
        "urgency": "LOW"
    },
    "CEG": {
        "action": "BUY",
        "trigger": "grade_above_55",
        "current_grade": 59,
        "position_size_pct": 2.0,
        "broker": "Schwab",
        "reason": "Nuclear + AI power, actual revenue, only $407 current position",
        "urgency": "MEDIUM"
    },
    
    # HOLD — No action needed
    "OSCR": {
        "action": "HOLD",
        "trigger": "grade_stable",
        "current_grade": 52,
        "reason": "2% position, wait for June 12 earnings",
        "urgency": "NONE"
    },
    "POET": {
        "action": "HOLD",
        "trigger": "grade_stable",
        "current_grade": 58,
        "reason": "0.3% speculative position, AI photonics thesis intact",
        "urgency": "NONE"
    }
}


def check_price_alerts():
    """Check price-based alerts."""
    alerts = []
    
    for ticker, config in ALERT_CONFIG.items():
        if config["action"] in ["HOLD"]:
            continue
            
        current_price = get_current_price(ticker)
        if not current_price:
            continue
        
        trigger = config.get("trigger", "")
        target = config.get("target_price", 0)
        
        # Check if trigger condition is met
        triggered = False
        if trigger == "price_below" and current_price <= target:
            triggered = True
        elif trigger == "price_above" and current_price >= target:
            triggered = True
        elif trigger == "grade_below_50" and config["current_grade"] < 50:
            triggered = True
        elif trigger == "grade_above_55" and config["current_grade"] > 55:
            triggered = True
            # For grade-based buys, use current price as target
            if not target:
                target = current_price
        
        if triggered:
            # Ensure target is set for grade-based alerts
            if not target and current_price:
                target = current_price
            alerts.append({
                "ticker": ticker,
                "action": config["action"],
                "current_price": current_price,
                "target_price": target,
                "grade": config["current_grade"],
                "broker": config.get("broker", ""),
                "shares": config.get("shares", 0),
                "position_size_pct": config.get("position_size_pct", 0),
                "reason": config["reason"],
                "urgency": config["urgency"]
            })
    
    return alerts


def format_sell_alert(alert):
    """Format a SELL alert with exact instructions."""
    ticker = alert["ticker"]
    price = alert["current_price"]
    shares = alert["shares"]
    broker = alert["broker"]
    value = price * shares
    
    msg = f"""🔴 *VOX SELL ALERT — EXECUTE TODAY*

📉 *{ticker}* — SELL ALL
💰 Current Price: ${price:.2f}
📊 Shares: {shares}
💵 Value: ${value:,.2f}
🏦 Broker: {broker}

*WHY:*
{alert['reason']}

*EXACT ACTION:*
1. Open {broker}
2. Sell {shares} shares of {ticker}
3. Market order (urgent — thesis broken)

*CASH FREED:* ${value:,.2f}

*WHAT TO DO WITH CASH:*
→ Transfer to Schwab for CEG add
→ Or hold for DELL/AMAT pullback

_Execute within 24 hours. This position is bleeding._
"""
    return msg


def format_buy_alert(alert):
    """Format a BUY alert with exact instructions."""
    ticker = alert["ticker"]
    price = alert["current_price"]
    target = alert.get("target_price", price)
    grade = alert["grade"]
    broker = alert["broker"]
    
    # Calculate position size
    portfolio = 196000
    position_pct = alert.get("position_size_pct", 2.0)
    position_value = portfolio * (position_pct / 100)
    shares = int(position_value / price)
    
    msg = f"""🟢 *VOX BUY ALERT — {ticker}*

📈 *{ticker}* — Grade: {grade}/100
💰 Current Price: ${price:.2f}
🎯 Target Entry: ${target:.2f}
🏦 Broker: {broker}

*WHY:*
{alert['reason']}

*EXACT ACTION:*
1. Open {broker}
2. Buy {shares} shares of {ticker}
3. Limit order at ${target:.2f} (or market if urgent)
4. Set stop loss at 8% below entry

*POSITION SIZE:*
• ${position_value:,.2f} ({position_pct}% of portfolio)
• {shares} shares @ ~${price:.2f}

*RISK MANAGEMENT:*
• Stop: ${price * 0.92:.2f} (8% below entry)
• Max loss: ${position_value * 0.08:,.2f}

_Do not chase above ${target * 1.02:.2f}. Wait for pullback if missed._
"""
    return msg


def format_bounce_sell_alert(alert):
    """Format a sell-on-bounce alert."""
    ticker = alert["ticker"]
    price = alert["current_price"]
    target = alert["target_price"]
    shares = alert["shares"]
    broker = alert["broker"]
    
    msg = f"""🟡 *VOX BOUNCE SELL — {ticker}*

📊 *{ticker}* — Current: ${price:.2f} | Target: ${target:.2f}
📈 Wait for price to hit ${target:.2f}+ before selling
📊 Shares: {shares}
🏦 Broker: {broker}

*WHY:*
{alert['reason']}

*EXACT ACTION:*
1. Set price alert at ${target:.2f}
2. When triggered, sell {shares} shares
3. Use limit order at ${target:.2f}

*CASH EXPECTED:* ${target * shares:,.2f}

*AFTER SELL:*
→ Add to CEG position
→ Or hold for better setup

_Do not sell below ${target * 0.95:.2f}. Wait for bounce._
"""
    return msg


def run_alert_system():
    """Main alert runner."""
    print(f"{'='*70}")
    print("🔔 VOX ALERT SYSTEM v2")
    print(f"{'='*70}")
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    alerts = check_price_alerts()
    
    print(f"Active alerts: {len(alerts)}")
    print()
    
    for alert in alerts:
        action = alert["action"]
        
        if action == "SELL_ALL":
            msg = format_sell_alert(alert)
        elif action == "SELL_ON_BOUNCE":
            msg = format_bounce_sell_alert(alert)
        elif action == "BUY_ON_PULLBACK":
            msg = format_buy_alert(alert)
        elif action == "BUY":
            msg = format_buy_alert(alert)
        else:
            continue
        
        print(f"\n{'='*70}")
        print(f"ALERT: {alert['ticker']} — {action}")
        print(f"{'='*70}")
        print(msg)
        
        # Send to Telegram
        send_telegram_message(msg)
    
    # Always print the Tuesday action plan
    print_tuesday_plan()
    
    return alerts


def print_tuesday_plan():
    """Print the clear Tuesday action plan."""
    plan = """
======================================================================
📋 VOX TUESDAY ACTION PLAN (May 27, 2026)
======================================================================

MORNING (Market Open 9:30 AM ET):
─────────────────────────────────
1. ⏰ Check Telegram for overnight alerts
2. 📊 Review VOX Morning Brief (auto-sent 8 AM)
3. 🔴 EXECUTE: SELL JMIA (if not done Monday)

MIDDAY (12:00 PM ET):
─────────────────────
4. 📈 Check intraday alert from VOX
5. 🟡 Set price alert: OKLO at $18.00 (bounce sell)

AFTERNOON (3:00-4:00 PM ET):
────────────────────────────
6. 🟢 Set buy alerts:
   • DELL below $280
   • AMAT below $415
   • LLY below $960
7. 🟢 Review CEG — add if grade still 55+

EVENING (After Close):
──────────────────────
8. 📨 Review VOX Evening Brief (auto-sent 6 PM)
9. 📝 Update trade journal with today's actions

======================================================================
EXACT EXECUTION DETAILS:
======================================================================

SELL — JMIA (URGENT)
├─ Broker: eToro
├─ Action: Sell 200 shares
├─ Order Type: Market (thesis broken, exit now)
├─ Expected Cash: ~$585
└─ Do This: Tuesday morning first thing

SELL — OKLO (ON BOUNCE)
├─ Broker: Schwab
├─ Action: Sell 25 shares when price ≥ $18
├─ Order Type: Limit at $18
├─ Expected Cash: ~$450
└─ Do This: Set alert, wait for bounce

BUY — CEG (ADD)
├─ Broker: Schwab
├─ Action: Buy to reach 2% position (~$3,900 total)
├─ Current: $407 (0.2%)
├─ Need to add: ~$3,500
├─ Order Type: Market or limit at current price
└─ Do This: Tuesday or Wednesday

BUY — DELL (PULLBACK)
├─ Broker: Schwab
├─ Action: Buy 2% position when price ≤ $280
├─ Shares: ~14 shares @ $280
├─ Order Type: Limit at $280
├─ Stop: $258 (8% below)
└─ Do This: Wait for alert, then execute

BUY — AMAT (PULLBACK)
├─ Broker: Schwab
├─ Action: Buy 2% position when price ≤ $415
├─ Shares: ~9 shares @ $415
├─ Order Type: Limit at $415
├─ Stop: $382 (8% below)
└─ Do This: Wait for alert, then execute

HOLD — OSCR, POET, VOO, AAPL, MSFT, etc.
└─ No action. Monitor grades daily.

======================================================================
CASH FLOW PLAN:
======================================================================

From Sells:
  JMIA:    +$585
  OKLO:    +$450 (when bounces)
  ─────────────────
  Total:   +$1,035

To Buys:
  CEG add: -$3,500 (from existing cash + sells)
  DELL:    -$3,900 (when pullback hits)
  AMAT:    -$3,900 (when pullback hits)
  ─────────────────
  Total needed: -$11,300

You need ~$10,300 additional cash for all buys.
Options:
  1. Use existing cash in Schwab
  2. Transfer from eToro after JMIA sell
  3. Add new deposit

======================================================================
"""
    print(plan)
    send_telegram_message(plan)


def main():
    run_alert_system()


if __name__ == "__main__":
    main()
