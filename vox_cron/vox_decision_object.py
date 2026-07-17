#!/usr/bin/env python3
"""
VOX Decision Object — Bucket A/B lists + confidence (hard gates only).

Used by Daily Ops Card. Soft intel (X, politicians, signals) does NOT rank.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"


def _parse_outside_tiers(text: str) -> Dict[str, List[Dict[str, str]]]:
    """Extract Tier A/B rows from Outside-Ideas markdown tables."""
    out: Dict[str, List[Dict[str, str]]] = {"A": [], "B": [], "C": []}
    tier = None
    for ln in text.splitlines():
        if "Tier A" in ln:
            tier = "A"
            continue
        if "Tier B" in ln:
            tier = "B"
            continue
        if "Tier C" in ln:
            tier = "C"
            continue
        if not tier or not ln.strip().startswith("|"):
            continue
        if "Ticker" in ln or "---" in ln:
            continue
        cells = [c.strip().replace("**", "") for c in ln.strip().strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        ticker = re.sub(r"[^A-Z0-9.\-]", "", cells[0].upper())
        if not ticker or len(ticker) > 12:
            continue
        grade = cells[1] if len(cells) > 1 else ""
        notes = cells[-1] if len(cells) > 2 else ""
        out[tier].append({"ticker": ticker, "grade": grade, "notes": notes})
    return out


def build_decision_object(
    cur,
    *,
    aum: float,
    energy_w: float,
    crypto_w: float,
    tech_w: float,
    pricing_ok: bool,
    null_asof: List[str],
    stale: List,
    fmp_n: int,
    held_tickers: set,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)

    # Material pricing only — ignore broker shells / spaces / dust crypto aliases
    def _material_null(t: str) -> bool:
        if not t or t in ("MIRROR_TOTAL", "CASH", "GBM O", "BI 270121", "TOTAL"):
            return False
        if " " in t:
            return False
        return True

    null_mat = [t for t in (null_asof or []) if _material_null(t)]
    # dust crypto often unpriced — don't fail the book on them if value-unknown at gate level
    DUST = {"PENGU", "KITE", "MORPHO", "VANA", "BONK", "NIGHT", "NXPC", "KAITO"}
    null_mat = [t for t in null_mat if t not in DUST]

    # Confidence gates
    gates = {
        "book": aum > 1000,
        "pricing": pricing_ok and len(null_mat) <= 5,
        "morning": (OBS / "Morning-Context-LATEST.md").exists()
        and (now.timestamp() - (OBS / "Morning-Context-LATEST.md").stat().st_mtime) < 36 * 3600,
        "outside": (OBS / "Outside-Ideas-LATEST.md").exists()
        and (now.timestamp() - (OBS / "Outside-Ideas-LATEST.md").stat().st_mtime) < 48 * 3600,
        "grades_fresh": False,
    }
    try:
        cur.execute("SELECT MAX(generated_at) AS m FROM vox_grades")
        m = cur.fetchone()
        mx = None
        if m is not None:
            if isinstance(m, dict):
                mx = m.get("m")
            else:
                mx = m[0]
        if mx is not None:
            if getattr(mx, "tzinfo", None) is None:
                mx = mx.replace(tzinfo=timezone.utc)
            age = (now - mx).total_seconds()
            # Naive DB timestamps sometimes look "in the future" vs true UTC — treat as fresh
            if age < 0:
                gates["grades_fresh"] = age > -12 * 3600  # within 12h ahead = clock skew OK
            else:
                gates["grades_fresh"] = age < 7 * 86400
    except Exception as e:
        gates["grades_fresh"] = False

    n_ok = sum(1 for v in gates.values() if v)
    if n_ok >= 4 and gates["book"] and gates["pricing"]:
        conf = "GREEN"
    elif n_ok >= 2 and gates["book"]:
        conf = "YELLOW"
    else:
        conf = "RED"

    # Bucket A — structure / owned hygiene (not a buy-the-universe list)
    bucket_a: List[str] = []
    if energy_w < 1.0:
        bucket_a.append("ADD structure **XLE** (energy sleeve ~0%)")
    if crypto_w >= 10:
        bucket_a.append(f"TRIM crypto sleeve (~{crypto_w:.0f}%) — alts first")
    if tech_w >= 40:
        bucket_a.append(f"NO ADD pure tech beta (tech ~{tech_w:.0f}%) — diversify only")
    # material weak from grades join optional
    try:
        cur.execute(
            """
            WITH latest AS (
              SELECT DISTINCT ON (ticker) ticker, vox_grade, action
              FROM vox_grades ORDER BY ticker, generated_at DESC
            )
            SELECT p.ticker, COALESCE(p.live_value_usd,p.live_value,0)::float v, l.vox_grade, l.action
            FROM positions p
            JOIN latest l ON l.ticker = p.ticker
            WHERE COALESCE(p.live_value_usd,p.live_value,0) > 0
            """
        )
        for r in cur.fetchall():
            t = (r["ticker"] or "").upper()
            if t in ("MIRROR_TOTAL", "CASH") or " " in t:
                continue
            w = 100.0 * float(r["v"] or 0) / max(aum, 1)
            g = r.get("vox_grade")
            act = (r.get("action") or "").upper()
            if w >= 2.5 and g is not None and float(g) < 48 and act == "SELL":
                bucket_a.append(f"REVIEW owned **{t}** hygiene g{int(g)} · {w:.1f}% AUM")
            if len(bucket_a) >= 6:
                break
    except Exception:
        pass
    if not bucket_a:
        bucket_a.append("No material structure action — hold owned quality")

    # Bucket B — outside only, anti-chase already in Outside file
    bucket_b: List[str] = []
    rejects: List[str] = []
    outside_path = OBS / "Outside-Ideas-LATEST.md"
    if outside_path.exists() and conf != "RED":
        tiers = _parse_outside_tiers(outside_path.read_text(errors="replace"))
        for row in tiers.get("A") or []:
            t = row["ticker"]
            if t in held_tickers:
                continue
            note = row.get("notes") or ""
            fund_tag = "fund=unknown" if "unknown" in note.lower() else ""
            bucket_b.append(
                f"**{t}** TierA hygiene {row.get('grade','?')} {fund_tag} — prefer first".strip()
            )
        for row in tiers.get("B") or []:
            t = row["ticker"]
            if t in held_tickers:
                continue
            if len(bucket_b) >= 8:
                break
            # Phase 3: label unknown when FMP missing (default for free tier midcaps)
            bucket_b.append(
                f"**{t}** TierB hygiene {row.get('grade','?')} fund=unknown — small size"
            )
        for row in tiers.get("C") or []:
            t = row["ticker"]
            rejects.append(f"**{t}** TierC chase/extended — dips only or skip")
    elif conf == "RED":
        bucket_b.append("_Confidence RED — no new-name list (fix system)_")
    else:
        bucket_b.append("_No Outside-Ideas-LATEST — run outside job_")

    # Hard structure diversifiers if Outside empty of A and conf ok
    if conf != "RED" and not any("TierA" in x for x in bucket_b):
        for t, why in [
            ("XLE", "structure energy"),
            ("V", "quality diversifier"),
            ("HWM", "industrials diversifier"),
            ("IBKR", "financials diversifier"),
        ]:
            if t not in held_tickers and not any(t in x for x in bucket_b):
                bucket_b.append(f"**{t}** structure/quality ({why})")
            if len([x for x in bucket_b if x.startswith("**")]) >= 6:
                break

    return {
        "confidence": conf,
        "gates": gates,
        "gates_ok": n_ok,
        "gates_total": len(gates),
        "bucket_a": bucket_a[:8],
        "bucket_b": bucket_b[:10],
        "rejects": rejects[:8],
        "fmp_n": fmp_n,
        "fund_note": (
            f"FMP free rows={fmp_n} (mega only; mid often unknown)"
            if fmp_n < 40
            else f"FMP rows={fmp_n}"
        ),
    }


def format_decision_md(d: Dict[str, Any]) -> List[str]:
    conf = d["confidence"]
    emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(conf, "⚪")
    lines = [
        f"## Decision Object {emoji} **{conf}** ({d['gates_ok']}/{d['gates_total']} hard gates)",
        "",
        f"_Hard gates only · grades=hygiene · soft intel does not rank · {d['fund_note']}_",
        "",
        "### Gate status",
    ]
    for k, v in (d.get("gates") or {}).items():
        lines.append(f"- {'✅' if v else '❌'} {k}")
    lines += ["", "### Bucket A — owned / structure (rebalance)"]
    for i, a in enumerate(d.get("bucket_a") or [], 1):
        lines.append(f"{i}. {a}")
    lines += ["", "### Bucket B — new capital (Outside + structure, anti-chase)"]
    if conf == "RED":
        lines.append("_Suppressed — fix RED gates before new buys_")
    else:
        for i, a in enumerate(d.get("bucket_b") or [], 1):
            lines.append(f"{i}. {a}")
    if d.get("rejects"):
        lines += ["", "### Rejects (do not market-buy)"]
        for r in d["rejects"]:
            lines.append(f"- {r}")
    lines.append("")
    return lines
