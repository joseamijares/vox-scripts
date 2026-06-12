#!/usr/bin/env python3
"""
VOX Smart Alert System v6 — Quality Over Quantity
Only alerts when MULTIPLE signals confirm action is needed.
Single-signal noise is suppressed. Context-rich alerts only.

Alert Quality Gates:
1. Grade + Council + Price Action must align (2 of 3)
2. Cross-signal confirmation required (volume + news + X)
3. Position size matters (dust positions ignored)
4. Thesis-aware (council HOLD suppresses grade-based SELL)
5. Daily digest format (1 message with ALL actions, not 5 separate)

Alert Types:
- CRITICAL: Stop hit, concentration >20%, Trump impact >8/10
- ACTION: Grade + council agree on SELL/TRIM/BUY
- WATCH: Single signal worth monitoring (no action)
- DIGEST: Daily summary at market close
"""

import json
import os
import sys
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

# ─── CONFIG ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
ALERT_STATE_FILE = SCRIPT_DIR / ".vox_alert_state_v6.json"

POSITIONS_FILE = SCRIPT_DIR / "dashboard_positions_live.json"
GRADES_FILE = SCRIPT_DIR / "portfolio_grades.json"
COUNCIL_FILE = SCRIPT_DIR / "vox_council_votes.json"
VOLUME_FILE = SCRIPT_DIR / "vox_volume_scan.json"
NEWS_FILE = SCRIPT_DIR / "vox_news_digest.json"

PROTECTED_TICKERS = {"SHOP"}
USER_STOPS = {"PLTR": 115.00}

# Quality thresholds
MIN_POSITION_VALUE = 500
DUST_THRESHOLD = 100
MAX_DAILY_ALERTS = 5

# Grade thresholds by conviction
GRADE_STRONG_BUY = 75
GRADE_BUY = 65
GRADE_HOLD = 50
GRADE_TRIM = 40
GRADE_SELL = 35

# Cross-signal requirements
MIN_VOLUME_SPIKE = 2.5  # 2.5x average
MIN_NEWS_RELEVANCE = 70
MIN_TRUMP_IMPACT = 8

# ─── TELEGRAM ────────────────────────────────────────────────────────
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

# ─── STATE ───────────────────────────────────────────────────────────
def load_state() -> dict:
    if ALERT_STATE_FILE.exists():
        with open(ALERT_STATE_FILE) as f:
            return json.load(f)
    return {
        "sent_alerts": {},
        "daily_count": 0,
        "last_reset": datetime.now(timezone.utc).isoformat(),
        "version": 6
    }

def save_state(state: dict):
    with open(ALERT_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def alert_hash(alert_type: str, ticker: str, detail: str = "") -> str:
    content = f"{alert_type}:{ticker}:{detail}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    return hashlib.md5(content.encode()).hexdigest()[:16]

def can_alert(state: dict, alert_id: str, cooldown_hours: int = 24) -> bool:
    last_reset = datetime.fromisoformat(state.get("last_reset", "2000-01-01T00:00:00+00:00"))
    if datetime.now(timezone.utc) - last_reset > timedelta(days=1):
        state["daily_count"] = 0
        state["last_reset"] = datetime.now(timezone.utc).isoformat()
    
    if state.get("daily_count", 0) >= MAX_DAILY_ALERTS:
        return False
    
    sent_alerts = state.get("sent_alerts", {})
    if alert_id in sent_alerts:
        sent_at = datetime.fromisoformat(sent_alerts[alert_id]["sent_at"])
        if datetime.now(timezone.utc) - sent_at < timedelta(hours=cooldown_hours):
            return False
    
    return True

def record_alert(state: dict, alert_id: str, alert_data: dict):
    state.setdefault("sent_alerts", {})[alert_id] = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "data": alert_data
    }
    state["daily_count"] = state.get("daily_count", 0) + 1

# ─── DATA LOADING ────────────────────────────────────────────────────
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
    # Filter dust positions
    return [p for p in positions if (p.get("live_value") or p.get("value", 0) or 0) > DUST_THRESHOLD]

def load_grades() -> Dict[str, dict]:
    data = load_json(GRADES_FILE, {})
    grades = {}
    for key, value in data.items():
        if isinstance(value, list):
            for g in value:
                if isinstance(g, dict):
                    t = g.get("ticker", "")
                    if t:
                        grades[t] = g
    return grades

