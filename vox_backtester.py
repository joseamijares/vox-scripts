#!/usr/bin/env python3
"""
VOX Strategy Backtester v1.0
Test trading strategies historically against portfolio data.

Strategies:
- grade_sell: Sell all positions with grade < threshold
- grade_buy: Buy positions with grade > threshold
- council_vote: Trade based on council consensus
- stop_loss: Sell when position drops X%
- trailing_stop: Sell when position drops X% from peak

Usage:
    python3 vox_backtester.py run --strategy grade_sell --threshold 50 --days 30
    python3 vox_backtester.py compare --days 60
    python3 vox_backtester.py optimize --strategy grade_sell
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import random

# Files
POSITIONS_FILE = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
GRADES_FILE = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
TRADES_FILE = Path.home() / ".hermes" / "scripts" / "vox_trade_journal.json"
OUTPUT_DIR = Path.home() / ".hermes" / "scripts" / "backtests"

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

ENV = load_env()
POLYGON_KEY = ENV.get("POLYGON_API_KEY", "")

def polygon_get(path, params=""):
    if not POLYGON_KEY:
        return {"error": "POLYGON_API_KEY not set"}
    url = f"https://api.polygon.io{path}?apiKey={POLYGON_KEY}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def get_historical_prices(ticker: str, days: int = 60) -> List[Dict]:
    """Get historical daily prices"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        return []
    return result.get("results", [])

def load_portfolio():
    """Load current portfolio"""
    if not POSITIONS_FILE.exists():
        return None
    with open(POSITIONS_FILE) as f:
        return json.load(f)

def load_grades():
    """Load current grades"""
    if not GRADES_FILE.exists():
        return {}
    with open(GRADES_FILE) as f:
        return json.load(f)

def simulate_grade_sell_strategy(portfolio: Dict, grades: Dict, threshold: int = 50, days: int = 30) -> Dict:
    """
    Strategy: Sell all positions with grade < threshold
    Hold positions with grade >= threshold
    Compare to buy-and-hold
    """
    positions = portfolio.get("positions", [])
    
    # Group positions by ticker
    ticker_positions = {}
    for pos in positions:
        ticker = pos["ticker"]
        if ticker not in ticker_positions:
            ticker_positions[ticker] = []
        ticker_positions[ticker].append(pos)
    
    # Get historical prices for each ticker
    results = []
    total_strategy_pnl = 0
    total_hold_pnl = 0
    
    for ticker, pos_list in list(ticker_positions.items())[:20]:  # Limit API calls
        grade = grades.get(ticker, {}).get("grade", 0)
        total_value = sum(p["value"] for p in pos_list)
        avg_cost = sum(p["value"] for p in pos_list) / sum(p["shares"] for p in pos_list) if sum(p["shares"] for p in pos_list) > 0 else 0
        
        # Get historical prices
        bars = get_historical_prices(ticker, days)
        if not bars or len(bars) < 5:
            continue
        
        # Simulate: if grade < threshold, we "sold" at the start
        start_price = bars[0]["c"]
        end_price = bars[-1]["c"]
        
        # Buy and hold P&L
        hold_pnl = (end_price - start_price) / start_price * total_value if start_price > 0 else 0
        total_hold_pnl += hold_pnl
        
        # Strategy P&L
        if grade < threshold:
            # We sold at start - no further P&L
            strategy_pnl = 0
            action = "SOLD"
        else:
            # We held - same as buy and hold
            strategy_pnl = hold_pnl
            action = "HELD"
        
        total_strategy_pnl += strategy_pnl
        
        results.append({
            "ticker": ticker,
            "grade": grade,
            "action": action,
            "value": total_value,
            "start_price": start_price,
            "end_price": end_price,
            "hold_pnl": hold_pnl,
            "strategy_pnl": strategy_pnl,
            "saved": hold_pnl - strategy_pnl if action == "SOLD" and hold_pnl < 0 else 0,
            "missed": strategy_pnl - hold_pnl if action == "SOLD" and hold_pnl > 0 else 0,
        })
    
    # Calculate metrics
    sold_positions = [r for r in results if r["action"] == "SOLD"]
    held_positions = [r for r in results if r["action"] == "HELD"]
    
    saved = sum(r["saved"] for r in sold_positions)
    missed = sum(r["missed"] for r in sold_positions)
    
    return {
        "strategy": f"grade_sell_{threshold}",
        "days": days,
        "positions_tested": len(results),
        "sold": len(sold_positions),
        "held": len(held_positions),
        "total_hold_pnl": total_hold_pnl,
        "total_strategy_pnl": total_strategy_pnl,
        "improvement": total_strategy_pnl - total_hold_pnl,
        "saved_from_losses": saved,
        "missed_gains": missed,
        "net_benefit": saved - missed,
        "win_rate": len([r for r in sold_positions if r["hold_pnl"] < 0]) / len(sold_positions) * 100 if sold_positions else 0,
        "results": results,
    }

