#!/usr/bin/env python3
"""
VOX Telegram Alert System v1.0
Sends real-time alerts for plays, grade changes, and system events

Usage:
    python3 vox_telegram_alerts.py --play NVDA BUY 78 "Earnings setup"
    python3 vox_telegram_alerts.py --alert "CRITICAL" "NVDA grade dropped to 35"
    python3 vox_telegram_alerts.py --daily --file vox_daily_brief.json
    python3 vox_telegram_alerts.py --plays --file vox_generated_plays.json
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime

# Load Telegram config from .env
def load_telegram_config():
    env_paths = [
        os.path.expanduser("~/.hermes/.env"),
        os.path.expanduser("~/.hermes/scripts/.env"),
        os.path.expanduser("~/.env"),
    ]
    config = {}
    for path in env_paths:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '=' in line:
                        k, v = line.strip().split('=', 1)
                        config[k] = v.strip().strip('"').strip("'")
    return config

CONFIG = load_telegram_config()
BOT_TOKEN = CONFIG.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = CONFIG.get('TELEGRAM_CHAT_ID') or CONFIG.get('TELEGRAM_HOME_CHANNEL')


def send_telegram_message(message: str, parse_mode="Markdown"):
    """Send message via Telegram Bot API"""
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: TELEGRAM_BOT_TOKEN or CHAT_ID not found in .env")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }).encode()
    
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get('ok'):
                print(f"✅ Message sent to Telegram")
                return True
            else:
                print(f"❌ Telegram error: {result}")
                return False
    except Exception as e:
        print(f"❌ Failed to send: {e}")
        return False


def format_play_alert(play: dict) -> str:
    """Format a play as a Telegram message"""
    emoji = {
        "BUY": "🟢",
        "SELL": "🔴",
        "TRIM": "🟡",
        "HOLD": "⚪",
        "WATCH": "🔵"
    }.get(play.get('type', ''), '⚪')
    
    conviction = play.get('conviction', 'SPEC')
    conv_emoji = "💎" if conviction == "CORE" else "🎯"
    
    msg = f"""{emoji} *VOX PLAY ALERT*

*{play.get('ticker', 'UNKNOWN')}* — {play.get('type', 'UNKNOWN')}
{conv_emoji} Conviction: {conviction}
📊 Confidence: {play.get('confidence', 0):.0f}/100

*Thesis:*
{play.get('thesis', 'No thesis')}

"""
    
    if play.get('entry_price'):
        msg += f"💰 Entry: `${play['entry_price']:.2f}`\n"
    if play.get('stop_loss'):
        msg += f"🛑 Stop: `${play['stop_loss']:.2f}`\n"
    if play.get('target_price'):
        msg += f"🎯 Target: `${play['target_price']:.2f}`\n"
    
    if play.get('catalysts'):
        msg += f"\n📈 Catalysts: {', '.join(play['catalysts'])}"
    if play.get('risks'):
        msg += f"\n⚠️ Risks: {', '.join(play['risks'])}"
    
    msg += f"\n\n_Signals: {', '.join(play.get('source_signals', []))}_"
    msg += f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_"
    
    return msg


def format_grade_alert(ticker: str, old_grade: int, new_grade: int) -> str:
    """Format a grade change alert"""
    diff = new_grade - old_grade
    emoji = "📈" if diff > 0 else "📉"
    severity = "🔴 CRITICAL" if new_grade < 40 else "🟡 WARNING" if new_grade < 55 else "🟢 INFO"
    
    return f"""{emoji} *GRADE CHANGE ALERT*

*{ticker}*
{severity}

Grade: {old_grade} → {new_grade} ({diff:+.0f})

_Action: {'SELL' if new_grade < 40 else 'TRIM' if new_grade < 55 else 'HOLD' if new_grade < 70 else 'BUY'}_
_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_
"""


def format_daily_brief(brief: dict) -> str:
    """Format daily briefing"""
    portfolio = brief.get('portfolio', {})
    recommendations = brief.get('recommendations', [])
    alerts = brief.get('alerts', [])
    
    msg = f"""📋 *VOX DAILY BRIEFING*
_{datetime.now().strftime('%A, %B %d, %Y')}_

💰 Portfolio: `${portfolio.get('total_value', 0):,.0f}`
📊 P&L: `${portfolio.get('total_pnl', 0):,.0f}`
📈 Positions: {portfolio.get('positions_count', 0)}

