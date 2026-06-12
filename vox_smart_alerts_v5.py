#!/usr/bin/env python3
"""
VOX Smart Alert System v5 — Event-Driven, Not Schedule-Driven
Only alerts when something CHANGED or REQUIRES ACTION.
No "all clear" spam. No repeated plans. Max 5 alerts/day.

Alert Triggers:
1. SELL: Grade < 45 AND position value > $500
2. TRIM: Grade 45-55 AND position > $1000 (or >8% of portfolio)
3. BUY: Grade >= 75 AND not in portfolio (new opportunity)
4. STOP: Unrealized loss > $500 in single day
5. CONCENTRATION: Single position > 15% of portfolio
6. PRICE HIT: Limit order price reached (instant)
7. NEWS: Trump tweet/earnings/major news affecting portfolio (immediate)

Cooldowns:
- Grade alerts: 24h per ticker
- Price hit: immediate (no cooldown)
- News: 6h per event
- Daily max: 5 alerts total
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
ALERT_STATE_FILE = SCRIPT_DIR / ".vox_alert_state_v5.json"

# Data sources
POSITIONS_FILE = SCRIPT_DIR / "dashboard_positions.json"
GRADES_FILE = SCRIPT_DIR / "portfolio_grades.json"
TRUMP_FILE = SCRIPT_DIR / "trump_tracker_results.json"
LIVE_PRICES_FILE = SCRIPT_DIR / "dashboard_positions_live.json"
VOLUME_FILE = SCRIPT_DIR / "vox_volume_scan.json"
X_MOMENTUM_FILE = SCRIPT_DIR / "snapshots" / "x_momentum_latest.json"
NEWS_FILE = SCRIPT_DIR / "vox_news_digest.json"
COUNCIL_FILE = SCRIPT_DIR / "vox_council_votes.json"

# Protected positions (never sell)
PROTECTED_TICKERS = {"SHOP"}

# User-defined stop losses — ticker: stop_price
USER_STOPS = {
    "PLTR": 115.00,  # Thesis break level
}

# Thresholds
MIN_GRADE_SELL = 35  # Was 45 — too aggressive for short-term pullbacks
MIN_GRADE_TRIM_LOW = 40  # Was 45
MAX_GRADE_TRIM_HIGH = 50  # Was 55
MIN_GRADE_BUY = 75
MAX_DAILY_ALERTS = 5
MIN_POSITION_VALUE = 500
MIN_LOSS_ALERT = 500
MAX_CONCENTRATION_PCT = 15
PRICE_MOVE_THRESHOLD = 5.0  # 5% daily move

# Grade alert thresholds by position value
# Small positions (<$1000) need lower grade to trigger (more lenient)
# Large positions (>$5000) need higher grade to trigger (more strict)
GRADE_SELL_SMALL = 30    # <$1000
GRADE_SELL_MEDIUM = 35   # $1000-5000
GRADE_SELL_LARGE = 40    # >$5000

GRADE_TRIM_SMALL = 35
GRADE_TRIM_MEDIUM = 40
GRADE_TRIM_LARGE = 45

# Cooldowns (hours)
COOLDOWN_GRADE = 24
COOLDOWN_NEWS = 6
COOLDOWN_PRICE = 0  # Immediate

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


# ─── STATE MANAGEMENT ────────────────────────────────────────────────
def load_state() -> dict:
    if ALERT_STATE_FILE.exists():
        with open(ALERT_STATE_FILE) as f:
            return json.load(f)
    return {
        "sent_alerts": {},
        "daily_count": 0,
        "last_reset": datetime.now(timezone.utc).isoformat(),
        "last_prices": {},  # For detecting price hits
        "version": 5
    }


def save_state(state: dict):
    with open(ALERT_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def alert_hash(alert_type: str, ticker: str, detail: str = "") -> str:
    content = f"{alert_type}:{ticker}:{detail}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def can_alert(state: dict, alert_id: str, cooldown_hours: int = 24) -> bool:
    """Check if alert can be sent (dedup + daily limit)."""
    # Check daily limit
    last_reset = datetime.fromisoformat(state.get("last_reset", "2000-01-01T00:00:00+00:00"))
    if datetime.now(timezone.utc) - last_reset > timedelta(days=1):
        state["daily_count"] = 0
        state["last_reset"] = datetime.now(timezone.utc).isoformat()

    if state.get("daily_count", 0) >= MAX_DAILY_ALERTS:
        return False

    # Check cooldown
    sent_alerts = state.get("sent_alerts", {})
    if alert_id in sent_alerts:
        sent_at = datetime.fromisoformat(sent_alerts[alert_id]["sent_at"])
        if datetime.now(timezone.utc) - sent_at < timedelta(hours=cooldown_hours):
            return False

    return True


def record_alert(state: dict, alert_id: str, alert_data: dict):
    """Record that alert was sent."""
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
    """Load portfolio positions from all sources."""
    positions = []

    # Primary: dashboard_positions.json
    data = load_json(POSITIONS_FILE, {})
    if isinstance(data, dict):
        positions.extend(data.get("positions", []))
    elif isinstance(data, list):
        positions.extend(data)

    # Fallback: unified_portfolio.json
    unified = load_json(SCRIPT_DIR / "unified_portfolio.json", {})
    if unified.get("positions"):
        # Merge, avoiding duplicates
        existing_tickers = {p.get("ticker") for p in positions}
        for p in unified.get("positions", []):
            if p.get("ticker") not in existing_tickers:
                positions.append(p)

    return positions


def load_grades() -> Dict[str, dict]:
    """Load grades indexed by ticker."""
    data = load_json(GRADES_FILE, {})
    grades = {}

    # Handle different formats
    if isinstance(data, dict):
        if "grades" in data:
            for g in data["grades"]:
                t = g.get("ticker", "")
                if t:
                    grades[t] = g
        else:
            # Check for category keys (strong_buy, avoid, etc.)
            for key, value in data.items():
                if isinstance(value, list):
                    for g in value:
                        if isinstance(g, dict):
                            t = g.get("ticker", "")
                            if t:
                                grades[t] = g
                elif isinstance(value, dict) and "ticker" in value:
                    t = value.get("ticker", "")
                    if t:
                        grades[t] = value
    elif isinstance(data, list):
        for g in data:
            t = g.get("ticker", "")
            if t:
                grades[t] = g

    return grades


def load_live_prices() -> Dict[str, float]:
    """Load live prices if available."""
    data = load_json(LIVE_PRICES_FILE, {})
    prices = {}
    for p in data.get("positions", []):
        t = p.get("ticker", "")
        if t:
            prices[t] = p.get("price", 0)
    return prices


# ─── ALERT GENERATORS ────────────────────────────────────────────────
def load_council_votes() -> Dict[str, str]:
    """Load council votes indexed by ticker. Returns consensus (BUY/HOLD/SELL)."""
    data = load_json(COUNCIL_FILE, {})
    votes = {}
    for result in data.get("results", []):
        ticker = result.get("ticker", "")
        if ticker:
            votes[ticker] = result.get("consensus", "HOLD")
    return votes


def check_sell_alerts(state: dict, positions: List[Dict], grades: Dict[str, dict], council_votes: Dict[str, str]) -> List[Dict]:
    """SELL: Grade below threshold AND position > $500 AND council not HOLD."""
    alerts = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in PROTECTED_TICKERS:
            continue
        
        # COUNCIL OVERRIDE: If council says HOLD, skip grade-based SELL
        council_vote = council_votes.get(ticker, "HOLD")
        if council_vote == "HOLD":
            continue
        
        value = pos.get("value", 0) or pos.get("market_value", 0)
        grade_data = grades.get(ticker, {})
        grade = grade_data.get("grade", 0) or grade_data.get("total_grade", 0)

        # Dynamic threshold based on position size
        if value >= 5000:
            threshold = GRADE_SELL_LARGE
        elif value >= 1000:
            threshold = GRADE_SELL_MEDIUM
        else:
            threshold = GRADE_SELL_SMALL

        if grade > 0 and grade < threshold and value > MIN_POSITION_VALUE:
            alert_id = alert_hash("SELL", ticker, f"grade_{grade}")
            if can_alert(state, alert_id, COOLDOWN_GRADE):
                alerts.append({
                    "id": alert_id,
                    "type": "SELL",
                    "ticker": ticker,
                    "grade": grade,
                    "value": value,
                    "shares": pos.get("shares", 0),
                    "broker": pos.get("broker", "Unknown"),
                    "pnl": pos.get("pnl", 0) or pos.get("unrealized_pnl", 0),
                    "message": f"""🔴 *SELL — {ticker}*

