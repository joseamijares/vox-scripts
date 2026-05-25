#!/usr/bin/env python3
"""
VOX Autonomous Agent v1.0
Self-running trading intelligence that operates 24/7

Capabilities:
- Monitors all positions for signal changes
- Discovers new plays via sector/supply chain scanning
- Generates daily briefings
- Tracks outcomes and learns from results
- Sends alerts via Telegram

Usage:
    python3 vox_autonomous_agent.py --mode monitor    # Run monitoring loop
    python3 vox_autonomous_agent.py --mode discover   # Discover new plays
    python3 vox_autonomous_agent.py --mode daily      # Generate daily briefing
    python3 vox_autonomous_agent.py --mode learn      # Run learning cycle
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Import harness
sys.path.insert(0, os.path.dirname(__file__))
from vox_ai_harness import VoxHarness, Play


@dataclass
class Alert:
    id: str
    ticker: str
    type: str          # GRADE_CHANGE, PRICE_ALERT, EARNINGS, STOP_HIT
    severity: str      # LOW, MEDIUM, HIGH, CRITICAL
    message: str
    timestamp: str
    acknowledged: bool = False


class VoxAgent:
    """Autonomous trading agent"""
    
    def __init__(self):
        self.harness = VoxHarness()
        self.scripts_dir = os.path.expanduser("~/.hermes/scripts")
        self.state_file = f"{self.scripts_dir}/vox_agent_state.json"
        self.alerts_file = f"{self.scripts_dir}/vox_agent_alerts.json"
        self.state = self._load_state()
        self.alerts: List[Alert] = self._load_alerts()
    
    def _load_state(self) -> Dict:
        """Load agent state"""
        if os.path.exists(self.state_file):
            with open(self.state_file) as f:
                return json.load(f)
        return {
            "last_scan": None,
            "last_daily_brief": None,
            "last_learning_cycle": None,
            "active_plays": [],
            "position_snapshots": {},
        }
    
    def _save_state(self):
        """Save agent state"""
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _load_alerts(self) -> List[Alert]:
        """Load alerts"""
        if os.path.exists(self.alerts_file):
            with open(self.alerts_file) as f:
                data = json.load(f)
                return [Alert(**a) for a in data]
        return []
    
    def _save_alerts(self):
        """Save alerts"""
        with open(self.alerts_file, 'w') as f:
            json.dump([asdict(a) for a in self.alerts], f, indent=2)
    
    def _add_alert(self, ticker: str, alert_type: str, severity: str, message: str):
        """Add new alert"""
        alert = Alert(
            id=f"alert_{ticker}_{int(time.time())}",
            ticker=ticker,
            type=alert_type,
            severity=severity,
            message=message,
            timestamp=datetime.now().isoformat()
        )
        self.alerts.append(alert)
        self._save_alerts()
        
        # TODO: Send Telegram notification
        print(f"🚨 ALERT [{severity}] {ticker}: {message}")
    
    def monitor_positions(self):
        """Monitor all positions for changes"""
        print(f"\n{'='*60}")
        print(f"🔍 POSITION MONITOR — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}\n")
        
        # Get current scores
        scores = self.harness.scan_all()
        
        # Check for significant changes
        changes_found = 0
        for score in scores:
            ticker = score.ticker
            prev_snapshot = self.state["position_snapshots"].get(ticker, {})
            
            # Check grade changes
            if score.grade and prev_snapshot.get("grade"):
                grade_diff = score.grade - prev_snapshot["grade"]
                if abs(grade_diff) >= 10:
                    severity = "HIGH" if abs(grade_diff) >= 20 else "MEDIUM"
                    self._add_alert(
                        ticker=ticker,
                        alert_type="GRADE_CHANGE",
                        severity=severity,
                        message=f"Grade changed from {prev_snapshot['grade']} to {score.grade} ({grade_diff:+.0f})"
                    )
                    changes_found += 1
            
            # Check composite score changes
            prev_score = prev_snapshot.get("composite", 50)
            score_diff = score.overall - prev_score
            if abs(score_diff) >= 15:
                self._add_alert(
                    ticker=ticker,
                    alert_type="SCORE_CHANGE",
                    severity="MEDIUM",
                    message=f"Composite score shifted from {prev_score:.0f} to {score.overall:.0f}"
                )
                changes_found += 1
            
            # Update snapshot
            self.state["position_snapshots"][ticker] = {
                "grade": score.grade,
                "composite": score.overall,
                "action": score.action,
                "timestamp": datetime.now().isoformat()
            }
        
        self.state["last_scan"] = datetime.now().isoformat()
        self._save_state()
        
        print(f"\n✅ Monitor complete. {changes_found} changes detected.")
        if changes_found > 0:
            print(f"   {len([a for a in self.alerts if not a.acknowledged])} unacknowledged alerts")
    
    def discover_plays(self):
        """Discover new plays via scanning"""
        print(f"\n{'='*60}")
        print(f"🔎 PLAY DISCOVERY — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}\n")
        
        # Generate plays from harness
        plays = self.harness.generate_plays()
        
        # Filter to new plays (not in active list)
        existing_tickers = {p["ticker"] for p in self.state["active_plays"]}
        new_plays = [p for p in plays if p.ticker not in existing_tickers]
        
        print(f"Generated {len(plays)} total plays")
        print(f"New plays: {len(new_plays)}")
        
        # Add high-confidence plays to active list
        for play in new_plays:
            if play.confidence >= 65:
                self.state["active_plays"].append(asdict(play))
                print(f"  + Added: {play.type} {play.ticker} (confidence: {play.confidence:.0f})")
        
        self._save_state()
        
        # Export to dashboard
        plays_file = f"{self.scripts_dir}/vox_generated_plays.json"
        with open(plays_file, 'w') as f:
            json.dump([asdict(p) for p in plays], f, indent=2)
        print(f"\n✅ Exported plays to {plays_file}")
    
    def generate_daily_brief(self):
        """Generate daily briefing"""
        print(f"\n{'='*60}")
        print(f"📋 DAILY BRIEFING — {datetime.now().strftime('%Y-%m-%d')}")
        print(f"{'='*60}\n")
        
        # Portfolio summary
        positions = self.harness.data["positions"]
        total_value = sum(p["value"] for p in positions)
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
        
        # Top movers
        movers = sorted(positions, key=lambda p: abs(p.get("unrealized_pnl_pct", 0)), reverse=True)[:10]
        
        # Active plays
        active_plays = self.state["active_plays"]
        
        # Unacknowledged alerts
        unacked = [a for a in self.alerts if not a.acknowledged]
        
        brief = {
            "date": datetime.now().isoformat(),
            "portfolio": {
                "total_value": total_value,
                "total_pnl": total_pnl,
                "positions_count": len(positions)
            },
            "top_movers": [
                {
                    "ticker": m["ticker"],
                    "broker": m["broker"],
                    "pnl_pct": m.get("unrealized_pnl_pct", 0),
                    "value": m["value"]
                } for m in movers
            ],
            "active_plays": active_plays[:10],
            "alerts": [
                {
                    "ticker": a.ticker,
                    "type": a.type,
                    "severity": a.severity,
                    "message": a.message
                } for a in unacked[-10:]
            ],
            "recommendations": []
        }
        
        # Generate recommendations
        scores = self.harness.scan_all()
        sells = [s for s in scores if s.action == "SELL"][:5]
        buys = [s for s in scores if s.action in ["BUY", "STRONG_BUY"]][:5]
        
        for s in sells:
            brief["recommendations"].append({
                "action": "SELL",
                "ticker": s.ticker,
                "reason": f"Grade {s.grade}, composite {s.overall:.0f}"
            })
        
        for s in buys:
            brief["recommendations"].append({
                "action": "BUY",
                "ticker": s.ticker,
                "reason": f"Grade {s.grade}, composite {s.overall:.0f}"
            })
        
        # Save briefing
        brief_file = f"{self.scripts_dir}/vox_daily_brief.json"
        with open(brief_file, 'w') as f:
            json.dump(brief, f, indent=2)
        
        self.state["last_daily_brief"] = datetime.now().isoformat()
        self._save_state()
        
        # Print summary
        print(f"Portfolio: ${total_value:,.0f} | P&L: ${total_pnl:,.0f}")
        print(f"Positions: {len(positions)}")
        print(f"\nTop Movers:")
        for m in movers[:5]:
            direction = "📈" if m.get("unrealized_pnl_pct", 0) >= 0 else "📉"
            print(f"  {direction} {m['ticker']}: {m.get('unrealized_pnl_pct', 0):+.1f}%")
        
        print(f"\nActive Plays: {len(active_plays)}")
        print(f"Unacknowledged Alerts: {len(unacked)}")
        print(f"\nRecommendations:")
        for r in brief["recommendations"][:5]:
            print(f"  {r['action']}: {r['ticker']} — {r['reason']}")
        
        print(f"\n✅ Brief saved to {brief_file}")
    
    def learning_cycle(self):
        """Run learning cycle — analyze outcomes and update models"""
        print(f"\n{'='*60}")
        print(f"🧠 LEARNING CYCLE — {datetime.now().strftime('%Y-%m-%d')}")
        print(f"{'='*60}\n")
        
        # Load closed plays
        closed_plays = [p for p in self.state["active_plays"] if p.get("status") == "CLOSED"]
        
        if not closed_plays:
            print("No closed plays to learn from yet.")
            return
        
        # Analyze outcomes
        wins = [p for p in closed_plays if p.get("pnl", 0) > 0]
        losses = [p for p in closed_plays if p.get("pnl", 0) <= 0]
        
        win_rate = len(wins) / len(closed_plays) if closed_plays else 0
        avg_win = sum(p.get("pnl", 0) for p in wins) / len(wins) if wins else 0
        avg_loss = sum(p.get("pnl", 0) for p in losses) / len(losses) if losses else 0
        
        print(f"Closed Plays: {len(closed_plays)}")
        print(f"Win Rate: {win_rate:.1%}")
        print(f"Avg Win: ${avg_win:,.0f}")
        print(f"Avg Loss: ${avg_loss:,.0f}")
        
        # Analyze which signals were most predictive
        signal_performance = {}
        for play in closed_plays:
            for signal in play.get("source_signals", []):
                if signal not in signal_performance:
                    signal_performance[signal] = {"correct": 0, "total": 0}
                signal_performance[signal]["total"] += 1
                if play.get("pnl", 0) > 0:
                    signal_performance[signal]["correct"] += 1
        
        print(f"\nSignal Accuracy:")
        for signal, stats in sorted(signal_performance.items(), key=lambda x: x[1]["correct"]/x[1]["total"] if x[1]["total"] > 0 else 0, reverse=True):
            acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {signal:15} | {acc:.1%} ({stats['correct']}/{stats['total']})")
        
        # Update harness weights based on performance
        print(f"\n🔄 Updating harness weights...")
        # This would adjust weights in the harness — simplified for now
        
        self.state["last_learning_cycle"] = datetime.now().isoformat()
        self._save_state()
        
        print(f"\n✅ Learning cycle complete")
    
    def run_monitor_loop(self, interval_minutes: int = 15):
        """Run continuous monitoring loop"""
        print(f"\n🤖 VOX Autonomous Agent Started")
        print(f"   Monitor interval: {interval_minutes} minutes")
        print(f"   Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.monitor_positions()
                
                # Check if it's time for daily brief (market open)
                now = datetime.now()
                if now.hour >= 9 and now.hour <= 16:
                    last_brief = self.state.get("last_daily_brief")
                    if not last_brief or (now - datetime.fromisoformat(last_brief)).days >= 1:
                        self.generate_daily_brief()
                
                print(f"\n⏳ Next check in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 Agent stopped")
            self._save_state()


def main():
    parser = argparse.ArgumentParser(description="VOX Autonomous Agent")
    parser.add_argument("--mode", choices=["monitor", "discover", "daily", "learn", "loop"], required=True)
    parser.add_argument("--interval", type=int, default=15, help="Monitor interval in minutes")
    
    args = parser.parse_args()
    
    agent = VoxAgent()
    
    if args.mode == "monitor":
        agent.monitor_positions()
    elif args.mode == "discover":
        agent.discover_plays()
    elif args.mode == "daily":
        agent.generate_daily_brief()
    elif args.mode == "learn":
        agent.learning_cycle()
    elif args.mode == "loop":
        agent.run_monitor_loop(args.interval)


if __name__ == "__main__":
    main()
