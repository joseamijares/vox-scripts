#!/usr/bin/env python3
"""
VOX Agent Council v1.0
Multi-agent voting system for trading decisions.

4 agents debate each play:
- Technical Analyst: Charts, patterns, volume
- Macro Analyst: Fed, CPI, sector rotation
- Sentiment Analyst: X, Reddit, fear/greed
- Risk Manager: Position sizing, correlation, drawdown

Each votes BUY/HOLD/SELL with conviction.
Weighted by historical accuracy.
Final consensus + dissent recorded.

Usage:
    python3 vox_council.py vote --ticker TSLA
    python3 vox_council.py vote --ticker NVDA --action BUY
    python3 vox_council.py batch
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

AGENTS_DIR = Path.home() / ".hermes" / "scripts" / "vox_agents"
OUTPUT_FILE = Path.home() / ".hermes" / "scripts" / "vox_council_votes.json"
DASHBOARD_FILE = Path.home() / "dev" / "vox-dashboard" / "public" / "vox_council_votes.json"
SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Load data sources
GRADES_FILE = SCRIPT_DIR / "portfolio_grades.json"
X_MOMENTUM_FILE = SCRIPT_DIR / "snapshots" / "x_momentum_latest.json"
VOLUME_FILE = SCRIPT_DIR / "vox_volume_scan.json"
NEWS_FILE = SCRIPT_DIR / "vox_news_digest.json"

# Agent weights (would be updated based on historical accuracy)
AGENT_WEIGHTS = {
    "technical": 1.0,
    "macro": 0.9,
    "sentiment": 0.7,
    "risk": 1.2,  # Risk manager gets higher weight
}


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def get_grade_data(ticker: str) -> Dict:
    """Get grade data for ticker from portfolio_grades.json."""
    data = load_json(GRADES_FILE, {})
    
    # Handle new format: {results: [...]}
    if isinstance(data, dict) and "results" in data:
        results = data["results"]
        if isinstance(results, list):
            for item in results:
                if item.get("ticker") == ticker:
                    return {"grade": item.get("grade", 0), "category": "graded"}
        elif isinstance(results, dict):
            if ticker in results:
                item = results[ticker]
                if isinstance(item, dict):
                    return {"grade": item.get("grade", 0), "category": "graded"}
                return {"grade": item, "category": "graded"}
    
    # Handle old format: {strong_buy: [...], moderate_buy: [...], avoid: [...]}
    for cat in ["strong_buy", "moderate_buy", "avoid"]:
        for item in data.get(cat, []):
            if isinstance(item, dict) and item.get("ticker") == ticker:
                return {"grade": item.get("grade", 0), "category": cat}
    
    return {}


def get_x_momentum_data(ticker: str) -> Dict:
    """Get X momentum data for ticker."""
    data = load_json(X_MOMENTUM_FILE, {})
    for item in data.get("results", []):
        if item["ticker"] == ticker:
            return {
                "sentiment": item.get("sentiment", "NEUTRAL"),
                "mentions": item.get("mentions", 0),
                "score": item.get("score", 0)
            }
    return {}


def get_volume_data(ticker: str) -> Dict:
    """Get volume data for ticker."""
    data = load_json(VOLUME_FILE, {})
    for item in data.get("results", []):
        if item["ticker"] == ticker:
            return {
                "volume_ratio": item.get("volume_ratio", 0),
                "alert": item.get("alert", "NONE"),
                "price_change": item.get("price_change_pct", 0)
            }
    return {}


def get_news_data(ticker: str) -> Dict:
    """Get news data for ticker."""
    data = load_json(NEWS_FILE, {})
    headlines = []
    for item in data.get("portfolio_impact", []):
        if item["ticker"] == ticker:
            headlines.append({
                "title": item.get("title", ""),
                "score": item.get("relevance_score", 0)
            })
    if headlines:
        best = max(headlines, key=lambda x: x["score"])
        return {"headline": best["title"], "score": best["score"]}
    return {}


def run_agent(agent_name: str, ticker: str = None) -> Dict:
    """Run an agent and get its vote"""
    script = AGENTS_DIR / f"{agent_name}.py"
    
    if not script.exists():
        return {"agent": agent_name, "error": "Agent not found"}
    
    try:
        if ticker:
            result = subprocess.run(
                ["python3", str(script), "--ticker", ticker],
                capture_output=True, text=True, timeout=30
            )
        else:
            result = subprocess.run(
                ["python3", str(script)],
                capture_output=True, text=True, timeout=60
            )
        
        # Parse output (agents print JSON or structured text)
        # For now, read their output files
        return parse_agent_output(agent_name, ticker)
    
    except Exception as e:
        return {"agent": agent_name, "error": str(e)}


def parse_agent_output(agent_name: str, ticker: str) -> Dict:
    """Parse agent output files — now with REAL data from vox signals"""
    
    # Load real signal data
    grade_data = get_grade_data(ticker)
    x_data = get_x_momentum_data(ticker)
    vol_data = get_volume_data(ticker)
    news_data = get_news_data(ticker)
    
    grade = grade_data.get("grade", 0)
    
    if agent_name == "technical_analyst":
        # Technical vote based on grade + volume
        vote = "HOLD"
        conviction = 50
        details = f"Grade: {grade}"
        
        if grade >= 70:
            vote = "BUY"
            conviction = min(100, grade)
            details = f"Strong technicals | Grade: {grade}"
        elif grade >= 55:
            vote = "HOLD"
            conviction = grade
            details = f"Moderate technicals | Grade: {grade}"
        elif grade > 0 and grade < 40:
            vote = "SELL"
            conviction = 100 - grade
            details = f"Weak technicals | Grade: {grade}"
        elif grade > 0:
            vote = "HOLD"
            conviction = 50
            details = f"Mixed technicals | Grade: {grade}"
        
        # Volume override
        if vol_data.get("volume_ratio", 0) > 2.5 and vol_data.get("price_change", 0) > 5:
            vote = "BUY"
            conviction = max(conviction, 70)
            details += f" | Volume spike: {vol_data['volume_ratio']:.1f}x"
        elif vol_data.get("volume_ratio", 0) > 2.5 and vol_data.get("price_change", 0) < -5:
            vote = "SELL"
            conviction = max(conviction, 70)
            details += f" | Volume dump: {vol_data['volume_ratio']:.1f}x"
        
        return {
            "agent": "technical",
            "vote": vote,
            "conviction": conviction,
            "signal": f"Grade: {grade}",
            "details": details,
        }
    
    elif agent_name == "macro_analyst":
        # Map ticker to sector (simplified)
        sector_map = {
            "TSLA": "technology", "NVDA": "technology", "AAPL": "technology",
            "MSFT": "technology", "GOOGL": "technology", "AMZN": "technology",
            "META": "technology", "PLTR": "technology", "SHOP": "technology",
            "DASH": "technology", "MELI": "technology", "DDOG": "technology",
            "CRWD": "technology", "SNOW": "technology", "OKLO": "energy",
            "CEG": "energy", "BTC": "crypto", "ETH": "crypto", "BNB": "crypto",
            "XRP": "crypto", "XLE": "energy", "SCCO": "materials",
            "JPM": "financials", "BAC": "financials", "C": "financials",
            "VOO": "consumer", "VTI": "consumer", "COST": "consumer",
            "WMT": "consumer", "AMZN": "consumer",
        }
        sector = sector_map.get(ticker, "technology")
        
        file = Path.home() / ".hermes" / "scripts" / "vox_macro_analysis.json"
        macro_vote = "HOLD"
        macro_conviction = 20
        macro_details = f"Sector: {sector}"
        
        if file.exists():
            with open(file) as f:
                data = json.load(f)
            for result in data.get("results", []):
                if result["sector"] == sector:
                    macro_vote = result["signal"].replace("STRONG_", "").replace("NEUTRAL", "HOLD")
                    macro_conviction = result["conviction"]
                    macro_details = f"Sector: {sector}, Score: {result['score']}"
        
        # News override
        if news_data.get("score", 0) >= 70:
            macro_vote = "BUY"
            macro_conviction = max(macro_conviction, 60)
            macro_details += f" | News: {news_data['headline'][:50]}..."
        elif news_data.get("score", 0) >= 50:
            macro_details += f" | News: {news_data['headline'][:40]}..."
        
        return {
            "agent": "macro",
            "vote": macro_vote,
            "conviction": macro_conviction,
            "signal": f"Sector: {sector}",
            "details": macro_details,
        }
    
    elif agent_name == "sentiment_analyst":
        # Sentiment vote based on X momentum + news
        sentiment_score = x_data.get("score", 0)
        mentions = x_data.get("mentions", 0)
        sentiment = x_data.get("sentiment", "NEUTRAL")
        validated = x_data.get("validated", False)
        
        # Only trust X data if validated (top post actually mentions ticker)
        if not validated and mentions > 0:
            # Unvalidated X data — reduce confidence, default to HOLD
            vote = "HOLD"
            conviction = 20
            details = f"X: {sentiment} ({mentions} mentions, UNVALIDATED — top post may not mention ticker)"
        elif sentiment_score >= 70:
            vote = "BUY"
            conviction = min(100, sentiment_score)
        elif sentiment_score <= 30:
            vote = "SELL"
            conviction = min(100, abs(sentiment_score - 50) * 2)
        elif mentions >= 5 and sentiment == "BULLISH":
            vote = "BUY"
            conviction = 60
        elif mentions >= 5 and sentiment == "BEARISH":
            vote = "SELL"
            conviction = 60
        else:
            vote = "HOLD"
            conviction = 30
        
        if validated:
            details = f"X: {sentiment} ({mentions} mentions, score: {sentiment_score}, validated)"
        else:
            details = f"X: {sentiment} ({mentions} mentions, score: {sentiment_score})"
        if news_data:
            details += f" | News score: {news_data.get('score', 0)}"
        
        return {
            "agent": "sentiment",
            "vote": vote,
            "conviction": conviction,
            "signal": sentiment,
            "details": details,
        }
    
    elif agent_name == "risk_manager":
        file = Path.home() / ".hermes" / "scripts" / "vox_risk_analysis.json"
        
        # Risk manager votes based on portfolio risk + position size
        risk_score = 3  # Default low risk
        if file.exists():
            with open(file) as f:
                data = json.load(f)
            risk_score = data.get("risk_score", 3)
        
        # Check if ticker is in portfolio
        positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
        in_portfolio = False
        position_value = 0
        if positions_file.exists():
            with open(positions_file) as f:
                portfolio = json.load(f)
            for pos in portfolio.get("positions", []):
                if pos["ticker"] == ticker:
                    in_portfolio = True
                    position_value = pos.get("value", 0)
                    break
        
        # Risk manager logic with grade awareness
        if risk_score >= 7:
            vote = "SELL"
            conviction = 80
        elif risk_score >= 4:
            vote = "HOLD"
            conviction = 60
        elif grade > 0 and grade < 30 and position_value > 2000:
            # Large position with very weak grade = risk
            vote = "SELL"
            conviction = 70
        elif grade > 0 and grade < 40 and position_value > 1000:
            # Medium+ position with weak grade = trim
            vote = "SELL"
            conviction = 60
        elif grade >= 70 and in_portfolio:
            vote = "HOLD"
            conviction = 60
        else:
            vote = "BUY" if not in_portfolio else "HOLD"
            conviction = 50
        
        return {
            "agent": "risk",
            "vote": vote,
            "conviction": conviction,
            "signal": f"Risk: {risk_score}/10",
            "details": f"Portfolio risk: {risk_score}/10, Position: ${position_value:,.0f}, Grade: {grade}",
        }
    
    return {"agent": agent_name, "vote": "HOLD", "conviction": 0, "details": "No data"}


def vote_on_ticker(ticker: str) -> Dict:
    """Get council vote on a ticker"""
    print(f"\n🗳️ COUNCIL VOTE: {ticker}")
    print("=" * 60)
    
    agents = ["technical_analyst", "macro_analyst", "sentiment_analyst", "risk_manager"]
    votes = []
    
    for agent in agents:
        vote = parse_agent_output(agent, ticker)
        votes.append(vote)
        
        emoji = "🟢" if vote["vote"] == "BUY" else "🔴" if vote["vote"] == "SELL" else "⚪"
        print(f"   {emoji} {vote['agent']:12} | {vote['vote']:6} | Conviction: {vote['conviction']:.0f} | {vote['details']}")
    
    # Calculate weighted consensus
    buy_votes = []
    sell_votes = []
    hold_votes = []
    
    for vote in votes:
        weight = AGENT_WEIGHTS.get(vote["agent"], 1.0)
        weighted_conviction = vote["conviction"] * weight
        
        if vote["vote"] == "BUY":
            buy_votes.append(weighted_conviction)
        elif vote["vote"] == "SELL":
            sell_votes.append(weighted_conviction)
        else:
            hold_votes.append(weighted_conviction)
    
    total_buy = sum(buy_votes)
    total_sell = sum(sell_votes)
    total_hold = sum(hold_votes)
    total_all = total_buy + total_sell + total_hold
    
    if total_all == 0:
        consensus = "HOLD"
        consensus_pct = 0
    else:
        buy_pct = total_buy / total_all * 100
        sell_pct = total_sell / total_all * 100
        hold_pct = total_hold / total_all * 100
        
        if buy_pct > sell_pct and buy_pct > hold_pct:
            consensus = "BUY"
            consensus_pct = buy_pct
        elif sell_pct > buy_pct and sell_pct > hold_pct:
            consensus = "SELL"
            consensus_pct = sell_pct
        else:
            consensus = "HOLD"
            consensus_pct = hold_pct
    
    # Dissenting opinions
    dissent = [v for v in votes if v["vote"] != consensus]
    
    result = {
        "ticker": ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "consensus": consensus,
        "consensus_pct": round(consensus_pct, 1),
        "votes": votes,
        "dissent": dissent,
        "action": consensus if consensus_pct > 60 else "HOLD",
    }
    
    emoji = "🟢" if consensus == "BUY" else "🔴" if consensus == "SELL" else "⚪"
    print(f"\n   {emoji} CONSENSUS: {consensus} ({consensus_pct:.0f}%)")
    
    if dissent:
        print(f"\n   ⚠️ DISSENT:")
        for d in dissent:
            print(f"      {d['agent']}: {d['vote']} ({d['details']})")
    
    return result


def batch_vote():
    """Vote on all portfolio positions"""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    
    if not positions_file.exists():
        print("❌ No portfolio data")
        return
    
    with open(positions_file) as f:
        data = json.load(f)
    
    tickers = list(set(p["ticker"] for p in data.get("positions", [])))
    
    print(f"\n🗳️ COUNCIL VOTING ON {len(tickers)} POSITIONS")
    print("=" * 60)
    
    results = []
    for ticker in tickers:  # Vote on ALL positions
        result = vote_on_ticker(ticker)
        results.append(result)
        print()
    
    # Summary
    buys = [r for r in results if r["consensus"] == "BUY"]
    sells = [r for r in results if r["consensus"] == "SELL"]
    holds = [r for r in results if r["consensus"] == "HOLD"]
    
    print("\n📊 COUNCIL SUMMARY")
    print(f"   🟢 BUY: {len(buys)}")
    print(f"   🔴 SELL: {len(sells)}")
    print(f"   ⚪ HOLD: {len(holds)}")
    
    if buys:
        print(f"\n   🟢 Strongest BUY signals:")
        for r in sorted(buys, key=lambda x: x["consensus_pct"], reverse=True)[:5]:
            print(f"      {r['ticker']}: {r['consensus_pct']:.0f}% consensus")
    
    if sells:
        print(f"\n   🔴 Strongest SELL signals:")
        for r in sorted(sells, key=lambda x: x["consensus_pct"], reverse=True)[:5]:
            print(f"      {r['ticker']}: {r['consensus_pct']:.0f}% consensus")
    
    # Save
    with open(OUTPUT_FILE, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "summary": {
                "buy": len(buys),
                "sell": len(sells),
                "hold": len(holds),
            }
        }, f, indent=2)
    
    if DASHBOARD_FILE.parent.exists():
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": results,
                "summary": {
                    "buy": len(buys),
                    "sell": len(sells),
                    "hold": len(holds),
                }
            }, f, indent=2)
    
    print(f"\n✅ Saved to {OUTPUT_FILE}")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Agent Council")
    parser.add_argument("--ticker", help="Vote on specific ticker")
    parser.add_argument("--batch", action="store_true", help="Vote on all positions")
    
    args = parser.parse_args()
    
    if args.ticker:
        result = vote_on_ticker(args.ticker)
        print(json.dumps(result, indent=2))
    else:
        batch_vote()


if __name__ == "__main__":
    main()