Grade: *{grade}/100* (thesis broken, threshold <{threshold})
Council: *{council_vote}* (overrides grade)
Position: {pos.get('shares', 0)} shares @ {pos.get('broker', 'Unknown')}
Value: ~${value:,.0f}
Unrealized P&L: ${(pos.get('pnl', 0) or pos.get('unrealized_pnl', 0)):+,.0f}

*Action:* Market sell now. Don't hold broken theses."""
                })

    return alerts


def check_trim_alerts(state: dict, positions: List[Dict], grades: Dict[str, dict], total_value: float, council_votes: Dict[str, str]) -> List[Dict]:
    """TRIM: Grade in weak range AND position > $1000 AND council not HOLD."""
    alerts = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        
        # COUNCIL OVERRIDE: If council says HOLD, skip grade-based TRIM
        council_vote = council_votes.get(ticker, "HOLD")
        if council_vote == "HOLD":
            continue
        
        value = pos.get("value", 0) or pos.get("market_value", 0)
        grade_data = grades.get(ticker, {})
        grade = grade_data.get("grade", 0) or grade_data.get("total_grade", 0)
        pct = (value / total_value * 100) if total_value > 0 else 0

        # Dynamic threshold based on position size
        if value >= 5000:
            threshold_low = GRADE_TRIM_LARGE
        elif value >= 1000:
            threshold_low = GRADE_TRIM_MEDIUM
        else:
            threshold_low = GRADE_TRIM_SMALL
        threshold_high = threshold_low + 10  # 10-point trim window

        if threshold_low <= grade <= threshold_high and value > 1000:
            alert_id = alert_hash("TRIM", ticker, f"grade_{grade}_pct_{pct:.1f}")
            if can_alert(state, alert_id, COOLDOWN_GRADE):
                reason = f"Grade {grade} (weak, threshold {threshold_low}-{threshold_high})"
                if pct > 8:
                    reason += f" + {pct:.1f}% of portfolio (concentrated)"

                alerts.append({
                    "id": alert_id,
                    "type": "TRIM",
                    "ticker": ticker,
                    "grade": grade,
                    "value": value,
                    "pct": pct,
                    "message": f"""🟡 *TRIM — {ticker}*

Grade: *{grade}/100* ({reason})
Council: *{council_vote}* (overrides grade)
Position: ~${value:,.0f} ({pct:.1f}% of portfolio)
Unrealized P&L: ${(pos.get('pnl', 0) or pos.get('unrealized_pnl', 0)):+,.0f}

*Action:* Reduce position by 30-50%. Free up cash for better setups."""
                })

    return alerts


