#!/usr/bin/env python3
"""
VOX Sentiment Analyst Agent
Monitors X, Reddit, fear/greed index.
Tracks ticker mentions, sentiment shifts.
Outputs: sentiment score per ticker (-100 to +100).

Usage:
    python3 sentiment_analyst.py analyze --ticker TSLA
    python3 sentiment_analyst.py batch
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Mock sentiment data (would integrate with X API, Reddit API in production)
# For now, use a simple heuristic based on recent price action

def analyze_sentiment(ticker: str) -> Dict:
    """Analyze sentiment for a ticker"""
    # In production, this would:
    # 1. Search X for ticker mentions
    # 2. Analyze Reddit r/wallstreetbets, r/stocks
    # 3. Check fear/greed index
    # 4. Check options flow (unusual calls/puts)
    
    # Mock implementation based on recent price action
    # Would be replaced with real API calls
    
    # Read technical analysis for context
    tech_file = Path.home() / ".hermes" / "scripts" / "vox_technical_analysis.json"
    
    sentiment_score = 0
    signals = []
    
    if tech_file.exists():
        with open(tech_file) as f:
            data = json.load(f)
        
        # Find this ticker's technical analysis
        for result in data.get("results", []):
            if result["ticker"] == ticker:
                # If technically bullish, assume positive sentiment
                if result["conviction"] > 30:
                    sentiment_score += 30
                    signals.append("technical_momentum")
                elif result["conviction"] < -30:
                    sentiment_score -= 30
                    signals.append("technical_weakness")
                
                # Volume spike = attention
                if result["volume"]["trend"] == "spike":
                    sentiment_score += 10
                    signals.append("volume_attention")
                
                break
    
    # Mock social sentiment (would be real API data)
    # For demonstration, randomize slightly around technical signal
    import random
    random.seed(hash(ticker) % 2**32)
    noise = random.randint(-20, 20)
    sentiment_score += noise
    
    if noise > 10:
        signals.append("social_buzz")
    elif noise < -10:
        signals.append("social_concern")
    
    # Clamp
    sentiment_score = max(-100, min(100, sentiment_score))
    
    # Determine sentiment
    if sentiment_score > 50:
        sentiment = "VERY_BULLISH"
    elif sentiment_score > 20:
        sentiment = "BULLISH"
    elif sentiment_score < -50:
        sentiment = "VERY_BEARISH"
    elif sentiment_score < -20:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"
    
    return {
        "ticker": ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sentiment": sentiment,
        "score": sentiment_score,
        "signals": signals,
        "sources": ["technical_proxy", "mock_social"],  # Would be ["x", "reddit", "fear_greed"]
    }


def analyze_portfolio() -> List[Dict]:
    """Analyze sentiment for all portfolio tickers"""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    
    if not positions_file.exists():
        print("❌ No portfolio data")
        return []
    
    with open(positions_file) as f:
        data = json.load(f)
    
    tickers = list(set(p["ticker"] for p in data.get("positions", [])))
    
    print(f"\n💭 Analyzing sentiment for {len(tickers)} tickers...")
    
    results = []
    for ticker in tickers[:20]:
        result = analyze_sentiment(ticker)
        results.append(result)
        
        emoji = "🟢" if result["score"] > 20 else "🔴" if result["score"] < -20 else "⚪"
        print(f"   {emoji} {ticker:8} | {result['sentiment']:15} | Score: {result['score']:+d}")
    
    # Save
    output_file = Path.home() / ".hermes" / "scripts" / "vox_sentiment_analysis.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": results,
        }, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Sentiment Analyst")
    parser.add_argument("--ticker", help="Analyze specific ticker")
    parser.add_argument("--batch", action="store_true", help="Analyze all portfolio tickers")
    
    args = parser.parse_args()
    
    if args.ticker:
        result = analyze_sentiment(args.ticker)
        print(json.dumps(result, indent=2))
    else:
        analyze_portfolio()


if __name__ == "__main__":
    main()
