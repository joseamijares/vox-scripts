#!/usr/bin/env python3
"""
VOX Smart Alert System v7 — Only What Changed

Rules:
1. NEVER repeat the same alert within 24h
2. Only alert on NEW information (price moved, news broke, grade changed)
3. No static grade alerts — grades don't change every 3 hours
4. Critical only: stops, massive moves (>10%), news, Trump
5. Daily digest at close — everything else in one message
6. Max 3 alerts/day, max 1 per ticker

Alert Types:
- STOP: User-defined stop hit (immediate, no cooldown)
- MOVE: >10% daily move (once per day)
- NEWS: Breaking news affecting position (once per event)
- TRUMP: Trump mention of portfolio ticker (immediate)
- DIGEST: Daily summary at 4 PM ET (always)
"""

import json
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
ALERT_STATE_FILE = SCRIPT_DIR / ".vox_alert_state_v7.json"

POSITIONS_FILE = SCRIPT_DIR / "dashboard_positions_live.json"
GRADES_FILE = SCRIPT_DIR / "portfolio_grades.json"
COUNCIL_FILE = SCRIPT_DIR / "vox_council_votes.json"
NEWS_FILE = SCRIPT_DIR / "vox_news_digest.json"

PROTECTED_TICKERS = {"SHOP"}
USER_STOPS = {"PLTR": 115.00}

# Only alert on significant moves
MIN_MOVE_PCT = 10  # 10% daily move
MIN_POSITION_VALUE = 500
MAX_DAILY_ALERTS = 3

def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v
    return keys

def send_telegram(message: str) -> bool:
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print(f"[TELEGRAM NOT CONFIGURED]\n{message}")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
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
        print(f"Telegram error: {e}")
        return False

def load_state() -> dict:
    if ALERT_STATE_FILE.exists():
        with open(ALERT_STATE_FILE) as f:
            return json.load(f)
    return {
        "sent_alerts": {},  # alert_id -> {sent_at, ticker, type}
        "daily_count": 0,
        "last_reset": datetime.now(timezone.utc).isoformat(),
        "last_prices": {},  # ticker -> price (for detecting new moves)
        "version": 7
    }

def save_state(state: dict):
    with open(ALERT_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def alert_hash(alert_type: str, ticker: str, detail: str = "") -> str:
    content = f"{alert_type}:{ticker}:{detail}"
    return hashlib.md5(content.encode()).hexdigest()[:16]

def can_alert(state: dict, alert_id: str, ticker: str, cooldown_hours: int = 24) -> bool:
    """Check if alert can be sent."""
    # Check daily limit
    last_reset = datetime.fromisoformat(state.get("last_reset", "2000-01-01T00:00:00+00:00"))
    if datetime.now(timezone.utc) - last_reset > timedelta(days=1):
        state["daily_count"] = 0
        state["last_reset"] = datetime.now(timezone.utc).isoformat()
    
    if state.get("daily_count", 0) >= MAX_DAILY_ALERTS:
        return False
    
    # Check if we already alerted on this ticker today
    sent_alerts = state.get("sent_alerts", {})
    for alert_data in sent_alerts.values():
        if alert_data.get("ticker") == ticker:
            sent_at = datetime.fromisoformat(alert_data["sent_at"])
            if datetime.now(timezone.utc) - sent_at < timedelta(hours=cooldown_hours):
                return False
    
    return True

def record_alert(state: dict, alert_id: str, ticker: str, alert_type: str):
    state.setdefault("sent_alerts", {})[alert_id] = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "type": alert_type
    }
    state["daily_count"] = state.get("daily_count", 0) + 1

def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def load_portfolio() -> List[Dict]:
    data = load_json(POSITIONS_FILE, {})
    positions = data.get("positions", [])
    return [p for p in positions if (p.get("live_value") or p.get("value", 0) or 0) > 100]