def check_buy_alerts(state: dict, positions: List[Dict], grades: Dict[str, dict]) -> List[Dict]:
    """BUY: Grade >= 75 AND not in portfolio."""
    alerts = []
    portfolio_tickers = {p.get("ticker", "") for p in positions}

    for ticker, grade_data in grades.items():
        if ticker in portfolio_tickers:
            continue

        grade = grade_data.get("grade", 0) or grade_data.get("total_grade", 0)
        rec = grade_data.get("recommendation", "")
        price = grade_data.get("price", 0)

        if grade >= MIN_GRADE_BUY and ("BUY" in rec or "ADD" in rec):
            alert_id = alert_hash("BUY", ticker, f"grade_{grade}")
            if can_alert(state, alert_id, COOLDOWN_GRADE * 2):  # 48h for buy alerts
                alerts.append({
                    "id": alert_id,
                    "type": "BUY",
                    "ticker": ticker,
                    "grade": grade,
                    "price": price,
                    "message": f"""🟢 *BUY OPPORTUNITY — {ticker}*

Grade: *{grade}/100* (strong setup)
Price: ~${price:.2f}
Rec: {rec}

*Action:* Consider 1-2% position size. Set stop at -8%."""
                })

    return alerts


def check_stop_loss_alerts(state: dict, positions: List[Dict], live_prices: Dict[str, float]) -> List[Dict]:
    """STOP: Position losing >$500 today OR user-defined stop hit."""
    alerts = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        cost_basis = pos.get("cost_basis", 0) or pos.get("avg_cost", 0)
        shares = pos.get("shares", 0)
        live_price = live_prices.get(ticker)

        if not live_price:
            continue

        # Check user-defined stops first (highest priority)
        user_stop = USER_STOPS.get(ticker)
        if user_stop and live_price <= user_stop:
            alert_id = alert_hash("USTOP", ticker, f"stop_{user_stop}")
            if can_alert(state, alert_id, 0):  # No cooldown — this is critical
                alerts.append({
                    "id": alert_id,
                    "type": "USER_STOP",
                    "ticker": ticker,
                    "stop_price": user_stop,
                    "current_price": live_price,
                    "message": f"""🛑 *STOP HIT — {ticker}*

Your stop at *${user_stop:.2f}* has been triggered.
Current Price: *${live_price:.2f}*

*Action:* SELL NOW. Thesis broken. No hesitation."""
                })
            continue  # Don't double-alert

        # Standard stop loss check
        if not cost_basis or not shares:
            continue

        unrealized = (live_price - cost_basis) * shares
        daily_change = pos.get("price_change_pct", 0)

        # Alert if losing >$500 AND dropping today
        if unrealized < -MIN_LOSS_ALERT and daily_change < -2:
            alert_id = alert_hash("STOP", ticker, f"loss_{abs(unrealized):.0f}")
            if can_alert(state, alert_id, 12):  # 12h cooldown
                alerts.append({
                    "id": alert_id,
                    "type": "STOP",
                    "ticker": ticker,
                    "loss": unrealized,
                    "daily_change": daily_change,
                    "message": f"""📉 *STOP LOSS — {ticker}*

Unrealized Loss: *${abs(unrealized):,.0f}* ({daily_change:+.1f}% today)
Cost Basis: ${cost_basis:.2f} | Current: ${live_price:.2f}
Shares: {shares}

*Action:* Cut loss. Thesis broken. Reallocate to better setup."""
                })

    return alerts