def simulate_stop_loss_strategy(portfolio: Dict, stop_pct: float = 10.0, days: int = 30) -> Dict:
    """
    Strategy: Sell when position drops stop_pct% from entry
    """
    positions = portfolio.get("positions", [])
    
    ticker_positions = {}
    for pos in positions:
        ticker = pos["ticker"]
        if ticker not in ticker_positions:
            ticker_positions[ticker] = []
        ticker_positions[ticker].append(pos)
    
    results = []
    total_strategy_pnl = 0
    total_hold_pnl = 0
    
    for ticker, pos_list in list(ticker_positions.items())[:20]:
        total_value = sum(p["value"] for p in pos_list)
        avg_cost = sum(p["value"] for p in pos_list) / sum(p["shares"] for p in pos_list) if sum(p["shares"] for p in pos_list) > 0 else 0
        
        bars = get_historical_prices(ticker, days)
        if not bars or len(bars) < 5:
            continue
        
        start_price = bars[0]["c"]
        end_price = bars[-1]["c"]
        
        # Find if stop loss was hit
        stop_price = avg_cost * (1 - stop_pct / 100)
        stop_hit = False
        stop_day = None
        
        for i, bar in enumerate(bars):
            if bar["l"] <= stop_price:
                stop_hit = True
                stop_day = i
                break
        
        # Buy and hold P&L
        hold_pnl = (end_price - start_price) / start_price * total_value if start_price > 0 else 0
        total_hold_pnl += hold_pnl
        
        # Strategy P&L
        if stop_hit:
            # Sold at stop
            strategy_pnl = (stop_price - avg_cost) / avg_cost * total_value if avg_cost > 0 else 0
            action = "STOPPED"
        else:
            # Held
            strategy_pnl = hold_pnl
            action = "HELD"
        
        total_strategy_pnl += strategy_pnl
        
        results.append({
            "ticker": ticker,
            "action": action,
            "value": total_value,
            "avg_cost": avg_cost,
            "stop_price": stop_price,
            "stop_hit": stop_hit,
            "stop_day": stop_day,
            "hold_pnl": hold_pnl,
            "strategy_pnl": strategy_pnl,
        })
    
    stopped = [r for r in results if r["action"] == "STOPPED"]
    
    return {
        "strategy": f"stop_loss_{stop_pct}",
        "days": days,
        "positions_tested": len(results),
        "stopped": len(stopped),
        "held": len(results) - len(stopped),
        "total_hold_pnl": total_hold_pnl,
        "total_strategy_pnl": total_strategy_pnl,
        "improvement": total_strategy_pnl - total_hold_pnl,
        "win_rate": len([r for r in stopped if r["hold_pnl"] < r["strategy_pnl"]]) / len(stopped) * 100 if stopped else 0,
        "results": results,
    }

