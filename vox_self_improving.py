#!/usr/bin/env python3
"""
VOX Self-Improving System v1.0
Auto-adjusts agent weights based on accuracy.

Tracks:
- Each agent's prediction accuracy
- Grade bucket win rates
- Signal type performance
- Market regime effectiveness

Adjusts:
- Agent weights in council voting
- Grade thresholds
- Position sizing multipliers
- Alert sensitivity
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
CONFIG_FILE = SCRIPTS_DIR / "vox_agent_config.json"
PERFORMANCE_FILE = SCRIPTS_DIR / "vox_performance_log.json"


class SelfImprovingSystem:
    """Automatically improves VOX based on outcomes"""
    
    def __init__(self):
        self.config = self.load_config()
        self.performance = self.load_performance()
    
    def load_config(self) -> Dict:
        """Load agent configuration"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
        return {
            "version": 1,
            "agent_weights": {
                "technical": 1.0,
                "macro": 0.9,
                "sentiment": 0.7,
                "risk": 1.2,
            },
            "grade_thresholds": {
                "buy": 70,
                "hold": 50,
                "sell": 45,
            },
            "position_sizing": {
                "multiplier": 1.0,
                "max_single_position": 0.08,
                "max_sector": 0.30,
                "max_crypto": 0.10,
            },
            "alert_sensitivity": {
                "grade_drop_threshold": 45,
                "loss_threshold": 500,
                "crypto_limit": 0.10,
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    
    def save_config(self):
        """Save configuration"""
        self.config["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def load_performance(self) -> Dict:
        """Load performance history"""
        if PERFORMANCE_FILE.exists():
            with open(PERFORMANCE_FILE) as f:
                return json.load(f)
        return {
            "agent_predictions": [],
            "grade_outcomes": [],
            "regime_performance": {},
        }
    
    def save_performance(self):
        """Save performance history"""
        with open(PERFORMANCE_FILE, 'w') as f:
            json.dump(self.performance, f, indent=2)
    
    def calculate_agent_accuracy(self, agent_name: str) -> float:
        """Calculate accuracy for a specific agent"""
        predictions = [p for p in self.performance.get("agent_predictions", [])
                      if p.get("agent") == agent_name]
        
        if not predictions:
            return 0.5  # Default 50%
        
        correct = sum(1 for p in predictions if p.get("outcome") == "correct")
        return correct / len(predictions)
    
    def calculate_grade_accuracy(self, grade_bucket: str) -> float:
        """Calculate accuracy for a grade bucket"""
        outcomes = self.performance.get("grade_outcomes", [])
        bucket_outcomes = [o for o in outcomes if o.get("bucket") == grade_bucket]
        
        if not bucket_outcomes:
            return 0.5
        
        wins = sum(1 for o in bucket_outcomes if o.get("result") == "win")
        return wins / len(bucket_outcomes)
    
    def adjust_agent_weights(self):
        """Adjust agent weights based on accuracy"""
        print("\n⚖️ Adjusting agent weights...")
        
        agents = ["technical", "macro", "sentiment", "risk"]
        current_weights = self.config["agent_weights"]
        
        adjustments = {}
        for agent in agents:
            accuracy = self.calculate_agent_accuracy(agent)
            
            # Adjust weight: more accurate = higher weight
            # Base weight * accuracy ratio
            base_weight = {"technical": 1.0, "macro": 0.9, "sentiment": 0.7, "risk": 1.2}[agent]
            new_weight = base_weight * (0.5 + accuracy)  # Scale: 0.5-1.5x
            
            # Clamp between 0.3 and 2.0
            new_weight = max(0.3, min(2.0, new_weight))
            
            old_weight = current_weights.get(agent, base_weight)
            adjustments[agent] = {
                "old": old_weight,
                "new": round(new_weight, 2),
                "accuracy": round(accuracy, 2),
            }
            
            current_weights[agent] = round(new_weight, 2)
        
        # Print adjustments
        for agent, adj in adjustments.items():
            change = "↑" if adj["new"] > adj["old"] else "↓" if adj["new"] < adj["old"] else "→"
            print(f"   {change} {agent}: {adj['old']:.2f} → {adj['new']:.2f} (accuracy: {adj['accuracy']:.0%})")
        
        return adjustments
    
    def adjust_grade_thresholds(self):
        """Adjust grade thresholds based on outcomes"""
        print("\n📊 Adjusting grade thresholds...")
        
        buckets = {
            "70+": self.calculate_grade_accuracy("70+"),
            "60-69": self.calculate_grade_accuracy("60-69"),
            "50-59": self.calculate_grade_accuracy("50-59"),
            "<50": self.calculate_grade_accuracy("<50"),
        }
        
        print("   Grade bucket accuracy:")
        for bucket, accuracy in buckets.items():
            print(f"     {bucket}: {accuracy:.0%}")
        
        # If 70+ bucket underperforms, raise threshold
        if buckets["70+"] < 0.6:
            old = self.config["grade_thresholds"]["buy"]
            self.config["grade_thresholds"]["buy"] = min(80, old + 2)
            print(f"   ↑ Buy threshold: {old} → {self.config['grade_thresholds']['buy']} (70+ underperforming)")
        
        # If <50 bucket overperforms, lower sell threshold
        if buckets["<50"] > 0.5:
            old = self.config["grade_thresholds"]["sell"]
            self.config["grade_thresholds"]["sell"] = max(35, old - 1)
            print(f"   ↓ Sell threshold: {old} → {self.config['grade_thresholds']['sell']} (<50 outperforming)")
    
    def adjust_position_sizing(self):
        """Adjust position sizing based on market regime performance"""
        print("\n💰 Adjusting position sizing...")
        
        regime_perf = self.performance.get("regime_performance", {})
        
        if not regime_perf:
            print("   No regime performance data yet")
            return
        
        # Find best performing regime
        best_regime = max(regime_perf.items(), key=lambda x: x[1].get("win_rate", 0))
        worst_regime = min(regime_perf.items(), key=lambda x: x[1].get("win_rate", 0))
        
        print(f"   Best regime: {best_regime[0]} ({best_regime[1].get('win_rate', 0):.0%} win rate)")
        print(f"   Worst regime: {worst_regime[0]} ({worst_regime[1].get('win_rate', 0):.0%} win rate)")
        
        # Adjust multiplier based on recent performance
        recent_win_rate = best_regime[1].get("win_rate", 0.5)
        
        if recent_win_rate > 0.6:
            old_mult = self.config["position_sizing"]["multiplier"]
            self.config["position_sizing"]["multiplier"] = min(1.5, old_mult + 0.1)
            print(f"   ↑ Size multiplier: {old_mult:.1f}x → {self.config['position_sizing']['multiplier']:.1f}x (strong performance)")
        elif recent_win_rate < 0.4:
            old_mult = self.config["position_sizing"]["multiplier"]
            self.config["position_sizing"]["multiplier"] = max(0.5, old_mult - 0.1)
            print(f"   ↓ Size multiplier: {old_mult:.1f}x → {self.config['position_sizing']['multiplier']:.1f}x (weak performance)")
    
    def generate_improvement_report(self) -> Dict:
        """Generate report of improvements made"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_weights": self.config["agent_weights"],
            "grade_thresholds": self.config["grade_thresholds"],
            "position_sizing": self.config["position_sizing"],
            "performance_summary": {
                "total_predictions": len(self.performance.get("agent_predictions", [])),
                "total_grade_outcomes": len(self.performance.get("grade_outcomes", [])),
            },
        }
    
    def run_improvement_cycle(self):
        """Run one improvement cycle"""
        print("\n" + "=" * 70)
        print("🔄 VOX SELF-IMPROVEMENT CYCLE")
        print(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print("=" * 70)
        
        # Adjust everything
        self.adjust_agent_weights()
        self.adjust_grade_thresholds()
        self.adjust_position_sizing()
        
        # Save
        self.save_config()
        self.save_performance()
        
        # Generate report
        report = self.generate_improvement_report()
        
        report_file = SCRIPTS_DIR / "vox_improvement_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print("\n✅ Improvement cycle complete")
        print(f"   Config saved to: {CONFIG_FILE}")
        
        return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Self-Improving System")
    parser.add_argument("command", choices=["improve", "config", "report"])
    
    args = parser.parse_args()
    
    system = SelfImprovingSystem()
    
    if args.command == "improve":
        system.run_improvement_cycle()
    elif args.command == "config":
        print(json.dumps(system.config, indent=2))
    elif args.command == "report":
        report_file = SCRIPTS_DIR / "vox_improvement_report.json"
        if report_file.exists():
            with open(report_file) as f:
                print(json.dumps(json.load(f), indent=2))
        else:
            print("No improvement report found")


if __name__ == "__main__":
    main()
