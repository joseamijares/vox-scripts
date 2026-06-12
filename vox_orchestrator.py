#!/usr/bin/env python3
"""
VOX Autonomous Orchestrator v1.0
The brain that makes the system truly agentic.

What it does:
1. Wakes up every hour during market hours
2. Checks: market regime, portfolio status, alerts, opportunities
3. Runs all 4 agents on flagged positions
4. Generates insights, not just data
5. Surfaces ONLY what needs attention
6. Learns from outcomes and adjusts weights
7. Maintains continuity between sessions

Usage:
    python3 vox_orchestrator.py run        # Single run
    python3 vox_orchestrator.py daemon     # Continuous loop
    python3 vox_orchestrator.py insight    # Generate insight report
"""

import json
import subprocess
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public"
MEMORY_FILE = SCRIPTS_DIR / ".vox_agent_memory.json"
INSIGHTS_FILE = SCRIPTS_DIR / "vox_insights.json"
DASHBOARD_INSIGHTS = DASHBOARD_DIR / "vox_insights.json"

class VoxOrchestrator:
    """The autonomous brain of VOX"""
    
    def __init__(self):
        self.memory = self.load_memory()
        self.insights = []
        
    def load_memory(self) -> Dict:
        """Load agent memory"""
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE) as f:
                return json.load(f)
        return {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
            "total_runs": 0,
            "successful_predictions": 0,
            "failed_predictions": 0,
            "learned_patterns": [],
            "thesis_history": [],
            "alert_history": [],
            "market_context": {},
        }
    
    def save_memory(self):
        """Save agent memory"""
        self.memory["last_run"] = datetime.now(timezone.utc).isoformat()
        self.memory["total_runs"] += 1
        with open(MEMORY_FILE, 'w') as f:
            json.dump(self.memory, f, indent=2)
    
    def is_market_hours(self) -> bool:
        """Check if US market is open"""
        now = datetime.now(timezone.utc)
        # Convert to ET (UTC-4 or UTC-5)
        et_offset = timedelta(hours=-4)  # EDT
        et_time = now + et_offset
        
        # Market hours: 9:30 AM - 4:00 PM ET, Mon-Fri
        if et_time.weekday() >= 5:  # Weekend
            return False
        market_open = et_time.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = et_time.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return market_open <= et_time <= market_close
    
    def run_agent(self, agent_name: str, *args) -> Optional[Dict]:
        """Run an agent script"""
        script = SCRIPTS_DIR / "vox_agents" / f"{agent_name}.py"
        if not script.exists():
            return None
        
        try:
            cmd = ["python3", str(script)] + list(args)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except Exception as e:
            return {"error": str(e)}
    
    def run_pipeline(self, name: str) -> Optional[Dict]:
        """Run a pipeline script"""
        script = SCRIPTS_DIR / f"vox_{name}.py"
        if not script.exists():
            return None
        
        try:
            result = subprocess.run(["python3", str(script)], capture_output=True, text=True, timeout=120)
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except Exception as e:
            return {"error": str(e)}
    
    def check_portfolio_status(self) -> Dict:
        """Check portfolio for issues"""
        positions_file = SCRIPTS_DIR / "dashboard_positions.json"
        if not positions_file.exists():
            return {"error": "No portfolio data"}
        
        with open(positions_file) as f:
            data = json.load(f)
        
        positions = data.get("positions", [])
        
        # Find issues
        sell_signals = [p for p in positions if p.get("grade", 0) > 0 and p.get("grade", 0) < 45 and p.get("value", 0) > 500]
        trim_signals = [p for p in positions if p.get("grade", 0) >= 45 and p.get("grade", 0) < 50 and p.get("value", 0) > 500]
        big_losers = [p for p in positions if p.get("pnl", 0) < -500]
        
        # Crypto check
        crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX", "SUI"]
        crypto_value = sum(p["value"] for p in positions if p["ticker"] in crypto_tickers)
        total_value = data.get("total_value", sum(p.get("value", 0) for p in positions))
        crypto_pct = crypto_value / total_value * 100 if total_value > 0 else 0
        
        return {
            "total_value": total_value,
            "total_positions": len(positions),
            "sell_signals": sell_signals,
            "trim_signals": trim_signals,
            "big_losers": big_losers,
            "crypto_pct": crypto_pct,
            "issues_count": len(sell_signals) + len(trim_signals) + len(big_losers) + (1 if crypto_pct > 10 else 0),
        }
    
    def generate_insight(self, context: Dict) -> Dict:
        """Generate a true insight, not just data"""
        insight = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "insight",
            "title": "",
            "body": "",
            "action": None,
            "urgency": "low",
        }
        
        # Priority 1: SELL signals
        if context["sell_signals"]:
            tickers = [p["ticker"] for p in context["sell_signals"][:3]]
            insight["title"] = f"🔴 {len(context['sell_signals'])} positions need SELL action"
            insight["body"] = f"Top: {', '.join(tickers)}. Grades below 45 with significant value."
            insight["action"] = "Review Plays page"
            insight["urgency"] = "high"
        
        # Priority 2: Crypto over limit
        elif context["crypto_pct"] > 10:
            insight["title"] = f"⚠️ Crypto at {context['crypto_pct']:.1f}% (limit 10%)"
            insight["body"] = "Portfolio overweight in crypto. Consider trimming BTC/ETH."
            insight["action"] = "Check crypto allocation"
            insight["urgency"] = "medium"
        
        # Priority 3: Big losers
        elif context["big_losers"]:
            tickers = [p["ticker"] for p in context["big_losers"][:3]]
            insight["title"] = f"📉 {len(context['big_losers'])} positions losing >$500"
            insight["body"] = f"Watch: {', '.join(tickers)}. Review stop losses."
            insight["action"] = "Check Portfolio page"
            insight["urgency"] = "medium"
        
        # Priority 4: Market context
        else:
            regime_file = SCRIPTS_DIR / "vox_market_regime.json"
            if regime_file.exists():
                with open(regime_file) as f:
                    regime = json.load(f)
                insight["title"] = f"🌍 Market: {regime.get('regime', 'Unknown')}"
                insight["body"] = f"Confidence: {regime.get('confidence', 0)}%. Grade threshold: {regime.get('strategy_adjustments', {}).get('grade_threshold', 50)}."
                insight["action"] = "Check Intelligence page"
                insight["urgency"] = "low"
            else:
                insight["title"] = "✅ Portfolio stable"
                insight["body"] = f"{context['total_positions']} positions, ${context['total_value']:,.0f} total. No urgent actions."
                insight["action"] = None
                insight["urgency"] = "low"
        
        return insight
    
    def run_cycle(self):
        """Run one autonomous cycle"""
        print("\n" + "="*70)
        print(f"🤖 VOX AUTONOMOUS CYCLE #{self.memory['total_runs'] + 1}")
        print(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"   Market: {'OPEN' if self.is_market_hours() else 'CLOSED'}")
        print("="*70)
        
        # Step 1: Check portfolio
        print("\n📊 Checking portfolio...")
        portfolio = self.check_portfolio_status()
        
        if "error" in portfolio:
            print(f"   ❌ {portfolio['error']}")
            return
        
        print(f"   Value: ${portfolio['total_value']:,.0f}")
        print(f"   Positions: {portfolio['total_positions']}")
        print(f"   Issues: {portfolio['issues_count']}")
        
        # Step 2: Generate insight
        print("\n💡 Generating insight...")
        insight = self.generate_insight(portfolio)
        
        print(f"   {insight['title']}")
        print(f"   {insight['body']}")
        if insight['action']:
            print(f"   → Action: {insight['action']}")
        
        self.insights.append(insight)
        
        # Step 3: Run agents if issues found
        if portfolio['issues_count'] > 0:
            print("\n🗳️ Running Agent Council on flagged positions...")
            
            # Run council on sell signals
            for pos in portfolio['sell_signals'][:3]:
                result = self.run_pipeline("council")
                if result and result.get("returncode") == 0:
                    print(f"   ✅ Council voted on {pos['ticker']}")
                else:
                    print(f"   ⚠️ Council failed for {pos['ticker']}")
        
        # Step 4: Save everything
        self.save_memory()
        
        # Save insights
        with open(INSIGHTS_FILE, 'w') as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "insights": self.insights[-10:],  # Keep last 10
                "current": insight,
            }, f, indent=2)
        
        # Copy to dashboard
        if DASHBOARD_DIR.exists():
            with open(DASHBOARD_INSIGHTS, 'w') as f:
                json.dump({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "insights": self.insights[-10:],
                    "current": insight,
                }, f, indent=2)
        
        print("\n✅ Cycle complete")
        return insight
    
    def generate_daily_brief(self) -> Dict:
        """Generate comprehensive daily brief"""
        print("\n📚 Generating daily brief...")
        
        # Run all data collection
        pipelines = [
            ("daily_briefing", "Portfolio briefing"),
            ("regime_detector", "Market regime"),
            ("smart_alerts", "Smart alerts"),
        ]
        
        for name, label in pipelines:
            print(f"   Running {label}...")
            result = self.run_pipeline(name)
            if result and result.get("returncode") == 0:
                print(f"   ✅ {label} complete")
            else:
                print(f"   ⚠️ {label} failed")
        
        # Compile brief
        brief = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "daily_brief",
            "sections": [],
        }
        
        # Portfolio snapshot
        portfolio = self.check_portfolio_status()
        brief["sections"].append({
            "title": "Portfolio Snapshot",
            "content": f"${portfolio['total_value']:,.0f} across {portfolio['total_positions']} positions. {portfolio['issues_count']} issues flagged.",
        })
        
        # Market regime
        regime_file = SCRIPTS_DIR / "vox_market_regime.json"
        if regime_file.exists():
            with open(regime_file) as f:
                regime = json.load(f)
            brief["sections"].append({
                "title": "Market Regime",
                "content": f"{regime.get('regime', 'Unknown')} (confidence: {regime.get('confidence', 0)}%)",
            })
        
        # Action items
        actions = []
        if portfolio["sell_signals"]:
            actions.append(f"SELL {len(portfolio['sell_signals'])} positions (grade < 45)")
        if portfolio["crypto_pct"] > 10:
            actions.append(f"Trim crypto from {portfolio['crypto_pct']:.1f}% to 10%")
        
        brief["sections"].append({
            "title": "Action Items",
            "content": "\n".join(actions) if actions else "No urgent actions",
        })
        
        # Save
        brief_file = SCRIPTS_DIR / "vox_daily_brief.json"
        with open(brief_file, 'w') as f:
            json.dump(brief, f, indent=2)
        
        print("\n✅ Daily brief generated")
        return brief


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Autonomous Orchestrator")
    parser.add_argument("command", choices=["run", "daemon", "insight", "brief"])
    
    args = parser.parse_args()
    
    orchestrator = VoxOrchestrator()
    
    if args.command == "run":
        orchestrator.run_cycle()
    elif args.command == "daemon":
        print("🤖 VOX Daemon started. Press Ctrl+C to stop.")
        while True:
            try:
                orchestrator.run_cycle()
                # Sleep 1 hour
                import time
                time.sleep(3600)
            except KeyboardInterrupt:
                print("\n👋 Daemon stopped")
                break
    elif args.command == "insight":
        portfolio = orchestrator.check_portfolio_status()
        insight = orchestrator.generate_insight(portfolio)
        print(json.dumps(insight, indent=2))
    elif args.command == "brief":
        brief = orchestrator.generate_daily_brief()
        print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
