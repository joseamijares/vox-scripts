#!/usr/bin/env python3
"""
VOX Harness Feed — Simple composite score exporter
Reads vox_ai_harness scores, exports JSON for dashboard + alerts
No wrapper complexity. Just data.
"""

import json
from datetime import datetime
from vox_ai_harness import VoxHarness

def main():
    h = VoxHarness()
    scores = h.scan_all()
    
    # Export all scores
    output = {
        "timestamp": datetime.now().isoformat(),
        "positions_scored": len(scores),
        "scores": []
    }
    
    for s in scores:
        output["scores"].append({
            "ticker": s.ticker,
            "overall": round(s.overall, 1),
            "grade": s.grade,
            "action": s.action,
            "confidence": round(s.confidence, 2),
            "catalysts": s.catalysts,
            "risks": s.risks,
            "signals": [{"name": sig.name, "value": round(sig.value, 1), "weight": sig.weight} for sig in s.signals]
        })
    
    # Save
    with open("vox_harness_scores.json", "w") as f:
        json.dump(output, f, indent=2)
    
    # Generate priority list
    print("🎯 PRIORITY POSITIONS")
    print("=" * 60)
    
    # Strong buys
    buys = [s for s in scores if s.overall >= 65]
    if buys:
        print(f"\n🟢 STRONG ({len(buys)}):")
        for s in buys[:5]:
            print(f"  {s.ticker:8} score={s.overall:.1f} grade={s.grade}")
    
    # Weak holds (need attention)
    weak = [s for s in scores if s.overall < 45 and s.overall >= 35]
    if weak:
        print(f"\n🟡 WATCH ({len(weak)}):")
        for s in weak[:5]:
            print(f"  {s.ticker:8} score={s.overall:.1f} grade={s.grade}")
    
    # Sells
    sells = [s for s in scores if s.overall < 35]
    if sells:
        print(f"\n🔴 SELL ({len(sells)}):")
        for s in sells[:5]:
            print(f"  {s.ticker:8} score={s.overall:.1f} grade={s.grade}")
    
    print(f"\n💾 Saved {len(scores)} scores to vox_harness_scores.json")

if __name__ == "__main__":
    main()
