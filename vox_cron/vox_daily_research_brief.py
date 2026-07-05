#!/usr/bin/env python3
"""
VOX Daily Research Brief v1.0

Generates a concise morning research brief from VOX data using a cheap
OpenRouter research model. Cost target: < $0.05/day.

Default model: deepseek/deepseek-v4-flash (cheap, good reasoning)
Fallback: deepseek/deepseek-v4-pro (better, still cheap)

Data sources:
- Top 10 unified grades
- 24h grade changes (swings)
- New discovery_queue entries
- Latest market regime snapshot

Usage:
    python vox_daily_research_brief.py [--run] [--model MODEL_ID]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import argparse
import json
import psycopg2
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import vox_utils as vu
from datetime import datetime, timedelta

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
FALLBACK_MODEL = "deepseek/deepseek-v4-pro"

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": "35577",
    "database": "railway",
    "user": "postgres",
    "password": os.environ.get("DB_PASSWORD", ""),
    "sslmode": "require",
}


def connect():
    return psycopg2.connect(**DB)


def gather_context() -> str:
    conn = connect()
    cur = conn.cursor()
    lines = []

    # Top 10 grades
    cur.execute("""
        SELECT u.ticker, u.unified_grade, u.action, u.contradiction
        FROM unified_grades u
        ORDER BY u.unified_grade DESC
        LIMIT 10
    """)
    top = cur.fetchall()
    lines.append("Top 10 Unified Grades:")
    for r in top:
        lines.append(f"  {r[0]}: grade {r[1]}, action {r[2]}")

    # 24h grade swings (largest increases)
    cur.execute("""
        SELECT ticker, unified_grade, computed_at
        FROM unified_grades
        WHERE computed_at > NOW() - INTERVAL '24 hours'
          AND unified_grade >= 60
        ORDER BY unified_grade DESC
        LIMIT 10
    """)
    swings = cur.fetchall()
    if swings:
        lines.append("\n24h High-Grade Tickers:")
        for r in swings:
            lines.append(f"  {r[0]}: {r[1]} (computed {r[2]})")

    # New discoveries
    cur.execute("""
        SELECT ticker, vox_grade, discovery_source, notes
        FROM discovery_queue
        WHERE status = 'pending'
          AND created_at > NOW() - INTERVAL '24 hours'
        ORDER BY vox_grade DESC
        LIMIT 10
    """)
    new = cur.fetchall()
    if new:
        lines.append("\nNew Discoveries (24h):")
        for r in new:
            lines.append(f"  {r[0]}: grade {r[1]}, source {r[2]}, notes {r[3]}")

    # Market regime
    cur.execute("""
        SELECT regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description, created_at
        FROM market_regime
        ORDER BY created_at DESC
        LIMIT 1
    """)
    regime = cur.fetchone()
    if regime:
        lines.append(f"\nMarket Regime: {regime[0]} (confidence {regime[1]}, VIX {regime[2]}, SPY {regime[3]}, yield {regime[4]}, Fed {regime[5]}, {regime[7]})")
        lines.append(f"  Description: {regime[6]}")

    conn.close()
    return "\n".join(lines)


def build_prompt(context: str) -> str:
    return f"""You are a senior research analyst writing a concise morning brief for an aggressive growth investor.

DATA:
{context}

INSTRUCTIONS:
- Write 3-5 bullet points of actionable insight.
- Highlight the 1-2 most compelling tickers and why.
- Note any risks or contradictions.
- Keep it under 200 words. No fluff.
- Tone: sharp, data-driven, aggressive but not reckless.
"""


def summarize(prompt: str, model: str) -> str:
    result = vu.call_openrouter(
        system_prompt="You are a senior research analyst writing a concise morning brief for an aggressive growth investor.",
        user_prompt=prompt,
        model=model,
        max_tokens=600,
        temperature=0.6,
        script_name="vox_daily_research_brief.py",
        notes=f"Daily research brief using {model}",
    )
    return result.get("content", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    context = gather_context()
    prompt = build_prompt(context)
    est_input = len(prompt) // 4
    est_output = 150
    cost_in = 0.00009 if "flash" in args.model else 0.000435
    cost_out = 0.00018 if "flash" in args.model else 0.00087
    est_cost = (est_input / 1000) * cost_in + (est_output / 1000) * cost_out

    print(f"VOX Daily Research Brief")
    print(f"Model: {args.model}")
    print(f"Estimated tokens: {est_input} in / {est_output} out")
    print(f"Estimated cost: ${est_cost:.4f}")
    print("\n=== DATA CONTEXT ===\n")
    print(context)
    print("\n=== END CONTEXT ===")

    if not args.run:
        print("\nDry-run. Add --run to call OpenRouter.")
        return 0

    try:
        brief = summarize(prompt, args.model)
    except Exception as e:
        print(f"ERROR with {args.model}: {e}")
        print(f"Trying fallback {FALLBACK_MODEL}...")
        brief = summarize(prompt, FALLBACK_MODEL)

    print("\n=== DAILY BRIEF ===\n")
    print(brief)

    # Save to file
    out_path = Path.home() / ".hermes" / "scripts" / "vox_cron" / f"daily_brief_{datetime.now().strftime('%Y%m%d')}.txt"
    out_path.write_text(brief)
    print(f"\nSaved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
