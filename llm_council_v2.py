#!/usr/bin/env python3
"""
LLM Council v2 — Multi-Agent Trading Debate
5 specialized agents: Fundamental, Technical, Sentiment, Risk, Contrarian
Uses OpenRouter for multi-model access.
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


def query_llm(model, prompt, max_tokens=800):
    """Query an LLM via OpenRouter."""
    env = load_env()
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set"}

    url = "https://openrouter.ai/api/v1/chat/completions"
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://vox-finance.local",
            "X-Title": "Vox Finance Council v2",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def build_agent_prompt(agent_role, ticker, grade_data, context=""):
    """Build specialized prompt for each agent."""
    price = grade_data.get("price", "N/A")
    total_grade = grade_data.get("total_grade", 0)
    breakdown = grade_data.get("breakdown", {})

    prompts = {
        "Fundamental": f"""You are a fundamental analyst. Focus on company financials, valuation, and business quality.

STOCK: {ticker} at ${price}
Fundamental Score: {breakdown.get('fundamental', {}).get('score', 'N/A')}/25

Analyze: Is this company financially healthy? Is it undervalued or overvalued?

Respond with:
VERDICT: [BULLISH / BEARISH / NEUTRAL]
CONFIDENCE: [1-10]
KEY POINT: [One sentence on financial health]
CONCERN: [One risk factor]""",

        "Technical": f"""You are a technical analyst. Focus on price action, trends, and chart patterns.

STOCK: {ticker} at ${price}
Technical Score: {breakdown.get('technical', {}).get('score', 'N/A')}/25
EMA21: {grade_data.get('ema21', 'N/A')}
EMA50: {grade_data.get('ema50', 'N/A')}
RSI: {grade_data.get('rsi', 'N/A')}

Analyze: Is the trend bullish? Is this a good entry point for a 1-4 week swing trade?

Respond with:
VERDICT: [BULLISH / BEARISH / NEUTRAL]
CONFIDENCE: [1-10]
KEY POINT: [One sentence on trend/setup]
CONCERN: [One technical risk]""",

        "Sentiment": f"""You are a sentiment analyst. Focus on market mood, social media, news, and insider activity.

STOCK: {ticker} at ${price}
Sentiment Score: {breakdown.get('sentiment', {}).get('score', 'N/A')}/20

Context: {context}

Analyze: Is sentiment positive or negative? Any news catalysts?

Respond with:
VERDICT: [BULLISH / BEARISH / NEUTRAL]
CONFIDENCE: [1-10]
KEY POINT: [One sentence on sentiment]
CONCERN: [One sentiment risk]""",

        "Risk": f"""You are a risk manager. Focus on position sizing, volatility, and portfolio impact.

STOCK: {ticker} at ${price}
Risk/Reward Score: {breakdown.get('risk_reward', {}).get('score', 'N/A')}/15
Total Grade: {total_grade}/100

Analyze: Is the risk/reward favorable? What position size is appropriate?

Respond with:
VERDICT: [APPROVE / REJECT / REDUCE]
CONFIDENCE: [1-10]
KEY POINT: [One sentence on risk assessment]
POSITION_SIZE: [Full / Half / Quarter / None]""",

        "Contrarian": f"""You are a contrarian analyst. Play devil's advocate. Find reasons NOT to trade this.

STOCK: {ticker} at ${price}
Total Grade: {total_grade}/100

Analyze: What could go wrong? Why might this trade fail?

