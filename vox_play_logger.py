#!/usr/bin/env python3
"""
VOX Play Logger
Logs every buy/sell/trim with P&L tracking for historic analysis.
Append-only JSONL format for durability.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
PLAYS_FILE = SCRIPT_DIR / "vox_historic_plays.jsonl"
PORTFOLIO_SNAPSHOTS = SCRIPT_DIR / "portfolio_snapshots"

def ensure_dir():
    PORTFOLIO_SNAPSHOTS.mkdir(exist_ok=True)

def log_play(ticker: str, action: str, shares: float, price: float, broker: str,
             reason: str = "", grade_at_entry: int = 0, council_at_entry: str = "",
             notes: str = ""):
    """Log a trade execution."""
    ensure_dir()
    
    play = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "action": action,  # BUY, SELL, TRIM, ADD
        "shares": shares,
        "price": price,
        "notional": round(shares * price, 2),
        "broker": broker,
        "reason": reason,
        "grade_at_entry": grade_at_entry,
        "council_at_entry": council_at_entry,
        "notes": notes,
        "closed": False,
        "exit_price": None,
        "exit_date": None,
        "pnl": None,
        "pnl_pct": None,
    }
    
    # Log to JSONL (legacy)
    with open(PLAYS_FILE, "a") as f:
        f.write(json.dumps(play) + "\n")
    
    # Sync to Supabase
    try:
        from vox_supabase_sync import sync_play
        sync_play(play)
        print(f"   ✅ Synced to Supabase")
    except Exception as e:
        print(f"   ⚠️ Supabase sync failed: {e}")
    
    print(f"✅ Logged: {action} {shares:.2f} {ticker} @ ${price:.2f} = ${play['notional']:.2f}")
    return play


def close_play(ticker: str, exit_price: float, exit_shares: float = None):
    """Close an open play and calculate P&L."""
    if not PLAYS_FILE.exists():
        print("❌ No plays file found")
        return
    
    plays = []
    with open(PLAYS_FILE) as f:
        for line in f:
            plays.append(json.loads(line.strip()))
    
    # Find most recent open play for this ticker
    target = None
    for p in reversed(plays):
        if p["ticker"] == ticker and not p.get("closed", False) and p["action"] in ("BUY", "ADD"):
            target = p
            break
    
    if not target:
        print(f"❌ No open BUY/ADD play found for {ticker}")
        return
    
    # Calculate P&L
    entry_notional = target["shares"] * target["price"]
    if exit_shares:
        exit_notional = exit_shares * exit_price
        shares_closed = exit_shares
    else:
        exit_notional = target["shares"] * exit_price
        shares_closed = target["shares"]
    
    pnl = exit_notional - (entry_notional * (shares_closed / target["shares"]))
    pnl_pct = (pnl / (entry_notional * (shares_closed / target["shares"]))) * 100
    
    target["closed"] = True
    target["exit_price"] = exit_price
    target["exit_date"] = datetime.now(timezone.utc).isoformat()
    target["exit_shares"] = shares_closed
    target["pnl"] = round(pnl, 2)
    target["pnl_pct"] = round(pnl_pct, 2)
    
    # Rewrite file
    with open(PLAYS_FILE, "w") as f:
        for p in plays:
            f.write(json.dumps(p) + "\n")
    
    emoji = "🟢" if pnl > 0 else "🔴"
    print(f"{emoji} Closed {ticker}: Entry ${target['price']:.2f} → Exit ${exit_price:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
    return target


def list_open_plays():
    """List all open plays."""
    if not PLAYS_FILE.exists():
        print("No plays logged yet")
        return []
    
    plays = []
    with open(PLAYS_FILE) as f:
        for line in f:
            plays.append(json.loads(line.strip()))
    
    open_plays = [p for p in plays if not p.get("closed", False) and p["action"] in ("BUY", "ADD")]
    
    print(f"\n📋 OPEN PLAYS: {len(open_plays)}")
    print("-" * 80)
    for p in open_plays:
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(p["timestamp"])).days
        print(f"  {p['ticker']:6s} | {p['action']:4s} | {p['shares']:8.2f} sh @ ${p['price']:8.2f} | ${p['notional']:10.2f} | {age_days}d ago | Grade: {p.get('grade_at_entry', 0)}")
    
    return open_plays


def get_stats():
    """Get historic play statistics."""
    if not PLAYS_FILE.exists():
        return {}
    
    plays = []
    with open(PLAYS_FILE) as f:
        for line in f:
            plays.append(json.loads(line.strip()))
    
    closed = [p for p in plays if p.get("closed", False)]
    open_p = [p for p in plays if not p.get("closed", False) and p["action"] in ("BUY", "ADD")]
    
    wins = [p for p in closed if p.get("pnl", 0) > 0]
    losses = [p for p in closed if p.get("pnl", 0) <= 0]
    
    total_pnl = sum(p.get("pnl", 0) for p in closed)
    avg_win = sum(p.get("pnl", 0) for p in wins) / len(wins) if wins else 0
    avg_loss = sum(p.get("pnl", 0) for p in losses) / len(losses) if losses else 0
    
    return {
        "total_plays": len(plays),
        "closed_plays": len(closed),
        "open_plays": len(open_p),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(closed) * 100 if closed else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_play": max(closed, key=lambda x: x.get("pnl", 0))["ticker"] if closed else None,
        "worst_play": min(closed, key=lambda x: x.get("pnl", 0))["ticker"] if closed else None,
    }


def snapshot_portfolio():
    """Save daily portfolio snapshot for tracking."""
    ensure_dir()
    
    live_file = SCRIPT_DIR / "dashboard_positions_live.json"
    if not live_file.exists():
        print("❌ No live positions file")
        return
    
    with open(live_file) as f:
        data = json.load(f)
    
    # Save snapshot
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_file = PORTFOLIO_SNAPSHOTS / f"portfolio_{date_str}.json"
    
    with open(snapshot_file, "w") as f:
        json.dump(data, f, indent=2)
    
    # Calculate totals
    positions = data.get("positions", [])
    total_value = sum(p.get("live_value", p.get("value", 0)) for p in positions if p.get("ticker") != "TOTAL")
    
    print(f"💾 Portfolio snapshot saved: ${total_value:,.2f} total value")
    return snapshot_file


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Play Logger")
    parser.add_argument("--log", action="store_true", help="Log a new play (interactive)")
    parser.add_argument("--close", help="Close a play by ticker")
    parser.add_argument("--exit-price", type=float, help="Exit price for closing")
    parser.add_argument("--list", action="store_true", help="List open plays")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--snapshot", action="store_true", help="Snapshot portfolio")
    
    args = parser.parse_args()
    
    if args.log:
        ticker = input("Ticker: ").upper()
        action = input("Action (BUY/SELL/TRIM/ADD): ").upper()
        shares = float(input("Shares: "))
        price = float(input("Price: "))
        broker = input("Broker: ")
        reason = input("Reason: ")
        log_play(ticker, action, shares, price, broker, reason)
    
    elif args.close and args.exit_price:
        close_play(args.close, args.exit_price)
    
    elif args.list:
        list_open_plays()
    
    elif args.stats:
        stats = get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.snapshot:
        snapshot_portfolio()
    
    else:
        # Default: snapshot + show stats
        snapshot_portfolio()
        stats = get_stats()
        if stats:
            print(f"\n📊 HISTORIC STATS")
            print(f"   Total plays: {stats['total_plays']}")
            print(f"   Closed: {stats['closed_plays']} | Open: {stats['open_plays']}")
            print(f"   Win rate: {stats['win_rate']:.1f}% ({stats['wins']}W / {stats['losses']}L)")
            print(f"   Total P&L: ${stats['total_pnl']:+.2f}")
            print(f"   Avg win: ${stats['avg_win']:+.2f} | Avg loss: ${stats['avg_loss']:+.2f}")


if __name__ == "__main__":
    main()
