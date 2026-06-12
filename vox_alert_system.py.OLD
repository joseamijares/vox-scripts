#!/usr/bin/env python3
"""
Vox Alert System — JOS-26
Bridges grade system → Telegram alerts for manual execution.
Phase 1: Alert only. Phase 2: One-click execute.
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


def get_current_price(ticker):
    """Fetch current price from Polygon to validate alert freshness."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return None
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            results = data.get("results", [])
            if results:
                return results[0].get("c", None)
    except:
        pass
    return None


def send_telegram_message(message):
    """Send a message via Telegram bot."""
    env = load_env()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        print(f"Message would be:\n{message}")
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


def check_grade_alerts():
    """Check grade_results.json for new alerts."""
    grade_path = Path.home() / ".hermes" / "scripts" / "grade_results.json"
    if not grade_path.exists():
        return []

    try:
        with open(grade_path) as f:
            data = json.load(f)
    except:
        return []

    alerts = []
    for grade in data.get("grades", []):
        score = grade.get("total_grade", 0)
        ticker = grade.get("ticker", "")
        rec = grade.get("recommendation", "")
        
        # Skip stale grades (older than 24 hours)
        grade_time = grade.get("timestamp", "")
        if grade_time:
            try:
                gt = datetime.fromisoformat(grade_time.replace("Z", "+00:00"))
                if datetime.now(gt.tzinfo) - gt > timedelta(hours=24):
                    continue  # Skip stale grades
            except:
                pass

        if score >= 85 and "BUY" in rec:
            alerts.append({
                "type": "ENTRY",
                "ticker": ticker,
                "score": score,
                "message": format_entry_alert(grade)
            })
        elif score < 50 and "AVOID" in rec:
            alerts.append({
                "type": "EXIT",
                "ticker": ticker,
                "score": score,
                "message": format_exit_alert(grade)
            })

    return alerts


def format_entry_alert(grade):
    """Format a buy alert with real-time price validation."""
    ticker = grade["ticker"]
    score = grade["total_grade"]
    grade_price = grade["price"]
    grade_time = grade.get("timestamp", "")
    action = grade["action"]

    # Fetch current price
    current_price = get_current_price(ticker)
    
    # Price validation
    price_warning = ""
    if current_price:
        price_diff = abs(current_price - grade_price) / grade_price * 100
        if price_diff > 2:
            price_warning = f"\n⚠️ PRICE CHANGED: Grade was at ${grade_price:.2f}, now ${current_price:.2f} ({price_diff:+.1f}%)\n🔄 RECOMMENDATION: Re-run grade before trading!"
    else:
        price_warning = "\n⚠️ Could not fetch current price. Verify before trading."

    # Time freshness
    time_warning = ""
    if grade_time:
        try:
            gt = datetime.fromisoformat(grade_time.replace("Z", "+00:00"))
            age_hours = (datetime.now(gt.tzinfo) - gt).total_seconds() / 3600
            if age_hours > 1:
                time_warning = f"\n⏰ Grade is {age_hours:.0f} hours old. Market conditions may have changed."
        except:
            pass

    breakdown = grade.get("breakdown", {})

    msg = f"""🚨 *VOX ALERT: STRONG BUY*

📈 *{ticker}* — Grade: *{score}/100*
💰 Grade Price: ${grade_price:.2f}
📊 Current Price: ${current_price:.2f if current_price else "N/A"}

*{action}*{price_warning}{time_warning}

*Grade Breakdown:*
"""
    for pillar, data in breakdown.items():
        name = pillar.replace("_", " ").title()
        msg += f"• {name}: {data['score']}/{data['max']}\n"

    msg += f"""
*Next Steps:*
1. Re-run grade: `python3 grade_system.py {ticker}`
2. Run position sizer with CURRENT price
3. Confirm entry and execute

_This is an alert, not financial advice. Prices change — verify before trading._
"""
    return msg


def format_exit_alert(grade):
    """Format an exit alert."""
    ticker = grade["ticker"]
    score = grade["total_grade"]
    price = grade["price"]
    grade_time = grade.get("timestamp", "")

    # Time freshness
    time_warning = ""
    if grade_time:
        try:
            gt = datetime.fromisoformat(grade_time.replace("Z", "+00:00"))
            age_hours = (datetime.now(gt.tzinfo) - gt).total_seconds() / 3600
            if age_hours > 1:
                time_warning = f"\n⏰ Grade is {age_hours:.0f} hours old."
        except:
            pass

    msg = f"""⚠️ *VOX ALERT: CONSIDER EXIT*

📉 *{ticker}* — Grade dropped to *{score}/100*
💰 Price at grade: ${price:.2f}{time_warning}

*Reason:* Grade below 50 — fundamentals/technical no longer aligned.

*Action:* Review position. Consider:
• Trailing stop at breakeven
• Partial exit (50%)
• Full exit if thesis broken

_Check your trade journal for original entry._
"""
    return msg


def check_trump_alerts():
    """Check trump tracker for high-impact policy alerts."""
    trump_path = Path.home() / ".hermes" / "scripts" / "trump_tracker_results.json"
    if not trump_path.exists():
        return []

    try:
        with open(trump_path) as f:
            data = json.load(f)
    except:
        return []

    alerts = []
    for tweet in data.get("tweets", []):
        impact = tweet["classification"]["impact_score"]
        if impact >= 7:
            sectors = ", ".join(tweet.get("affected_sectors", []))
            msg = f"""🔴 *POLICY ALERT*

Trump tweet — *HIGH IMPACT* ({impact}/10)

{tweet['text'][:200]}{'...' if len(tweet['text']) > 200 else ''}

*Affected sectors:* {sectors}

*Action:* Review positions in these sectors.
"""
            alerts.append({
                "type": "POLICY",
                "message": msg
            })

    return alerts


def run_alert_system():
    """Main alert runner."""
    print(f"{'='*70}")
    print("🔔 VOX ALERT SYSTEM")
    print(f"{'='*70}")
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_alerts = []

    # Check grades
    grade_alerts = check_grade_alerts()
    all_alerts.extend(grade_alerts)
    print(f"Grade alerts: {len(grade_alerts)}")

    # Check Trump tweets
    trump_alerts = check_trump_alerts()
    all_alerts.extend(trump_alerts)
    print(f"Policy alerts: {len(trump_alerts)}")

    # Send alerts
    sent = 0
    for alert in all_alerts:
        print(f"\n{'='*70}")
        print(f"ALERT: {alert['type']}")
        print(f"{'='*70}")
        print(alert['message'])

        # In Phase 1, just print. Phase 2 will send Telegram.
        # Uncomment when Telegram is configured:
        # if send_telegram_message(alert['message']):
        #     sent += 1

    print(f"\n{'='*70}")
    print(f"Total alerts: {len(all_alerts)}")
    print(f"Sent: {sent}")
    print(f"{'='*70}")

    return all_alerts


def main():
    run_alert_system()


if __name__ == "__main__":
    main()
