#!/usr/bin/env python3
"""
Trade Journal — JOS-13
Logs every trade, tracks P&L, measures grade accuracy.
"""

import json
import os
from pathlib import Path
from datetime import datetime


JOURNAL_PATH = Path.home() / ".hermes" / "scripts" / "trade_journal.json"


def load_journal():
    """Load trade journal."""
    if JOURNAL_PATH.exists():
        with open(JOURNAL_PATH) as f:
            return json.load(f)
    return {"trades": [], "stats": {}}


def save_journal(journal):
    """Save trade journal."""
    with open(JOURNAL_PATH, "w") as f:
        json.dump(journal, f, indent=2)


def add_trade(ticker, action, entry_price, quantity, stop_loss=None, target=None, grade_at_entry=None, notes=""):
    """Add a new trade to the journal."""
    journal = load_journal()

    trade = {
        "id": f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "ticker": ticker,
        "action": action,  # BUY, SELL, SHORT, COVER
        "entry_price": entry_price,
        "quantity": quantity,
        "entry_date": datetime.now().isoformat(),
        "stop_loss": stop_loss,
        "target": target,
        "grade_at_entry": grade_at_entry,
        "notes": notes,
        "status": "OPEN",
        "exit_price": None,
        "exit_date": None,
        "pnl": None,
        "pnl_pct": None,
    }

    journal["trades"].append(trade)
    save_journal(journal)

    print(f"✅ Trade logged: {action} {quantity} {ticker} @ ${entry_price}")
    return trade


def close_trade(trade_id, exit_price, notes=""):
    """Close an existing trade."""
    journal = load_journal()

    for trade in journal["trades"]:
        if trade["id"] == trade_id and trade["status"] == "OPEN":
            trade["exit_price"] = exit_price
            trade["exit_date"] = datetime.now().isoformat()
            trade["status"] = "CLOSED"
            trade["notes"] += f" | Exit: {notes}"

            # Calculate P&L
            if trade["action"] == "BUY":
                trade["pnl"] = (exit_price - trade["entry_price"]) * trade["quantity"]
                trade["pnl_pct"] = (exit_price - trade["entry_price"]) / trade["entry_price"] * 100
            elif trade["action"] == "SHORT":
                trade["pnl"] = (trade["entry_price"] - exit_price) * trade["quantity"]
                trade["pnl_pct"] = (trade["entry_price"] - exit_price) / trade["entry_price"] * 100

            save_journal(journal)
            emoji = "🟢" if trade["pnl"] > 0 else "🔴" if trade["pnl"] < 0 else "⚪"
            print(f"{emoji} Trade closed: {trade['ticker']} | P&L: ${trade['pnl']:.2f} ({trade['pnl_pct']:+.2f}%)")
            return trade

    print(f"❌ Trade {trade_id} not found or already closed")
    return None


def get_stats():
    """Calculate journal statistics."""
    journal = load_journal()
    trades = journal["trades"]

    if not trades:
        return {"message": "No trades yet"}

    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_trades = [t for t in trades if t["status"] == "OPEN"]

    if not closed:
        return {
            "total_trades": len(trades),
            "open_trades": len(open_trades),
            "message": "No closed trades yet",
        }

    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] < 0]

    total_pnl = sum(t["pnl"] for t in closed)
    avg_pnl = total_pnl / len(closed)
    win_rate = len(wins) / len(closed) * 100

    # Grade accuracy
    graded_trades = [t for t in closed if t.get("grade_at_entry")]
    grade_accuracy = None
    if graded_trades:
        correct_grades = 0
        for t in graded_trades:
            grade = t["grade_at_entry"]
            if grade >= 70 and t["pnl"] > 0:
                correct_grades += 1
            elif grade < 55 and t["pnl"] < 0:
                correct_grades += 1
        grade_accuracy = correct_grades / len(graded_trades) * 100

    return {
        "total_trades": len(trades),
        "closed_trades": len(closed),
        "open_trades": len(open_trades),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl_per_trade": avg_pnl,
        "wins": len(wins),
        "losses": len(losses),
        "grade_accuracy": grade_accuracy,
    }


def show_journal():
    """Display full journal."""
    journal = load_journal()
    trades = journal["trades"]

    print("=" * 80)
    print("📓 VOX TRADE JOURNAL")
    print("=" * 80)
    print(f"Total trades: {len(trades)}")
    print()

    if not trades:
        print("No trades logged yet.")
        print("\nTo add a trade:")
        print("  python3 trade_journal.py add TICKER ACTION PRICE QTY [STOP] [TARGET]")
        return

    # Open trades
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    if open_trades:
        print("OPEN TRADES:")
        print("-" * 80)
        for t in open_trades:
            print(f"  {t['ticker']:8} | {t['action']:6} | ${t['entry_price']:.2f} x {t['quantity']} | Grade: {t.get('grade_at_entry', 'N/A')}")
        print()

    # Closed trades
    closed = [t for t in trades if t["status"] == "CLOSED"]
    if closed:
        print("CLOSED TRADES:")
        print("-" * 80)
        for t in closed[-10:]:  # Last 10
            emoji = "🟢" if t["pnl"] > 0 else "🔴"
            print(f"  {emoji} {t['ticker']:8} | {t['action']:6} | ${t['entry_price']:.2f} → ${t['exit_price']:.2f} | P&L: ${t['pnl']:.2f} ({t['pnl_pct']:+.1f}%)")
        print()

    # Stats
    stats = get_stats()
    print("=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"Win rate: {stats.get('win_rate', 0):.1f}%")
    print(f"Total P&L: ${stats.get('total_pnl', 0):.2f}")
    print(f"Avg per trade: ${stats.get('avg_pnl_per_trade', 0):.2f}")
    print(f"Wins: {stats.get('wins', 0)} | Losses: {stats.get('losses', 0)}")
    if stats.get("grade_accuracy"):
        print(f"Grade accuracy: {stats['grade_accuracy']:.1f}%")


def main():
    import sys

    if len(sys.argv) < 2:
        show_journal()
        return

    command = sys.argv[1].lower()

    if command == "add":
        if len(sys.argv) < 5:
            print("Usage: python3 trade_journal.py add TICKER ACTION PRICE QTY [STOP] [TARGET]")
            print("Example: python3 trade_journal.py add AAPL BUY 150.00 10 140.00 170.00")
            return
        ticker = sys.argv[2].upper()
        action = sys.argv[3].upper()
        price = float(sys.argv[4])
        qty = int(sys.argv[5])
        stop = float(sys.argv[6]) if len(sys.argv) > 6 else None
        target = float(sys.argv[7]) if len(sys.argv) > 7 else None
        add_trade(ticker, action, price, qty, stop, target)

    elif command == "close":
        if len(sys.argv) < 4:
            print("Usage: python3 trade_journal.py close TRADE_ID EXIT_PRICE")
            return
        trade_id = sys.argv[2]
        exit_price = float(sys.argv[3])
        close_trade(trade_id, exit_price)

    elif command == "stats":
        stats = get_stats()
        print(json.dumps(stats, indent=2))

    else:
        show_journal()


if __name__ == "__main__":
    main()