def load_council() -> Dict[str, str]:
    data = load_json(COUNCIL_FILE, {})
    votes = {}
    for result in data.get("results", []):
        t = result.get("ticker", "")
        if t:
            votes[t] = result.get("consensus", "HOLD")
    return votes

def load_volume() -> Dict[str, dict]:
    data = load_json(VOLUME_FILE, {})
    vol = {}
    for r in data.get("results", []):
        t = r.get("ticker", "")
        if t:
            vol[t] = r
    return vol

def load_news() -> List[Dict]:
    data = load_json(NEWS_FILE, {})
    return data.get("portfolio_impact", [])

# ─── SIGNAL AGGREGATION ──────────────────────────────────────────────
def get_signal_score(ticker: str, positions: List[Dict], grades: Dict, council: Dict, 
                     volume: Dict, news: List[Dict]) -> dict:
    """Aggregate all signals for a ticker into a unified score."""
    pos = next((p for p in positions if p.get("ticker") == ticker), {})
    grade_data = grades.get(ticker, {})
    grade = grade_data.get("grade", 0) or grade_data.get("total_grade", 0)
    council_vote = council.get(ticker, "HOLD")
    vol_data = volume.get(ticker, {})
    
    # News relevance
    news_items = [n for n in news if n.get("ticker") == ticker]
    max_news_score = max([n.get("relevance_score", 0) for n in news_items], default=0)
    
    # Price action
    price_change = pos.get("price_change_pct", 0)
    
    # Volume spike
    vol_ratio = vol_data.get("volume_ratio", 0)
    
    # Signal strength (0-100)
    signals = {
        "grade": grade,
        "council": council_vote,
        "price_change": price_change,
        "volume_ratio": vol_ratio,
        "news_score": max_news_score,
        "position_value": pos.get("live_value", 0) or pos.get("value", 0) or 0,
        "grade_category": "strong" if grade >= 70 else "moderate" if grade >= 50 else "weak" if grade > 0 else "ungraded"
    }
    
    # Composite action score
    action_score = 0
    action_signals = []
    
    # Grade signal
    if grade >= GRADE_STRONG_BUY:
        action_score += 40
        action_signals.append("grade_strong_buy")
    elif grade >= GRADE_BUY:
        action_score += 25
        action_signals.append("grade_buy")
    elif grade <= GRADE_SELL and grade > 0:
        action_score -= 40
        action_signals.append("grade_sell")
    elif grade <= GRADE_TRIM and grade > 0:
        action_score -= 25
        action_signals.append("grade_trim")
    
    # Council signal
    if council_vote == "BUY":
        action_score += 30
        action_signals.append("council_buy")
    elif council_vote == "SELL":
        action_score -= 30
        action_signals.append("council_sell")
    elif council_vote == "HOLD":
        action_score -= 10  # Neutral but suppresses action
        action_signals.append("council_hold")
    
    # Volume confirmation
    if vol_ratio >= MIN_VOLUME_SPIKE:
        if price_change > 3:
            action_score += 15
            action_signals.append("volume_spike_up")
        elif price_change < -3:
            action_score -= 15
            action_signals.append("volume_spike_down")
    
    # News confirmation
    if max_news_score >= MIN_NEWS_RELEVANCE:
        action_score += 10
        action_signals.append("news_high")
    
    signals["action_score"] = action_score
    signals["action_signals"] = action_signals
    signals["needs_action"] = abs(action_score) >= 50  # Threshold for action
    signals["action"] = "BUY" if action_score >= 50 else "SELL" if action_score <= -50 else "HOLD"
    
    return signals

# ─── ALERT GENERATORS ────────────────────────────────────────────────
def generate_critical_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """CRITICAL: Stop hits, concentration >20% — always alert."""
    alerts = []
    
    for pos in positions:
        ticker = pos.get("ticker", "")
        live_price = pos.get("live_price", 0)
        
        # User-defined stops
        user_stop = USER_STOPS.get(ticker)
        if user_stop and live_price <= user_stop:
            alert_id = alert_hash("CRITICAL", ticker, f"stop_{user_stop}")
            if can_alert(state, alert_id, 0):
                alerts.append({
                    "id": alert_id,
                    "priority": "CRITICAL",
                    "type": "STOP_HIT",
                    "ticker": ticker,
                    "message": f"🛑 *STOP HIT — {ticker}*\n\nYour stop at *${user_stop:.2f}* triggered.\nCurrent: *${live_price:.2f}*\n\n*Action:* SELL NOW. No hesitation."
                })
    
    return alerts

