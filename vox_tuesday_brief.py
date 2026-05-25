#!/usr/bin/env python3
"""
VOX Tuesday Action Brief — May 27, 2026
Single-file executable brief with exact actions.
"""

import json
from pathlib import Path
from datetime import datetime

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

def send_telegram_message(message):
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        print(f"⚠️ Telegram not configured\n{message}")
        return False
    import urllib.request
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

def main():
    brief = f"""🎯 *VOX TUESDAY BRIEF — May 27, 2026*

⏰ Market opens 9:30 AM ET (holiday Monday, so this is first trading day of week)

═══════════════════════════════════════
🔴 *URGENT: SELL TODAY*
═══════════════════════════════════════

*JMIA — SELL ALL*
├─ Broker: eToro
├─ Shares: 200
├─ Current Price: ~$6.97
├─ Expected Cash: ~$1,394
├─ Order: MARKET (exit now)
└─ Why: Grade 41, thesis broken, -68% loss

*ACTION:* Open eToro → Sell 200 shares JMIA → Market order

═══════════════════════════════════════
🟡 *SET ALERTS TODAY*
═══════════════════════════════════════

*OKLO — SELL ON BOUNCE*
├─ Broker: Schwab
├─ Shares: 25
├─ Target: $18.00+
├─ Expected Cash: ~$450
└─ Why: Grade 49, swap to CEG eventually

*ACTION:* Set price alert at $18.00 in Schwab

═══════════════════════════════════════
🟢 *BUY TODAY (If Cash Available)*
═══════════════════════════════════════

*CEG — ADD TO POSITION*
├─ Broker: Schwab
├─ Current: $407 (0.2%)
├─ Target: $3,920 (2.0%)
├─ Need to add: ~$3,500
├─ Current Price: ~$294
├─ Shares to buy: ~12
├─ Order: Market or limit at $294
└─ Stop: $270 (8% below)

*ACTION:* Open Schwab → Buy 12 shares CEG → Set stop at $270

═══════════════════════════════════════
⏳ *WAIT FOR PULLBACK (Set Alerts)*
═══════════════════════════════════════

*DELL — Buy below $280*
├─ Target: 2% position (~$3,900)
├─ Shares: ~14 @ $280
├─ Stop: $258
└─ Why: Grade 67, RSI 76 overbought, wait for cooldown

*AMAT — Buy below $415*
├─ Target: 2% position (~$3,900)
├─ Shares: ~9 @ $415
├─ Stop: $382
└─ Why: Grade 63, buy at EMA21 support

*LLY — Buy below $960*
├─ Target: 1.5% position (~$2,900)
├─ Shares: ~3 @ $960
├─ Stop: $883
└─ Why: Grade 66, GLP-1 leader, 10% pullback

*ACTION:* Set price alerts in Schwab for all three

═══════════════════════════════════════
📋 *HOLD — NO ACTION*
═══════════════════════════════════════

• OSCR — Grade 52, wait June 12 earnings
• POET — Grade 58, 0.3% speculative, thesis intact
• VOO, AAPL, MSFT, CRWD, TSLA, AMD, etc.

═══════════════════════════════════════
💰 *CASH FLOW*
═══════════════════════════════════════

From Sells:     +$1,394 (JMIA)
                +$450  (OKLO, when bounces)
                ─────────
                +$1,844

For CEG Add:    -$3,500
For DELL:       -$3,900 (when hits)
For AMAT:       -$3,900 (when hits)
                ─────────
                -$11,300

*You need ~$9,500 more cash for all buys.*
Options:
1. Use existing Schwab cash
2. Transfer from eToro after JMIA sell
3. Add new deposit

═══════════════════════════════════════
📅 *TUESDAY SCHEDULE*
═══════════════════════════════════════

08:00 AM → VOX Morning Brief (auto)
09:30 AM → 🔴 SELL JMIA
10:00 AM → Set OKLO alert at $18
12:00 PM → VOX Intraday Check (auto)
03:00 PM → Set DELL/AMAT/LLY alerts
04:00 PM → Market close
04:30 PM → VOX Evening Brief (auto)
06:00 PM → VOX Suggested Plays (auto)

═══════════════════════════════════════
_This is your only job today: Sell JMIA, add CEG, set alerts._
"""
    print(brief)
    send_telegram_message(brief)

if __name__ == "__main__":
    main()
