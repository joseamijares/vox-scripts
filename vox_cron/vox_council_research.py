#!/usr/bin/env python3
"""
VOX AI Council + Daily Research Engine v1.1

Takes the current VOX top-N opportunities and asks multiple models to:
1. Re-grade each ticker independently
2. Give a conviction/action verdict
3. Provide a 1-paragraph bull/bear case

Models used:
- anthropic/claude-sonnet-5  (reasoning, risk-aware)
- deepseek/deepseek-v4-pro   (technical/code/math, deep reasoning)

Results are stored in `council_deliberations` (one row per ticker) and blended into `unified_grades`.

Cost model (OpenRouter, per 1K tokens):
- Sonnet 5: ~$0.003 in / $0.015 out
- DeepSeek v4 Pro: ~$0.000435 in / $0.00087 out

For 10 tickers x 2 models ~ 3K input + 1.5K output per model = ~$0.05-0.10/run.

Usage:
    python vox_council_research.py --top-n 10 --run

Without --run, it prints the prompt and cost estimate and exits (dry-run).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import argparse
import json
import psycopg2
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import vox_utils as vu
from collections import Counter
from datetime import datetime, timezone
from typing import List, Dict

import re


MODELS = [
    {"name": "claude-sonnet-5", "id": "anthropic/claude-sonnet-5", "cost_in": 0.003, "cost_out": 0.015},
    {"name": "deepseek-v4-pro", "id": "deepseek/deepseek-v4-pro", "cost_in": 0.000435, "cost_out": 0.00087},
]

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


def get_top_opportunities(n: int) -> List[Dict]:
    """Load top N non-owned, non-defensive opportunities from unified_grades."""
    defensive = {
        'PG','KO','KMB','CL','CHD','PSA','AVB','PLD','FRT','SPG','EXR','KIM','INVH','IFF','TKO','NTRS','TROW','AFL','ECL','MLM','MTB','SNDK','KEY','PPG','KVUE','HST','RF','FITB','MKC','STLD','NUE','SPGI','BAC','C','LLY','PM','JNJ','CPB','DOC','AIZ','BF-B','REG','HBAN','CFG','ABBV','VMC','GL','UDR','SYY','MOG-A','NAFTRAC','NAFTRAC ISHRS','GBM O','XLU','XLRE','VZ','T','MO','PEP','WMT','COST','GIS','K','UL'
    }
    conn = connect()
    cur = conn.cursor()

    # Owned positions
    cur.execute("SELECT DISTINCT ticker FROM positions WHERE shares > 0")
    owned = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT DISTINCT ticker FROM broker_positions WHERE shares > 0")
    owned |= {r[0] for r in cur.fetchall()}

    exclude = list(defensive | owned)

    cur.execute("""
        WITH latest_prices AS (
            SELECT DISTINCT ON (ticker) ticker, current_price
            FROM vox_grades
            ORDER BY ticker, generated_at DESC
        )
        SELECT u.ticker, u.unified_grade, u.action, u.vox_grade, u.sp500_grade, u.trade_grade, u.tech_score, COALESCE(lp.current_price, 0) as current_price
        FROM unified_grades u
        LEFT JOIN latest_prices lp ON lp.ticker = u.ticker
        WHERE u.ticker != ALL(%s)
          AND COALESCE(lp.current_price, 0) > 0
        ORDER BY u.unified_grade DESC
        LIMIT %s
    """, (exclude, n))

    rows = []
    for r in cur.fetchall():
        rows.append({
            "ticker": r[0],
            "unified_grade": float(r[1]) if r[1] else 0,
            "action": r[2] or "HOLD",
            "vox_grade": float(r[3]) if r[3] else 0,
            "sp500_grade": float(r[4]) if r[4] else 0,
            "trade_grade": float(r[5]) if r[5] else 0,
            "tech_score": float(r[6]) if r[6] else 0,
            "price": float(r[7]) if r[7] else 0,
        })

    conn.close()
    return rows


def build_prompt(tickers: List[Dict]) -> str:
    lines = [
        "You are an elite growth-stock analyst for an aggressive investor targeting 25-50% yearly returns.",
        "The user rejects defensive stocks (utilities, REITs, consumer staples, telcos) and wants hybrid quality + aggressive plays across ALL sectors.",
        "",
        "Current VOX top opportunities (grade 0-100, price $USD):",
    ]
    for t in tickers:
        lines.append(f"- {t['ticker']}: price ${t['price']:.2f}, VOX unified grade {t['unified_grade']:.0f}, action {t['action']}, supporting grades vox={t['vox_grade']:.0f} sp500={t['sp500_grade']:.0f} trade={t['trade_grade']:.0f} tech={t['tech_score']:.0f}")
    lines.extend([
        "",
        "For EACH ticker, produce EXACTLY this JSON format:",
        '{"ticker": "SYMBOL", "model_grade": 0-100, "action": "STRONG_BUY|BUY|ACCUMULATE|HOLD|SELL", "thesis": "1-2 sentence bull/bear case", "risk_flag": "none|binary|macro|liquidity|regulatory"}',
        "",
        "Return a JSON array of these objects. No extra text outside the JSON array. Be decisive — grades should range widely (40-85), not cluster near 60.",
    ])
    return "\n".join(lines)


import re


def _extract_json_objects(text: str) -> List[Dict]:
    """Extract all complete JSON objects from text using brace counting. Tolerates truncation."""
    objects = []
    i = 0
    n = len(text)
    while i < n:
        # Find next opening brace
        while i < n and text[i] != '{':
            i += 1
        if i >= n:
            break
        start = i
        depth = 0
        in_string = False
        escape = False
        while i < n:
            c = text[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[start:i+1])
                            if isinstance(obj, dict):
                                objects.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i += 1
                        break
            i += 1
        else:
            # Reached end without closing brace - truncated object, ignore
            break
    return objects


def _extract_json_array(text: str) -> List[Dict]:
    """Extract JSON verdicts from model output. Tolerates markdown fences, surrounding text, and truncation."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
    # Try the whole text as a JSON array first
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [o for o in obj if isinstance(o, dict)]
        if isinstance(obj, dict):
            return [obj]
    except json.JSONDecodeError:
        pass
    # Extract complete objects individually (handles truncation)
    objects = _extract_json_objects(text)
    if objects:
        return objects
    raise ValueError(f"Could not parse JSON objects from: {text[:200]}...")


