#!/usr/bin/env python3
"""
Vox Telegram Bot Handler
Sends alerts and receives commands from Jose.
"""

import os
import json
import urllib.request
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


def send_telegram_message(message, parse_mode="Markdown"):
    """Send a message via Telegram bot."""
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        print("⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        print(f"Message would be:\n{message}")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
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


def send_grade_alert(ticker, grade_data):
    """Send a grade-based buy/exit alert."""
    score = grade_data.get("total_grade", 0)
    price = grade_data.get("price", 0)
    rec = grade_data.get("recommendation", "")
    action = grade_data.get("action", "")
    breakdown = grade_data.get("breakdown", {})

    emoji = "🟢" if score >= 85 else "🟡" if score >= 70 else "⚪" if score >= 55 else "🔴"

    msg = f"""{emoji} *VOX ALERT: {ticker}*

📊 Grade: *{score}/100*
💰 Price: ${price:.2f}
📋 {rec}

*{action}*

*Breakdown:*
"""
    for pillar, data in breakdown.items():
        name = pillar.replace("_", " ").title()
        msg += f"• {name}: {data['score']}/{data['max']}\n"

    msg += f"""
*Commands:*
`/grade {ticker}` — Re-run grade
`/size {ticker} {price:.2f} <stop> <target>` — Position size
`/buy {ticker} <qty>` — Execute via Alpaca

_This is an alert, not financial advice._
"""
    return send_telegram_message(msg)


def send_policy_alert(tweet_data):
    """Send a Trump/policy alert."""
    text = tweet_data.get("text", "")[:200]
    impact = tweet_data["classification"]["impact_score"]
    sectors = ", ".join(tweet_data.get("affected_sectors", [])[:5])

    msg = f"""🔴 *POLICY ALERT*

Trump tweet — Impact: *{impact}/10*

{text}{'...' if len(tweet_data.get('text', '')) > 200 else ''}

*Sectors:* {sectors}

*Action:* Review positions in affected sectors.
"""
    return send_telegram_message(msg)


def send_portfolio_summary():
    """Send portfolio summary."""
    portfolio_path = Path.home() / ".hermes" / "scripts" / "unified_portfolio.json"
    if not portfolio_path.exists():
        return send_telegram_message("⚠️ No portfolio data found.")

    try:
        with open(portfolio_path) as f:
            data = json.load(f)
    except:
        return send_telegram_message("⚠️ Error reading portfolio data.")

    total = data.get("total_aum_usd", 0)
    brokers = data.get("brokers", {})

    msg = f"""📊 *PORTFOLIO SUMMARY*

💰 Total AUM: *${total:,.0f}*

*By Broker:*
"""
    for name, info in brokers.items():
        value = info.get("value_usd", 0)
        pct = value / total * 100 if total > 0 else 0
        msg += f"• {name}: ${value:,.0f} ({pct:.1f}%)\n"

    msg += f"""
_Last updated: {data.get('timestamp', 'unknown')}_
"""
    return send_telegram_message(msg)


def test_telegram():
    """Test Telegram connection."""
    print("=" * 70)
    print("📱 TELEGRAM BOT TEST")
    print("=" * 70)

    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")

    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        print("   1. Message @BotFather on Telegram")
        print("   2. Create new bot")
        print("   3. Copy the token")
        print("   4. Add to ~/.hermes/.env: TELEGRAM_BOT_TOKEN=your_token")
        return False

    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID not set")
        print("   1. Message @userinfobot on Telegram")
        print("   2. Copy your chat ID")
        print("   3. Add to ~/.hermes/.env: TELEGRAM_CHAT_ID=your_id")
        return False

    print(f"Bot token: {bot_token[:10]}...")
    print(f"Chat ID: {chat_id}")
    print()

    # Test message
    success = send_telegram_message(
        "🧪 *Vox Bot Test*\n\nIf you see this, Telegram alerts are working! ✅\n\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        parse_mode="Markdown"
    )

    if success:
        print("✅ Test message sent successfully!")
    else:
        print("❌ Failed to send test message")
        print("   Check bot token and chat ID are correct")

    return success


def main():
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "test":
            test_telegram()
        elif cmd == "portfolio":
            send_portfolio_summary()
        else:
            print("Usage:")
            print("  python3 telegram_bot.py test")
            print("  python3 telegram_bot.py portfolio")
    else:
        test_telegram()


if __name__ == "__main__":
    main()
