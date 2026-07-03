#!/usr/bin/env python3
"""
VOX DAILY TOP 10 — double-layer grader.
Layer 1: corrected VOX grade (50% VOX + 50% fresh technical)
Layer 2: Claude Sonnet 5 interpretation
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the script dir is importable
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from vox_utils import (
    OUTPUT_DIR, save_cache, load_cache, call_openrouter, build_snapshot
)


def daily_analysis(top10: list) -> dict:
    system_prompt = """You are an elite active trader writing a concise daily "Top 10" watchlist for an aggressive growth investor targeting 25-50% annual returns. You must cover ALL 10 tickers in the input. Be concise and specific."""

    user_prompt = f"""Today's VOX-corrected top candidates ({datetime.now().strftime('%Y-%m-%d')}):

{json.dumps(top10, indent=2)}

OUTPUT FORMAT (strictly, keep it short so you fit within the token limit):
1. **Top 5 trades for today** — for each: ticker, entry range, stop loss, target, size % of new capital, and ONE sentence thesis. Rank by your conviction, not just grade.
2. **Honorable mentions #6-10** — one line per ticker: ticker | grade | action | one-sentence reason.
3. **Portfolio flags** — which of the top 10 are already owned, and whether to add or hold.
4. **Risk of the day** — one sentence macro/sector risk.
5. **ESTIMATED_COST_LINE** — print exactly: `ESTIMATED_COST: $X.XXXX`

IMPORTANT: The list above has exactly 10 tickers. Do not skip any."""

    return call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="anthropic/claude-sonnet-5",
        max_tokens=4000,
        temperature=0.5,
    )


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[VOX Daily Top 10] Building snapshot for {today}...")

    snapshot = build_snapshot(limit=100)
    save_cache(today, {"snapshot": snapshot})
    top10 = snapshot[:10]

    print(f"[VOX Daily Top 10] Calling Claude Sonnet 5 for top 10...")
    analysis = daily_analysis(top10)

    output = {
        "generated": datetime.now().isoformat(),
        "type": "daily_top10",
        "model": analysis["model"],
        "cost_usd": analysis["cost_usd"],
        "prompt_tokens": analysis["prompt_tokens"],
        "completion_tokens": analysis["completion_tokens"],
        "top10": top10,
        "analysis": analysis["content"],
    }

    out_path = OUTPUT_DIR / f"vox_daily_top10_{today}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"[VOX Daily Top 10] Cost: ${analysis['cost_usd']:.6f}")
    print(f"[VOX Daily Top 10] Saved to: {out_path}")
    print("\n" + "=" * 60)
    print(analysis["content"])
    print("=" * 60)


if __name__ == "__main__":
    main()