def call_openrouter(model_id: str, prompt: str) -> List[Dict]:
    result = vu.call_openrouter(
        system_prompt="",
        user_prompt=prompt,
        model=model_id,
        max_tokens=4096,
        temperature=0.4,
        script_name="vox_council_research.py",
        notes=f"AI Council call via model {model_id}",
    )
    content = result.get("content", "")
    return _extract_json_array(content)


def compute_consensus(votes: List[str]) -> tuple:
    """Return (consensus_action, consensus_pct) based on action votes."""
    if not votes:
        return "HOLD", 0.0
    c = Counter(votes)
    most_common, count = c.most_common(1)[0]
    pct = (count / len(votes)) * 100
    return most_common, round(pct, 1)


def action_rank(action: str) -> int:
    return {
        "STRONG_BUY": 4,
        "BUY": 3,
        "ACCUMULATE": 2,
        "HOLD": 1,
        "SELL": 0,
    }.get(action.upper(), 1)


def save_deliberations(tickers: List[Dict], verdicts_by_model: Dict[str, List[Dict]]):
    """Store one row per ticker into the existing council_deliberations table."""
    conn = connect()
    cur = conn.cursor()

    for t in tickers:
        ticker = t["ticker"]
        deliberations = []
        votes = []
        risk_veto = False
        risk_veto_reasons = []
        avg_model_grade = 0.0
        count = 0

        for model_name, responses in verdicts_by_model.items():
            for r in responses:
                if r.get("ticker") == ticker:
                    deliberations.append({
                        "model": model_name,
                        "model_grade": r.get("model_grade"),
                        "action": r.get("action"),
                        "thesis": r.get("thesis"),
                        "risk_flag": r.get("risk_flag"),
                    })
                    votes.append(r.get("action", "HOLD"))
                    flag = (r.get("risk_flag") or "").lower()
                    if flag in ("regulatory", "binary", "liquidity"):
                        risk_veto = True
                        risk_veto_reasons.append(f"{model_name}: {flag}")
                    avg_model_grade += float(r.get("model_grade", 0) or 0)
                    count += 1

        consensus, consensus_pct = compute_consensus(votes)
        if count:
            avg_model_grade = round(avg_model_grade / count, 2)

        # Final action: consensus, but downgrade by one step if risk veto exists
        if risk_veto and action_rank(consensus) > action_rank("HOLD"):
            if consensus.upper() == "STRONG_BUY":
                final_action = "BUY"
            elif consensus.upper() == "BUY":
                final_action = "ACCUMULATE"
            else:
                final_action = "HOLD"
        else:
            final_action = consensus

        risk_veto_reason = "; ".join(risk_veto_reasons) if risk_veto else None

        cur.execute("""
            INSERT INTO council_deliberations
                (ticker, timestamp, consensus, consensus_pct, votes, deliberations, risk_veto, risk_veto_reason, final_action)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s)
        """, (
            ticker, consensus, consensus_pct, json.dumps(votes), json.dumps(deliberations),
            risk_veto, risk_veto_reason, final_action
        ))

    conn.commit()
    conn.close()