Respond with:
VERDICT: [BULLISH / BEARISH / NEUTRAL]
CONFIDENCE: [1-10]
KEY POINT: [One sentence on contrarian view]
CONCERN: [Biggest risk to this trade]""",
    }

    return prompts.get(agent_role, "Analyze this stock.")


def parse_verdict(response):
    """Parse verdict from agent response."""
    for line in response.split("\n"):
        if line.startswith("VERDICT:"):
            return line.split(":", 1)[1].strip().upper()
    return "UNKNOWN"


def run_council_v2(ticker, grade_data=None, context=""):
    """Run the full LLM Council v2 with 5 agents."""
    print("=" * 80)
    print("🧠 VOX LLM COUNCIL v2 — Multi-Agent Debate")
    print("=" * 80)
    print(f"Ticker: {ticker} | Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load grade data
    if grade_data is None:
        grade_path = Path.home() / ".hermes" / "scripts" / "grade_results.json"
        if grade_path.exists():
            with open(grade_path) as f:
                data = json.load(f)
            for g in data.get("grades", []):
                if g["ticker"] == ticker:
                    grade_data = g
                    break

    if not grade_data:
        print(f"❌ No grade data for {ticker}. Run: python3 grade_system.py {ticker}")
        return

    # Agent configuration
    agents = {
        "Fundamental": "anthropic/claude-sonnet-4",
        "Technical": "openai/gpt-4o",
        "Sentiment": "x-ai/grok-4.3",
        "Risk": "anthropic/claude-sonnet-4",
        "Contrarian": "openai/gpt-4o",
    }

    votes = {}
    responses = {}

    print("🔄 Running 5 specialized agents...\n")

    for agent_name, model in agents.items():
        print(f"🤖 {agent_name:12} analyzing...", end=" ")
        prompt = build_agent_prompt(agent_name, ticker, grade_data, context)
        response = query_llm(model, prompt)
        responses[agent_name] = response
        verdict = parse_verdict(response)
        votes[agent_name] = verdict
        print(f"→ {verdict}")

    # Calculate consensus
    bullish = sum(1 for v in votes.values() if v in ["BULLISH", "APPROVE"])
    bearish = sum(1 for v in votes.values() if v in ["BEARISH", "REJECT"])
    neutral = sum(1 for v in votes.values() if v == "NEUTRAL")
    total = len(votes)

    if bullish >= 3:
        consensus = "BULLISH"
    elif bearish >= 3:
        consensus = "BEARISH"
    elif bullish >= 2 and neutral >= 2:
        consensus = "CAUTIOUSLY BULLISH"
    elif bearish >= 2 and neutral >= 2:
        consensus = "CAUTIOUSLY BEARISH"
    else:
        consensus = "NEUTRAL"

    # Display results
    print("\n" + "=" * 80)
    print("AGENT REPORTS")
    print("=" * 80)

    for agent_name, response in responses.items():
        print(f"\n{'─' * 80}")
        print(f"🤖 {agent_name}")
        print(f"{'─' * 80}")
        print(response)

    print("\n" + "=" * 80)
    print("CONSENSUS")
    print("=" * 80)
    print(f"Votes: BULLISH={bullish}, BEARISH={bearish}, NEUTRAL={neutral}")
    print(f"\n🎯 CONSENSUS: {consensus}")

    # Action recommendation
    if consensus == "BULLISH":
        print("✅ ACTION: Consider entry with proper position size")
    elif consensus == "BEARISH":
        print("❌ ACTION: Avoid or exit existing position")
    elif consensus == "CAUTIOUSLY BULLISH":
        print("⚠️ ACTION: Small position or wait for confirmation")
    elif consensus == "CAUTIOUSLY BEARISH":
        print("⚠️ ACTION: Reduce or trim position")
    else:
        print("⏸️ ACTION: No action — monitor for setup improvement")

    # Save results
    out_path = Path.home() / ".hermes" / "scripts" / "llm_council_v2_results.json"
    council_data = {
        "timestamp": datetime.now().isoformat(),
        "ticker": ticker,
        "grade": grade_data.get("total_grade", 0),
        "votes": votes,
        "consensus": consensus,
        "responses": responses,
    }

    history = []
    if out_path.exists():
        try:
            with open(out_path) as f:
                history = json.load(f)
        except:
            pass
    if not isinstance(history, list):
        history = []

    history.append(council_data)
    with open(out_path, "w") as f:
        json.dump(history, f, indent=2)

    print(f"\n💾 Saved to: {out_path}")
    return council_data


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 llm_council_v2.py TICKER [context]")
        print("Example: python3 llm_council_v2.py GS 'Financial sector rally post-earnings'")
        return

    ticker = sys.argv[1].upper()
    context = sys.argv[2] if len(sys.argv) > 2 else ""
    run_council_v2(ticker, context=context)


if __name__ == "__main__":
    main()
