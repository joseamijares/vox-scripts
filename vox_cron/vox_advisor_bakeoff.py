#!/usr/bin/env python3
"""VOX Advisor Bakeoff — k3 vs Sonnet 5 vs GLM 5.2 (soft layer only).

Fair test: same context + same prompts → three models → scored rubric.
Does NOT change Ops SSOT or execute trades.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

from psycopg2.extras import RealDictCursor
from vox_k3_advisor import build_prompt, load_context
from vox_pricing_refresh import connect

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT_DIR = OBS / "advisor-bakeoff"
KIMI_URL = "https://api.kimi.com/coding/v1/chat/completions"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = (
    "You are VOX's senior portfolio advisor (soft layer only). "
    "Critique grades, state hypotheses+kill criteria, agree/disagree with Ops Bucket A/B, "
    "list blind risks. Never claim to execute trades. Never invent prices. "
    "Grades are hygiene not buy signals. Prefer NEW names over adding to winners. "
    "Anti-chase. Multi-broker never a sell reason. Energy structure gap matters. "
    "Ops Card is SSOT for actions — you critique only. Be direct, numeric, falsifiable. "
    "Max ~900 words. Markdown."
)

# Specialized mini-tests (same for all models)
MINI_TESTS = {
    "anti_chase": """VOX mini-test ANTI-CHASE (soft only).
Book already has NVDA ~4%, TSLA large, crypto sleeve elevated.
Outside shows ALAB TierC extended and a name up +45% in 3m.
Should we market-buy ALAB or the parabolic name today? Why/why not.
Answer with: ACTION (BUY/SKIP/DIP_ONLY), SIZE, KILL_CRITERIA, 5 bullets max.""",
    "grade_trap": """VOX mini-test GRADE TRAP (soft only).
Hygiene shows VOO g~52 HOLD, OKLO g~27 SELL, NAFTRAC g~57 HOLD with tiny day%.
AUM ~$200k balanced mandate ~20% aim. Multi-broker ownership exists.
For each of VOO / OKLO / NAFTRAC: is grade actionable? What should human do?
Table: ticker | grade_read | mandate_action | why. No invented prices.""",
    "structure": """VOX mini-test STRUCTURE (soft only).
