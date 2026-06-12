#!/usr/bin/env python3
"""
VOX Trade Journal v1.0
Log, track, and learn from every trade.

Schema:
{
  "trade_id": "uuid",
  "timestamp": "ISO",
  "ticker": "TSLA",
  "action": "BUY|SELL|TRIM|ADD",
  "shares": 50,
  "price": 240.00,
  "broker": "eToro",
  "total_value": 12000.00,
  
  "thesis": "Grade 70, breakout above $235, volume spike",
  "signals": ["technical", "grade", "volume"],
  
  "stop_loss": 220.00,
  "target": 280.00,
  "timeframe": "swing|day|core",
  
  "status": "OPEN|CLOSED|STOPPED|TARGET",
  "exit_price": null,
  "exit_date": null,
  "pnl": null,
  "pnl_pct": null,
  
  "reflection": "What I learned",
  "grade_at_entry": 70,
  "grade_at_exit": null,
  
  "agent_notes": "Council voted 3-1 BUY"
}

Usage:
    python3 vox_trade_journal.py log --ticker TSLA --action BUY --shares 50 --price 240 --broker eToro --stop 220 --target 280 --thesis "Breakout play"
    python3 vox_trade_journal.py close --trade-id <id> --price 260 --reflection "Worked perfectly"
    python3 vox_trade_journal.py list --status OPEN
    python3 vox_trade_journal.py stats
"""

import json
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_FILE = Path.home() / ".hermes" / "scripts" / "vox_trade_journal.json"
GRADES_FILE = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
DASHBOARD_FILE = Path.home() / "dev" / "vox-dashboard" / "public" / "vox_trade_journal.json"


def load_journal():
    """Load trade journal"""
    if JOURNAL_FILE.exists():
        with open(JOURNAL_FILE) as f:
            return json.load(f)
    return {"trades": [], "stats": {"total_trades": 0, "win_rate": 0, "avg_pnl": 0}}