def blend_into_unified(tickers: List[Dict], verdicts_by_model: Dict[str, List[Dict]]):
    """Council grades are advisory only — do NOT overwrite unified_grades."""
    return


def format_summary(tickers: List[Dict], verdicts_by_model: Dict[str, List[Dict]]) -> str:
    """Return a Telegram-friendly summary of the council verdicts."""
    lines = ["🏛️ *VOX AI COUNCIL — Daily Verdicts*", ""]
    for t in tickers:
        ticker = t["ticker"]
        votes = []
        grades = []
        theses = []
        flags = []
        for model_name, responses in verdicts_by_model.items():
            for r in responses:
                if r.get("ticker") == ticker:
                    votes.append(r.get("action", "HOLD"))
                    grades.append(float(r.get("model_grade", 0) or 0))
                    theses.append(f"{model_name}: {r.get('thesis', '')}")
                    risk_flag = r.get("risk_flag") or "none"
                    if risk_flag.lower() != "none":
                        flags.append(f"{model_name} {risk_flag}")
        consensus, consensus_pct = compute_consensus(votes)
        avg_grade = round(sum(grades) / len(grades), 1) if grades else 0
        final = consensus
        if flags and action_rank(consensus) > action_rank("HOLD"):
            final = "ACCUMULATE" if consensus.upper() == "BUY" else "HOLD"
        lines.append(f"*{ticker}* — grade {avg_grade} → *{final}* ({consensus_pct:.0f}% agree)")
        if flags:
            lines.append(f"⚠️ Risk flags: {', '.join(flags)}")
        lines.append(f"💡 {theses[0]}")
        if len(theses) > 1:
            lines.append(f"💡 {theses[1]}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="VOX AI Council + Daily Research")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--run", action="store_true", help="Actually call models (costs money)")
    parser.add_argument("--models", nargs="+", default=[m["id"] for m in MODELS], help="Override model IDs")
    args = parser.parse_args()

    tickers = get_top_opportunities(args.top_n)
    if not tickers:
        print("No opportunities found.")
        return 1

    prompt = build_prompt(tickers)
    estimated_input_tokens = len(prompt) // 4
    estimated_output_tokens = 200 * len(tickers) * len(args.models)
    cost = sum(
        (estimated_input_tokens / 1000) * m["cost_in"] + (estimated_output_tokens / len(args.models) / 1000) * m["cost_out"]
        for m in MODELS if m["id"] in args.models
    )

    print(f"VOX Council Research: {len(tickers)} tickers x {len(args.models)} models")
    print(f"Estimated input tokens: {estimated_input_tokens}, output tokens: {estimated_output_tokens}")
    print(f"Estimated OpenRouter cost: ${cost:.4f}")
    print("")
    print("=== PROMPT ===")
    print(prompt)
    print("=== END PROMPT ===")

    if not args.run:
        print("\nDry-run mode. Add --run to execute (requires OPENROUTER_API_KEY in env).")
        return 0

    verdicts_by_model = {}
    for model in MODELS:
        if model["id"] not in args.models:
            continue
        print(f"\nCalling {model['name']} ({model['id']})...")
        try:
            responses = call_openrouter(model["id"], prompt)
            verdicts_by_model[model["name"]] = responses
            print(f"  Got {len(responses)} verdicts")
        except Exception as e:
            print(f"  ERROR: {e}")

    if verdicts_by_model:
        try:
            save_deliberations(tickers, verdicts_by_model)
            blend_into_unified(tickers, verdicts_by_model)
            summary = format_summary(tickers, verdicts_by_model)
            print("\n" + summary)
            print("\nCouncil verdicts saved and blended into unified_grades.")
        except Exception as e:
            print(f"\nERROR saving/blending: {e}")
    else:
        print("\nNo model responses received. Nothing saved.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
