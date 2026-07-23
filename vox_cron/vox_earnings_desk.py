#!/usr/bin/env python3
"""
VOX Earnings Desk (Phase 2)

Held + watch names reporting this week:
  - date/hour, eps est/act, book weight, day%
  - optional DeepSeek 3-liners for reported names

Writes:
  brain/Earnings-Desk-LATEST.md
  cron/output/intel/EarningsDesk-LATEST.json

Usage:
  python3 vox_cron/vox_earnings_desk.py
  python3 vox_cron/vox_earnings_desk.py --no-llm
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
INTEL = Path.home() / ".hermes" / "cron" / "output" / "intel"
OUT_MD = OBS / "Earnings-Desk-LATEST.md"
OUT_JSON = INTEL / "EarningsDesk-LATEST.json"
OUTSIDE_JSON = Path.home() / ".hermes" / "cron" / "output" / "brain" / "OutsideIdeas-LATEST.json"
JUNK = {"MIRROR_TOTAL", "CASH", "GBM O", "TOTAL", "VAULTA", "KITE", "FF"}
CRYPTO = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX", "BONK", "PENGU"}
MEGA = ["GOOGL", "GOOG", "MSFT", "AAPL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX"]


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def http_json(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "VOX-EarningsDesk/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def book() -> tuple[list[dict], float]:
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT UPPER(ticker) t,
               COALESCE(live_value_usd, live_value, 0)::float v,
               day_chg_pct::float daychg,
               grade, sector
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        ORDER BY v DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    aum = sum(float(r["v"] or 0) for r in rows) or 1.0
    held = []
    for r in rows:
        t = (r["t"] or "").strip().upper()
        if not t or t in JUNK or " " in t:
            continue
        held.append(
            {
                "ticker": t,
                "v": float(r["v"] or 0),
                "w": float(r["v"] or 0) / aum * 100.0,
                "daychg": r.get("daychg"),
                "grade": r.get("grade"),
                "sector": r.get("sector"),
            }
        )
    return held, aum


def outside_watch() -> list[str]:
    if not OUTSIDE_JSON.exists():
        return []
    try:
        data = json.loads(OUTSIDE_JSON.read_text())
        out = []
        for bucket in ("tier_a", "tier_b"):
            for i in data.get(bucket) or []:
                t = str(i.get("ticker") or "").upper()
                if t:
                    out.append(t)
        return out[:20]
    except Exception:
        return []


def earnings_cal(symbols: list[str], start: str, end: str) -> list[dict]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    url = (
        "https://finnhub.io/api/v1/calendar/earnings"
        f"?from={start}&to={end}&token={urllib.parse.quote(key)}"
    )
    data = http_json(url, timeout=30)
    cal = data.get("earningsCalendar") if isinstance(data, dict) else None
    if not isinstance(cal, list):
        return []
    want = set(symbols)
    out = []
    for row in cal:
        sym = (row.get("symbol") or "").upper()
        if sym not in want:
            continue
        out.append(
            {
                "ticker": sym,
                "date": row.get("date"),
                "hour": row.get("hour") or "",
                "epsEstimate": row.get("epsEstimate"),
                "epsActual": row.get("epsActual"),
                "revenueEstimate": row.get("revenueEstimate"),
                "revenueActual": row.get("revenueActual"),
                "reported": row.get("epsActual") is not None,
            }
        )
    out.sort(key=lambda x: (x.get("date") or "", x.get("ticker") or ""))
    return out


def surprise_note(row: dict) -> str:
    est, act = row.get("epsEstimate"), row.get("epsActual")
    try:
        if est is None or act is None:
            return ""
        est_f, act_f = float(est), float(act)
        if est_f == 0:
            return f"act={act_f}"
        pct = (act_f - est_f) / abs(est_f) * 100.0
        return f"EPS {pct:+.1f}% vs est"
    except Exception:
        return ""


def llm_notes(rows: list[dict], aum: float) -> dict[str, str]:
    """ticker -> 3-line note for reported held names."""
    if os.environ.get("VOX_EARN_NO_LLM") == "1":
        return {}
    reported = [r for r in rows if r.get("reported") and r.get("bucket") == "held"][:8]
    if not reported:
        return {}
    try:
        from vox_utils import call_openrouter
    except Exception:
        return {}
    lines = []
    for r in reported:
        lines.append(
            f"{r['ticker']} w={r.get('book_w',0):.1f}% day={r.get('daychg')} "
            f"{surprise_note(r)} hour={r.get('hour')} grade={r.get('grade')}"
        )
    prompt = (
        "For each ticker below write exactly 3 short bullets: "
        "(1) what printed (2) book implication (3) do-not-chase note. "
        "Soft only. No orders.\n\n" + "\n".join(lines)
    )
    try:
        result = call_openrouter(
            system_prompt="VOX earnings desk. Terse. Soft only.",
            user_prompt=prompt,
            model=os.environ.get("VOX_EARN_MODEL", "deepseek/deepseek-chat"),
            max_tokens=800,
            temperature=0.2,
            script_name="vox_earnings_desk",
            notes="earnings notes",
        )
        text = ""
        if isinstance(result, dict):
            for k in ("content", "text", "reasoning"):
                if result.get(k) and str(result.get(k)).strip() not in ("", "None"):
                    text = str(result[k]).strip()
                    break
        # naive split by ticker headers
        notes = {}
        cur = None
        buf = []
        for ln in text.splitlines():
            up = ln.strip().upper()
            hit = None
            for r in reported:
                t = r["ticker"]
                if up.startswith(t) or f"**{t}**" in ln.upper() or ln.strip().startswith(t):
                    hit = t
                    break
            if hit:
                if cur and buf:
                    notes[cur] = "\n".join(buf)[:500]
                cur = hit
                buf = [ln]
            elif cur:
                buf.append(ln)
        if cur and buf:
            notes[cur] = "\n".join(buf)[:500]
        # if parse failed, attach blob to first
        if not notes and text:
            notes[reported[0]["ticker"]] = text[:600]
        return notes
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    if args.no_llm:
        os.environ["VOX_EARN_NO_LLM"] = "1"

    day = datetime.now().strftime("%Y-%m-%d")
    start = day
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    held, aum = book()
    hmap = {h["ticker"]: h for h in held}
    watch = [t for t in outside_watch() + MEGA if t not in hmap]
    symbols = [h["ticker"] for h in held if h["ticker"] not in CRYPTO][:80] + watch[:25]
    symbols = list(dict.fromkeys(symbols))

    cal = earnings_cal(symbols, start, end)
    rows = []
    for c in cal:
        t = c["ticker"]
        if t in hmap:
            h = hmap[t]
            rows.append(
                {
                    **c,
                    "bucket": "held",
                    "book_w": round(h["w"], 2),
                    "daychg": h.get("daychg"),
                    "grade": h.get("grade"),
                    "v": h.get("v"),
                }
            )
        else:
            rows.append({**c, "bucket": "watch", "book_w": 0.0, "daychg": None, "grade": None, "v": 0})

    notes = llm_notes(rows, aum)

    held_r = [r for r in rows if r["bucket"] == "held"]
    watch_r = [r for r in rows if r["bucket"] == "watch"]

    lines = [
        f"# Earnings Desk — {day}",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · Finnhub · **not auto-trade**_",
        f"_Window `{start}` → `{end}` · AUM ${aum:,.0f} · held events {len(held_r)} · watch {len(watch_r)}_",
        "",
        "## Held reporting",
        "",
        "| Ticker | Date | When | W% | Day% | EPS | Note |",
        "|--------|------|------|---:|-----:|-----|------|",
    ]
    if not held_r:
        lines.append("| — | | | | | | none in window |")
    for r in held_r:
        dayp = f"{r['daychg']:+.1f}%" if r.get("daychg") is not None else "—"
        eps = surprise_note(r) or ("REPORTED" if r.get("reported") else "upcoming")
        lines.append(
            f"| **{r['ticker']}** | {r.get('date')} | {r.get('hour') or '—'} | "
            f"{r.get('book_w',0):.1f} | {dayp} | {eps} | {'yes' if r['ticker'] in notes else ''} |"
        )

    lines += ["", "## Watch / mega (not held or Outside)", ""]
    if not watch_r:
        lines.append("_none_")
    else:
        for r in watch_r[:12]:
            flag = "REPORTED" if r.get("reported") else "upcoming"
            lines.append(f"- **{r['ticker']}** {r.get('date')} {r.get('hour') or ''} · {flag}")

    if notes:
        lines += ["", "## Soft notes (DeepSeek · reported held only)"]
        for t, body in notes.items():
            lines += [f"### {t}", body, ""]

    lines += [
        "",
        "## How to use",
        "1. Ops Card EVENT earnings lines",
        "2. Do not FOMO reverse on print day alone",
        "3. Material weight (≥2.5%) prints get priority attention",
        "",
        f"JSON: `{OUT_JSON}`",
        "",
    ]
    text = "\n".join(lines) + "\n"
    OBS.mkdir(parents=True, exist_ok=True)
    INTEL.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(text)
    (OBS / f"Earnings-Desk-{day}.md").write_text(text)
    payload = {
        "day": day,
        "window": {"from": start, "to": end},
        "aum": aum,
        "held": held_r,
        "watch": watch_r[:20],
        "notes": notes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print(f"EARNINGS DESK {day}")
    print(f"held={len(held_r)} watch={len(watch_r)} notes={len(notes)}")
    for r in held_r[:8]:
        print(
            f"  · {r['ticker']} {r.get('date')} {r.get('hour')} w={r.get('book_w')} "
            f"{'REPORTED' if r.get('reported') else 'upcoming'}"
        )
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
