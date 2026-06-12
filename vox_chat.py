#!/usr/bin/env python3
"""
VOX Chat Interface v1.0
Natural language interface to VOX.

Usage:
    python3 vox_chat.py "Should I trim crypto?"
    python3 vox_chat.py "What are my worst positions?"
    python3 vox_chat.py "Run council on TSLA"
    python3 vox_chat.py "Generate insights"
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"


def load_json(filename: str) -> Dict:
    filepath = SCRIPTS_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


def parse_query(query: str) -> Dict:
    """Parse natural language query into intent"""
    query_lower = query.lower()
    
    # Intent detection
    intents = {
        "portfolio_status": ["portfolio", "positions", "holdings", "what do i have"],
        "worst_positions": ["worst", "losing", "biggest loser", "biggest loss"],
        "best_positions": ["best", "winning", "biggest winner", "biggest gain"],
        "crypto_check": ["crypto", "bitcoin", "btc", "eth", "ethereum"],
        "trim_crypto": ["trim crypto", "reduce crypto", "sell crypto", "crypto too much"],
        "run_council": ["council", "vote", "agent", "analyze"],
        "generate_insights": ["insight", "what should i know", "important"],
        "predict": ["predict", "forecast", "where is", "going to"],
        "plays": ["play", "trade", "buy", "sell"],
        "earnings": ["earnings", "report", "quarterly"],
        "help": ["help", "what can you do", "commands"],
    }
    
    detected_intent = None
    for intent, keywords in intents.items():
        if any(kw in query_lower for kw in keywords):
            detected_intent = intent
            break
    
    # Extract ticker
    ticker_match = re.search(r'\b([A-Z]{1,5})\b', query.upper())
    ticker = ticker_match.group(1) if ticker_match else None
    
    return {
        "intent": detected_intent or "unknown",
        "ticker": ticker,
        "raw_query": query,
    }


def handle_portfolio_status() -> str:
    """Handle portfolio status query"""
    portfolio = load_json("dashboard_positions.json")
    positions = portfolio.get("positions", [])
    total = portfolio.get("total_value", sum(p.get("value", 0) for p in positions))
    
    losers = [p for p in positions if p.get("pnl", 0) < -500]
    low_grades = [p for p in positions if p.get("grade", 0) > 0 and p.get("grade", 0) < 45]
    
    response = f"📊 Portfolio: ${total:,.0f} across {len(positions)} positions.\n"
    
    if losers:
        response += f"\n🔴 {len(losers)} positions losing >$500."
    if low_grades:
        response += f"\n⚠️ {len(low_grades)} positions with grade <45 (consider selling)."
    
    if not losers and not low_grades:
        response += "\n✅ Portfolio looks healthy. No urgent actions."
    
    return response


def handle_worst_positions() -> str:
    """Handle worst positions query"""
    portfolio = load_json("dashboard_positions.json")
    positions = portfolio.get("positions", [])
    
    losers = sorted([p for p in positions if p.get("pnl", 0) < 0], 
                   key=lambda x: x["pnl"])[:5]
    
    if not losers:
        return "✅ No losing positions! Great job."
    
    response = "📉 Worst Positions:\n"
    for p in losers:
        response += f"\n   {p['ticker']}: ${p['pnl']:,.0f} loss ({p.get('pnlPct', 0):.1f}%)"
        if p.get("grade"):
            response += f" | Grade: {p['grade']}"
    
    return response


def handle_crypto_check() -> str:
    """Handle crypto check query"""
    portfolio = load_json("dashboard_positions.json")
    positions = portfolio.get("positions", [])
    total = portfolio.get("total_value", sum(p.get("value", 0) for p in positions))
    
    crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX", "SUI"]
    crypto_positions = [p for p in positions if p["ticker"] in crypto_tickers]
    crypto_value = sum(p["value"] for p in crypto_positions)
    crypto_pct = crypto_value / total * 100 if total > 0 else 0
    
    response = f"₿ Crypto: ${crypto_value:,.0f} ({crypto_pct:.1f}% of portfolio)\n"
    
    if crypto_pct > 10:
        response += f"\n⚠️ OVERWEIGHT! Limit is 10%. Consider trimming ${crypto_value - total * 0.1:,.0f}."
        response += "\n   Run: python3 vox_paper_trader.py execute-plays"
    elif crypto_pct > 7:
        response += "\n🟡 Close to limit. Monitor closely."
    else:
        response += "\n✅ Within limits."
    
    response += f"\n\n   Holdings:"
    for p in crypto_positions:
        response += f"\n   • {p['ticker']}: ${p['value']:,.0f}"
    
    return response


def handle_run_council(ticker: Optional[str] = None) -> str:
    """Handle council run query"""
    if ticker:
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "vox_council.py"), "--ticker", ticker],
            capture_output=True, text=True, timeout=60
        )
        return f"🗳️ Council vote for {ticker}:\n{result.stdout[:500]}"
    else:
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "vox_council.py"), "--batch"],
            capture_output=True, text=True, timeout=120
        )
        return f"🗳️ Running council on all positions...\n{result.stdout[:300]}"


def handle_predict(ticker: str) -> str:
    """Handle prediction query"""
    result = subprocess.run(
        ["python3", str(SCRIPTS_DIR / "vox_predictive.py"), "ticker", "--ticker", ticker],
        capture_output=True, text=True, timeout=60
    )
    
    try:
        pred = json.loads(result.stdout)
        emoji = "🟢" if pred["direction"] == "UP" else "🔴" if pred["direction"] == "DOWN" else "⚪"
        response = f"{emoji} {ticker} Prediction:\n"
        response += f"   Direction: {pred['direction']} ({pred['confidence']}% confidence)\n"
        response += f"   Target: {pred['target']} | Timeframe: {pred['timeframe']}\n"
        response += f"\n   Reasons:\n"
        for reason in pred.get("reasons", [])[:2]:
            response += f"   • {reason}\n"
        return response
    except:
        return f"No prediction available for {ticker}."


def handle_help() -> str:
    """Handle help query"""
    return """
