#!/usr/bin/env python3
"""
VOX GRADE ALERTS — detect grade swings >=20 points vs yesterday.
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

THRESHOLD = 20


def detect_changes(current: list) -> list:
    """Compare today's corrected grades with yesterday's snapshot."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prior = load_cache(yesterday)
    if not prior or "snapshot" not in prior:
        return []

    prior_map = {r["ticker"]: r for r in prior["snapshot"]}
    alerts = []
    for r in current:
        t = r["ticker"]
        if t not in prior_map:
            continue
        old = prior_map[t]["corrected_grade"]
        new = r["corrected_grade"]
        delta = new - old
        if abs(delta) >= THRESHOLD:
            alerts.append({
                "ticker": t,
                "old_grade": old,
                "new_grade": new,
                "delta": delta,
                "fresh_technical": r["fresh_technical"],
                "price": r["price"],
                "1d": r.get("1d"),
                "1w": r.get("1w"),
                "1m": r.get("1m"),
                "action": r["action"],
                "ownership": r["ownership"],
                "direction": "UPGRADE" if delta > 0 else "DOWNGRADE",
            })

    alerts.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return alerts


def alert_summary(alerts: list) -> dict:
    if not alerts:
        return {
            "model": None,
            "cost_usd": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "content": "No grade swings >= 20 points today.",
        }

    system_prompt = """You are a disciplined alert writer for an aggressive growth portfolio. Summarize significant grade swings detected by the VOX grading system. For each alert, explain likely cause and whether action is required. Be concise."""

    user_prompt = f"""VOX grade alerts ({datetime.now().strftime('%Y-%m-%d')}):

{json.dumps(alerts, indent=2)}

OUTPUT:
1. **Critical alerts** (delta >= 25): ticker, direction, new grade, and recommended action.
2. **Watchlist alerts** (delta 20-24): one line each.
3. **Any existing portfolio positions** flagged.
4. **ESTIMATED_COST_LINE** — exactly: `ESTIMATED_COST: $X.XXXX`
"""

    return call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="anthropic/claude-sonnet-5",
        max_tokens=2000,
        temperature=0.3,
    )


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[VOX Grade Alerts] Checking {today}...")

    snapshot = build_snapshot(limit=150)
    save_cache(today, {"snapshot": snapshot})

    alerts = detect_changes(snapshot)
    print(f"[VOX Grade Alerts] {len(alerts)} alerts detected")

    summary = alert_summary(alerts)

    output = {
        "generated": datetime.now().isoformat(),
        "type": "grade_alerts",
        "model": summary["model"] if summary.get("model") else None,
        "cost_usd": summary["cost_usd"],
        "prompt_tokens": summary["prompt_tokens"],
        "completion_tokens": summary["completion_tokens"],
        "alerts": alerts,
        "summary": summary["content"],
    }

    out_path = OUTPUT_DIR / f"vox_grade_alerts_{today}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"[VOX Grade Alerts] Cost: ${summary['cost_usd']:.6f}", file=sys.stderr)
    print(f"[VOX Grade Alerts] Saved to: {out_path}", file=sys.stderr)

    # Only print to stdout when there are actionable alerts (no_agent=True cron delivers stdout as message)
    if alerts:
        print("\n" + "=" * 60)
        print(summary["content"])
        print("=" * 60)
    else:
        # Empty stdout = silent delivery for cron with no_agent=True
        pass


if __name__ == "__main__":
    main()