"""
    
    if recommendations:
        msg += "*Top Recommendations:*\n"
        for r in recommendations[:5]:
            emoji = "🟢" if r.get('action') == 'BUY' else "🔴" if r.get('action') == 'SELL' else "🟡"
            msg += f"{emoji} {r.get('action')}: *{r.get('ticker')}* — {r.get('reason')}\n"
        msg += "\n"
    
    if alerts:
        msg += "*Active Alerts:*\n"
        for a in alerts[:5]:
            emoji = "🔴" if a.get('severity') == 'HIGH' else "🟡"
            msg += f"{emoji} {a.get('ticker')}: {a.get('message')}\n"
    
    msg += f"\n[Open Dashboard](https://vox-dashboard-five.vercel.app)"
    
    return msg


def send_play_alert(play: dict):
    """Send a single play alert"""
    msg = format_play_alert(play)
    return send_telegram_message(msg)


def send_plays_from_file(filepath: str, min_confidence: float = 60):
    """Send all high-confidence plays from a file"""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    
    with open(filepath) as f:
        plays = json.load(f)
    
    if not isinstance(plays, list):
        print("Invalid plays file format")
        return
    
    # Filter high-confidence plays
    high_conf = [p for p in plays if p.get('confidence', 0) >= min_confidence]
    
    if not high_conf:
        print(f"No plays above {min_confidence} confidence")
        return
    
    # Send summary first
    summary = f"""🎯 *VOX PLAY DISCOVERY*

Found {len(high_conf)} high-confidence plays:

"""
    for p in high_conf[:10]:
        emoji = {"BUY": "🟢", "SELL": "🔴", "TRIM": "🟡"}.get(p.get('type'), '⚪')
        summary += f"{emoji} {p.get('type')}: *{p.get('ticker')}* ({p.get('confidence', 0):.0f}%)\n"
    
    summary += f"\n_Details below..._"
    send_telegram_message(summary)
    
    # Send individual plays
    for play in high_conf[:5]:  # Limit to top 5
        send_play_alert(play)
    
    print(f"Sent {min(len(high_conf), 5)} play alerts")


def send_daily_brief(filepath: str):
    """Send daily briefing"""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    
    with open(filepath) as f:
        brief = json.load(f)
    
    msg = format_daily_brief(brief)
    send_telegram_message(msg)
    print("Daily brief sent")


def main():
    parser = argparse.ArgumentParser(description="VOX Telegram Alerts")
    parser.add_argument("--play", nargs=4, metavar=("TICKER", "TYPE", "CONFIDENCE", "THESIS"),
                        help="Send single play alert")
    parser.add_argument("--grade-change", nargs=3, metavar=("TICKER", "OLD", "NEW"),
                        help="Send grade change alert")
    parser.add_argument("--alert", nargs=2, metavar=("SEVERITY", "MESSAGE"),
                        help="Send custom alert")
    parser.add_argument("--plays", action="store_true", help="Send plays from file")
    parser.add_argument("--daily", action="store_true", help="Send daily brief")
    parser.add_argument("--file", help="Input JSON file")
    parser.add_argument("--min-confidence", type=float, default=60, help="Minimum confidence for plays")
    
    args = parser.parse_args()
    
    if args.play:
        play = {
            "ticker": args.play[0],
            "type": args.play[1],
            "confidence": float(args.play[2]),
            "thesis": args.play[3],
            "conviction": "SPEC",
            "source_signals": ["manual"]
        }
        send_play_alert(play)
    
    elif args.grade_change:
        msg = format_grade_alert(args.grade_change[0], int(args.grade_change[1]), int(args.grade_change[2]))
        send_telegram_message(msg)
    
    elif args.alert:
        emoji = "🔴" if args.alert[0] == "CRITICAL" else "🟡" if args.alert[0] == "WARNING" else "🟢"
        msg = f"""{emoji} *VOX ALERT* — {args.alert[0]}

{args.alert[1]}

_{datetime.now().strftime('%Y-%m-%d %H:%M')}_"""
        send_telegram_message(msg)
    
    elif args.plays:
        filepath = args.file or os.path.expanduser("~/.hermes/scripts/vox_generated_plays.json")
        send_plays_from_file(filepath, args.min_confidence)
    
    elif args.daily:
        filepath = args.file or os.path.expanduser("~/.hermes/scripts/vox_daily_brief.json")
        send_daily_brief(filepath)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
