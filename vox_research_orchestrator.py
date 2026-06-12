#!/usr/bin/env python3
"""
VOX Research Orchestrator
Coordinates all research agents and feeds into Council voting system

Pipeline:
1. Stock Researcher → technical + fundamental + thesis
2. Crypto Researcher → on-chain + sentiment + macro
3. X Intelligence → social sentiment + trending
4. Reddit Intelligence → retail sentiment + mentions
5. Volume Intelligence → unusual activity + institutional flow
6. Council Integration → all signals feed into voting
7. Watchlist Manager → auto-update with best opportunities

Runs every 4 hours via cron
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def run_researcher(script: str, name: str) -> dict:
    """Run a research agent and return results."""
    print(f"\n🔬 Running {name}...")
    print("-" * 40)
    
    try:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / script)],
            capture_output=True,
            text=True,
            timeout=300
        )
        print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        if result.stderr:
            print(f"   [stderr] {result.stderr[:200]}")
        return {"status": "ok", "output": result.stdout}
    except Exception as e:
        print(f"   ERROR: {e}")
        return {"status": "error", "error": str(e)}

def aggregate_research() -> dict:
    """Aggregate all research into unified signals."""
    print("\n" + "=" * 50)
    print("📊 AGGREGATING RESEARCH")
    print("=" * 50)
    
    signals = {}
    
    # Load stock research
    research_dir = SCRIPT_DIR / "research_reports"
    if research_dir.exists():
        for file in research_dir.glob("*.json"):
            ticker = file.stem
            with open(file) as f:
                data = json.load(f)
                signals[ticker] = {
                    "type": "stock",
                    "score": data.get("score", 50),
                    "signal": data.get("signal", "HOLD"),
                    "technical": data.get("technical", {}),
                    "levels": data.get("levels", {})
                }
    
    # Load crypto research
    crypto_dir = SCRIPT_DIR / "crypto_research"
    if crypto_dir.exists():
        aggregate_file = crypto_dir / "aggregate.json"
        if aggregate_file.exists():
            with open(aggregate_file) as f:
                data = json.load(f)
                for coin in data.get("coins", []):
                    signals[coin["symbol"]] = {
                        "type": "crypto",
                        "score": coin.get("score", 50),
                        "signal": coin.get("signal", "HOLD"),
                        "price": coin.get("price", 0)
                    }
    
    # Load X intelligence
    x_file = SCRIPT_DIR / "x_intelligence" / "x_intelligence.json"
    if x_file.exists():
        with open(x_file) as f:
            data = json.load(f)
            for result in data.get("results", []):
                ticker = result.get("ticker", "")
                if ticker in signals:
                    signals[ticker]["x_sentiment"] = result.get("sentiment", "NEUTRAL")
                    signals[ticker]["x_score"] = result.get("score", 50)
                    signals[ticker]["x_trending"] = result.get("trending", False)
    
    # Load Reddit intelligence
    reddit_file = SCRIPT_DIR / "reddit_intelligence" / "reddit_intelligence.json"
    if reddit_file.exists():
        with open(reddit_file) as f:
            data = json.load(f)
            for mention in data.get("top_mentions", [])[:20]:
                ticker = mention.get("ticker", "")
                if ticker in signals:
                    signals[ticker]["reddit_mentions"] = mention.get("mentions", 0)
                    signals[ticker]["reddit_score"] = mention.get("score", 0)
    
    # Load volume intelligence
    volume_file = SCRIPT_DIR / "volume_intelligence" / "volume_intelligence.json"
    if volume_file.exists():
        with open(volume_file) as f:
            data = json.load(f)
            for anomaly in data.get("anomalies", []):
                ticker = anomaly.get("ticker", "")
                if ticker in signals:
                    signals[ticker]["volume_signal"] = anomaly.get("signal", "NEUTRAL")
                    signals[ticker]["volume_ratio"] = anomaly.get("volume_ratio", 1)
    
    return signals

def generate_council_input(signals: dict) -> List[dict]:
    """Generate council votes from research signals."""
    council_votes = []
    
    for ticker, data in signals.items():
        # Weighted score from all sources
        base_score = data.get("score", 50)
        x_score = data.get("x_score", 50)
        reddit_score = data.get("reddit_score", 50)
        volume_ratio = data.get("volume_ratio", 1)
        
        # Volume boost
        volume_boost = 0
        if volume_ratio > 3:
            volume_boost = 15
        elif volume_ratio > 2:
            volume_boost = 10
        
        # Social sentiment boost
        social_boost = 0
        if data.get("x_trending"):
            social_boost = 10
        if data.get("reddit_mentions", 0) > 5:
            social_boost += 5
        
        final_score = min(100, base_score + volume_boost + social_boost)
        
        # Determine consensus
        if final_score >= 75:
            consensus = "STRONG_BUY"
        elif final_score >= 60:
            consensus = "BUY"
        elif final_score >= 45:
            consensus = "HOLD"
        elif final_score >= 30:
            consensus = "TRIM"
        else:
            consensus = "SELL"
        
        council_votes.append({
            "ticker": ticker,
            "consensus": consensus,
            "score": final_score,
            "technical_score": data.get("technical", {}).get("score", 50),
            "x_sentiment": data.get("x_sentiment", "NEUTRAL"),
            "reddit_mentions": data.get("reddit_mentions", 0),
            "volume_signal": data.get("volume_signal", "NEUTRAL"),
            "levels": data.get("levels", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    # Sort by score
    council_votes.sort(key=lambda x: x["score"], reverse=True)
    return council_votes

def update_watchlist(council_votes: List[dict]):
    """Update watchlist with top opportunities."""
    print("\n" + "=" * 50)
    print("👁️ UPDATING WATCHLIST")
    print("=" * 50)
    
    # Filter for buy opportunities
    buy_opportunities = [v for v in council_votes if v["consensus"] in ["STRONG_BUY", "BUY"]]
    
    watchlist = []
    for vote in buy_opportunities[:15]:  # Top 15
        watchlist.append({
            "ticker": vote["ticker"],
            "signal": vote["consensus"],
            "score": vote["score"],
            "buy_zone": vote.get("levels", {}).get("buy_zone", 0),
            "stop_loss": vote.get("levels", {}).get("stop_loss", 0),
            "target": vote.get("levels", {}).get("target_2", 0),
            "sources": [
                f"Technical: {vote.get('technical_score', 50)}",
                f"X: {vote.get('x_sentiment', 'NEUTRAL')}",
                f"Reddit: {vote.get('reddit_mentions', 0)} mentions",
                f"Volume: {vote.get('volume_signal', 'NEUTRAL')}"
            ],
            "added_at": datetime.now(timezone.utc).isoformat()
        })
    
    # Save
    watchlist_file = SCRIPT_DIR / "vox_autonomous_watchlist.json"
    with open(watchlist_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(watchlist),
            "watchlist": watchlist
        }, f, indent=2)
    
    print(f"   Updated with {len(watchlist)} opportunities")
    for w in watchlist[:5]:
        print(f"   🟢 {w['ticker']:6s} | {w['signal']:12s} | Score: {w['score']:2d} | Buy: ${w['buy_zone']}")

def update_council(council_votes: List[dict]):
    """Update council votes file."""
    council_file = SCRIPT_DIR / "vox_council_votes.json"
    
    with open(council_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_votes": len(council_votes),
            "strong_buy": len([v for v in council_votes if v["consensus"] == "STRONG_BUY"]),
            "buy": len([v for v in council_votes if v["consensus"] == "BUY"]),
            "hold": len([v for v in council_votes if v["consensus"] == "HOLD"]),
            "trim": len([v for v in council_votes if v["consensus"] == "TRIM"]),
            "sell": len([v for v in council_votes if v["consensus"] == "SELL"]),
            "results": council_votes
        }, f, indent=2)
    
    print(f"\n💾 Council updated: {len(council_votes)} votes")

def main():
    """Main orchestrator loop."""
    print("🤖 VOX RESEARCH ORCHESTRATOR")
    print("=" * 60)
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    
    # Run all research agents
    run_researcher("vox_stock_researcher.py", "Stock Researcher")
    run_researcher("vox_crypto_researcher.py", "Crypto Researcher")
    run_researcher("vox_x_intelligence.py", "X Intelligence")
    run_researcher("vox_reddit_intelligence.py", "Reddit Intelligence")
    run_researcher("vox_volume_intelligence.py", "Volume Intelligence")
    
    # Aggregate
    signals = aggregate_research()
    print(f"\n📊 Total signals aggregated: {len(signals)}")
    
    # Generate council votes
    council_votes = generate_council_input(signals)
    
    # Update systems
    update_council(council_votes)
    update_watchlist(council_votes)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ RESEARCH CYCLE COMPLETE")
    print("=" * 60)
    print(f"Signals: {len(signals)}")
    print(f"Council votes: {len(council_votes)}")
    print(f"Watchlist: {len([v for v in council_votes if v['consensus'] in ['STRONG_BUY', 'BUY']])} buy opportunities")
    print(f"Next run: +4 hours")

if __name__ == "__main__":
    main()
