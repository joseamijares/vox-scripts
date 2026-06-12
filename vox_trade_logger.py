#!/usr/bin/env python3
"""
VOX Trade Execution Logger v1.0
Logs trades from user input or broker APIs.

Usage:
    python3 vox_trade_logger.py log --ticker TSLA --action BUY --shares 10 --price 240 --broker eToro
    python3 vox_trade_logger.py import --file trades.csv
    python3 vox_trade_logger.py stats
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

TRADES_FILE = Path.home() / ".hermes" / "scripts" / "vox_trade_journal.json"


def load_trades() -> List[Dict]:
    """Load trade journal"""
    if TRADES_FILE.exists():
        with open(TRADES_FILE) as f:
            data = json.load(f)
            return data.get("trades", [])
    return []


def save_trades(trades: List[Dict]):
    """Save trade journal"""
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRADES_FILE, 'w') as f:
        json.dump({"trades": trades}, f, indent=2)


def log_trade(ticker: str, action: str, shares: float, price: float, broker: str,
              stop: float = None, target: float = None, thesis: str = None) -> Dict:
    """Log a new trade"""
    trades = load_trades()
    
    trade = {
        "trade_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker.upper(),
        "action": action.upper(),
        "shares": shares,
        "price": price,
        "value": shares * price,
        "broker": broker,
        "status": "OPEN",
        "stop": stop,
        "target": target,
        "thesis": thesis,
        "exit_price": None,
        "exit_date": None,
        "pnl": None,
        "pnl_pct": None,
        "reflection": None,
    }
    
    trades.append(trade)
    save_trades(trades)
    
    print(f"✅ Trade logged: {trade['trade_id']}")
    print(f"   {action.upper()} {shares} {ticker.upper()} @ ${price:.2f}")
    print(f"   Value: ${trade['value']:,.2f} | Broker: {broker}")
    
    return trade


def close_trade(trade_id: str, exit_price: float, reflection: str = None) -> Dict:
    """Close an open trade"""
    trades = load_trades()
    
    for trade in trades:
        if trade["trade_id"] == trade_id and trade["status"] == "OPEN":
            trade["status"] = "CLOSED"
            trade["exit_price"] = exit_price
            trade["exit_date"] = datetime.now(timezone.utc).isoformat()
            
            # Calculate P&L
            if trade["action"] == "BUY":
                trade["pnl"] = (exit_price - trade["price"]) * trade["shares"]
                trade["pnl_pct"] = (exit_price - trade["price"]) / trade["price"] * 100
            else:
                trade["pnl"] = (trade["price"] - exit_price) * trade["shares"]
                trade["pnl_pct"] = (trade["price"] - exit_price) / trade["price"] * 100
            
            trade["reflection"] = reflection
            
            save_trades(trades)
            
            emoji = "🟢" if trade["pnl"] > 0 else "🔴"
            print(f"{emoji} Trade closed: {trade_id}")
            print(f"   {trade['ticker']} @ ${trade['price']:.2f} → ${exit_price:.2f}")
            print(f"   P&L: ${trade['pnl']:+,.2f} ({trade['pnl_pct']:+.1f}%)")
            
            return trade
    
    print(f"❌ Trade {trade_id} not found or already closed")
    return None


def show_stats():
    """Show trade statistics"""
    trades = load_trades()
    
    if not trades:
        print("📊 No trades logged yet")
        return
    
    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    
    if closed:
        total_pnl = sum(t["pnl"] for t in closed)
        avg_pnl = total_pnl / len(closed)
        win_rate = len([t for t in closed if t["pnl"] > 0]) / len(closed) * 100
        
        print("\n📊 TRADE STATISTICS")
        print("=" * 60)
        print(f"   Total trades: {len(trades)}")
        print(f"   Closed: {len(closed)}")
        print(f"   Open: {len(open_trades)}")
        print(f"   Win rate: {win_rate:.1f}%")
        print(f"   Total P&L: ${total_pnl:+,.2f}")
        print(f"   Avg P&L: ${avg_pnl:+,.2f}")
        
        # By ticker
        ticker_pnl = {}
        for t in closed:
            ticker = t["ticker"]
            if ticker not in ticker_pnl:
                ticker_pnl[ticker] = []
            ticker_pnl[ticker].append(t["pnl"])
        
        print(f"\n🏆 Best performers:")
        sorted_tickers = sorted(ticker_pnl.items(), key=lambda x: sum(x[1]), reverse=True)[:5]
        for ticker, pnls in sorted_tickers:
            print(f"   {ticker}: ${sum(pnls):+,.2f} ({len(pnls)} trades)")
    
    if open_trades:
        print(f"\n📈 Open positions:")
        for t in open_trades:
            print(f"   {t['ticker']}: {t['shares']} shares @ ${t['price']:.2f} (ID: {t['trade_id']})")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Trade Logger")
    subparsers = parser.add_subparsers(dest="command")
    
    log_cmd = subparsers.add_parser("log", help="Log a trade")
    log_cmd.add_argument("--ticker", required=True)
    log_cmd.add_argument("--action", choices=["BUY", "SELL", "TRIM", "ADD"], required=True)
    log_cmd.add_argument("--shares", type=float, required=True)
    log_cmd.add_argument("--price", type=float, required=True)
    log_cmd.add_argument("--broker", required=True)
    log_cmd.add_argument("--stop", type=float)
    log_cmd.add_argument("--target", type=float)
    log_cmd.add_argument("--thesis")
    
    close_cmd = subparsers.add_parser("close", help="Close a trade")
    close_cmd.add_argument("--trade-id", required=True)
    close_cmd.add_argument("--price", type=float, required=True)
    close_cmd.add_argument("--reflection")
    
    stats_cmd = subparsers.add_parser("stats", help="Show statistics")
    
    args = parser.parse_args()
    
    if args.command == "log":
        log_trade(args.ticker, args.action, args.shares, args.price, args.broker,
                  args.stop, args.target, args.thesis)
    elif args.command == "close":
        close_trade(args.trade_id, args.price, args.reflection)
    elif args.command == "stats":
        show_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
