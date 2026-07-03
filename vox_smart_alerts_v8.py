#!/usr/bin/env python3
"""
VOX Smart Alert System v8.1 — LLM-Enhanced Intelligence + DeepSeek Fact-Check Layer

Flow:
1. Detect raw signals (stop, move, news, trump)
2. Pass through Claude Sonnet 5 for context + reasoning
3. DeepSeek v4 Pro fact-checks the proposed alert against raw data
4. Only send if both layers approve and guardrails pass
5. Rich, factual, portfolio-context-aware messages

Rules:
- LLM is the final gatekeeper — no alert without approval
- DeepSeek rejects hallucinations, sensationalism, and tiny-position noise
- Every alert explains WHY it matters to YOUR portfolio
- Exact actions with numbers only from raw data
- Max 3 alerts/day, 1 per ticker, no repeats
"""

import json
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
ALERT_STATE_FILE = SCRIPT_DIR / ".vox_alert_state_v8.json"

POSITIONS_FILE = SCRIPT_DIR / "dashboard_positions_live.json"
GRADES_FILE = SCRIPT_DIR / "portfolio_grades.json"
NEWS_FILE = SCRIPT_DIR / "vox_news_digest.json"
MACRO_FILE = SCRIPT_DIR / "vox_macro_analysis.json"
SECTOR_FILE = SCRIPT_DIR / "vox_sector_analysis.json"

PROTECTED_TICKERS = {"SHOP"}
USER_STOPS = {"PLTR": 115.00}

MIN_MOVE_PCT = 10
MIN_POSITION_VALUE = 500
MIN_POSITION_WEIGHT = 0.025          # Only alert on positions >= 2.5% of portfolio
MAX_UNREALIZED_PCT_ARTIFACT = 1000   # Ignore >1000% gains on tiny positions (bad cost basis)
MAX_DAILY_ALERTS = 3

# ─── LLM ─────────────────────────────────────────────────────────────
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


def call_llm(prompt: str, model: str = "anthropic/claude-sonnet-5", max_tokens: int = 800) -> str:
    """Call an LLM via OpenRouter."""
    env = load_env()
    api_key = env.get("OPENROUTER_API_KEY", "")

    if not api_key:
        return ""

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vox-dashboard-five.vercel.app",
        "X-Title": "VOX Alert System"
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are VOX, an elite trading intelligence system. You must use ONLY the numbers provided in the prompt. Never invent prices, percentages, position sizes, or news narratives. If a requested number is not in the prompt, say 'NOT_PROVIDED'. Be concise."
            },
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return ""


def deepseek_review(prompt_context: str, proposed_alert: dict) -> dict:
    """Second-layer review: DeepSeek v4 Pro validates facts, relevance, and rejects sensationalism."""
    review_prompt = f"""FACT-CHECK and RELEVANCE-CHECK this proposed alert against the raw data.

RAW DATA:
{prompt_context}

PROPOSED ALERT:
Headline: {proposed_alert.get('headline', '')}
Action: {proposed_alert.get('action', '')}
Reason: {proposed_alert.get('why', '')}

Rules:
1. The headline must only describe facts from the RAW DATA. If it mentions a percentage, price, position size, or news story, verify it appears in the RAW DATA.
2. If any number in the proposed alert is not found in the RAW DATA, it is a hallucination — reject.
3. Reject if the alert is sensationalist or uses words like "rockets", "crashes", "explodes", "massive", "windfall", "unrealized gains" without proper context, or is not actionable.
4. Reject if the position is tiny (< 2.5% of portfolio) AND the alert is about taking action on that position — the user doesn't care about 0.2% positions.
5. The action must be mathematically consistent and directly useful to the portfolio owner.

Respond ONLY with JSON:
{{"approved": true/false, "reason": "short reason", "corrected_headline": "factual headline or null", "corrected_action": "factual action or null"}}"""

    response = call_llm(review_prompt, model="deepseek/deepseek-v4-pro", max_tokens=600)
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
    except Exception:
        pass

    return {"approved": False, "reason": "Review failed — rejecting for safety", "corrected_headline": None, "corrected_action": None}


# ─── TELEGRAM ────────────────────────────────────────────────────────
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
        "last_prices": {},
        "version": 8
    }