def check_concentration_alerts(state: dict, positions: List[Dict], total_value: float) -> List[Dict]:
    """CONCENTRATION: Single position > 15% of portfolio."""
    alerts = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        value = pos.get("value", 0) or pos.get("market_value", 0)
        pct = (value / total_value * 100) if total_value > 0 else 0

        if pct > MAX_CONCENTRATION_PCT:
            alert_id = alert_hash("CONC", ticker, f"pct_{pct:.1f}")
            if can_alert(state, alert_id, COOLDOWN_GRADE):
                alerts.append({
                    "id": alert_id,
                    "type": "CONCENTRATION",
                    "ticker": ticker,
                    "pct": pct,
                    "value": value,
                    "message": f"""⚠️ *CONCENTRATION RISK — {ticker}*

Position: *{pct:.1f}%* of portfolio (${value:,.0f})
Max recommended: 15%

*Action:* Trim to 10-12% max. Diversify or raise cash."""
                })

    return alerts


def check_price_hit_alerts(state: dict, positions: List[Dict], live_prices: Dict[str, float]) -> List[Dict]:
    """PRICE HIT: Significant daily move (>5%)."""
    alerts = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        change_pct = pos.get("price_change_pct", 0)
        live_price = live_prices.get(ticker, 0)

        if abs(change_pct) >= PRICE_MOVE_THRESHOLD:
            alert_id = alert_hash("PRICE", ticker, f"move_{change_pct:+.1f}")
            if can_alert(state, alert_id, COOLDOWN_PRICE):  # No cooldown for price hits
                direction = "UP" if change_pct > 0 else "DOWN"
                emoji = "🚀" if change_pct > 0 else "🔻"

                # Check if this is a limit trigger
                # (In future: compare against user's limit orders)
                alerts.append({
                    "id": alert_id,
                    "type": "PRICE_HIT",
                    "ticker": ticker,
                    "change_pct": change_pct,
                    "price": live_price,
                    "message": f"""{emoji} *PRICE MOVE — {ticker}*

Daily Move: *{change_pct:+.1f}%*
Current Price: ${live_price:.2f}

*Action:* Review position. {'Consider trimming if winner.' if change_pct > 0 else 'Check if thesis still valid.'}"""
                })

    return alerts


