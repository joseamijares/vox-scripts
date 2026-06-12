#!/usr/bin/env python3
"""
VOX Paper Trader v1.0
Paper trade integration with Alpaca.

Tracks:
- Virtual portfolio
- Paper P&L
- Strategy performance
- Risk metrics

Usage:
    python3 vox_paper_trader.py buy --ticker TSLA --shares 10 --price 240
    python3 vox_paper_trader.py sell --ticker TSLA --shares 5 --price 250
    python3 vox_paper_trader.py status
    python3 vox_paper_trader.py execute-plays
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
PAPER_PORTFOLIO = SCRIPTS_DIR / "vox_paper_portfolio.json"
PAPER_TRADES = SCRIPTS_DIR / "vox_paper_trades.json"


def load_paper_portfolio() -> Dict:
    """Load paper portfolio"""
    if PAPER_PORTFOLIO.exists():
        with open(PAPER_PORTFOLIO) as f:
            return json.load(f)
    return {
        "cash": 100000.0,
        "positions": {},
        "total_value": 100000.0,
        "total_pnl": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_paper_portfolio(portfolio: Dict):
    """Save paper portfolio"""
    with open(PAPER_PORTFOLIO, 'w') as f:
        json.dump(portfolio, f, indent=2)


def load_paper_trades() -> List[Dict]:
    """Load paper trade history"""
    if PAPER_TRADES.exists():
        with open(PAPER_TRADES) as f:
            return json.load(f)
    return []


def save_paper_trades(trades: List[Dict]):
    """Save paper trade history"""
    with open(PAPER_TRADES, 'w') as f:
        json.dump(trades, f, indent=2)


def paper_buy(ticker: str, shares: float, price: float, reason: str = "") -> Dict:
    """Execute paper buy"""
    portfolio = load_paper_portfolio()
    
    cost = shares * price
    if cost > portfolio["cash"]:
        return {"error": f"Insufficient cash. Need ${cost:.2f}, have ${portfolio['cash']:.2f}"}
    
    # Update portfolio
    portfolio["cash"] -= cost
    
    if ticker in portfolio["positions"]:
        # Average down
        pos = portfolio["positions"][ticker]
        total_shares = pos["shares"] + shares
        total_cost = (pos["shares"] * pos["avg_price"]) + cost
        pos["shares"] = total_shares
        pos["avg_price"] = total_cost / total_shares
    else:
        portfolio["positions"][ticker] = {
            "shares": shares,
            "avg_price": price,
            "entry_date": datetime.now(timezone.utc).isoformat(),
        }
    
    # Record trade
    trade = {
        "id": f"paper_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{ticker}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "action": "BUY",
        "shares": shares,
        "price": price,
        "value": cost,
        "reason": reason,
    }
    
    trades = load_paper_trades()
    trades.append(trade)
    save_paper_trades(trades)
    
    # Update total value
    portfolio["total_value"] = portfolio["cash"] + sum(
        p["shares"] * p["avg_price"] for p in portfolio["positions"].values()
    )
    
    save_paper_portfolio(portfolio)
    
    return {
        "success": True,
        "trade": trade,
        "portfolio": {
            "cash": portfolio["cash"],
            "positions_count": len(portfolio["positions"]),
            "total_value": portfolio["total_value"],
        },
    }


def paper_sell(ticker: str, shares: float, price: float, reason: str = "") -> Dict:
    """Execute paper sell"""
    portfolio = load_paper_portfolio()
    
    if ticker not in portfolio["positions"]:
        return {"error": f"No position in {ticker}"}
    
    pos = portfolio["positions"][ticker]
    if shares > pos["shares"]:
        shares = pos["shares"]  # Sell all if trying to sell more
    
    proceeds = shares * price
    pnl = (price - pos["avg_price"]) * shares
    
    # Update portfolio
    portfolio["cash"] += proceeds
    pos["shares"] -= shares
    
    if pos["shares"] <= 0:
        del portfolio["positions"][ticker]
    
    # Record trade
    trade = {
        "id": f"paper_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{ticker}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "action": "SELL",
        "shares": shares,
        "price": price,
        "value": proceeds,
        "pnl": pnl,
        "pnl_pct": (price / pos.get("avg_price", price) - 1) * 100 if pos.get("avg_price") else 0,
        "reason": reason,
    }
    
    trades = load_paper_trades()
    trades.append(trade)
    save_paper_trades(trades)
    
    # Update total value and P&L
    portfolio["total_pnl"] += pnl
    portfolio["total_value"] = portfolio["cash"] + sum(
        p["shares"] * p["avg_price"] for p in portfolio["positions"].values()
    )
    
    save_paper_portfolio(portfolio)
    
    return {
        "success": True,
        "trade": trade,
        "portfolio": {
            "cash": portfolio["cash"],
            "positions_count": len(portfolio["positions"]),
            "total_value": portfolio["total_value"],
            "total_pnl": portfolio["total_pnl"],
        },
    }


def get_status() -> Dict:
    """Get paper portfolio status"""
    portfolio = load_paper_portfolio()
    trades = load_paper_trades()
    
    # Calculate current P&L based on latest prices
    # In real implementation, would fetch live prices
    current_positions = []
    for ticker, pos in portfolio["positions"].items():
        current_positions.append({
            "ticker": ticker,
            "shares": pos["shares"],
            "avg_price": pos["avg_price"],
            "entry_date": pos["entry_date"],
        })
    
    # Performance metrics
    win_trades = [t for t in trades if t.get("pnl", 0) > 0]
    loss_trades = [t for t in trades if t.get("pnl", 0) < 0]
    
    return {
        "cash": portfolio["cash"],
        "positions": current_positions,
        "total_value": portfolio["total_value"],
        "total_pnl": portfolio["total_pnl"],
        "total_trades": len(trades),
        "win_rate": len(win_trades) / len(trades) * 100 if trades else 0,
        "avg_win": sum(t["pnl"] for t in win_trades) / len(win_trades) if win_trades else 0,
        "avg_loss": sum(t["pnl"] for t in loss_trades) / len(loss_trades) if loss_trades else 0,
        "return_pct": (portfolio["total_value"] / 100000 - 1) * 100,
    }


def execute_plays():
    """Execute paper trades based on VOX plays"""
    plays_file = SCRIPTS_DIR / "vox_generated_plays.json"
    if not plays_file.exists():
        print("No plays file found")
        return
    
    with open(plays_file) as f:
        plays = json.load(f)
    
    executed = []
    for play in plays.get("plays", []):
        if play.get("action") == "SELL" and play.get("grade", 0) < 45:
            # Paper sell
            result = paper_sell(
                ticker=play["ticker"],
                shares=play.get("sell_shares", 0),
                price=play.get("price", 0),
                reason=f"Grade {play['grade']} - Council SELL signal"
            )
            if result.get("success"):
                executed.append(result["trade"])
                print(f"✅ Paper SELL: {play['ticker']} @ ${play['price']}")
    
    print(f"\nExecuted {len(executed)} paper trades")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Paper Trader")
    parser.add_argument("command", choices=["buy", "sell", "status", "execute-plays", "reset"])
    parser.add_argument("--ticker", help="Ticker symbol")
    parser.add_argument("--shares", type=float, help="Number of shares")
    parser.add_argument("--price", type=float, help="Price per share")
    parser.add_argument("--reason", default="", help="Reason for trade")
    
    args = parser.parse_args()
    
    if args.command == "buy":
        if not all([args.ticker, args.shares, args.price]):
            print("Error: --ticker, --shares, and --price required")
            return
        result = paper_buy(args.ticker.upper(), args.shares, args.price, args.reason)
        print(json.dumps(result, indent=2))
    
    elif args.command == "sell":
        if not all([args.ticker, args.shares, args.price]):
            print("Error: --ticker, --shares, and --price required")
            return
        result = paper_sell(args.ticker.upper(), args.shares, args.price, args.reason)
        print(json.dumps(result, indent=2))
    
    elif args.command == "status":
        status = get_status()
        print(f"\n📊 PAPER PORTFOLIO")
        print(f"   Cash: ${status['cash']:,.2f}")
        print(f"   Positions: {len(status['positions'])}")
        print(f"   Total Value: ${status['total_value']:,.2f}")
        print(f"   Total P&L: ${status['total_pnl']:,.2f} ({status['return_pct']:+.1f}%)")
        print(f"   Win Rate: {status['win_rate']:.0f}%")
        print(f"   Total Trades: {status['total_trades']}")
        
        if status['positions']:
            print(f"\n   Current Positions:")
            for pos in status['positions']:
                print(f"     {pos['ticker']}: {pos['shares']:.2f} shares @ ${pos['avg_price']:.2f}")
    
    elif args.command == "execute-plays":
        execute_plays()
    
    elif args.command == "reset":
        portfolio = {
            "cash": 100000.0,
            "positions": {},
            "total_value": 100000.0,
            "total_pnl": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_paper_portfolio(portfolio)
        save_paper_trades([])
        print("✅ Paper portfolio reset to $100,000")


if __name__ == "__main__":
    main()