def save_state(state: dict):
    with open(ALERT_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def alert_hash(alert_type: str, ticker: str, detail: str = "") -> str:
    content = f"{alert_type}:{ticker}:{detail}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def can_alert(state: dict, alert_id: str, ticker: str, cooldown_hours: int = 24) -> bool:
    last_reset = datetime.fromisoformat(state.get("last_reset", "2000-01-01T00:00:00+00:00"))
    if datetime.now(timezone.utc) - last_reset > timedelta(days=1):
        state["daily_count"] = 0
        state["last_reset"] = datetime.now(timezone.utc).isoformat()

    if state.get("daily_count", 0) >= MAX_DAILY_ALERTS:
        return False

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

# ─── DATA ────────────────────────────────────────────────────────────
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


def get_portfolio_context(positions: List[Dict]) -> Dict:
    total = sum(p.get("live_value", 0) or 0 for p in positions)
    return {
        "total_value": total,
        "position_count": len(positions),
        "cash": 15000  # Approximate
    }


def get_macro_context() -> Dict:
    macro = load_json(MACRO_FILE, {})
    sector = load_json(SECTOR_FILE, {})
    return {
        "regime": macro.get("regime", "NEUTRAL"),
        "vix": macro.get("vix", {}).get("level", 0),
        "sector_rotation": sector.get("rotation", "NEUTRAL")
    }


def position_weight(pos: Dict, portfolio: Dict) -> float:
    return (pos.get("live_value", 0) / portfolio["total_value"]) if portfolio["total_value"] else 0


def unrealized_pct(pos: Dict) -> float:
    avg_cost = pos.get("avg_cost") or 0
    live_price = pos.get("live_price") or 0
    if avg_cost > 0:
        return ((live_price - avg_cost) / avg_cost) * 100
    return 0.0


# ─── LLM ENHANCEMENT ─────────────────────────────────────────────────
def _extract_json(response: str) -> dict:
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
    except Exception:
        pass
    return {}


def llm_enhance_stop(ticker: str, stop_price: float, current_price: float,
                     position: Dict, portfolio: Dict, macro: Dict) -> Dict:
    """Claude decides if stop alert is worth sending."""
    prompt = f"""STOP LOSS ALERT — {ticker}

POSITION: {position.get('shares', 0):.2f} shares @ avg ${position.get('avg_cost', 0):.2f}
STOP: ${stop_price:.2f} | CURRENT: ${current_price:.2f}
VALUE: ${position.get('live_value', 0):,.0f} ({position_weight(position, portfolio):.2f}% of portfolio)
UNREALIZED: {unrealized_pct(position):+.1f}%

MACRO: {macro['regime']} | VIX {macro['vix']:.1f}

Should this alert be sent? Respond ONLY with JSON:
{{"send": true/false, "priority": "CRITICAL", "headline": "one factual line", "action": "exact action with numbers", "why": "one sentence on portfolio impact"}}"""

    result = _extract_json(call_llm(prompt, model="anthropic/claude-sonnet-5", max_tokens=400))
    result["_prompt_context"] = prompt
    return result if result else {
        "send": True,
        "priority": "CRITICAL",
        "headline": f"STOP HIT: {ticker} at ${current_price:.2f}",
        "action": f"SELL {position.get('shares', 0):.2f} shares at market",
        "why": f"Stop loss triggered — protect ${position.get('live_value', 0):,.0f} position"
    }


def llm_enhance_move(ticker: str, change_pct: float, position: Dict,
                     portfolio: Dict, macro: Dict) -> Dict:
    """Claude decides if move alert is worth sending."""
    prompt = f"""BIG MOVE — {ticker} {change_pct:+.1f}%

POSITION: ${position.get('live_value', 0):,.0f} ({position_weight(position, portfolio):.2f}% of portfolio)
AVG COST: ${position.get('avg_cost', 0):.2f} | CURRENT: ${position.get('live_price', 0):.2f}
UNREALIZED: {unrealized_pct(position):+.1f}%

MACRO: {macro['regime']} | SECTOR ROTATION: {macro['sector_rotation']}

Is this move significant enough to alert? This is an aggressive growth portfolio; ignore tiny positions (<2.5% AUM) and data artifacts. Respond ONLY with JSON:
{{"send": true/false, "priority": "HIGH/MEDIUM", "headline": "one factual line, no sensationalism", "action": "exact action", "why": "portfolio context"}}"""

    result = _extract_json(call_llm(prompt, model="anthropic/claude-sonnet-5", max_tokens=500))
    result["_prompt_context"] = prompt
    return result if result else {
        "send": abs(change_pct) >= 15,
        "priority": "HIGH",
        "headline": f"{ticker} {change_pct:+.1f}% — review position",
        "action": "Monitor closely" if change_pct > 0 else "Check thesis",
        "why": f"Significant move on ${position.get('live_value', 0):,.0f} position"
    }


def llm_enhance_news(ticker: str, headline: str, relevance: int,
                     position: Dict, portfolio: Dict) -> Dict:
    """Claude decides if news alert is worth sending."""
    prompt = f"""NEWS ALERT — {ticker}

HEADLINE: {headline}
RELEVANCE: {relevance}/100
POSITION: ${position.get('live_value', 0):,.0f} ({position_weight(position, portfolio):.2f}% of portfolio)
UNREALIZED: {unrealized_pct(position):+.1f}%

Is this news actionable? Respond ONLY with JSON:
{{"send": true/false, "priority": "HIGH/MEDIUM", "headline": "one factual line, no sensationalism", "action": "exact action", "why": "why it matters to this portfolio"}}"""

    result = _extract_json(call_llm(prompt, model="anthropic/claude-sonnet-5", max_tokens=500))
    result["_prompt_context"] = prompt
    return result if result else {
        "send": relevance >= 85,
        "priority": "HIGH",
        "headline": f"NEWS: {ticker} — {headline[:60]}",
        "action": "Review position",
        "why": f"High-relevance news on ${position.get('live_value', 0):,.0f} position"
    }


def llm_generate_digest(positions: List[Dict], alerts_today: List[Dict], macro: Dict) -> str:
    """Claude generates daily digest."""
    total = sum(p.get("live_value", 0) or 0 for p in positions)
    movers = sorted([(p.get("ticker"), p.get("price_change_pct", 0)) for p in positions if abs(p.get("price_change_pct", 0)) >= 5],
                    key=lambda x: abs(x[1]), reverse=True)[:5]

    movers_text = "\n".join([f"{t}: {c:+.1f}%" for t, c in movers]) if movers else "None significant"

    prompt = f"""DAILY DIGEST — Portfolio ${total:,.0f}

MOVERS (>±5%):
{movers_text}

ALERTS TODAY: {len(alerts_today)}
{chr(10).join([f"- {a.get('type')} {a.get('ticker')}" for a in alerts_today[:3]]) if alerts_today else "None"}

MACRO: {macro['regime']} | VIX {macro['vix']:.1f}

Write a tight, factual digest. 3-4 sentences max. Include:
1. Key takeaway from today
2. One position to watch tomorrow
3. Macro implication

No generic advice. Use actual numbers only. No sensationalism."""

    response = call_llm(prompt, model="anthropic/claude-sonnet-5", max_tokens=600)

    if response:
        return f"📊 *VOX DAILY DIGEST — {datetime.now(timezone.utc).strftime('%b %d')}*\n\n{response}\n\n_Portfolio: ${total:,.0f}_"

    # Fallback
    lines = [f"📊 *VOX DAILY DIGEST — {datetime.now(timezone.utc).strftime('%b %d')}*\n"]
    lines.append(f"Portfolio: *${total:,.0f}*\n")
    if movers:
        lines.append("*Movers:*")
        for t, c in movers[:3]:
            lines.append(f"{'🟢' if c > 0 else '🔴'} {t}: {c:+.1f}%")
    lines.append(f"\n*Alerts:* {len(alerts_today)}")
    return "\n".join(lines)


# ─── ALERT DETECTORS ─────────────────────────────────────────────────
def check_stops(state: dict, positions: List[Dict], portfolio: Dict, macro: Dict) -> List[Dict]:
    alerts = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        live_price = pos.get("live_price", 0)
        user_stop = USER_STOPS.get(ticker)

        if not user_stop or live_price <= 0 or live_price > user_stop:
            continue

        if state.get("daily_count", 0) >= MAX_DAILY_ALERTS:
            continue

        llm_result = llm_enhance_stop(ticker, user_stop, live_price, pos, portfolio, macro)

        if not llm_result.get("send", False):
            print(f"   [LLM BLOCKED] Stop {ticker} — not actionable")
            continue

        review = deepseek_review(llm_result.get("_prompt_context", ""), llm_result)
        if not review.get("approved", False):
            print(f"   [DEEPSEEK REJECTED] Stop {ticker} — {review.get('reason', 'fact-check failed')}")
            continue

        if review.get("corrected_headline"):
            llm_result["headline"] = review["corrected_headline"]
        if review.get("corrected_action"):
            llm_result["action"] = review["corrected_action"]

        alert_id = alert_hash("STOP", ticker, f"stop_{user_stop}")

        alerts.append({
            "id": alert_id,
            "type": "STOP",
            "ticker": ticker,
            "priority": llm_result.get("priority", "CRITICAL"),
            "message": f"""🛑 *{llm_result.get('headline', f'STOP: {ticker}')}*

{llm_result.get('why', '')}

*Action:* {llm_result.get('action', 'SELL NOW')}"""
        })
    return alerts


def check_moves(state: dict, positions: List[Dict], portfolio: Dict, macro: Dict) -> List[Dict]:
    alerts = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker in PROTECTED_TICKERS:
            continue

        change_pct = pos.get("price_change_pct", 0)
        if abs(change_pct) < MIN_MOVE_PCT:
            continue

        weight = position_weight(pos, portfolio)
        if weight < MIN_POSITION_WEIGHT:
            print(f"   [FILTERED] Move {ticker} {change_pct:+.1f}% — weight {weight:.2%} < {MIN_POSITION_WEIGHT:.2%}")
            continue

        if abs(unrealized_pct(pos)) > MAX_UNREALIZED_PCT_ARTIFACT and weight < 0.05:
            print(f"   [FILTERED] Move {ticker} — extreme unrealized {unrealized_pct(pos):+.0f}% on tiny {weight:.2%} position (bad cost basis)")
            continue

        alert_id = alert_hash("MOVE", ticker, f"move_{change_pct:+.1f}")
        if not can_alert(state, alert_id, ticker, 24):
            continue

        llm_result = llm_enhance_move(ticker, change_pct, pos, portfolio, macro)

        if not llm_result.get("send", False):
            print(f"   [LLM BLOCKED] Move {ticker} {change_pct:+.1f}% — not actionable")
            continue

        review = deepseek_review(llm_result.get("_prompt_context", ""), llm_result)
        if not review.get("approved", False):
            print(f"   [DEEPSEEK REJECTED] Move {ticker} {change_pct:+.1f}% — {review.get('reason', 'fact-check failed')}")
            continue

        if review.get("corrected_headline"):
            llm_result["headline"] = review["corrected_headline"]
        if review.get("corrected_action"):
            llm_result["action"] = review["corrected_action"]

        emoji = "🚀" if change_pct > 0 else "🔻"
        alerts.append({
            "id": alert_id,
            "type": "MOVE",
            "ticker": ticker,
            "priority": llm_result.get("priority", "HIGH"),
            "message": f"""{emoji} *{llm_result.get('headline', f'{ticker} {change_pct:+.1f}%')}*

{llm_result.get('why', '')}

*Action:* {llm_result.get('action', 'Review position')}"""
        })
    return alerts


def check_news(state: dict, positions: List[Dict], portfolio: Dict) -> List[Dict]:
    alerts = []
    portfolio_tickers = {p.get("ticker", "") for p in positions}
    news_data = load_json(NEWS_FILE, {})

    for headline in news_data.get("portfolio_impact", []):
        ticker = headline.get("ticker", "")
        if ticker not in portfolio_tickers:
            continue

        score = headline.get("relevance_score", 0)
        title = headline.get("title", "")
        if score < 80:
            continue

        pos = next((p for p in positions if p.get("ticker") == ticker), {})
        weight = position_weight(pos, portfolio)
        if weight < MIN_POSITION_WEIGHT:
            print(f"   [FILTERED] News {ticker} — weight {weight:.2%} < {MIN_POSITION_WEIGHT:.2%}")
            continue

        alert_id = alert_hash("NEWS", ticker, f"news_{title[:40]}")
        if not can_alert(state, alert_id, ticker, 12):
            continue

        llm_result = llm_enhance_news(ticker, title, score, pos, portfolio)

        if not llm_result.get("send", False):
            print(f"   [LLM BLOCKED] News {ticker} — not actionable")
            continue

        review = deepseek_review(llm_result.get("_prompt_context", ""), llm_result)
        if not review.get("approved", False):
            print(f"   [DEEPSEEK REJECTED] News {ticker} — {review.get('reason', 'fact-check failed')}")
            continue

        if review.get("corrected_headline"):
            llm_result["headline"] = review["corrected_headline"]
        if review.get("corrected_action"):
            llm_result["action"] = review["corrected_action"]

        alerts.append({
            "id": alert_id,
            "type": "NEWS",
            "ticker": ticker,
            "priority": llm_result.get("priority", "HIGH"),
            "message": f"""📰 *{llm_result.get('headline', f'NEWS: {ticker}')}*

{llm_result.get('why', '')}

*Action:* {llm_result.get('action', 'Review position')}"""
        })
    return alerts


def check_digest(state: dict, positions: List[Dict], macro: Dict) -> List[Dict]:
    now = datetime.now(timezone.utc)
    if now.hour != 20:  # 8 PM UTC = 3 PM CT
        return []

    alert_id = alert_hash("DIGEST", "portfolio", now.strftime("%Y-%m-%d"))
    if alert_id in state.get("sent_alerts", {}):
        return []

    daily_alerts = [a for a in state.get("sent_alerts", {}).values()
                    if datetime.fromisoformat(a["sent_at"]).date() == now.date() and a["type"] != "DIGEST"]

    digest = llm_generate_digest(positions, daily_alerts, macro)

    return [{
        "id": alert_id,
        "type": "DIGEST",
        "ticker": "PORTFOLIO",
        "priority": "DIGEST",
        "message": digest
    }]


# ─── MAIN ────────────────────────────────────────────────────────────
def generate_alerts():
    state = load_state()
    positions = load_portfolio()
    portfolio = get_portfolio_context(positions)
    macro = get_macro_context()

    # Silent by default — only output if there are alerts
    all_alerts = []

    all_alerts.extend(check_stops(state, positions, portfolio, macro))
    all_alerts.extend(check_moves(state, positions, portfolio, macro))
    all_alerts.extend(check_news(state, positions, portfolio))
    all_alerts.extend(check_digest(state, positions, macro))

    # Apply daily limit
    non_digest = [a for a in all_alerts if a["type"] != "DIGEST"]
    digest = [a for a in all_alerts if a["type"] == "DIGEST"]

    if len(non_digest) > MAX_DAILY_ALERTS:
        non_digest = sorted(non_digest, key=lambda x: 0 if x["priority"] == "CRITICAL" else 1)[:MAX_DAILY_ALERTS]

    all_alerts = non_digest + digest

    if not all_alerts:
        # Silent exit — no noise when nothing is happening
        save_state(state)
        return []

    # Build and send message
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")

    if len(all_alerts) == 1 and all_alerts[0]["type"] == "DIGEST":
        combined = all_alerts[0]["message"]
    else:
        action_count = len([a for a in all_alerts if a["type"] != "DIGEST"])
        lines = [f"🚨 *VOX ALERTS — {action_count} Action Required*\n_{now}_\n"]
        for alert in all_alerts:
            lines.append(alert["message"])
            lines.append("\n" + "─" * 30 + "\n")
        combined = "\n".join(lines)

    sent = send_telegram(combined)
    print(combined)  # Only print the actual alert, not system noise

    # Record
    for alert in all_alerts:
        if alert["type"] == "DIGEST":
            state["sent_alerts"][alert["id"]] = {
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "ticker": "PORTFOLIO",
                "type": "DIGEST"
            }
        else:
            record_alert(state, alert["id"], alert["ticker"], alert["type"])

    # Update prices
    for pos in positions:
        ticker = pos.get("ticker", "")
        price = pos.get("live_price", 0)
        if ticker and price:
            state.setdefault("last_prices", {})[ticker] = price

    save_state(state)
    return all_alerts


if __name__ == "__main__":
    generate_alerts()
