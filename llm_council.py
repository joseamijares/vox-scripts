#!/usr/bin/env python3
"""
LLM Council — JOS-12
Multi-AI debate system for trade validation.
Uses OpenRouter to query Claude, GPT, and Grok.
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


def query_llm(model, prompt, max_tokens=500):
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
            "X-Title": "Vox Finance Council",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def build_prompt(ticker, grade_data, context=""):
    """Build the debate prompt for all agents."""
    price = grade_data.get("price", "N/A")
    total_grade = grade_data.get("total_grade", 0)
    breakdown = grade_data.get("breakdown", {})
    recommendation = grade_data.get("recommendation", "")

    breakdown_text = "\n".join([
        f"- {k.replace('_', ' ').title()}: {v['score']}/{v['max']}"
        for k, v in breakdown.items()
    ])

    return f"""You are a senior trading analyst. Analyze this stock for a swing trade (1-4 week hold).

STOCK: {ticker}
CURRENT PRICE: ${price}
VOX GRADE: {total_grade}/100
RECOMMENDATION: {recommendation}

GRADE BREAKDOWN:
{breakdown_text}

{context}

Provide your analysis in this exact format:

VERDICT: [BUY / SELL / HOLD / PASS]
CONFIDENCE: [1-10]
RATIONALE: [2-3 sentences max]
KEY RISK: [1 sentence]
POSITION SIZE: [Full / Half / Quarter / None]

Be concise. No fluff."""


def run_council(ticker, grade_data=None, context=""):
    """Run the LLM Council debate."""
    print("=" * 70)
    print("🧠 VOX LLM COUNCIL")
    print("=" * 70)
    print(f"Ticker: {ticker}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load grade data if not provided
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
        print(f"❌ No grade data found for {ticker}. Run: python3 grade_system.py {ticker}")
        return

    # Build prompt
    prompt = build_prompt(ticker, grade_data, context)

    # Define agents
    agents = {
        "Claude (Analyst)": "anthropic/claude-sonnet-4",
        "GPT (Contrarian)": "openai/gpt-4o",
        "Grok (Sentiment)": "x-ai/grok-4.3",
    }

    votes = {}
    responses = {}

    print("Querying AI Council...\n")

    for agent_name, model in agents.items():
        print(f"🤖 {agent_name} thinking...", end=" ")
        response = query_llm(model, prompt)
        responses[agent_name] = response

        # Parse verdict
        verdict = "UNKNOWN"
        for line in response.split("\n"):
            if line.startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip().upper()
                break

        votes[agent_name] = verdict
        print(f"→ {verdict}")

    # Calculate consensus
    buy_votes = sum(1 for v in votes.values() if v == "BUY")
    sell_votes = sum(1 for v in votes.values() if v == "SELL")
    hold_votes = sum(1 for v in votes.values() if v == "HOLD")
    pass_votes = sum(1 for v in votes.values() if v == "PASS")

    total = len(votes)
    consensus = "NO CONSENSUS"
    if buy_votes >= 2:
        consensus = "BUY"
    elif sell_votes >= 2:
        consensus = "SELL"
    elif hold_votes >= 2:
        consensus = "HOLD"
    elif pass_votes >= 2:
        consensus = "PASS"

    # Display results
    print("\n" + "=" * 70)
    print("COUNCIL RESULTS")
    print("=" * 70)

    for agent_name, response in responses.items():
        print(f"\n{'─' * 70}")
        print(f"🤖 {agent_name}")
        print(f"{'─' * 70}")
        print(response)

    print("\n" + "=" * 70)
    print("CONSENSUS")
    print("=" * 70)
    print(f"Votes: BUY={buy_votes}, SELL={sell_votes}, HOLD={hold_votes}, PASS={pass_votes}")
    print(f"\n🎯 CONSENSUS: {consensus}")

    # Save results
    out_path = Path.home() / ".hermes" / "scripts" / "llm_council_results.json"
    council_data = {
        "timestamp": datetime.now().isoformat(),
        "ticker": ticker,
        "grade": grade_data.get("total_grade", 0),
        "votes": votes,
        "consensus": consensus,
        "responses": responses,
    }

    # Append to history
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
        print("Usage: python3 llm_council.py TICKER [context]")
        print("Example: python3 llm_council.py WDC 'Trump announced tariffs on semiconductors'")
        return

    ticker = sys.argv[1].upper()
    context = sys.argv[2] if len(sys.argv) > 2 else ""
    run_council(ticker, context=context)


if __name__ == "__main__":
    main()