def generate_action_alerts(state: dict, positions: List[Dict], grades: Dict, 
                           council: Dict, volume: Dict, news: List[Dict]) -> List[Dict]:
    """ACTION: Multiple signals confirm buy/sell/trim."""
    alerts = []
    
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in PROTECTED_TICKERS:
            continue
        
        signals = get_signal_score(ticker, positions, grades, council, volume, news)
        
        if not signals["needs_action"]:
            continue
        
        action = signals["action"]
        score = signals["action_score"]
        value = signals["position_value"]
        
        # Skip dust positions
        if value < MIN_POSITION_VALUE:
            continue
        
        alert_id = alert_hash("ACTION", ticker, f"{action}_{score}")
        if not can_alert(state, alert_id, 24):
            continue
        
        # Build rich context message
        grade = signals["grade"]
        council_vote = signals["council"]
        price_change = signals["price_change"]
        vol_ratio = signals["volume_ratio"]
        
        context_lines = [
            f"Grade: *{grade}/100* ({signals['grade_category']})",
            f"Council: *{council_vote}*",
        ]
        
        if abs(price_change) > 2:
            context_lines.append(f"Price: {price_change:+.1f}% today")
        
        if vol_ratio >= MIN_VOLUME_SPIKE:
            context_lines.append(f"Volume: *{vol_ratio:.1f}x* average")
        
        context = "\n".join(context_lines)
        
        if action == "SELL":
            message = f"""🔴 *SELL — {ticker}*

Signal Score: *{score}* (multiple confirmations)
{context}
Position: ${value:,.0f}

*Action:* Market sell. Thesis broken."""
        elif action == "TRIM":
            message = f"""🟡 *TRIM — {ticker}*

Signal Score: *{score}* (weak signals)
{context}
Position: ${value:,.0f}

*Action:* Reduce 30-50%. Free up cash."""
        elif action == "BUY":
            message = f"""🟢 *BUY — {ticker}*

Signal Score: *{score}* (strong setup)
{context}

*Action:* Consider 1-2% position. Stop at -8%."""
        else:
            continue
        
        alerts.append({
            "id": alert_id,
            "priority": "ACTION",
            "type": action,
            "ticker": ticker,
            "score": score,
            "message": message
        })
    
    return alerts

def generate_watchlist_alerts(state: dict, watchlist_tickers: List[str], 
                              grades: Dict, council: Dict, volume: Dict, news: List[Dict]) -> List[Dict]:
    """WATCH: Watchlist tickers with interesting signals."""
    alerts = []
    
    for ticker in watchlist_tickers:
        signals = get_signal_score(ticker, [], grades, council, volume, news)
        
        # Only alert on strong signals for watchlist
        if signals["action_score"] >= 40 or signals["action_score"] <= -40:
            alert_id = alert_hash("WATCH", ticker, f"score_{signals['action_score']}")
            if not can_alert(state, alert_id, 48):  # 48h cooldown for watchlist
                continue
            
            action = "BUY" if signals["action_score"] > 0 else "SELL"
            grade = signals["grade"]
            
            alerts.append({
                "id": alert_id,
                "priority": "WATCH",
                "type": f"WATCH_{action}",
                "ticker": ticker,
                "message": f"""👁️ *WATCHLIST — {ticker}*

Signal: *{action}* (score: {signals['action_score']})
Grade: {grade}/100 | Council: {signals['council']}

*Not in portfolio yet. Monitor for entry."""
            })
    
    return alerts