Sleeves: heavy tech/index, crypto elevated, energy ~0%.
Cash limited. Prefer NEW names; structure stubs OK (XLE).
Give top 3 capital uses ranked, with broker-agnostic rationale and what NOT to do.
Max 12 lines.""",
}


def call_kimi(model: str, user: str, max_tokens: int = 4000) -> Tuple[str, dict]:
    key = os.environ.get("KIMI_API_KEY") or ""
    if not key:
        raise RuntimeError("KIMI_API_KEY missing")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 1,  # k3 requires 1
    }
    req = urllib.request.Request(
        KIMI_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    lat = time.time() - t0
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        content = (msg.get("reasoning_content") or "").strip() or "_empty_"
    usage = data.get("usage") or {}
    usage["_latency_s"] = round(lat, 2)
    usage["_model_resolved"] = data.get("model") or model
    return content, usage


def call_openrouter(model: str, user: str, max_tokens: int = 4000) -> Tuple[str, dict]:
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY missing")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        OR_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://vox.local",
            "X-Title": "VOX Advisor Bakeoff",
        },
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    lat = time.time() - t0
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    content = (msg.get("content") or "").strip() or "_empty_"
    usage = data.get("usage") or {}
    usage["_latency_s"] = round(lat, 2)
    usage["_model_resolved"] = data.get("model") or model
    return content, usage


MODELS = [
    {"id": "k3", "label": "Kimi K3", "path": "kimi", "model": "k3"},
    {
        "id": "sonnet5",
        "label": "Claude Sonnet 5",
        "path": "openrouter",
        "model": "anthropic/claude-sonnet-5",
    },
    {
        "id": "glm52",
        "label": "GLM 5.2",
        "path": "openrouter",
        "model": "z-ai/glm-5.2",
    },
]


def run_model(m: dict, prompt: str) -> dict:
    try:
        if m["path"] == "kimi":
            text, usage = call_kimi(m["model"], prompt)
        else:
            text, usage = call_openrouter(m["model"], prompt)
        return {
            "ok": True,
            "text": text,
            "usage": usage,
            "error": None,
            "chars": len(text),
        }
    except Exception as e:
        return {
            "ok": False,
            "text": f"_ERROR: {e}_",
            "usage": {},
            "error": str(e),
            "chars": 0,
        }


# --- Rubric (deterministic checks + light quality heuristics) ---

def score_output(text: str, test_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    t = text.lower()
    scores = {}
    notes = []

    # 1 Policy: soft only / no execution
    exec_bad = any(
        p in t
        for p in [
            "i bought",
            "order placed",
            "executing now",
            "auto-buy",
            "will purchase for you",
        ]
    )
    scores["policy_soft"] = 0 if exec_bad else 10
    if exec_bad:
        notes.append("claims execution")

    # 2 Anti-chase / ALAB / parabolic
    if test_id == "anti_chase":
        skip_good = any(
            x in t for x in ["skip", "dip_only", "dips only", "do not market", "don't buy", "not buy", "chase"]
        )
        buy_bad = ("action: buy" in t or "action **buy**" in t) and "skip" not in t
        scores["anti_chase"] = 10 if skip_good and not buy_bad else (4 if skip_good else 1)
        if not skip_good:
            notes.append("weak anti-chase")
    else:
        scores["anti_chase"] = None

    # 3 Grade hygiene language
    hyg = any(
        x in t
        for x in [
            "hygiene",
            "not a buy",
            "not auto",
            "not a sell signal",
            "grades are",
            "ranking",
            "not deploy",
        ]
    )
    # VOO should not be automatic sell
    voo_sell = "voo" in t and "sell" in t and "not sell" not in t and "don't sell" not in t
    # crude: if VOO mentioned with sell without hold/protect
    if "voo" in t:
        voo_ok = any(x in t for x in ["hold", "core", "index", "not sell", "keep", "structure"])
        scores["grade_trap"] = 10 if voo_ok else (3 if voo_sell else 6)
    else:
        scores["grade_trap"] = 7 if hyg else 5
    if test_id == "grade_trap" and not hyg:
        notes.append("weak hygiene framing")

    # 4 Structure / energy
    if test_id == "structure":
        energy = any(x in t for x in ["xle", "energy", "0%", "underweight energy"])
        new_pref = any(x in t for x in ["new name", "new ticker", "not add", "prefer new", "outside"])
        scores["structure"] = (5 if energy else 0) + (5 if new_pref else 2)
        if not energy:
            notes.append("missed energy/XLE")
    else:
        energy = "xle" in t or "energy" in t
        scores["structure"] = 8 if energy else 5

    # 5 Falsifiable kill criteria
    kill = any(
        x in t
        for x in [
            "kill",
            "invalidat",
            "stop if",
            "thesis break",
            "exit if",
            "falsif",
            "break if",
        ]
    )
    scores["falsifiable"] = 10 if kill else 3
    if not kill:
        notes.append("no kill/invalidation")

    # 6 Ops SSOT respect
    ops = any(
        x in t
        for x in ["ops", "ssot", "decision object", "agree", "disagree", "bucket"]
    )
    scores["ops_ssot"] = 10 if ops else 4

    # 7 Completeness for main advisor pass
    if test_id == "main":
        secs = sum(
            1
            for s in [
                "grade audit",
                "hypothes",
                "ops a/b",
                "blind",
                "## 1",
                "## 2",
                "## 3",
                "## 4",
            ]
            if s in t
        )
        scores["structure_sections"] = min(10, secs * 2)
    else:
        scores["structure_sections"] = 8 if len(text) > 200 else 3

    # 8 Numeric / book grounded
    book_tickers = [p["ticker"].lower() for p in ctx.get("positions", [])[:15]]
    hits = sum(1 for tk in book_tickers if tk in t)
    scores["book_grounded"] = min(10, hits)
    if hits < 3:
        notes.append("few book tickers")

    # 9 Hallucination guards — invented extreme certainty
    hype = any(
        x in t
        for x in ["guaranteed", "can't lose", "100% sure", "definitely buy now"]
    )
    scores["no_hype"] = 0 if hype else 10

    # 10 Brevity / usable
    n = len(text)
    if n < 200:
        scores["usable_length"] = 3
    elif n < 8000:
        scores["usable_length"] = 10
    else:
        scores["usable_length"] = 6
        notes.append("verbose")

    # aggregate
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    total = round(sum(vals) / max(len(vals), 1), 2)
    return {"scores": scores, "total": total, "notes": notes}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    ctx = load_context(cur)
    conn.close()

    main_prompt = build_prompt(ctx)
    # append required section 4 if missing in template
    if "Blind risks" not in main_prompt:
        main_prompt += "\n## 4) Blind risks — 5 bullets\n## 5) One-line: what Ops gets right / wrong today\n"

    results: Dict[str, Any] = {
        "stamp": stamp,
        "day": day,
        "asof": ctx["asof"],
        "aum": ctx["aum_usd"],
        "sleeves": ctx["sleeves"],
        "models": {},
        "tests": {},
    }

    tests = {"main": main_prompt, **MINI_TESTS}

    for m in MODELS:
        mid = m["id"]
        results["models"][mid] = {"label": m["label"], "api_model": m["model"], "runs": {}}
        print(f"\n=== {m['label']} ({m['model']}) ===")
        for tid, prompt in tests.items():
            print(f"  → {tid} ...", flush=True)
            out = run_model(m, prompt)
            sc = score_output(out["text"], tid, ctx) if out["ok"] else {
                "scores": {},
                "total": 0,
                "notes": [out.get("error") or "fail"],
            }
            results["models"][mid]["runs"][tid] = {
                "ok": out["ok"],
                "chars": out["chars"],
                "usage": out["usage"],
                "error": out["error"],
                "score": sc,
                "text": out["text"],
            }
            print(
                f"     ok={out['ok']} chars={out['chars']} "
                f"score={sc['total']} lat={out['usage'].get('_latency_s')}s"
            )
            time.sleep(0.5)

    # aggregate leaderboard
    board = []
    for mid, md in results["models"].items():
        runs = md["runs"]
        totals = [r["score"]["total"] for r in runs.values() if r.get("ok")]
        avg = round(sum(totals) / max(len(totals), 1), 2) if totals else 0
        main_sc = runs.get("main", {}).get("score", {}).get("total", 0)
        board.append(
            {
                "id": mid,
                "label": md["label"],
                "avg": avg,
                "main": main_sc,
                "n_ok": sum(1 for r in runs.values() if r.get("ok")),
                "lat_main": runs.get("main", {}).get("usage", {}).get("_latency_s"),
            }
        )
    board.sort(key=lambda x: (-x["avg"], -x["main"]))
    results["leaderboard"] = board

    # write JSON full
    jpath = OUT_DIR / f"bakeoff-{stamp}.json"
    jpath.write_text(json.dumps(results, indent=2, default=str))
    (OUT_DIR / "bakeoff-LATEST.json").write_text(jpath.read_text())

    # write markdown report
    lines = [
        f"# VOX Advisor Bakeoff — {day}",
        "",
        f"_Generated {stamp} · soft layer only · Ops remains SSOT_",
        "",
        f"**AUM:** ${ctx['aum_usd']:,.0f} · sleeves: `{json.dumps(ctx['sleeves'])}`",
        "",
        "## Leaderboard (avg rubric 0–10)",
        "",
        "| Rank | Model | Avg | Main pass | OK runs | Latency main |",
        "|-----:|-------|----:|----------:|--------:|-------------:|",
    ]
    for i, b in enumerate(board, 1):
        lines.append(
            f"| {i} | **{b['label']}** | **{b['avg']}** | {b['main']} | "
            f"{b['n_ok']}/4 | {b['lat_main']}s |"
        )

    winner = board[0] if board else None
    lines += [
        "",
        f"## Winner (this run): **{winner['label'] if winner else 'n/a'}**",
        "",
        "### Rubric dimensions",
        "- policy_soft, anti_chase, grade_trap, structure, falsifiable,",
        "  ops_ssot, structure_sections, book_grounded, no_hype, usable_length",
        "",
        "### Validation notes",
        "- Same system prompt + same live book/Ops/Outside context",
        "- K3 via Kimi Coding API (temp=1); Sonnet5 + GLM5.2 via OpenRouter",
        "- Automated rubric is necessary but not sufficient — read samples below",
        "",
    ]

    for tid in tests:
        lines += [f"## Test: `{tid}`", ""]
        for m in MODELS:
            mid = m["id"]
            run = results["models"][mid]["runs"][tid]
            lines.append(f"### {m['label']} — score **{run['score']['total']}**")
            if run["score"].get("notes"):
                lines.append(f"_flags: {', '.join(run['score']['notes'])}_")
            lines.append("")
            lines.append("```")
            # truncate huge
            txt = run["text"][:4500]
            lines.append(txt)
            if len(run["text"]) > 4500:
                lines.append("…[truncated]…")
            lines.append("```")
            lines.append("")

    lines += [
        "## Recommendation for VOX",
        "",
        "1. Keep **Ops Card** as SSOT regardless of winner.",
        "2. Soft advisor cron can use the winner; others optional A/B offline.",
        "3. Re-run bakeoff after major book or policy changes.",
        "",
        f"JSON: `{jpath}`",
        "",
    ]

    md = "\n".join(lines) + "\n"
    md_path = OUT_DIR / f"bakeoff-{stamp}.md"
    md_path.write_text(md)
    (OUT_DIR / "bakeoff-LATEST.md").write_text(md)
    (OBS / "Advisor-Bakeoff-LATEST.md").write_text(md)

    print("\n==== LEADERBOARD ====")
    for i, b in enumerate(board, 1):
        print(f"  {i}. {b['label']}: avg={b['avg']} main={b['main']}")
    print(f"\nWrote {md_path}")
    print(f"LATEST → {OBS / 'Advisor-Bakeoff-LATEST.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
