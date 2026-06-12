#!/usr/bin/env python3
"""
VOX LLM Alert Layer v1.0
Enhances raw alerts with AI-generated context, reasoning, and action recommendations.

What it does:
1. Takes raw alert signals (stop, move, news, trump)
2. Queries LLM with full context (position size, thesis, macro, sector)
3. Returns: should_alert (yes/no), priority, enhanced_message, action_plan

Rules:
- LLM decides if alert is WORTH sending (not just if signal triggered)
- Provides WHY the alert matters to YOUR portfolio specifically
- Suggests exact action with position sizing
- Never generic — always personalized to your holdings and thesis
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# LLM Configuration
LLM_PROVIDER = "openrouter"  # Can switch to anthropic, openai, etc.
LLM_MODEL = "anthropic/claude-sonnet-4"

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

def call_llm(prompt: str, max_tokens: int = 800) -> str:
    """Call LLM via OpenRouter."""
    env = load_env()
    api_key = env.get("OPENROUTER_API_KEY", "")
    
    if not api_key:
        print("[LLM] No API key found, skipping enhancement")
        return ""
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vox-dashboard-five.vercel.app",
        "X-Title": "VOX Alert System"
    }
    
    data = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are VOX, an elite trading intelligence system. You analyze alerts for a $203K portfolio. Be concise, actionable, and specific. Never generic advice. Always reference exact position sizes and portfolio context."
            },
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return ""

def enhance_stop_alert(ticker: str, stop_price: float, current_price: float, 
                       position: Dict, portfolio_context: Dict) -> Dict:
    """Enhance stop alert with LLM reasoning."""
    
    prompt = f"""Analyze this stop loss alert for the portfolio:

TICKER: {ticker}
STOP PRICE: ${stop_price:.2f}
CURRENT PRICE: ${current_price:.2f}
POSITION SIZE: ${position.get('live_value', 0):,.0f} ({position.get('shares', 0):.2f} shares)
AVG COST: ${position.get('avg_cost', 0):.2f}
UNREALIZED P&L: {((current_price - position.get('avg_cost', 0)) / position.get('avg_cost', 1) * 100):+.1f}%

PORTFOLIO CONTEXT:
- Total portfolio: ${portfolio_context.get('total_value', 0):,.0f}
- This position: {position.get('live_value', 0) / portfolio_context.get('total_value', 1) * 100:.1f}% of portfolio
- Cash available: ${portfolio_context.get('cash', 0):,.0f}

TASK:
1. Should this alert be sent? (yes/no + why)
2. What's the exact action? (sell X shares at market/limit?)
3. Any nuance? (partial close? move stop? hold through?)

Respond in JSON:
{{
    "should_alert": true/false,
    "priority": "CRITICAL/HIGH/MEDIUM",
    "reasoning": "2-3 sentences",
    "action": "exact action with numbers",
    "nuance": "any special consideration"
}}"""
    
    response = call_llm(prompt, max_tokens=600)
    
    try:
        # Extract JSON from response
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(response[json_start:json_end])
        else:
            result = {
                "should_alert": True,
                "priority": "CRITICAL",
                "reasoning": f"Stop hit at ${stop_price:.2f}, current ${current_price:.2f}",
                "action": f"SELL {position.get('shares', 0):.2f} shares of {ticker} at market",
                "nuance": "Stop loss triggered — execute immediately"
            }
    except:
        result = {
            "should_alert": True,
            "priority": "CRITICAL",
            "reasoning": f"Stop hit at ${stop_price:.2f}, current ${current_price:.2f}",
            "action": f"SELL {position.get('shares', 0):.2f} shares of {ticker} at market",
            "nuance": "Stop loss triggered — execute immediately"
        }
    
    return result

def enhance_move_alert(ticker: str, change_pct: float, position: Dict, 
                       portfolio_context: Dict, macro_context: Dict) -> Dict:
    """Enhance big move alert with LLM reasoning."""
    
    prompt = f"""Analyze this big move alert:

TICKER: {ticker}
DAILY MOVE: {change_pct:+.1f}%
CURRENT PRICE: ${position.get('live_price', 0):.2f}
POSITION SIZE: ${position.get('live_value', 0):,.0f}
UNREALIZED P&L: {((position.get('live_price', 0) - position.get('avg_cost', 0)) / position.get('avg_cost', 1) * 100):+.1f}%

MACRO CONTEXT:
- VIX: {macro_context.get('vix', 'N/A')}
- Market regime: {macro_context.get('regime', 'N/A')}
- Sector rotation: {macro_context.get('sector_rotation', 'N/A')}

PORTFOLIO CONTEXT:
- Total portfolio: ${portfolio_context.get('total_value', 0):,.0f}
- This position: {position.get('live_value', 0) / portfolio_context.get('total_value', 1) * 100:.1f}% of portfolio

TASK:
1. Is this move significant enough to alert? (yes/no + why)
2. What's causing it? (earnings? news? sector rotation?)
3. What action if any? (trim? add? hold? set stop?)
4. Position sizing recommendation