def check_stop_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """CRITICAL: User-defined stops. No cooldown."""
    alerts = []
    
    for pos in positions:
        ticker = pos.get("ticker", "")
        live_price = pos.get("live_price", 0)
        
        user_stop = USER_STOPS.get(ticker)
        if user_stop and live_price > 0 and live_price <= user_stop:
            alert_id = alert_hash("STOP", ticker, f"stop_{user_stop}")
            # Stops have NO cooldown - always alert
            if state.get("daily_count", 0) < MAX_DAILY_ALERTS:
                alerts.append({
                    "id": alert_id,
                    "priority": "CRITICAL",
                    "type": "STOP",
                    "ticker": ticker,
                    "message": f"🛑 *STOP HIT — {ticker}*\n\nYour stop at *${user_stop:.2f}* triggered.\nCurrent: *${live_price:.2f}*\n\n*Action:* SELL NOW."
                })
    
    return alerts

def check_move_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """ALERT: >10% daily move. Once per ticker per day."""
    alerts = []
    last_prices = state.get("last_prices", {})
    
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in PROTECTED_TICKERS:
            continue
        
        change_pct = pos.get("price_change_pct", 0)
        live_price = pos.get("live_price", 0)
        value = pos.get("live_value") or pos.get("value", 0) or 0
        
        # Only alert on significant moves
        if abs(change_pct) < MIN_MOVE_PCT:
            continue
        
        # Skip if already alerted today
        alert_id = alert_hash("MOVE", ticker, f"move_{change_pct:+.1f}")
        if not can_alert(state, alert_id, ticker, 24):
            continue
        
        emoji = "🚀" if change_pct > 0 else "🔻"
        action = "Review for trim." if change_pct > 0 else "Check thesis."
        
        alerts.append({
            "id": alert_id,
            "priority": "HIGH",
            "type": "MOVE",
            "ticker": ticker,
            "message": f"""{emoji} *BIG MOVE — {ticker}*

Daily: *{change_pct:+.1f}%*
Price: ${live_price:.2f}
Position: ${value:,.0f}

*Action:* {action}"""
        })
    
    return alerts

def check_news_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """ALERT: Breaking news with relevance >80."""
    alerts = []
    portfolio_tickers = {p.get("ticker", "") for p in positions}
    news_data = load_json(NEWS_FILE, {})
    
    for headline in news_data.get("portfolio_impact", []):
        ticker = headline.get("ticker", "")
        if ticker not in portfolio_tickers:
            continue
        
        score = headline.get("relevance_score", 0)
        title = headline.get("title", "")
        
        # Only high-relevance news
        if score < 80:
            continue
        
        alert_id = alert_hash("NEWS", ticker, f"news_{title[:40]}")
        if not can_alert(state, alert_id, ticker, 12):
            continue
        
        pos = next((p for p in positions if p.get("ticker") == ticker), {})
        value = pos.get("live_value") or pos.get("value", 0) or 0
        
        alerts.append({
            "id": alert_id,
            "priority": "HIGH",
            "type": "NEWS",
            "ticker": ticker,
            "message": f"""📰 *NEWS — {ticker}*

{title[:120]}{'...' if len(title) > 120 else ''}
Relevance: *{score}/100*
Position: ${value:,.0f}

*Action:* Review position."""
        })
    
    return alerts