def compare_strategies(days: int = 30):
    """Compare multiple strategies"""
    portfolio = load_portfolio()
    grades = load_grades()
    
    if not portfolio:
        print("❌ No portfolio data")
        return
    
    print(f"\n📊 BACKTEST COMPARISON ({days} days)")
    print("=" * 70)
    
    strategies = [
        ("Buy & Hold", None, None),
        ("Grade < 50 Sell", "grade_sell", 50),
        ("Grade < 45 Sell", "grade_sell", 45),
        ("Grade < 40 Sell", "grade_sell", 40),
        ("10% Stop Loss", "stop_loss", 10),
        ("15% Stop Loss", "stop_loss", 15),
    ]
    
    results = []
    
    for name, strategy, param in strategies:
        if strategy == "grade_sell":
            result = simulate_grade_sell_strategy(portfolio, grades, param, days)
        elif strategy == "stop_loss":
            result = simulate_stop_loss_strategy(portfolio, param, days)
        else:
            # Buy and hold baseline
            result = simulate_grade_sell_strategy(portfolio, grades, 0, days)
            result["strategy"] = "buy_hold"
            result["total_strategy_pnl"] = result["total_hold_pnl"]
            result["improvement"] = 0
        
        results.append({
            "name": name,
            "pnl": result["total_strategy_pnl"],
            "improvement": result.get("improvement", 0),
            "win_rate": result.get("win_rate", 0),
        })
        
        emoji = "🟢" if result.get("improvement", 0) > 0 else "🔴" if result.get("improvement", 0) < 0 else "⚪"
        print(f"   {emoji} {name:20} | P&L: ${result['total_strategy_pnl']:+,.0f} | Improvement: ${result.get('improvement', 0):+,.0f} | Win Rate: {result.get('win_rate', 0):.0f}%")
    
    # Best strategy
    best = max(results, key=lambda x: x["pnl"])
    print(f"\n🏆 BEST: {best['name']} (${best['pnl']:+,.0f})")
    
    # Save
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_file = OUTPUT_DIR / f"backtest_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "days": days,
            "results": results,
        }, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")
    return results

def optimize_grade_threshold(days: int = 60):
    """Find optimal grade threshold for selling"""
    portfolio = load_portfolio()
    grades = load_grades()
    
    if not portfolio:
        print("❌ No portfolio data")
        return
    
    print(f"\n🔍 OPTIMIZING GRADE SELL THRESHOLD ({days} days)")
    print("=" * 70)
    
    best_threshold = 0
    best_pnl = float('-inf')
    
    for threshold in range(30, 71, 5):
        result = simulate_grade_sell_strategy(portfolio, grades, threshold, days)
        
        emoji = "🟢" if result["improvement"] > 0 else "🔴"
        print(f"   {emoji} Grade < {threshold:2d}: P&L ${result['total_strategy_pnl']:+,.0f} | Improvement ${result['improvement']:+,.0f} | Saved ${result['saved_from_losses']:,.0f} | Missed ${result['missed_gains']:,.0f}")
        
        if result["total_strategy_pnl"] > best_pnl:
            best_pnl = result["total_strategy_pnl"]
            best_threshold = threshold
    
    print(f"\n🏆 OPTIMAL: Sell when grade < {best_threshold}")
    print(f"   Expected P&L: ${best_pnl:+,.0f}")
    
    return best_threshold

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Backtester")
    subparsers = parser.add_subparsers(dest="command")
    
    run_cmd = subparsers.add_parser("run", help="Run single strategy")
    run_cmd.add_argument("--strategy", choices=["grade_sell", "stop_loss"], required=True)
    run_cmd.add_argument("--threshold", type=int, default=50)
    run_cmd.add_argument("--stop-pct", type=float, default=10.0)
    run_cmd.add_argument("--days", type=int, default=30)
    
    compare_cmd = subparsers.add_parser("compare", help="Compare strategies")
    compare_cmd.add_argument("--days", type=int, default=30)
    
    optimize_cmd = subparsers.add_parser("optimize", help="Find optimal parameters")
    optimize_cmd.add_argument("--strategy", choices=["grade_sell"], default="grade_sell")
    optimize_cmd.add_argument("--days", type=int, default=60)
    
    args = parser.parse_args()
    
    if args.command == "run":
        portfolio = load_portfolio()
        grades = load_grades()
        if args.strategy == "grade_sell":
            result = simulate_grade_sell_strategy(portfolio, grades, args.threshold, args.days)
        else:
            result = simulate_stop_loss_strategy(portfolio, args.stop_pct, args.days)
        print(json.dumps(result, indent=2))
    elif args.command == "compare":
        compare_strategies(args.days)
    elif args.command == "optimize":
        optimize_grade_threshold(args.days)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
