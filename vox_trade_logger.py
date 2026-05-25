#!/usr/bin/env python3
"""
VOX Trade Logger
Logs every buy, sell, trim to Trade Execution Log + Mistake Journal
Auto-updates P&L, win rate, and flags mistakes
"""

import json
import os
from datetime import datetime
from pathlib import Path

VAULT_PATH = "/Users/jos/Documents/Obsidian Vault/Portfolio-Finance"
LOG_FILE = f"{VAULT_PATH}/02-Portfolio/Trade Execution Log.md"
MISTAKE_FILE = f"{VAULT_PATH}/10-Strategy/Mistake Journal.md"

class TradeLogger:
    def __init__(self):
        self.trades = []
        self.load_existing()
    
    def load_existing(self):
        """Parse existing trades from markdown"""
        if not os.path.exists(LOG_FILE):
            return
        # Simple parsing - in production, use frontmatter
        pass
    
    def log_trade(self, ticker, action, shares, entry_price, exit_price=None, 
                  broker="Schwab", grade_at_entry=0, thesis="", stop=None, target=None):
        """Log a new trade"""
        
        trade = {
            "id": f"TRADE-{len(self.trades)+1:03d}",
            "ticker": ticker,
            "action": action.upper(),  # BUY, SELL, TRIM, ADD
            "shares": shares,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "broker": broker,
            "date_in": datetime.now().strftime("%Y-%m-%d"),
            "date_out": datetime.now().strftime("%Y-%m-%d") if exit_price else None,
            "grade_at_entry": grade_at_entry,
            "thesis": thesis,
            "stop": stop,
            "target": target,
            "pnl": 0,
            "pnl_pct": 0,
            "status": "OPEN" if not exit_price else "CLOSED"
        }
        
        # Calculate P&L if closed
        if exit_price:
            trade["pnl"] = (exit_price - entry_price) * shares
            trade["pnl_pct"] = ((exit_price - entry_price) / entry_price) * 100
            trade["status"] = "CLOSED"
        
        self.trades.append(trade)
        
        # Auto-flag mistakes
        if trade["pnl"] < -500:
            self.flag_mistake(trade)
        
        # Append to markdown
        self.append_to_log(trade)
        
        return trade
    
    def flag_mistake(self, trade):
        """Auto-flag mistakes for journal"""
        mistake_type = "Unknown"
        
        if trade["grade_at_entry"] < 50 and trade["action"] == "BUY":
            mistake_type = "Low Grade Entry"
        elif trade["pnl_pct"] < -20 and trade["action"] == "SELL":
            mistake_type = "Hope/Holding Too Long"
        elif trade.get("stop") and trade["exit_price"] < trade["stop"]:
            mistake_type = "Stop Violation"
        
        print(f"⚠️  MISTAKE FLAGGED: {trade['ticker']} — {mistake_type} — Loss: ${trade['pnl']:.0f}")
        print(f"   Review: {MISTAKE_FILE}")
    
    def append_to_log(self, trade):
        """Append trade to markdown log"""
        entry = f"""
#### {trade['id']}: {trade['action']} {trade['ticker']}
| Field | Value |
|-------|-------|
| **Ticker** | {trade['ticker']} |
| **Action** | {trade['action']} |
| **Shares** | {trade['shares']} |
| **Entry Price** | ${trade['entry_price']:.2f} |
| **Exit Price** | ${trade['exit_price']:.2f if trade['exit_price'] else 'OPEN'} |
| **P&L** | ${trade['pnl']:.0f} |
| **P&L %** | {trade['pnl_pct']:.1f}% |
| **Broker** | {trade['broker']} |
| **Date** | {trade['date_in']} |
| **Grade** | {trade['grade_at_entry']} |
| **Thesis** | {trade['thesis']} |
| **Status** | {trade['status']} |
"""
        
        with open(LOG_FILE, "a") as f:
            f.write(entry)
        
        print(f"✅ Logged: {trade['id']} — {trade['action']} {trade['ticker']}")
    
    def get_stats(self):
        """Get trading statistics"""
        closed = [t for t in self.trades if t["status"] == "CLOSED"]
        if not closed:
            return {"total_trades": 0}
        
        wins = [t for t in closed if t["pnl"] > 0]
        
        return {
            "total_trades": len(self.trades),
            "closed_trades": len(closed),
            "win_rate": len(wins) / len(closed) * 100,
            "total_pnl": sum(t["pnl"] for t in closed),
            "avg_pnl": sum(t["pnl"] for t in closed) / len(closed),
            "best_trade": max(t["pnl"] for t in closed),
            "worst_trade": min(t["pnl"] for t in closed)
        }

if __name__ == "__main__":
    logger = TradeLogger()
    
    # Example: Log yesterday's trades
    # logger.log_trade("JMIA", "SELL", 200, 7.50, 2.40, "eToro", 55, "African e-commerce")
    # logger.log_trade("BTC", "TRIM", 0.064, 45000, 105520, "Binance", 70, "Bitcoin halving")
    
    stats = logger.get_stats()
    print(f"\n📊 Stats: {stats}")
