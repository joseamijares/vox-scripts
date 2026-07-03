#!/usr/bin/env python3
"""
VOX Sonnet 5 Verification — Final review of cron consolidation and fixes.
Collects state metadata and asks Sonnet 5 for an independent verification.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import json
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_utils as vu

HERMES_HOME = Path.home() / ".hermes"
SCRIPT_DIR = HERMES_HOME / "scripts"


def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def collect_state():
    state = {
        "timestamp": datetime.now().isoformat(),
        "cron_summary": run_cmd("python3 ~/.hermes/scripts/vox_cron/vox_cron_status_monitor.py"),
        "git_log": run_cmd("cd ~/.hermes/scripts && git log --oneline -5"),
        "git_status": run_cmd("cd ~/.hermes/scripts && git status --short"),
        "table_counts": vu.query_db("""
            SELECT 'compounding_projections' as tbl, COUNT(*) as n FROM compounding_projections
            UNION ALL SELECT 'portfolio_goals', COUNT(*) FROM portfolio_goals
            UNION ALL SELECT 'top_opportunities', COUNT(*) FROM top_opportunities
            UNION ALL SELECT 'sector_rotation', COUNT(*) FROM sector_rotation
            UNION ALL SELECT 'sp500_sector_leaders', COUNT(*) FROM sp500_sector_leaders
            UNION ALL SELECT 'macro_signals', COUNT(*) FROM macro_signals
            UNION ALL SELECT 'macro_indicators', COUNT(*) FROM macro_indicators
            UNION ALL SELECT 'discovery_queue', COUNT(*) FROM discovery_queue
            UNION ALL SELECT 'discovery_history', COUNT(*) FROM discovery_history
            UNION ALL SELECT 'trader_alerts', COUNT(*) FROM trader_alerts
            UNION ALL SELECT 'pattern_alerts', COUNT(*) FROM pattern_alerts
            UNION ALL SELECT 'insider_trades', COUNT(*) FROM insider_trades
            UNION ALL SELECT 'vox_llm_costs', COUNT(*) FROM vox_llm_costs
            UNION ALL SELECT 'council_deliberations', COUNT(*) FROM council_deliberations
            UNION ALL SELECT 'grade_alerts', COUNT(*) FROM grade_alerts
            UNION ALL SELECT 'theme_alignment', COUNT(*) FROM theme_alignment
            UNION ALL SELECT 'sector_opportunities', COUNT(*) FROM sector_opportunities
            UNION ALL SELECT 'market_regime', COUNT(*) FROM market_regime
            UNION ALL SELECT 'earnings_calendar', COUNT(*) FROM earnings_calendar
            UNION ALL SELECT 'vox_grades', COUNT(*) FROM vox_grades
        """),
        "stale_grades": vu.query_db("SELECT COUNT(DISTINCT ticker) FROM vox_grades WHERE generated_at < NOW() - INTERVAL '7 days'"),
        "recent_costs": vu.query_db("SELECT model, COUNT(*), SUM(total_cost) FROM vox_llm_costs GROUP BY model"),
    }
    return state


def main():
    print("🔍 Collecting VOX state for Sonnet 5 verification...")
    state = collect_state()

    system_prompt = "You are an expert DevOps/SRE auditor reviewing a VOX trading cron-fleet consolidation. Be concise, factual, and flag any risks."
    user_prompt = f"""Review the following VOX system state and verify that the work is complete, correct, and safe.

CONTEXT:
- The user asked to consolidate a VOX cron fleet from ~59 to ~33 active crons by merging redundant crons into 6 unified engines, fix a cron monitor, refresh stale grades, add OpenRouter cost tracking, replace earnings-tracker mock data with Yahoo Finance, and verify with Sonnet 5.
- 1Password CLI is broken, so secrets still fall back to ~/.hermes/.env.

STATE:
```json
{json.dumps(state, indent=2, default=str)}
```

Please answer in this format:
1. VERDICT: (PASS / PASS_WITH_NOTES / FAIL)
2. What is working as expected.
3. Any remaining risks or issues, ranked by severity.
4. Specific recommendations for the next 24 hours.
"""

    result = vu.call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model="anthropic/claude-sonnet-5",
        max_tokens=4000,
        temperature=0.2,
        script_name="vox_sonnet5_verification.py",
        notes="Final verification of VOX cron consolidation",
    )

    print("\n" + "="*70)
    print("SONNET 5 VERDICT")
    print("="*70)
    print(result["content"])
    print("="*70)
    print(f"Tokens: {result['prompt_tokens']} prompt + {result['completion_tokens']} completion = ${result['cost_usd']}")

    out_path = HERMES_HOME / "cron" / "output" / f"vox_sonnet5_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(out_path, "w") as f:
        f.write(f"# VOX Sonnet 5 Verification — {datetime.now().isoformat()}\n\n")
        f.write(result["content"] + "\n\n")
        f.write(f"**Tokens:** {result['prompt_tokens']} prompt + {result['completion_tokens']} completion = ${result['cost_usd']}\n")
        f.write(f"\n```json\n{json.dumps(state, indent=2, default=str)}\n```\n")
    print(f"\n✅ Saved to {out_path}")


if __name__ == '__main__':
    main()