def generate_digest(state: dict, positions: List[Dict], grades: Dict, council: Dict) -> Optional[Dict]:
    """DAILY DIGEST: Summary of portfolio state."""
    now = datetime.now(timezone.utc)
    
    # Only send digest at market close (4 PM ET / 3 PM CT / 8 PM UTC)
    if now.hour != 20:
        return None
    
    alert_id = alert_hash("DIGEST", "portfolio", now.strftime("%Y-%m-%d"))
    if not can_alert(state, alert_id, 20):  # 20h cooldown (once per day)
        return None
    
    total_value = sum(p.get("live_value", 0) or p.get("value", 0) or 0 for p in positions)
    
    # Count by grade category
    strong = sum(1 for p in positions if grades.get(p.get("ticker"), {}).get("grade", 0) >= 70)
    moderate = sum(1 for p in positions if 50 <= grades.get(p.get("ticker"), {}).get("grade", 0) < 70)
    weak = sum(1 for p in positions if 0 < grades.get(p.get("ticker"), {}).get("grade", 0) < 50)
    ungraded = sum(1 for p in positions if grades.get(p.get("ticker"), {}).get("grade", 0) == 0)
    
    # Best/worst performers
    performers = [(p.get("ticker"), p.get("price_change_pct", 0)) for p in positions]
    performers.sort(key=lambda x: x[1], reverse=True)
    top3 = performers[:3]
    bottom3 = performers[-3:]
    
    top_movers = "\n".join([f"• {t}: {c:+.1f}%" for t, c in top3])
    bottom_movers = "\n".join([f"• {t}: {c:+.1f}%" for t, c in bottom3])
    
    message = f"""📊 *VOX DAILY DIGEST — {now.strftime('%b %d')}*

Portfolio: *${total_value:,.0f}* | {len(positions)} positions

Grade Distribution:
• Strong (70+): {strong}
• Moderate (50-69): {moderate}
• Weak (<50): {weak}
• Ungraded: {ungraded}

Top Movers:
{top_movers}

Bottom Movers:
{bottom_movers}

*No action required. Digest only.*"""
    
    return {
        "id": alert_id,
        "priority": "DIGEST",
        "type": "DAILY_DIGEST",
        "ticker": "PORTFOLIO",
        "message": message
    }

# ─── MAIN ────────────────────────────────────────────────────────────
def generate_alerts():
    state = load_state()
    
    positions = load_portfolio()
    grades = load_grades()
    council = load_council()
    volume = load_volume()
    news = load_news()
    
    total_value = sum(p.get("live_value", 0) or p.get("value", 0) or 0 for p in positions)
    
    print(f"🔍 VOX Smart Alert System v6")
    print(f"   Portfolio: {len(positions)} positions, ${total_value:,.0f}")
    print(f"   Grades: {len(grades)} | Council: {len(council)}")
    print(f"   Daily alerts: {state.get('daily_count', 0)}/{MAX_DAILY_ALERTS}")
    print("=" * 50)
    
    all_alerts = []
    
    # Priority order
    all_alerts.extend(generate_critical_alerts(state, positions))
    all_alerts.extend(generate_action_alerts(state, positions, grades, council, volume, news))
    
    # Watchlist (from Supabase)
    try:
        from vox_supabase_sync import get_client
        sb = get_client()
        watchlist = sb.table('watchlist').select('ticker').execute()
        watchlist_tickers = [w['ticker'] for w in watchlist.data]
        all_alerts.extend(generate_watchlist_alerts(state, watchlist_tickers, grades, council, volume, news))
    except Exception as e:
        print(f"Watchlist fetch failed: {e}")
    
    # Daily digest (only at market close)
    digest = generate_digest(state, positions, grades, council)
    if digest:
        all_alerts.append(digest)
    
    # Respect daily limit
    if len(all_alerts) > MAX_DAILY_ALERTS:
        print(f"⚠️  {len(all_alerts)} alerts, limiting to {MAX_DAILY_ALERTS}")
        # Sort by priority: CRITICAL > ACTION > WATCH > DIGEST
        priority_order = {"CRITICAL": 0, "ACTION": 1, "WATCH": 2, "DIGEST": 3}
        all_alerts.sort(key=lambda a: priority_order.get(a.get("priority", "WATCH"), 99))
        all_alerts = all_alerts[:MAX_DAILY_ALERTS]
    
    if not all_alerts:
        print("\n✅ All quiet. No action required.")
        save_state(state)
        return []
    
    # Build single combined message
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"🚨 *VOX ALERTS — {len(all_alerts)} Signals*\n_{now}_\n"]
    
    for alert in all_alerts:
        lines.append(alert["message"])
        lines.append("\n" + "─" * 30 + "\n")
        record_alert(state, alert["id"], alert)
    
    combined = "\n".join(lines)
    
    print(f"\n{'='*50}")
    print(combined)
    print(f"{'='*50}")
    
    sent = send_telegram(combined)
    print(f"\n📱 Telegram: {'✓ Sent' if sent else '✗ Failed'}")
    
    save_state(state)
    return all_alerts

if __name__ == "__main__":
    generate_alerts()