def check_volume_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """VOLUME: Unusual volume spike on portfolio position."""
    alerts = []
    vol_data = load_json(VOLUME_FILE, {})
    
    for result in vol_data.get("results", []):
        ticker = result.get("ticker", "")
        vol_ratio = result.get("volume_ratio", 0)
        alert_level = result.get("alert", "NONE")
        price_change = result.get("price_change_pct", 0)
        
        if alert_level == "NONE":
            continue
        
        # Only alert on significant volume + price movement
        if vol_ratio >= 2.0 and abs(price_change) >= 3:
            alert_id = alert_hash("VOL", ticker, f"vol_{vol_ratio:.1f}_price_{price_change:.1f}")
            if can_alert(state, alert_id, 12):  # 12h cooldown
                pos = next((p for p in positions if p.get("ticker") == ticker), {})
                value = pos.get("live_value") or pos.get("value", 0) or pos.get("market_value", 0)
                
                emoji = "🚀" if price_change > 0 else "🔻"
                action = "Review for trim." if price_change > 0 else "Check if thesis broken."
                
                alerts.append({
                    "id": alert_id,
                    "type": "VOLUME",
                    "ticker": ticker,
                    "vol_ratio": vol_ratio,
                    "price_change": price_change,
                    "message": f"""{emoji} *VOLUME SPIKE — {ticker}*

Volume: *{vol_ratio:.1f}x* average
Price: {price_change:+.1f}%
Position: ${value:,.0f}

*Action:* {action}"""
                })
    
    return alerts


def check_x_momentum_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """X MOMENTUM: Significant social sentiment shift."""
    alerts = []
    x_data = load_json(X_MOMENTUM_FILE, {})
    portfolio_tickers = {p.get("ticker", "") for p in positions}
    
    for result in x_data.get("results", []):
        ticker = result.get("ticker", "")
        if ticker not in portfolio_tickers:
            continue
        
        sentiment = result.get("sentiment", "NEUTRAL")
        mentions = result.get("mentions", 0)
        
        # Only alert on strong sentiment with activity
        if mentions >= 5 and sentiment in {"BULLISH", "BEARISH"}:
            alert_id = alert_hash("X", ticker, f"sent_{sentiment}_{mentions}")
            if can_alert(state, alert_id, 24):  # 24h cooldown
                pos = next((p for p in positions if p.get("ticker") == ticker), {})
                value = pos.get("live_value") or pos.get("value", 0) or pos.get("market_value", 0)
                live_price = pos.get("live_price", 0)
                change = pos.get("price_change_pct", 0)
                
                emoji = "🟢" if sentiment == "BULLISH" else "🔴"
                action = "Momentum building. Hold/add if thesis intact." if sentiment == "BULLISH" else "Negative buzz. Monitor closely."
                
                alerts.append({
                    "id": alert_id,
                    "type": "X_MOMENTUM",
                    "ticker": ticker,
                    "sentiment": sentiment,
                    "mentions": mentions,
                    "message": f"""{emoji} *X MOMENTUM — {ticker}*

Sentiment: *{sentiment}* ({mentions} mentions)
Price: ${live_price:.2f} ({change:+.2f}%)
Position: ${value:,.0f}

*Action:* {action}"""
                })
    
    return alerts


def check_news_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """NEWS: High-relevance news for portfolio positions."""
    alerts = []
    news_data = load_json(NEWS_FILE, {})
    portfolio_tickers = {p.get("ticker", "") for p in positions}
    
    for headline in news_data.get("portfolio_impact", []):
        ticker = headline.get("ticker", "")
        if ticker not in portfolio_tickers:
            continue
        
        score = headline.get("relevance_score", 0)
        title = headline.get("title", "")
        
        if score >= 65:  # High relevance only
            alert_id = alert_hash("NEWS", ticker, f"news_{title[:30]}")
            if can_alert(state, alert_id, 12):  # 12h cooldown
                pos = next((p for p in positions if p.get("ticker") == ticker), {})
                value = pos.get("live_value") or pos.get("value", 0) or pos.get("market_value", 0)
                
                alerts.append({
                    "id": alert_id,
                    "type": "NEWS",
                    "ticker": ticker,
                    "score": score,
                    "message": f"""📰 *NEWS — {ticker}*

{title[:100]}{'...' if len(title) > 100 else ''}
Relevance: *{score}/100*
Position: ${value:,.0f}

*Action:* Review position. News may affect thesis."""
                })
    
    return alerts