Respond in JSON:
{{
    "should_alert": true/false,
    "priority": "CRITICAL/HIGH/MEDIUM/LOW",
    "cause": "likely cause",
    "reasoning": "2-3 sentences",
    "action": "exact action",
    "position_size": "recommended sizing"
}}"""
    
    response = call_llm(prompt, max_tokens=700)
    
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(response[json_start:json_end])
        else:
            raise ValueError("No JSON found")
    except:
        result = {
            "should_alert": abs(change_pct) >= 10,
            "priority": "HIGH" if abs(change_pct) >= 15 else "MEDIUM",
            "cause": "Unknown",
            "reasoning": f"{ticker} moved {change_pct:+.1f}% today",
            "action": "Review position" if change_pct > 0 else "Check thesis",
            "position_size": "No change"
        }
    
    return result

def enhance_news_alert(ticker: str, headline: str, relevance: int, 
                       position: Dict, portfolio_context: Dict) -> Dict:
    """Enhance news alert with LLM reasoning."""
    
    prompt = f"""Analyze this news alert:

TICKER: {ticker}
HEADLINE: {headline}
RELEVANCE SCORE: {relevance}/100
POSITION SIZE: ${position.get('live_value', 0):,.0f}
UNREALIZED P&L: {((position.get('live_price', 0) - position.get('avg_cost', 0)) / position.get('avg_cost', 1) * 100):+.1f}%

PORTFOLIO CONTEXT:
- Total portfolio: ${portfolio_context.get('total_value', 0):,.0f}
- This position: {position.get('live_value', 0) / portfolio_context.get('total_value', 1) * 100:.1f}% of portfolio

TASK:
1. Is this news actionable? (yes/no + why)
2. Bullish or bearish for this position?
3. What action if any?
4. Urgency level?

Respond in JSON:
{{
    "should_alert": true/false,
    "priority": "CRITICAL/HIGH/MEDIUM/LOW",
    "direction": "BULLISH/BEARISH/NEUTRAL",
    "reasoning": "2-3 sentences",
    "action": "exact action",
    "urgency": "immediate/today/this week/none"
}}"""
    
    response = call_llm(prompt, max_tokens=600)
    
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(response[json_start:json_end])
        else:
            raise ValueError("No JSON found")
    except:
        result = {
            "should_alert": relevance >= 80,
            "priority": "HIGH" if relevance >= 90 else "MEDIUM",
            "direction": "NEUTRAL",
            "reasoning": f"News relevance {relevance}/100 for {ticker}",
            "action": "Review position",
            "urgency": "today"
        }
    
    return result

def generate_digest_summary(positions: List[Dict], alerts_today: List[Dict], 
                           macro_context: Dict) -> str:
    """Generate LLM-enhanced daily digest."""
    
    total_value = sum(p.get('live_value', 0) or 0 for p in positions)
    top_movers = sorted(positions, key=lambda x: abs(x.get('price_change_pct', 0)), reverse=True)[:5]
    
    movers_text = "\n".join([
        f"- {p.get('ticker')}: {p.get('price_change_pct', 0):+.1f}% (${p.get('live_value', 0):,.0f})"
        for p in top_movers
    ])
    
    prompt = f"""Generate a daily portfolio digest:

PORTfolio: ${total_value:,.0f} | {len(positions)} positions

TOP MOVERS TODAY:
{movers_text}

ALERTS TODAY: {len(alerts_today)}
{chr(10).join([f"- {a.get('type')} {a.get('ticker')}: {a.get('reasoning', '')}" for a in alerts_today[:3]]) if alerts_today else "None"}

MACRO:
- Regime: {macro_context.get('regime', 'N/A')}
- VIX: {macro_context.get('vix', 'N/A')}

TASK: Write a concise, insightful digest. 1-2 paragraphs max. Include:
1. Key takeaway from today's action
2. Any positions needing attention tomorrow
3. Macro context implication

Be specific. Reference actual tickers and numbers. No generic advice."""
    
    response = call_llm(prompt, max_tokens=800)
    
    if not response:
        # Fallback
        lines = [
            f"📊 *VOX DAILY DIGEST*",
            f"",
            f"Portfolio: *${total_value:,.0f}* | {len(positions)} positions",
            f"",
            f"*Top Movers:*"
        ]
        for p in top_movers[:3]:
            emoji = "🟢" if p.get('price_change_pct', 0) > 0 else "🔴"
            lines.append(f"{emoji} {p.get('ticker')}: {p.get('price_change_pct', 0):+.1f}%")
        lines.append(f"")
        lines.append(f"*Alerts today:* {len(alerts_today)}")
        lines.append(f"")
        lines.append(f"*No action required. Digest only.*")
        response = "\n".join(lines)
    
    return response

if __name__ == "__main__":
    # Test
    print("🧠 VOX LLM Alert Layer")
    print("=" * 50)
    
    # Test with sample data
    test_position = {
        "ticker": "NVDA",
        "shares": 10,
        "avg_cost": 750.00,
        "live_price": 892.34,
        "live_value": 8923.40,
        "price_change_pct": 12.5
    }
    
    portfolio = {"total_value": 203660, "cash": 15000}
    macro = {"vix": 18.5, "regime": "RISK_ON", "sector_rotation": "TECH_LEADERSHIP"}
    
    print("\nTesting move alert enhancement...")
    result = enhance_move_alert("NVDA", 12.5, test_position, portfolio, macro)
    print(json.dumps(result, indent=2))