🤖 VOX Chat - What I can do:

Portfolio:
   "What are my worst positions?" - Show biggest losers
   "How's my crypto?" - Check crypto allocation
   "Portfolio status" - Overall health check

Analysis:
   "Run council on TSLA" - Agent voting
   "Predict NVDA" - Price forecast
   "Generate insights" - Proactive intelligence

Actions:
   "Should I trim crypto?" - Rebalancing advice
   "Execute plays" - Paper trade signals
   "What plays for tomorrow?" - Next day setup

Just ask naturally - I understand context!
"""


def process_query(query: str) -> str:
    """Process a natural language query"""
    parsed = parse_query(query)
    intent = parsed["intent"]
    ticker = parsed["ticker"]
    
    handlers = {
        "portfolio_status": handle_portfolio_status,
        "worst_positions": handle_worst_positions,
        "best_positions": handle_worst_positions,  # Same logic, different sort
        "crypto_check": handle_crypto_check,
        "trim_crypto": handle_crypto_check,
        "run_council": lambda: handle_run_council(ticker),
        "predict": lambda: handle_predict(ticker) if ticker else "Which ticker?",
        "help": handle_help,
    }
    
    handler = handlers.get(intent)
    if handler:
        return handler()
    
    return f"🤔 I'm not sure what you mean by '{query}'. Try 'help' for examples."


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Chat")
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    if args.interactive:
        print("🤖 VOX Chat - Type 'exit' to quit")
        print("=" * 50)
        while True:
            try:
                query = input("\nYou: ").strip()
                if query.lower() in ["exit", "quit", "bye"]:
                    print("👋 Goodbye!")
                    break
                if query:
                    response = process_query(query)
                    print(f"\nVOX: {response}")
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
    elif args.query:
        response = process_query(args.query)
        print(response)
    else:
        print("Usage: python3 vox_chat.py 'your question'")
        print("       python3 vox_chat.py --interactive")


if __name__ == "__main__":
    main()
