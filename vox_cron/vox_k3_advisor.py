#!/usr/bin/env python3
"""
VOX Kimi K3 Advisor layer (soft only).

- Provider: Kimi Coding API (KIMI_API_KEY) — NOT OpenRouter
- Model: k3
- Role: grade audit, hypotheses, agree/disagree with Ops A/B, blind risks
- Does NOT: set prices, auto-trade, override Decision Object

Writes:
  Obsidian memory/brain/K3-Advisor-LATEST.md
  + dated archive

Usage:
  python3 vox_cron/vox_k3_advisor.py
  python3 vox.py advisor
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

from psycopg2.extras import RealDictCursor

from vox_pricing_refresh import connect
from vox_outside_ideas import ret_map, load_fmp_scores

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT = OBS / "K3-Advisor-LATEST.md"
ARCH = OBS / "k3-archive"
KIMI_URL = "https://api.kimi.com/coding/v1/chat/completions"
MODEL = "k3"

CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX",
    "DOT", "BONK", "PENGU", "VAULTA", "VANA", "MORPHO",
}


def load_context(cur) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT UPPER(ticker) t,
               COALESCE(live_value_usd, live_value, 0)::float v,
               live_price::float px,
               day_chg_pct::float daychg,
               grade, sector, brokers
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 100
        ORDER BY v DESC
        """
    )
    book = [dict(r) for r in cur.fetchall()]
    aum = sum(r["v"] for r in book) or 1.0

    cur.execute(
        """
        SELECT DISTINCT ON (ticker)
          ticker, vox_grade, action, technical_score, fundamental_score,
          macro_score, sentiment_score
        FROM vox_grades
        ORDER BY ticker, generated_at DESC
        """
    )
    grades = {r["ticker"].upper(): dict(r) for r in cur.fetchall()}
    fmp = load_fmp_scores(cur)
    r5 = ret_map(cur, 5)
    r63 = ret_map(cur, 63)

    mat = []
    for r in book:
        t = r["t"]
        if t in ("MIRROR_TOTAL", "CASH"):
            continue
        g = grades.get(t, {})
        w = 100.0 * r["v"] / aum
        if w < 1.0 and r["v"] < 1500:
            continue
        mat.append(
            {
                "ticker": t,
                "weight_pct": round(w, 2),
                "value_usd": round(r["v"], 0),
                "price": r["px"],
                "day_chg_pct": r["daychg"],
                "vox_grade": g.get("vox_grade"),
                "action": g.get("action"),
                "T": g.get("technical_score"),
                "F": g.get("fundamental_score"),
                "fmp_fund": fmp.get(t),
                "ret_1w": None if r5.get(t) is None else round(r5[t], 1),
                "ret_3m": None if r63.get(t) is None else round(r63[t], 1),
                "sector": r.get("sector"),
            }
        )

    sec: Dict[str, float] = defaultdict(float)
    for r in book:
        t = r["t"]
        w = 100.0 * r["v"] / aum
        if t in CRYPTO:
            sec["Crypto"] += w
        elif t in ("VOO", "QQQ", "VTI", "SPY"):
            sec["Index"] += w
        else:
            sec[r.get("sector") or "Unknown"] += w

    ops_snip = ""
    ops_path = OBS / "Daily-Ops-LATEST.md"
    if ops_path.exists():
        ops_snip = ops_path.read_text(errors="replace")[:3500]

    outside_snip = ""
    out_path = OBS / "Outside-Ideas-LATEST.md"
    if out_path.exists():
        outside_snip = out_path.read_text(errors="replace")[:2000]

    return {
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "aum_usd": round(aum, 0),
        "sleeves": dict(sorted(sec.items(), key=lambda x: -x[1])),
        "positions": mat[:35],
        "ops_card_snip": ops_snip,
        "outside_snip": outside_snip,
        "policy": {
            "grades_hygiene_only": True,
            "prefer_new_names": True,
            "anti_chase": True,
            "ops_is_ssot": True,
            "advisor_soft_only": True,
        },
    }


