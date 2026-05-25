#!/usr/bin/env python3
"""
Vox Play Journal
- Logs every play decision: suggested → approved → executed → closed
- Tracks what worked, what didn't
- Feeds back into grade system calibration
- Outputs to Google Sheets '📓 Play Journal' tab
"""
import json, os
from datetime import datetime

JOURNAL_FILE = "vox_play_journal.json"

def load_journal():
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE) as f:
            return json.load(f)
    return []

def save_journal(entries):
    with open(JOURNAL_FILE, "w") as f:
        json.dump(entries, f, indent=2)

def log_play(play_id, ticker, play_type, decision, grade, council, entry, exit_price, pnl, lesson, worked, didnt):
    """Log a play decision."""
    entries = load_journal()
    entry_data = {
        "date": datetime.now().isoformat(),
        "play_id": play_id,
        "ticker": ticker,
        "type": play_type,
        "decision": decision,
        "grade": grade,
        "council": council,
        "entry": entry,
        "exit": exit_price,
        "pnl": pnl,
        "lesson": lesson,
        "what_worked": worked,
        "what_didnt": didnt
    }
    entries.append(entry_data)
    save_journal(entries)
    print(f"✅ Logged: {ticker} {decision} | P&L: {pnl}")
    return entry_data

def log_suggested(ticker, grade, council, setup_notes):
    """Log when a play is suggested by the system."""
    return log_play(
        play_id=f"SUG_{ticker}_{datetime.now().strftime('%Y%m%d')}",
        ticker=ticker,
        play_type="SUGGESTED",
        decision="SYSTEM_SUGGESTED",
        grade=grade,
        council=council,
        entry="—",
        exit_price="—",
        pnl="—",
        lesson=f"Setup: {setup_notes}",
        worked="—",
        didnt="—"
    )

def log_approved(play_id, ticker, grade, council, entry, stop, target, risk):
    """Log when user approves a play."""
    return log_play(
        play_id=play_id,
        ticker=ticker,
        play_type="APPROVED",
        decision="USER_APPROVED",
        grade=grade,
        council=council,
        entry=entry,
        exit_price="—",
        pnl="—",
        lesson=f"Stop: {stop}, Target: {target}, Risk: ${risk}",
        worked="—",
        didnt="—"
    )

def log_executed(play_id, ticker, fill_price, qty, broker):
    """Log when a play is executed."""
    return log_play(
        play_id=play_id,
        ticker=ticker,
        play_type="EXECUTED",
        decision=f"EXECUTED_ON_{broker}",
        grade="—",
        council="—",
        entry=fill_price,
        exit_price="—",
        pnl="—",
        lesson=f"Qty: {qty}, Broker: {broker}",
        worked="—",
        didnt="—"
    )

def log_closed(play_id, ticker, exit_price, pnl, lesson, worked, didnt):
    """Log when a play is closed."""
    return log_play(
        play_id=play_id,
        ticker=ticker,
        play_type="CLOSED",
        decision="POSITION_CLOSED",
        grade="—",
        council="—",
        entry="—",
        exit_price=exit_price,
        pnl=pnl,
        lesson=lesson,
        worked=worked,
        didnt=didnt
    )

def get_stats():
    """Get journal statistics."""
    entries = load_journal()
    
    executed = [e for e in entries if e["type"] == "EXECUTED"]
    closed = [e for e in entries if e["type"] == "CLOSED" and e["pnl"] not in ("—", None)]
    
    wins = [e for e in closed if isinstance(e["pnl"], (int, float)) and e["pnl"] > 0]
    losses = [e for e in closed if isinstance(e["pnl"], (int, float)) and e["pnl"] < 0]
    
    total_pnl = sum(e["pnl"] for e in closed if isinstance(e["pnl"], (int, float)))
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    
    return {
        "total_plays": len(entries),
        "executed": len(executed),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(sum(e["pnl"] for e in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(e["pnl"] for e in losses) / len(losses), 2) if losses else 0,
    }

def main():
    print("📓 Vox Play Journal")
    print("-" * 50)
    
    entries = load_journal()
    print(f"Total entries: {len(entries)}")
    
    stats = get_stats()
    print(f"\n📊 Stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    if entries:
        print(f"\n📝 Last 3 entries:")
        for e in entries[-3:]:
            print(f"  {e['date'][:10]} | {e['ticker']} | {e['type']} | {e['decision']}")
    
    print("\n✅ Done")

if __name__ == "__main__":
    main()