def check_digest(state: dict, positions: List[Dict]) -> List[Dict]:
    """DAILY DIGEST: Only at 4 PM ET / 3 PM CT / 8 PM UTC."""
    now = datetime.now(timezone.utc)
    
    # Only at market close (8 PM UTC = 3 PM CT = 4 PM ET)
    if now.hour != 20:
        return []
    
    alert_id = alert_hash("DIGEST", "portfolio", now.strftime("%Y-%m-%d"))
    
    # Check if digest already sent today
    sent_alerts = state.get("sent_alerts", {})
    if alert_id in sent_alerts:
        return []
    
    total_value = sum(p.get("live_value", 0) or p.get("value", 0) or 0 for p in positions)
    
    # Count significant movers (>5%)
    movers = [(p.get("ticker"), p.get("price_change_pct", 0)) for p in positions if abs(p.get("price_change_pct", 0)) >= 5]
    movers.sort(key=lambda x: abs(x[1]), reverse=True)
    
    # Grade summary
    grades = load_json(GRADES_FILE, {})
    weak_grades = []
    for cat, items in grades.items():
        if isinstance(items, list):
            for g in items:
                if isinstance(g, dict) and g.get("grade", 100) < 40:
                    weak_grades.append(g.get("ticker", ""))
    
    # Build digest
    lines = [f"📊 *VOX DAILY DIGEST — {now.strftime('%b %d')}*\n"]
    lines.append(f"Portfolio: *${total_value:,.0f}* | {len(positions)} positions\n")
    
    if movers:
        lines.append("*Big Movers Today:*")
        for t, c in movers[:5]:
            emoji = "🟢" if c > 0 else "🔴"
            lines.append(f"{emoji} {t}: {c:+.1f}%")
        lines.append("")
    
    if weak_grades:
        lines.append(f"*Weak Grades (<40):* {', '.join(weak_grades[:5])}")
        lines.append("")
    
    # Active alerts summary
    daily_alerts = [a for a in state.get("sent_alerts", {}).values() 
                    if datetime.fromisoformat(a["sent_at"]).date() == now.date()]
    if daily_alerts:
        lines.append(f"*Alerts Today:* {len(daily_alerts)}")
        for a in daily_alerts:
            lines.append(f"• {a['type']} {a['ticker']}")
    else:
        lines.append("*No alerts today.*")
    
    lines.append("\n*No action required. Digest only.*")
    
    return [{
        "id": alert_id,
        "priority": "DIGEST",
        "type": "DIGEST",
        "ticker": "PORTFOLIO",
        "message": "\n".join(lines)
    }]

def generate_alerts():
    state = load_state()
    positions = load_portfolio()
    
    total_value = sum(p.get("live_value", 0) or p.get("value", 0) or 0 for p in positions)
    
    print(f"🔍 VOX Alert System v7")
    print(f"   Portfolio: {len(positions)} positions, ${total_value:,.0f}")
    print(f"   Daily alerts sent: {state.get('daily_count', 0)}/{MAX_DAILY_ALERTS}")
    print(f"   Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    print("=" * 50)
    
    all_alerts = []
    
    # Priority order
    all_alerts.extend(check_stop_alerts(state, positions))
    all_alerts.extend(check_move_alerts(state, positions))
    all_alerts.extend(check_news_alerts(state, positions))
    all_alerts.extend(check_digest(state, positions))
    
    # Respect daily limit (digest doesn't count)
    non_digest = [a for a in all_alerts if a["type"] != "DIGEST"]
    digest = [a for a in all_alerts if a["type"] == "DIGEST"]
    
    if len(non_digest) > MAX_DAILY_ALERTS:
        print(f"⚠️  {len(non_digest)} alerts, limiting to {MAX_DAILY_ALERTS}")
        non_digest = non_digest[:MAX_DAILY_ALERTS]
    
    all_alerts = non_digest + digest
    
    if not all_alerts:
        print("\n✅ All quiet. No action required.")
        save_state(state)
        return []
    
    # Build message
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    
    if len(all_alerts) == 1 and all_alerts[0]["type"] == "DIGEST":
        # Just digest
        combined = all_alerts[0]["message"]
    else:
        lines = [f"🚨 *VOX ALERTS — {len([a for a in all_alerts if a['type'] != 'DIGEST'])} Action Required*\n_{now}_\n"]
        for alert in all_alerts:
            lines.append(alert["message"])
            lines.append("\n" + "─" * 30 + "\n")
        combined = "\n".join(lines)
    
    print(f"\n{'='*50}")
    print(combined)
    print(f"{'='*50}")
    
    sent = send_telegram(combined)
    print(f"\n📱 Telegram: {'✓ Sent' if sent else '✗ Failed'}")
    
    # Record alerts
    for alert in all_alerts:
        if alert["type"] == "DIGEST":
            state["sent_alerts"][alert["id"]] = {
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "ticker": "PORTFOLIO",
                "type": "DIGEST"
            }
        else:
            record_alert(state, alert["id"], alert["ticker"], alert["type"])
    
    # Update last prices
    for pos in positions:
        ticker = pos.get("ticker", "")
        price = pos.get("live_price", 0)
        if ticker and price:
            state.setdefault("last_prices", {})[ticker] = price
    
    save_state(state)
    return all_alerts

if __name__ == "__main__":
    generate_alerts()