def call_k3(prompt: str) -> tuple:
    key = os.environ.get("KIMI_API_KEY") or ""
    if not key:
        raise RuntimeError("KIMI_API_KEY missing — Kimi Coding subscription required")

    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are VOX's senior portfolio advisor (Kimi K3). "
                    "Soft layer only: critique grades, state hypotheses+kill criteria, "
                    "agree/disagree with Ops Bucket A/B, list blind risks. "
                    "Never claim to execute trades. Never invent prices. "
                    "Grades are hygiene not buy signals. Be direct, numeric, falsifiable. "
                    "Max ~800 words. Markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4000,
        "temperature": 1,  # k3 requires temperature=1
    }
    req = urllib.request.Request(
        KIMI_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        # some responses are reasoning-heavy; try refusal fields
        content = (msg.get("reasoning_content") or "").strip() or "_Empty K3 content_"
    usage = data.get("usage") or {}
    return content, usage


def build_prompt(ctx: Dict[str, Any]) -> str:
    pos_lines = []
    for m in ctx["positions"]:
        pos_lines.append(
            f"{m['ticker']:8} w={m['weight_pct']:5.1f}% ${m['value_usd']:,.0f} "
            f"g={m['vox_grade']} {m['action']} T={m['T']} F={m['F']} "
            f"fmp={m['fmp_fund']} 1w={m['ret_1w']} 3m={m['ret_3m']} day={m['day_chg_pct']}"
        )
    return f"""VOX advisor pass — soft only. Ops Card is SSOT for actions.

AUM ${ctx['aum_usd']:,.0f} · asof {ctx['asof']}
SLEEVES: {json.dumps(ctx['sleeves'])}

POLICY: grades=hygiene; prefer NEW names; anti-chase; energy gap matters; alts trim; you do not execute.

MATERIAL POSITIONS:
{chr(10).join(pos_lines)}

--- OPS CARD (snip) ---
{ctx['ops_card_snip'][:3000]}

--- OUTSIDE IDEAS (snip) ---
{ctx['outside_snip'][:1500]}

Write exactly these sections:
## 1) Grade audit (misleading vs coherent) — top 10 names
## 2) Hypotheses + kill criteria — book + top held risks
## 3) Ops A/B critique — agree/disagree with each Do-today / Bucket item
## 4) Buy ranking (this book only) — top 4 max, new-name bias
## 5) Blind risks (3 bullets)
## 6) Advisor one-liner (what matters this week)
"""


def main() -> int:
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    ctx = load_context(cur)
    conn.close()

    try:
        analysis, usage = call_k3(build_prompt(ctx))
    except Exception as e:
        analysis = f"_K3 advisor failed: {e}_"
        usage = {}

    now = datetime.now(timezone.utc)
    header = [
        f"# K3 Advisor — {now.strftime('%Y-%m-%d')}",
        "",
        f"_Generated {ctx['asof']} · model **{MODEL}** · Kimi Coding API · **soft only**_",
        f"_AUM ~${ctx['aum_usd']:,.0f} · usage={usage}_",
        "",
        "> Does **not** override Ops Card Decision Object. Hygiene grades ≠ auto-trade.",
        "",
    ]
    text = "\n".join(header) + analysis.strip() + "\n"

    OBS.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    (ARCH / f"K3-Advisor-{now.strftime('%Y-%m-%d')}.md").write_text(text)

    # short stdout for cron
    print(f"🧠 K3 Advisor · {MODEL} · AUM ${ctx['aum_usd']:,.0f}")
    # extract one-liner if present
    one = ""
    for ln in analysis.splitlines():
        if "one-liner" in ln.lower() or ln.startswith("## 6"):
            one = ln
        elif one and ln.strip() and not ln.startswith("#"):
            print(f"  {ln.strip()[:200]}")
            break
    print(f"Full: {OUT}")
    if usage:
        print(f"tokens: {usage}")
    return 0 if "failed:" not in analysis.lower() else 1


if __name__ == "__main__":
    raise SystemExit(main())
