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
OUT = OBS / "K3-Advisor-LATEST.md"  # cron snip path (k3 only)
ARCH = OBS / "k3-archive"
KIMI_URL = "https://api.kimi.com/coding/v1/chat/completions"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "k3"  # default cron model id

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

SYSTEM_PROMPT = (
    "You are VOX's senior portfolio advisor (soft layer only). "
    "Critique grades, state hypotheses+kill criteria, agree/disagree with Ops Bucket A/B, "
    "list blind risks. Never claim to execute trades. Never invent prices. "
    "Grades are hygiene not buy signals — OKLO-class low grade is NOT auto-sell. "
    "Prefer NEW names over adding to winners. Anti-chase. Multi-broker never a sell reason. "
    "Energy structure gap matters. Ops Card is SSOT for actions — you critique only. "
    "Be direct, numeric, falsifiable. Max ~900 words. Markdown."
)

# Bakeoff 2026-07-20: Sonnet5 > k3 > GLM5.2 for hard critique; k3 stays cron default.
ADVISOR_MODELS = {
    "k3": {
        "label": "Kimi K3",
        "path": "kimi",
        "model": "k3",
        "out": "K3-Advisor-LATEST.md",
        "arch_prefix": "K3-Advisor",
        "role": "cron_default",
    },
    "sonnet5": {
        "label": "Claude Sonnet 5",
        "path": "openrouter",
        "model": "anthropic/claude-sonnet-5",
        "out": "Sonnet5-Advisor-LATEST.md",
        "arch_prefix": "Sonnet5-Advisor",
        "role": "on_demand_best",
    },
    "glm52": {
        "label": "GLM 5.2",
        "path": "openrouter",
        "model": "z-ai/glm-5.2",
        "out": "GLM52-Advisor-LATEST.md",
        "arch_prefix": "GLM52-Advisor",
        "role": "draft_only",
    },
}


def call_k3(prompt: str) -> tuple:
    key = os.environ.get("KIMI_API_KEY") or ""
    if not key:
        raise RuntimeError("KIMI_API_KEY missing — Kimi Coding subscription required")

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
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
        content = (msg.get("reasoning_content") or "").strip() or "_Empty K3 content_"
    usage = data.get("usage") or {}
    usage["_provider"] = "kimi-coding"
    usage["_model"] = data.get("model") or MODEL
    return content, usage


def call_openrouter(model: str, prompt: str, temperature: float = 0.3) -> tuple:
    """On-demand hard critique (Sonnet 5) or draft (GLM). Never cron SSOT."""
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY missing")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4000,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        OR_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://vox.local",
            "X-Title": "VOX Soft Advisor",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    content = (msg.get("content") or "").strip() or "_Empty OpenRouter content_"
    usage = data.get("usage") or {}
    usage["_provider"] = "openrouter"
    usage["_model"] = data.get("model") or model
    return content, usage


def call_advisor(model_key: str, prompt: str) -> tuple:
    cfg = ADVISOR_MODELS[model_key]
    if cfg["path"] == "kimi":
        try:
            return call_k3(prompt)
        except Exception as e:
            # Kimi coding API intermittent 403 in headless cron — soft fallback
            # DeepSeek is batch workhorse; never SSOT. Label output clearly.
            analysis, usage = call_openrouter(
                os.environ.get("VOX_K3_FALLBACK_MODEL", "deepseek/deepseek-chat"),
                prompt,
                temperature=0.3,
            )
            usage = dict(usage or {})
            usage["_fallback_from"] = f"kimi_failed:{e}"
            usage["_provider"] = "openrouter-fallback"
            header = (
                f"_⚠️ Kimi k3 unavailable (`{e}`). Soft fallback via OpenRouter "
                f"`{usage.get('_model') or 'deepseek'}`. Still **not SSOT**._\n\n"
            )
            return header + analysis, usage
    return call_openrouter(cfg["model"], prompt)


def write_advisor_output(
    model_key: str, ctx: Dict[str, Any], analysis: str, usage: dict
) -> Path:
    cfg = ADVISOR_MODELS[model_key]
    now = datetime.now(timezone.utc)
    header = [
        f"# {cfg['label']} Advisor — {now.strftime('%Y-%m-%d')}",
        "",
        f"_Generated {ctx['asof']} · model **{cfg['model']}** · "
        f"{'Kimi Coding' if cfg['path']=='kimi' else 'OpenRouter'} · **soft only**_",
        f"_AUM ~${ctx['aum_usd']:,.0f} · role={cfg['role']} · usage={usage}_",
        "",
        "> Does **not** override Ops Card Decision Object. Hygiene grades ≠ auto-trade.",
        "> Bakeoff 2026-07-20: Sonnet5 best hard critique; k3 cron default; GLM draft-only.",
        "",
    ]
    text = "\n".join(header) + analysis.strip() + "\n"
    OBS.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    out_path = OBS / cfg["out"]
    out_path.write_text(text)
    (ARCH / f"{cfg['arch_prefix']}-{now.strftime('%Y-%m-%d')}.md").write_text(text)
    # Unified pointer for latest any-model run (not Ops snip — k3 LATEST stays cron snip)
    (OBS / "Advisor-LATEST.md").write_text(text)
    return out_path


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
    import argparse

    ap = argparse.ArgumentParser(description="VOX soft advisor (never SSOT)")
    ap.add_argument(
        "--model",
        default="k3",
        choices=["k3", "sonnet5", "glm52", "all"],
        help="k3=cron default; sonnet5=best hard critique; glm52=draft; all=run three",
    )
    args = ap.parse_args()

    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    ctx = load_context(cur)
    conn.close()
    prompt = build_prompt(ctx)

    keys = list(ADVISOR_MODELS.keys()) if args.model == "all" else [args.model]
    fails = 0
    for mk in keys:
        cfg = ADVISOR_MODELS[mk]
        try:
            analysis, usage = call_advisor(mk, prompt)
            out = write_advisor_output(mk, ctx, analysis, usage)
            print(f"🧠 {cfg['label']} · {cfg['model']} · AUM ${ctx['aum_usd']:,.0f}")
            one = ""
            for ln in analysis.splitlines():
                if "one-liner" in ln.lower() or ln.startswith("## 6"):
                    one = ln
                elif one and ln.strip() and not ln.startswith("#"):
                    print(f"  {ln.strip()[:200]}")
                    break
            print(f"Full: {out}")
            if usage:
                print(f"tokens: {usage}")
            if "failed:" in analysis.lower() or analysis.startswith("_Empty"):
                fails += 1
        except Exception as e:
            fails += 1
            print(f"❌ {cfg['label']} failed: {e}")
            # still write error stub for cron visibility on k3
            if mk == "k3":
                write_advisor_output(mk, ctx, f"_K3 advisor failed: {e}_", {})
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