def check_trump_alerts(state: dict, positions: List[Dict]) -> List[Dict]:
    """Trump tweet alerts — high impact only."""
    alerts = []
    portfolio_tickers = {p.get("ticker", "") for p in positions}

    data = load_json(TRUMP_FILE, {})
    for tweet in data.get("tweets", []):
        impact = tweet.get("classification", {}).get("impact_score", 0)
        if impact < 8:
            continue

        text = tweet.get("text", "")[:120]
        action_plan = tweet.get("action_plan", {})
        overlap = action_plan.get("portfolio_overlap", [])
        risk = action_plan.get("risk_level", "MEDIUM")

        # Only alert if affects portfolio
        if not overlap or not any(t in portfolio_tickers for t in overlap):
            continue

        alert_id = alert_hash("TRUMP", text[:40], f"impact_{impact}")
        if can_alert(state, alert_id, COOLDOWN_NEWS):
            alerts.append({
                "id": alert_id,
                "type": "TRUMP",
                "ticker": overlap[0] if overlap else "PORTFOLIO",
                "impact": impact,
                "message": f"""🔴 *TRUMP ALERT — Impact {impact}/10*

{text}...

*Your positions at risk:* {', '.join(overlap)}
Risk Level: {risk}

*Action:* Review affected positions. Consider defensive moves."""
            })

    return alerts


# ─── MAIN ────────────────────────────────────────────────────────────
def generate_alerts():
    state = load_state()

    # Load data
    positions = load_portfolio()
    grades = load_grades()
    live_prices = load_live_prices()
    live_data = load_json(LIVE_PRICES_FILE, {})
    council_votes = load_council_votes()

    # Use live prices/values if available
    if live_data.get("positions"):
        positions = live_data["positions"]
        print(f"   Using LIVE prices (updated {live_data.get('updated_at', 'unknown')})")

    total_value = sum(p.get("live_value") or p.get("value", 0) or p.get("market_value", 0) for p in positions)

    print(f"🔍 VOX Smart Alert System v5")
    print(f"   Portfolio: {len(positions)} positions, ${total_value:,.0f} total")
    print(f"   Grades: {len(grades)} tickers graded")
    print(f"   Council: {len(council_votes)} votes loaded")
    print(f"   Daily alerts sent today: {state.get('daily_count', 0)}/{MAX_DAILY_ALERTS}")
    print("=" * 50)

    all_alerts = []

    # Priority order: most urgent first
    all_alerts.extend(check_stop_loss_alerts(state, positions, live_prices))
    all_alerts.extend(check_sell_alerts(state, positions, grades, council_votes))
    all_alerts.extend(check_concentration_alerts(state, positions, total_value))
    all_alerts.extend(check_trim_alerts(state, positions, grades, total_value, council_votes))
    all_alerts.extend(check_price_hit_alerts(state, positions, live_prices))
    all_alerts.extend(check_volume_alerts(state, positions))
    all_alerts.extend(check_x_momentum_alerts(state, positions))
    all_alerts.extend(check_news_alerts(state, positions))
    all_alerts.extend(check_trump_alerts(state, positions))
    all_alerts.extend(check_buy_alerts(state, positions, grades))

    # Respect daily limit
    if len(all_alerts) > MAX_DAILY_ALERTS:
        print(f"⚠️  {len(all_alerts)} alerts generated, limiting to {MAX_DAILY_ALERTS} most urgent")
        all_alerts = all_alerts[:MAX_DAILY_ALERTS]

    if not all_alerts:
        print("\n✅ No action required. All quiet.")
        print("   (No Telegram message sent — staying silent)")
        save_state(state)
        return []

    # Build combined message
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"🚨 *VOX ALERTS — {len(all_alerts)} Action Required*\n_{now}_\n"]

    for alert in all_alerts:
        lines.append(alert["message"])
        lines.append("\n" + "─" * 30 + "\n")
        record_alert(state, alert["id"], alert)

    combined = "\n".join(lines)

    # Print locally
    print(f"\n{'='*50}")
    print(combined)
    print(f"{'='*50}")

    # Send to Telegram
    sent = send_telegram(combined)
    print(f"\n📱 Telegram: {'✓ Sent' if sent else '✗ Failed'}")

    save_state(state)
    return all_alerts


if __name__ == "__main__":
    generate_alerts()