def save_journal(data):
    """Save trade journal"""
    with open(JOURNAL_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    # Also copy to dashboard
    if DASHBOARD_FILE.parent.exists():
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def get_current_grade(ticker):
    """Get current grade for ticker"""
    if GRADES_FILE.exists():
        with open(GRADES_FILE) as f:
            grades = json.load(f)
        for cat in ['strong_buy', 'moderate_buy', 'avoid']:
            for item in grades.get(cat, []):
                if item['ticker'] == ticker:
                    return item['grade']
    return None


def log_trade(args):
    """Log a new trade"""
    journal = load_journal()
    
    trade = {
        "trade_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": args.ticker.upper(),
        "action": args.action.upper(),
        "shares": args.shares,
        "price": args.price,
        "broker": args.broker,
        "total_value": round(args.shares * args.price, 2),
        "thesis": args.thesis or "",
        "signals": args.signals.split(',') if args.signals else [],
        "stop_loss": args.stop,
        "target": args.target,
        "timeframe": args.timeframe or "swing",
        "status": "OPEN",
        "exit_price": None,
        "exit_date": None,
        "pnl": None,
        "pnl_pct": None,
        "reflection": "",
        "grade_at_entry": get_current_grade(args.ticker.upper()),
        "grade_at_exit": None,
        "agent_notes": args.notes or "",
    }
    
    journal["trades"].append(trade)
    journal["stats"]["total_trades"] = len(journal["trades"])
    
    save_journal(journal)
    
    print(f"✅ Trade logged: {trade['trade_id']}")
    print(f"   {args.action.upper()} {args.shares} {args.ticker.upper()} @ ${args.price}")
    print(f"   Value: ${trade['total_value']:,.2f} | Grade: {trade['grade_at_entry']}")
    if args.stop:
        print(f"   Stop: ${args.stop} | Target: ${args.target}")
    
    return trade


def close_trade(args):
    """Close an existing trade"""
    journal = load_journal()
    
    trade = None
    for t in journal["trades"]:
        if t["trade_id"] == args.trade_id:
            if t["status"] == "OPEN":
                trade = t
                break
        if args.ticker and t["ticker"] == args.ticker.upper():
            if t["status"] == "OPEN":
                trade = t
                break
    
    if not trade:
        print(f"❌ No open trade found for {args.trade_id or args.ticker}")
        return
    
    # Calculate P&L
    if trade["action"] == "BUY":
        pnl = (args.price - trade["price"]) * trade["shares"]
        pnl_pct = (args.price - trade["price"]) / trade["price"] * 100
    else:  # SELL
        pnl = (trade["price"] - args.price) * trade["shares"]
        pnl_pct = (trade["price"] - args.price) / trade["price"] * 100
    
    trade["status"] = "CLOSED"
    trade["exit_price"] = args.price
    trade["exit_date"] = datetime.now(timezone.utc).isoformat()
    trade["pnl"] = round(pnl, 2)
    trade["pnl_pct"] = round(pnl_pct, 2)
    trade["reflection"] = args.reflection or ""
    trade["grade_at_exit"] = get_current_grade(trade["ticker"])
    
    save_journal(journal)
    
    emoji = "🟢" if pnl > 0 else "🔴"
    print(f"{emoji} Trade closed: {trade['trade_id']}")
    print(f"   {trade['ticker']} @ ${trade['price']} → ${args.price}")
    print(f"   P&L: ${pnl:+,.2f} ({pnl_pct:+.1f}%)")
    if args.reflection:
        print(f"   Reflection: {args.reflection}")
    
    return trade


def list_trades(args):
    """List trades"""
    journal = load_journal()
    trades = journal["trades"]
    
    if args.status:
        trades = [t for t in trades if t["status"] == args.status.upper()]
    
    if args.ticker:
        trades = [t for t in trades if t["ticker"] == args.ticker.upper()]
    
    if not trades:
        print("No trades found")
        return
    
    print(f"\n{'ID':<10} {'Ticker':<8} {'Action':<6} {'Shares':>8} {'Entry':>10} {'Exit':>10} {'P&L':>12} {'Status':<8}")
    print("-" * 80)
    
    for t in trades[-20:]:  # Last 20
        pnl_str = f"${t['pnl']:+,.0f}" if t['pnl'] is not None else "-"
        exit_str = f"${t['exit_price']:.2f}" if t['exit_price'] else "-"
        print(f"{t['trade_id']:<10} {t['ticker']:<8} {t['action']:<6} {t['shares']:>8} ${t['price']:>8.2f} {exit_str:>10} {pnl_str:>12} {t['status']:<8}")
    
    print(f"\nTotal: {len(trades)} trades")


def show_stats(args):
    """Show trading statistics"""
    journal = load_journal()
    trades = journal["trades"]
    
    if not trades:
        print("No trades yet")
        return
    
    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    
    total_pnl = sum(t["pnl"] for t in closed if t["pnl"])
    win_rate = len(wins) / len(closed) if closed else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    
    print("\n📊 TRADING STATISTICS")
    print("=" * 50)
    print(f"Total Trades: {len(trades)}")
    print(f"Open: {len(open_trades)} | Closed: {len(closed)}")
    print(f"\nWin Rate: {win_rate:.1%} ({len(wins)}W / {len(losses)}L)")
    print(f"Total P&L: ${total_pnl:+,.2f}")
    print(f"Avg Win: ${avg_win:,.2f}")
    print(f"Avg Loss: ${avg_loss:,.2f}")
    
    if closed:
        best = max(closed, key=lambda x: x["pnl"])
        worst = min(closed, key=lambda x: x["pnl"])
        print(f"\nBest Trade: {best['ticker']} ${best['pnl']:+,.2f}")
        print(f"Worst Trade: {worst['ticker']} ${worst['pnl']:+,.2f}")
    
    # Grade accuracy
    grade_trades = [t for t in closed if t.get("grade_at_entry")]
    if grade_trades:
        high_grade_wins = [t for t in grade_trades if t["grade_at_entry"] >= 70 and t["pnl"] > 0]
        high_grade_total = [t for t in grade_trades if t["grade_at_entry"] >= 70]
        if high_grade_total:
            print(f"\nGrade 70+ Win Rate: {len(high_grade_wins)/len(high_grade_total):.1%}")


def main():
    parser = argparse.ArgumentParser(description="VOX Trade Journal")
    subparsers = parser.add_subparsers(dest="command")
    
    # Log command
    log_parser = subparsers.add_parser("log", help="Log a new trade")
    log_parser.add_argument("--ticker", required=True)
    log_parser.add_argument("--action", required=True, choices=["BUY", "SELL", "TRIM", "ADD"])
    log_parser.add_argument("--shares", type=float, required=True)
    log_parser.add_argument("--price", type=float, required=True)
    log_parser.add_argument("--broker", required=True)
    log_parser.add_argument("--stop", type=float)
    log_parser.add_argument("--target", type=float)
    log_parser.add_argument("--thesis")
    log_parser.add_argument("--signals")
    log_parser.add_argument("--timeframe", choices=["day", "swing", "core"])
    log_parser.add_argument("--notes")
    
    # Close command
    close_parser = subparsers.add_parser("close", help="Close a trade")
    close_parser.add_argument("--trade-id")
    close_parser.add_argument("--ticker")
    close_parser.add_argument("--price", type=float, required=True)
    close_parser.add_argument("--reflection")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List trades")
    list_parser.add_argument("--status", choices=["OPEN", "CLOSED"])
    list_parser.add_argument("--ticker")
    
    # Stats command
    subparsers.add_parser("stats", help="Show statistics")
    
    args = parser.parse_args()
    
    if args.command == "log":
        log_trade(args)
    elif args.command == "close":
        close_trade(args)
    elif args.command == "list":
        list_trades(args)
    elif args.command == "stats":
        show_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
