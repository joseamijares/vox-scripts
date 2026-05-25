#!/usr/bin/env python3
"""
Vox Pullback Alert System — JOS-27
Auto-triggers when overbought stocks cool off to buy zones.
"""

import os
import json
import urllib.request
import time
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


def get_daily_bars(ticker, days=60):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        return []
    return result.get("results", [])


def get_current_price(ticker):
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/prev")
    if "error" in result:
        return None
    results = result.get("results", [])
    if results:
        return results[0].get("c", None)
    return None


def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def send_telegram_message(message):
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        print(f"⚠️ Telegram not configured\n{message}")
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
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


# ============ PULLBACK WATCHLIST ============
# Stocks we want to buy on pullback with trigger levels

PULLBACK_WATCHLIST = {
    # High-grade stocks waiting for better entry
    "DELL": {
        "grade": 67,
        "target_rsi": 65,
        "target_price": 280.00,
        "position_pct": 2.0,
        "broker": "Schwab",
        "reason": "AI servers, grade 67, wait for RSI cooldown from 76"
    },
    "AMAT": {
        "grade": 63,
        "target_rsi": 60,
        "target_price": 415.00,
        "position_pct": 2.0,
        "broker": "Schwab",
        "reason": "Semiconductor equipment, buy at EMA21"
    },
    "LLY": {
        "grade": 66,
        "target_rsi": 60,
        "target_price": 960.00,
        "position_pct": 1.5,
        "broker": "Schwab",
        "reason": "GLP-1 leader, 10% pullback entry"
    },
    "PANW": {
        "grade": 65,
        "target_rsi": 60,
        "target_price": 180.00,
        "position_pct": 2.0,
        "broker": "Schwab",
        "reason": "Cybersecurity leader, RSI 84 extremely overbought"
    },
    "NVDA": {
        "grade": 64,
        "target_rsi": 60,
        "target_price": 380.00,
        "position_pct": 3.0,
        "broker": "Schwab",
        "reason": "AI chip leader, wait for pullback to EMA21"
    },
    "MU": {
        "grade": 60,
        "target_rsi": 55,
        "target_price": 85.00,
        "position_pct": 2.0,
        "broker": "Schwab",
        "reason": "Memory cycle recovery, buy on weakness"
    },
    "IONQ": {
        "grade": 60,
        "target_rsi": 55,
        "target_price": 28.00,
        "position_pct": 1.0,
        "broker": "Schwab",
        "reason": "Quantum computing speculative, tight risk"
    },
    "RKLB": {
        "grade": 58,
        "target_rsi": 55,
        "target_price": 22.00,
        "position_pct": 1.0,
        "broker": "Schwab",
        "reason": "Space launch, wait for pullback"
    }
}


def check_pullback_alerts():
    """Check if any watchlist stocks hit pullback triggers."""
    alerts = []
    
    for ticker, config in PULLBACK_WATCHLIST.items():
        print(f"Checking {ticker}...")
        time.sleep(0.5)  # Rate limit: 2 requests per second
        
        bars = get_daily_bars(ticker, days=60)
        if not bars:
            print(f"  ⚠️ No data for {ticker}")
            continue
        
        closes = [bar["c"] for bar in bars]
        current_price = closes[-1]
        rsi = calculate_rsi(closes)
        ema21 = calculate_ema(closes, 21)
        
        print(f"  Price: ${current_price:.2f} | RSI: {rsi:.1f} | EMA21: ${ema21:.2f}" if ema21 else f"  Price: ${current_price:.2f} | RSI: {rsi:.1f} | EMA21: N/A")
        
        target_rsi = config["target_rsi"]
        target_price = config["target_price"]
        
        triggered = False
        trigger_reason = ""
        
        # Trigger 1: RSI cooled off
        if rsi and rsi <= target_rsi:
            triggered = True
            trigger_reason = f"RSI cooled to {rsi:.1f} (target: {target_rsi})"
        
        # Trigger 2: Price hit target
        if current_price <= target_price:
            triggered = True
            trigger_reason = f"Price ${current_price:.2f} hit target ${target_price:.2f}"
        
        # Trigger 3: Price at EMA21 (dynamic)
        if ema21 and current_price <= ema21 * 1.02:
            triggered = True
            trigger_reason = f"Price at EMA21 ${ema21:.2f}"
        
        if triggered:
            portfolio = 196000
            position_pct = config["position_pct"]
            position_value = portfolio * (position_pct / 100)
            shares = int(position_value / current_price)
            
            alerts.append({
                "ticker": ticker,
                "current_price": current_price,
                "rsi": rsi,
                "ema21": ema21,
                "target_rsi": target_rsi,
                "target_price": target_price,
                "grade": config["grade"],
                "broker": config["broker"],
                "shares": shares,
                "position_value": position_value,
                "position_pct": position_pct,
                "reason": config["reason"],
                "trigger_reason": trigger_reason
            })
    
    return alerts


def format_pullback_alert(alert):
    """Format a pullback buy alert."""
    ticker = alert["ticker"]
    price = alert["current_price"]
    rsi = alert["rsi"]
    ema21 = alert["ema21"]
    grade = alert["grade"]
    shares = alert["shares"]
    value = alert["position_value"]
    broker = alert["broker"]
    
    msg = f"""🎯 *VOX PULLBACK ALERT — BUY NOW*

📈 *{ticker}* — Pullback Triggered!
💰 Current Price: ${price:.2f}
📊 RSI: {rsi:.1f} (cooled off)
📈 EMA21: ${ema21:.2f}""" if ema21 else f"""🎯 *VOX PULLBACK ALERT — BUY NOW*

📈 *{ticker}* — Pullback Triggered!
💰 Current Price: ${price:.2f}
📊 RSI: {rsi:.1f} (cooled off)
📈 EMA21: N/A"""
    
    msg += f"""
🏆 Grade: {grade}/100

*TRIGGER:*
{alert['trigger_reason']}

*WHY:*
{alert['reason']}

*EXACT ACTION:*
1. Open {broker}
2. Buy {shares} shares of {ticker}
3. Limit order at ${price:.2f}
4. Set stop loss at ${price * 0.92:.2f} (8% below)

*POSITION SIZE:*
• ${value:,.2f} ({alert['position_pct']}% of portfolio)
• {shares} shares @ ~${price:.2f}

*RISK:*
• Stop: ${price * 0.92:.2f}
• Max loss: ${value * 0.08:,.2f}

_This is a pullback entry. Execute within 24 hours or price may move._
"""
    return msg


def run_pullback_scan():
    """Main pullback scanner."""
    print(f"{'='*70}")
    print("🎯 VOX PULLBACK ALERT SYSTEM")
    print(f"{'='*70}")
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Watching {len(PULLBACK_WATCHLIST)} stocks for pullback entries")
    print()
    
    alerts = check_pullback_alerts()
    
    print(f"\n{'='*70}")
    print(f"Pullback alerts triggered: {len(alerts)}")
    print(f"{'='*70}")
    
    for alert in alerts:
        msg = format_pullback_alert(alert)
        print(f"\n{'='*70}")
        print(f"ALERT: {alert['ticker']}")
        print(f"{'='*70}")
        print(msg)
        send_telegram_message(msg)
    
    if not alerts:
        print("\nNo pullback alerts today.")
        print("Market still extended. Waiting for better entries.")
    
    return alerts


def main():
    run_pullback_scan()


if __name__ == "__main__":
    main()
