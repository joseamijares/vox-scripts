#!/usr/bin/env python3
"""
VOX WEEKLY DEEP DIVE — double-layer grader.
Layer 1: corrected VOX grade (50% VOX + 50% fresh technical)
Layer 2: Claude Sonnet 5 portfolio-level interpretation
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from vox_utils import (
    OUTPUT_DIR, save_cache, load_cache, call_openrouter, build_snapshot,
)


def weekly_analysis(top20: list) -> dict:
    system_prompt = """You are an elite growth portfolio strategist writing a Sunday "Week Ahead" research note for an aggressive investor targeting 25-50% annual returns. You have VOX-corrected grades (50% VOX + 50% fresh technical), momentum metrics, and ownership status. Provide conviction-weighted ideas, risk management, and portfolio construction."""

    user_prompt = f"""Week Ahead — VOX-corrected top 20 ({datetime.now().strftime('%Y-%m-%d')}):

{json.dumps(top20, indent=2)}

OUTPUT FORMAT:
1. **Top 5 weekly plays** — ticker, entry, stop, target 1, target 2, position size % of NEW capital, thesis, key catalyst/theme.
2. **Next 5 honorable mentions** — one line each (ticker, grade, action, why watch).
3. **Portfolio construction** — how to blend new money vs. add to existing positions. Max sector concentration warning.
4. **Macro/sector risk radar** — 3 risks to watch this week.
5. **Earnings/catalyst calendar** — list any known catalysts if inferable from the themes (be conservative, state if unknown).
6. **ESTIMATED_COST_LINE** — exactly: `ESTIMATED_COST: $X.XXXX`
"""

    return call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="anthropic/claude-sonnet-5",
        max_tokens=6000,
        temperature=0.5,
    )


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[VOX Weekly Deep Dive] Building snapshot for {today}...")

    snapshot = build_snapshot(limit=150)
    save_cache(today, {"snapshot": snapshot})
    top20 = snapshot[:20]

    print(f"[VOX Weekly Deep Dive] Calling Claude Sonnet 5 for weekly analysis...")
    analysis = weekly_analysis(top20)

    output = {
        "generated": datetime.now().isoformat(),
        "type": "weekly_deep_dive",
        "model": analysis["model"],
        "cost_usd": analysis["cost_usd"],
        "prompt_tokens": analysis["prompt_tokens"],
        "completion_tokens": analysis["completion_tokens"],
        "top20": top20,
        "analysis": analysis["content"],
    }

    out_path = OUTPUT_DIR / f"vox_weekly_deep_dive_{today}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"[VOX Weekly Deep Dive] Cost: ${analysis['cost_usd']:.6f}")
    print(f"[VOX Weekly Deep Dive] Saved to: {out_path}")
    print("\n" + "=" * 60)
    print(analysis["content"])
    print("=" * 60)


if __name__ == "__main__":
    main()
