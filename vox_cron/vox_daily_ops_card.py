#!/usr/bin/env python3
"""
VOX Daily Ops Card — single source of truth for the day.

Aggregates: book · pricing health · big movers · material plan · outside ideas ·
breaking · data warnings. Writes Obsidian + stdout (cron deliver).

Usage:
  python3 vox_cron/vox_daily_ops_card.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import re

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

from vox_decision_object import build_decision_object, format_decision_md

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT = OBS / "Daily-Ops-LATEST.md"
ARCHIVE_DIR = OBS / "ops-archive"
CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX",
    "DOT", "BONK", "PENGU", "VAULTA", "VANA", "MORPHO",
}
MATERIAL_W = 2.5  # % AUM for material sells


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def read_snip(path: Path, n: int = 12) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(errors="replace").splitlines()
    # skip empty / pure headers noise
    body = [ln for ln in lines if ln.strip()]
    return body[:n]


def main():
    now = datetime.now(timezone.utc)
    ct_note = now.strftime("%Y-%m-%d %H:%M UTC")
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ── Book ──
    cur.execute(
        """
        SELECT ticker, shares, avg_cost,
               COALESCE(live_price, 0) live_price,
               COALESCE(live_value_usd, live_value, 0) v,
               grade, council, sector, price_asof, price_source,
               prev_close, day_chg_pct
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        ORDER BY COALESCE(live_value_usd, live_value, 0) DESC
        """
    )
    rows = cur.fetchall()
    aum = sum(float(r["v"] or 0) for r in rows) or 1.0
    npos = len(rows)
    sector_w = defaultdict(float)
    crypto_w = 0.0
    for r in rows:
        t = (r["ticker"] or "").upper()
        w = 100.0 * float(r["v"] or 0) / aum
        sector_w[r.get("sector") or "Unknown"] += w
        if t in CRYPTO:
            crypto_w += w

    tech_w = sum(v for k, v in sector_w.items() if "tech" in (k or "").lower())
    energy_w = sum(v for k, v in sector_w.items() if "energy" in (k or "").lower())

    # ── Pricing health ──
    # Ignore unpriceable junk / broker shells so confidence isn't false YELLOW
    JUNK_ASOF = {
        "MIRROR_TOTAL", "CASH", "GBM O", "BI 270121", "TOTAL",
        # dust / unlisted shells — never gate Ops Card on these
        "VAULTA", "KITE", "FF",
    }
    def _priceable(t: str, v: float = 0.0) -> bool:
        if not t or t in JUNK_ASOF:
            return False
        if " " in t:  # broker note symbols
            return False
        # dust row gate ignore (policy: ignore dust/shells)
        if float(v or 0) < 25:
            return False
        return True

    stale = []
    null_asof = []
    big = []
    for r in rows:
        t = (r["ticker"] or "").upper()
        if not _priceable(t, float(r.get("v") or 0)):
            continue
        asof = r.get("price_asof")
        if asof is None:
            null_asof.append(t)
        else:
            age_h = (now - asof.replace(tzinfo=timezone.utc) if asof.tzinfo is None else now - asof).total_seconds() / 3600
            if age_h > 18:
                stale.append((t, age_h))
        chg = r.get("day_chg_pct")
        if chg is not None and abs(float(chg)) >= 8:
            big.append((t, float(chg), float(r["live_price"] or 0), float(r["v"] or 0)))

    big.sort(key=lambda x: abs(x[1]), reverse=True)

    # ── Material names (weight) ──
    material = []
    for r in rows:
        t = (r["ticker"] or "").upper()
        if t in ("MIRROR_TOTAL", "CASH"):
            continue
        w = 100.0 * float(r["v"] or 0) / aum
        if w >= MATERIAL_W:
            material.append(
                {
                    "ticker": t,
                    "w": w,
                    "v": float(r["v"] or 0),
                    "grade": r.get("grade"),
                    "council": r.get("council"),
                    "day": float(r["day_chg_pct"]) if r.get("day_chg_pct") is not None else None,
                }
            )
    material.sort(key=lambda x: -x["w"])

    # weak material (grade soft)
    weak = [m for m in material if (m["grade"] or 50) < 45]
    junk = []
    for r in rows:
        t = (r["ticker"] or "").upper()
        v = float(r["v"] or 0)
        g = r.get("grade")
        if t in CRYPTO and t not in ("BTC", "ETH"):
            if v >= 200:
                junk.append((t, v, "alt crypto"))
        elif g is not None and g < 40 and v >= 400:
            junk.append((t, v, f"grade {g}"))

    junk.sort(key=lambda x: -x[1])

    # ── FMP coverage ──
    try:
        cur.execute("SELECT COUNT(*) c FROM fmp_fundamentals")
        row = cur.fetchone()
        fmp_n = int(row["c"]) if row else 0
    except Exception:
        fmp_n = 0

    cur.execute("SELECT MAX(date) d FROM price_history")
    ph_row = cur.fetchone() or {}
    ph_max = ph_row.get("d")

    # ── Regime ──
    cur.execute(
        "SELECT regime, confidence, description FROM market_regime ORDER BY created_at DESC LIMIT 1"
    )
    regime = cur.fetchone() or {}

    # ── Files ──
    brain = OBS / "Brain-LATEST.md"
    outside = OBS / "Outside-Ideas-LATEST.md"
    breaking = Path.home() / "Documents/Obsidian/VOX/vox/memory/decisions/Breaking-LATEST.md"
    if not breaking.exists():
        breaking = Path.home() / "Documents/Obsidian/VOX/vox/memory/intel"
        # latest morning
        cands = sorted(breaking.glob("morning-*.md"), reverse=True) if breaking.exists() else []
        breaking = cands[0] if cands else Path("/dev/null")
    top10 = OBS / "FullSystem-Top10-LATEST.md"

    # Outside pick lines
    outside_lines = []
    if outside.exists():
        for ln in outside.read_text(errors="replace").splitlines():
            if any(x in ln for x in ("Tier A", "Tier B", "**", "| ")):
                outside_lines.append(ln.strip())
            if len(outside_lines) >= 10:
                break

    # Breaking first meaningful bullets
    brk_lines = []
    bp = Path.home() / "Documents/Obsidian/VOX/vox/memory/decisions/Breaking-LATEST.md"
    if bp.exists():
        for ln in bp.read_text(errors="replace").splitlines():
            s = ln.strip()
            if s.startswith(("#", ">", "---")):
                continue
            if s:
                brk_lines.append(s)
            if len(brk_lines) >= 6:
                break

    # Top10 first table rows
    t10 = []
    if top10.exists():
        for ln in top10.read_text(errors="replace").splitlines():
            if ln.strip().startswith("|") and "Ticker" not in ln and "---" not in ln:
                t10.append(ln.strip())
            if len(t10) >= 10:
                break

    # ── Actions (rule-based, honest) ──
    actions = []
    if crypto_w >= 10:
        actions.append(
            f"TRIM crypto sleeve (~{crypto_w:.0f}% AUM) — alts first; keep BTC/ETH core only if thesis holds"
        )
    if energy_w < 1:
        actions.append("STRUCTURE: add energy sleeve (XLE) — book nearly 0% energy")
    if junk:
        jn = ", ".join(f"{t} (${v:.0f})" for t, v, _ in junk[:5])
        actions.append(f"CLEANUP junk/weak: {jn}")
    if weak:
        actions.append(
            "REVIEW material weak grades: "
            + ", ".join(f"{m['ticker']} g{m['grade']} {m['w']:.1f}%" for m in weak[:5])
        )
    if big:
        downs = [b for b in big if b[1] <= -8][:4]
        ups = [b for b in big if b[1] >= 8][:3]
        if downs:
            actions.append(
                "EVENT downs (no FOMO reverse): "
                + ", ".join(f"{t} {c:+.0f}%" for t, c, _, __ in downs)
            )
        if ups:
            actions.append(
                "Hot names — do not chase: "
                + ", ".join(f"{t} {c:+.0f}%" for t, c, _, __ in ups)
            )

    # Radar Board → EVENT earnings (held this week)
    radar_path = Path.home() / ".hermes" / "cron" / "output" / "brain" / "RadarBoard-LATEST.json"
    radar = {}
    if radar_path.exists():
        try:
            radar = json.loads(radar_path.read_text())
        except Exception:
            radar = {}
    earn_held = (radar.get("earnings") or {}).get("held") or []
    # Prefer earnings desk if fresher/richer
    desk_path = Path.home() / ".hermes" / "cron" / "output" / "intel" / "EarningsDesk-LATEST.json"
    desk = {}
    if desk_path.exists():
        try:
            desk = json.loads(desk_path.read_text())
        except Exception:
            desk = {}
    if desk.get("held"):
        earn_held = [
            {
                "ticker": r.get("ticker"),
                "date": r.get("date"),
                "status": "REPORTED" if r.get("reported") else "UPCOMING",
                "book_w": r.get("book_w"),
            }
            for r in desk["held"]
        ]
    if earn_held:
        bits = []
        for e in earn_held[:6]:
            st = e.get("status") or ""
            bits.append(f"{e.get('ticker')} {e.get('date')}{('*' if st=='REPORTED' or e.get('reported') else '')}")
        actions.append("EVENT earnings (held): " + ", ".join(bits))
    ai_veto = (radar.get("disruption") or {}).get("outside_veto") or []
    if ai_veto:
        actions.append("AI veto Outside longs: " + ", ".join(ai_veto[:8]))

    # Intel digest headline (soft)
    intel_path = OBS / "Intel-Digest-LATEST.md"
    intel_snip = []
    if intel_path.exists():
        body = [ln for ln in intel_path.read_text(errors="replace").splitlines() if ln.strip()]
        grab = False
        for ln in body:
            if ln.startswith("## Book-relevant"):
                grab = True
                continue
            if grab and ln.startswith("## "):
                break
            if grab and ln.startswith("-"):
                intel_snip.append(ln)
            if len(intel_snip) >= 4:
                break
    if intel_snip:
        # keep actions lean — full section later
        pass

    if t10:
        actions.append("New capital: see **Decision Object Bucket B** below (not stale FullSystem file)")
    if not actions:
        actions.append("No material action — hold quality, skip noise")

    pricing_ok = len(null_asof) <= 5 and len(stale) <= 10
    warnings = []
    if null_asof:
        warnings.append(f"{len(null_asof)} names missing price_asof")
    if stale:
        warnings.append(f"{len(stale)} names price_asof >18h")
    if fmp_n < 30:
        warnings.append(f"FMP fund rows only {fmp_n} (mega-cap free tier)")
    if (regime.get("confidence") or 0) and float(regime.get("confidence") or 0) <= 55:
        warnings.append("Regime table low-info (NEUTRAL/low conf) — ignore for decisions")

    held_tickers = {
        (r["ticker"] or "").upper()
        for r in rows
        if (r["ticker"] or "").upper() not in ("MIRROR_TOTAL", "CASH")
    }
    decision = build_decision_object(
        cur,
        aum=aum,
        energy_w=energy_w,
        crypto_w=crypto_w,
        tech_w=tech_w,
        pricing_ok=pricing_ok,
        null_asof=null_asof,
        stale=stale,
        fmp_n=fmp_n,
        held_tickers=held_tickers,
        now=now,
    )
    try:
        conn.close()
    except Exception:
        pass

    # ── Markdown ──
    conf = decision["confidence"]
    conf_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(conf, "⚪")
    lines = [
        f"# Daily Ops Card — {now.strftime('%Y-%m-%d')}",
        "",
        f"_Generated {ct_note} · **Decision Object SSOT** · not auto-trade_",
        "",
        f"## Snapshot · Confidence {conf_emoji} **{conf}**",
        f"- **AUM:** ${aum:,.0f} · **positions:** {npos}",
        f"- **Tech ~{tech_w:.0f}%** · **Energy ~{energy_w:.0f}%** · **Crypto ~{crypto_w:.0f}%**",
        f"- **Pricing:** {'OK-ish' if pricing_ok else 'NEEDS REFRESH'} · history max `{ph_max}` · FMP rows `{fmp_n}`",
        f"- **Regime (ignore if mushy):** {regime.get('regime')} ({regime.get('confidence')})",
        "",
        "## Do today (max 5)",
    ]
    for i, a in enumerate(actions[:5], 1):
        lines.append(f"{i}. {a}")

    lines += [""] + format_decision_md(decision)
    lines += ["", "## Big day moves (|%| ≥ 8)"]
    if not big:
        lines.append("_None material in book_")
    else:
        for t, c, px, v in big[:12]:
            lines.append(f"- **{t}** {c:+.1f}% @ ${px:.2f} · book ${v:,.0f}")

    lines += ["", "## Material weights (≥2.5%)"]
    for m in material[:15]:
        day = f"{m['day']:+.1f}%" if m["day"] is not None else "—"
        lines.append(
            f"- **{m['ticker']}** {m['w']:.1f}% · ${m['v']:,.0f} · g{m['grade'] or '—'} · {m['council'] or '—'} · day {day}"
        )

    lines += ["", "## Outside ideas (file snip)"]
    if outside_lines:
        lines.extend(f"- {ln}" for ln in outside_lines[:8])
    else:
        lines.append("_No Outside-Ideas-LATEST.md_")

    # Radar Board snips (earnings + AI + shorts) — not SSOT
    lines += ["", "## Radar Board (earnings · AI · shorts — not SSOT)"]
    if radar or desk:
        if earn_held:
            lines.append(
                "- **Held earnings:** "
                + ", ".join(
                    f"{e.get('ticker')} {e.get('date')}"
                    + (f" w={e.get('book_w')}" if e.get("book_w") else "")
                    for e in earn_held[:8]
                )
            )
        earn_w = (radar.get("earnings") or {}).get("watch") or []
        if earn_w:
            lines.append(
                "- **Watch earnings:** "
                + ", ".join(f"{e.get('ticker')} {e.get('date')}" for e in earn_w[:6])
            )
        if not earn_held and not earn_w:
            lines.append("- Earnings window: _none detected / calendar sparse_")
        if ai_veto:
            lines.append("- **AI veto Outside longs:** " + ", ".join(ai_veto[:10]))
        shorts = ((radar.get("shorts") or {}).get("candidates") or [])[:5]
        if shorts:
            lines.append(
                "- **Short candidates (cap-aware):** "
                + ", ".join(f"{s.get('ticker')}({s.get('score')})" for s in shorts)
            )
        lines.append(f"- Full: `{OBS / 'Radar-Board-LATEST.md'}` · `{OBS / 'Earnings-Desk-LATEST.md'}`")
    else:
        lines.append("_No Radar/Earnings desk yet — run intel spine / radar scripts_")

    # Intel digest
    lines += ["", "## Intel digest (soft — not SSOT)"]
    if intel_snip:
        lines.extend(intel_snip[:5])
        lines.append(f"- Full: `{intel_path}`")
    elif intel_path.exists():
        # first bullets anywhere
        body = [ln for ln in intel_path.read_text(errors="replace").splitlines() if ln.startswith("- ")]
        lines.extend(body[:4] or ["_Digest present but empty bullets_"])
        lines.append(f"- Full: `{intel_path}`")
    else:
        lines.append("_No Intel-Digest-LATEST.md — run `vox_intel_ingest` + `vox_intel_distill`_")

    # Morning research pack (06:15)
    morning = OBS / "Morning-Context-LATEST.md"
    morn_lines = []
    if morning.exists():
        body = [ln for ln in morning.read_text(errors="replace").splitlines() if ln.strip()]
        # prefer synthesis section if present
        in_synth = False
        for ln in body:
            if "Analyst synthesis" in ln or "synthesis" in ln.lower() and ln.startswith("#"):
                in_synth = True
                continue
            if in_synth:
                if ln.startswith("## ") and "synthesis" not in ln.lower():
                    break
                morn_lines.append(ln)
            if len(morn_lines) >= 14:
                break
        if not morn_lines:
            # markets table + first bullets
            for ln in body:
                if ln.startswith("| SPY") or ln.startswith("| QQQ") or ln.startswith("| XLE") or ln.startswith("- "):
                    morn_lines.append(ln)
                if len(morn_lines) >= 12:
                    break

    lines += ["", "## Morning research context"]
    if morn_lines:
        lines.extend(morn_lines[:14])
    else:
        lines.append("_No Morning-Context-LATEST.md yet (runs 06:15 CT)_")

    lines += ["", "## Breaking / macro tape"]
    if brk_lines:
        lines.extend(f"- {ln}" for ln in brk_lines[:6])
    else:
        lines.append("_No Breaking-LATEST.md_")

    # K3 soft advisor snip (never SSOT)
    k3_path = OBS / "K3-Advisor-LATEST.md"
    k3_lines = []
    if k3_path.exists():
        age_h = (now.timestamp() - k3_path.stat().st_mtime) / 3600
        body = [ln for ln in k3_path.read_text(errors="replace").splitlines() if ln.strip()]
        # prefer one-liner / section 6 / last bullets
        grab = False
        for ln in body:
            if "one-liner" in ln.lower() or ln.startswith("## 6") or "Blind risks" in ln or ln.startswith("## 5"):
                grab = True
            if grab:
                k3_lines.append(ln)
            if len(k3_lines) >= 12:
                break
        if not k3_lines:
            k3_lines = body[4:14]
        if age_h > 96:
            k3_lines = [f"_Advisor file stale ({age_h:.0f}h) — run `python3 vox.py advisor`_"] + k3_lines[:6]

    lines += ["", "## K3 Advisor (soft — not SSOT)"]
    if k3_lines:
        lines.extend(k3_lines[:12])
    else:
        lines.append("_No K3-Advisor-LATEST.md — run `python3 vox.py advisor` (Kimi Coding k3)_")

    # FullSystem demoted — history only, not SSOT
    lines += [
        "",
        "## Archive note",
        "- FullSystem-Top10 is **not** decision SSOT (may be stale). Use **Decision Object** above.",
        "- K3 Advisor is **critique only** — does not override Do today / Decision Object.",
    ]

    lines += ["", "## Data warnings"]
    for w in warnings:
        lines.append(f"- ⚠️ {w}")
    if null_asof[:8]:
        lines.append(f"- Missing asof sample: {', '.join(null_asof[:12])}")

    lines += [
        "",
        "## Action loop",
        "1. Decide from **Do today** + **Decision Object** only",
        "2. Execute in brokers (you)",
        "3. Re-import / prices",
        "4. Re-run this card tomorrow — compare",
        "",
        "## Sources used (hard)",
        "- positions · price_asof · Outside-Ideas · Morning-Context · hygiene grades",
        "- FMP count (mega free) · Breaking soft only",
        "",
        "_Hygiene only · multi-broker never a sell reason · no day-trade FOMO_",
        "",
    ]

    text = "\n".join(lines) + "\n"
    OBS.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    arch = ARCHIVE_DIR / f"Daily-Ops-{now.strftime('%Y-%m-%d')}.md"
    arch.write_text(text)

    # Telegram-friendly short stdout
    short = [
        f"VOX OPS {now.strftime('%Y-%m-%d')} {conf_emoji}{conf}",
        f"AUM ${aum:,.0f} · Tech {tech_w:.0f}% · Energy {energy_w:.0f}% · Crypto {crypto_w:.0f}%",
        f"Pricing {'OK' if pricing_ok else 'REFRESH'} · FMP {fmp_n} · big moves {len(big)}",
        "DO:",
    ]
    for i, a in enumerate(actions[:5], 1):
        short.append(f" {i}. {a}")
    # bucket B one-liner
    b_tickers = []
    for x in decision.get("bucket_b") or []:
        m = re.search(r"\*\*([A-Z0-9.\-]+)\*\*", x)
        if m:
            b_tickers.append(m.group(1))
    if b_tickers and conf != "RED":
        short.append("B: " + " · ".join(b_tickers[:8]))
    if earn_held[:4]:
        short.append(
            "EARN: " + " · ".join(f"{e.get('ticker')} {e.get('date')}" for e in earn_held[:4])
        )
    if ai_veto[:6]:
        short.append("AI-VETO: " + " · ".join(ai_veto[:6]))
    if big[:5]:
        short.append("MOVES: " + " · ".join(f"{t} {c:+.0f}%" for t, c, _, __ in big[:5]))
    if warnings:
        short.append("WARN: " + "; ".join(warnings[:3]))
    short.append(f"Full: {OUT}")
    print("\n".join(short))
    print("\n---\n")
    print(text[:2800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
