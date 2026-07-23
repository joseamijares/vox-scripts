#!/usr/bin/env python3
"""
VOX Weekly Monitor — publish-only broadcast card.

Uses TELEGRAM_BROADCAST_BOT_TOKEN + TELEGRAM_BROADCAST_CHAT_ID
(separate from Hermes interactive bot). Hermes cron deliver=local;
this script self-sends via Telegram Bot API.

Content SSOT:
  - Book AUM / sleeves / material weights (DB)
  - Outside Tier A/B (Outside-Ideas-LATEST)
  - Structure gaps + do-list snip (Daily-Ops-LATEST / Decision Object)
  - Week Δ AUM via simple snapshot file

Not: councils, LLM essays, chase day-movers as "best plays".
Grades = hygiene labels only.

Usage:
  python3 vox_cron/vox_weekly_monitor.py           # build + send
  python3 vox_cron/vox_weekly_monitor.py --dry     # print only
  python3 vox_cron/vox_weekly_monitor.py --discover  # print bot chats from getUpdates
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT_MD = OBS / "Weekly-Monitor-LATEST.md"
SNAP = Path.home() / ".hermes" / "cron" / "output" / "brain" / "weekly_aum_snapshots.json"
RADAR_JSON = Path.home() / ".hermes" / "cron" / "output" / "brain" / "RadarBoard-LATEST.json"
OUTSIDE = OBS / "Outside-Ideas-LATEST.md"
OPS = OBS / "Daily-Ops-LATEST.md"
CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX",
    "DOT", "BONK", "PENGU", "VAULTA", "VANA", "MORPHO", "KAITO", "NIGHT",
}
ENERGY_HINT = {"XLE", "XOM", "CVX", "OXY", "COP", "EOG", "SLB", "HAL", "USO", "XOP"}
# shells / non-priceable (pricing gate family)
JUNK = {
    "MIRROR_TOTAL", "CASH", "GBM O", "BI 270121", "TOTAL", "VAULTA", "KITE", "FF",
}


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def tg_api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}", "body": body[:300]}


def send_broadcast(text: str) -> tuple[bool, str]:
    token = os.environ.get("TELEGRAM_BROADCAST_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_BROADCAST_CHAT_ID", "").strip()
    if not token:
        return False, "TELEGRAM_BROADCAST_BOT_TOKEN missing"
    if not chat:
        return False, "TELEGRAM_BROADCAST_CHAT_ID missing — /start the bot then --discover"
    # Telegram hard limit ~4096
    chunks = []
    while text:
        if len(text) <= 4000:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, 3900)
        if cut < 1000:
            cut = 3900
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    last = ""
    for i, ch in enumerate(chunks):
        res = tg_api(
            token,
            "sendMessage",
            {
                "chat_id": chat,
                "text": ch,
                "disable_web_page_preview": True,
            },
        )
        if not res.get("ok"):
            return False, f"send failed part {i+1}: {res}"
        last = f"msg_id={res.get('result', {}).get('message_id')}"
    return True, last


def load_snapshots() -> list[dict]:
    if not SNAP.exists():
        return []
    try:
        return json.loads(SNAP.read_text()).get("snaps", [])
    except Exception:
        return []


def save_snapshot(aum: float, n: int, day: str) -> None:
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    snaps = load_snapshots()
    # one per calendar day
    snaps = [s for s in snaps if s.get("day") != day]
    snaps.append({"day": day, "aum": aum, "n": n, "ts": datetime.now(timezone.utc).isoformat()})
    snaps = sorted(snaps, key=lambda s: s["day"])[-26:]  # ~6 months weekly
    SNAP.write_text(json.dumps({"snaps": snaps}, indent=2) + "\n")
    SNAP.chmod(0o600)


def week_delta(aum: float, day: str) -> str | None:
    snaps = load_snapshots()
    target = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    # nearest snap on or before target
    prior = [s for s in snaps if s.get("day") and s["day"] <= target]
    if not prior:
        # fallback: oldest older than 5d
        older = [s for s in snaps if s.get("day") and s["day"] < day]
        if not older:
            return None
        prior = older
    p = prior[-1]
    try:
        pa = float(p["aum"])
    except Exception:
        return None
    if pa <= 0:
        return None
    dlt = aum - pa
    pct = (dlt / pa) * 100.0
    sign = "+" if dlt >= 0 else ""
    return f"{sign}${dlt:,.0f} ({sign}{pct:.1f}%) vs {p['day']}"


def parse_outside_tiers(text: str, limit_a: int = 5, limit_b: int = 5) -> tuple[list[str], list[str]]:
    a, b = [], []
    section = None
    for ln in text.splitlines():
        if ln.startswith("## Tier A"):
            section = "A"
            continue
        if ln.startswith("## Tier B"):
            section = "B"
            continue
        if ln.startswith("## Tier C") or ln.startswith("## How"):
            section = None
            continue
        if not ln.startswith("|"):
            continue
        # | **ALAB** | 75 | ...
        m = re.match(r"\|\s*\*?\*?([A-Z][A-Z0-9.\-]{0,11})\*?\*?\s*\|\s*([0-9]{1,3})", ln)
        if not m:
            continue
        t, g = m.group(1), m.group(2)
        if t.upper() in {"TICKER", "----", "-----"}:
            continue
        line = f"{t} g{g}"
        if section == "A" and len(a) < limit_a:
            a.append(line)
        elif section == "B" and len(b) < limit_b:
            b.append(line)
    return a, b


def ops_snip(path: Path) -> tuple[list[str], list[str]]:
    """Return (do_lines, structure_lines) from Ops card."""
    if not path.exists():
        return [], []
    lines = path.read_text(errors="replace").splitlines()
    do, struct = [], []
    mode = None
    for ln in lines:
        if ln.startswith("## Do today"):
            mode = "do"
            continue
        if ln.startswith("### Bucket A"):
            mode = "a"
            continue
        if ln.startswith("### Bucket B") or ln.startswith("## Decision") or ln.startswith("## Big"):
            if mode == "a":
                mode = None
            if ln.startswith("### Bucket B"):
                mode = None
            continue
        if mode == "do" and re.match(r"^\d+\.", ln.strip()):
            do.append(ln.strip())
            if len(do) >= 5:
                mode = None
        if mode == "a" and re.match(r"^\d+\.", ln.strip()):
            struct.append(ln.strip())
            if len(struct) >= 4:
                mode = None
    return do, struct


def load_radar() -> dict:
    if not RADAR_JSON.exists():
        return {}
    try:
        return json.loads(RADAR_JSON.read_text())
    except Exception:
        return {}


def sector_of(row) -> str:
    sec = (row.get("sector") or "").strip()
    t = (row.get("ticker") or "").upper()
    if t in CRYPTO or "crypto" in sec.lower():
        return "Crypto"
    if t in ENERGY_HINT or "energy" in sec.lower() or "oil" in sec.lower():
        return "Energy"
    if not sec:
        return "Other"
    return sec


def build_card() -> str:
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT ticker, shares, avg_cost,
               COALESCE(live_price, 0) live_price,
               COALESCE(live_value_usd, live_value, 0) v,
               grade, sector, price_asof, day_chg_pct
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        ORDER BY COALESCE(live_value_usd, live_value, 0) DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    def _is_junk(r) -> bool:
        t = (r.get("ticker") or "").strip().upper()
        if t in JUNK or " " in t:
            return True
        return False

    # AUM includes all positive book value; display lists exclude shells
    aum = sum(float(r["v"] or 0) for r in rows)
    n = len(rows)
    show = [r for r in rows if not _is_junk(r)]
    by_sec = defaultdict(float)
    for r in show:
        by_sec[sector_of(r)] += float(r["v"] or 0)

    def pct(sec: str) -> float:
        return (by_sec.get(sec, 0) / aum * 100.0) if aum else 0.0

    tech = sum(v for k, v in by_sec.items() if "tech" in k.lower())
    tech_p = (tech / aum * 100.0) if aum else 0.0
    energy_p = pct("Energy")
    crypto_p = pct("Crypto")

    material = [r for r in show if aum and float(r["v"] or 0) / aum * 100 >= 2.5][:12]
    junk = [
        r
        for r in show
        if float(r["v"] or 0) >= 500
        and aum
        and float(r["v"] or 0) / aum * 100 < 2.5
        and (r.get("grade") is None or float(r.get("grade") or 0) < 55)
    ][:6]

    outside_txt = OUTSIDE.read_text(errors="replace") if OUTSIDE.exists() else ""
    tier_a, tier_b = parse_outside_tiers(outside_txt)
    do, struct = ops_snip(OPS)

    delta = week_delta(aum, day)
    # save after reading prior
    save_snapshot(aum, n, day)

    radar = load_radar()
    ra = radar.get("aum") or {}
    wow = (ra.get("wow") or {}).get("delta_str") or delta
    mom = (ra.get("mom") or {}).get("delta_str") or "n/a"
    sleeve_pct = ra.get("sleeve_pct") or {}
    sleeve_line = ""
    if sleeve_pct:
        top_sl = sorted(sleeve_pct.items(), key=lambda kv: -float(kv[1]))[:5]
        sleeve_line = " · ".join(f"{k} {float(v):.0f}%" for k, v in top_sl)

    top_sec = sorted(by_sec.items(), key=lambda kv: -kv[1])[:5]
    sec_line = " · ".join(f"{k} {v/aum*100:.0f}%" for k, v in top_sec if aum)

    conf = "🟡"
    if energy_p < 1 and crypto_p >= 10:
        conf = "🟡"
    gates_note = "hygiene grades · anti-chase · radar not council · not auto-trade"

    lines = [
        f"VOX WEEKLY · {day} {conf}",
        f"AUM ${aum:,.0f} · {n} names",
        f"WoW {wow} · MoM {mom}",
        f"Tech ~{tech_p:.0f}% · Energy ~{energy_p:.0f}% · Crypto ~{crypto_p:.0f}%",
        f"Sleeves: {sleeve_line}" if sleeve_line else (f"Sectors: {sec_line}" if sec_line else ""),
        "",
        "TOP HELD (≥2.5%)",
    ]
    for r in material:
        t = r["ticker"]
        w = float(r["v"] or 0) / aum * 100 if aum else 0
        g = r.get("grade")
        gs = f"g{int(g)}" if g is not None else "g?"
        lines.append(f"· {t} {w:.1f}% ${float(r['v']):,.0f} {gs}")

    lines += ["", "BEST NEW (Outside · prefer A · AI-veto applied)"]
    if tier_a:
        lines.append("A: " + " · ".join(tier_a))
    else:
        lines.append("A: _(none / stale Outside file)_")
    if tier_b:
        lines.append("B: " + " · ".join(tier_b[:5]))

    # Radar panels B/C/D
    earn_h = (radar.get("earnings") or {}).get("held") or []
    earn_w = (radar.get("earnings") or {}).get("watch") or []
    lines += ["", "EARNINGS (Radar B)"]
    if earn_h:
        lines.append(
            "Held: "
            + " · ".join(
                f"{e.get('ticker')} {e.get('date')}{('*' if e.get('reported') else '')}"
                for e in earn_h[:6]
            )
        )
    if earn_w:
        lines.append("Watch: " + " · ".join(f"{e.get('ticker')} {e.get('date')}" for e in earn_w[:5]))
    if not earn_h and not earn_w:
        lines.append("· none detected this window")

    veto = (radar.get("disruption") or {}).get("outside_veto") or []
    caution = (radar.get("disruption") or {}).get("outside_caution") or []
    lines += ["", "AI DISRUPTION (Radar C)"]
    lines.append("Veto longs: " + (", ".join(veto[:8]) if veto else "—"))
    if caution:
        lines.append("Caution: " + ", ".join(caution[:8]))

    shorts = (radar.get("shorts") or {}).get("candidates") or []
    pol = (radar.get("shorts") or {}).get("policy") or {}
    lines += ["", "SHORT CANDIDATES (Radar D · not auto)"]
    lines.append(
        f"Cap gross {pol.get('gross_short_max_pct', 8)}% · name {pol.get('per_name_max_pct', 2)}%"
    )
    if shorts:
        lines.append(
            "· "
            + " · ".join(f"{s.get('ticker')}({s.get('score')}/{s.get('role')})" for s in shorts[:6])
        )
    else:
        lines.append("· none above threshold")

    synth = (radar.get("synth") or {}).get("text")
    if synth:
        bits = [ln.strip(" -•") for ln in synth.splitlines() if ln.strip()][:2]
        if bits:
            lines += ["", "SOFT NOTE (E · not SSOT)"]
            for b in bits:
                lines.append(f"· {b[:160]}")

    lines += ["", "STRUCTURE / OWNED"]
    if struct:
        for s in struct:
            lines.append(f"· {s}")
    else:
        # fallback rules
        if energy_p < 1.5:
            lines.append("· ADD structure XLE (energy ~0%)")
        if crypto_p >= 10:
            lines.append(f"· TRIM crypto sleeve (~{crypto_p:.0f}%) — alts first")
        if not any(x.startswith("·") for x in lines[-3:]):
            lines.append("· _(see Ops Card Bucket A)_")

    if do:
        lines += ["", "FROM OPS (still open)"]
        for d in do[:4]:
            lines.append(f"· {d}")

    if junk:
        lines += ["", "CLEANUP WATCH (<2.5%, ≥$500, weak hygiene)"]
        for r in junk:
            g = r.get("grade")
            gs = f"g{int(g)}" if g is not None else "g?"
            lines.append(f"· {r['ticker']} ${float(r['v']):,.0f} {gs}")

    lines += [
        "",
        f"_{gates_note}_",
        f"Full: Radar-Board-LATEST · Ops · Outside · Brain-LATEST",
    ]
    text = "\n".join(ln for ln in lines if ln is not None)
    # write markdown twin
    OBS.mkdir(parents=True, exist_ok=True)
    md = [
        f"# Weekly Monitor — {day}",
        "",
        f"_Generated {now.strftime('%Y-%m-%d %H:%M UTC')} · broadcast bot · not Hermes chat_",
        "",
        "```",
        text,
        "```",
        "",
    ]
    OUT_MD.write_text("\n".join(md) + "\n")
    return text


def discover() -> int:
    token = os.environ.get("TELEGRAM_BROADCAST_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BROADCAST_BOT_TOKEN missing")
        return 1
    me = tg_api(token, "getMe")
    print("bot:", me.get("result", {}).get("username"), "ok", me.get("ok"))
    up = tg_api(token, "getUpdates")
    print("updates:", len(up.get("result") or []))
    chats = {}
    for u in up.get("result") or []:
        for key in ("message", "channel_post", "my_chat_member", "edited_message"):
            block = u.get(key) or {}
            chat = block.get("chat") or (block if "id" in block and "type" in block else None)
            if not chat and key == "my_chat_member":
                chat = (u.get("my_chat_member") or {}).get("chat")
            if chat and chat.get("id") is not None:
                chats[chat["id"]] = {
                    "id": chat.get("id"),
                    "type": chat.get("type"),
                    "title": chat.get("title"),
                    "username": chat.get("username"),
                    "first_name": chat.get("first_name"),
                }
    if not chats:
        print("No chats yet. Open @Vox_alertsbot_bot → /start, then re-run --discover")
        return 2
    for c in chats.values():
        print(json.dumps(c))
    print("Set TELEGRAM_BROADCAST_CHAT_ID to the id above (DM id == your user id).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--no-send", action="store_true", help="alias of --dry")
    ap.add_argument(
        "--refresh-radar",
        action="store_true",
        default=True,
        help="Run vox_radar_board.py before building card (default on)",
    )
    ap.add_argument(
        "--no-refresh-radar",
        action="store_true",
        help="Skip radar refresh",
    )
    args = ap.parse_args()
    if args.discover:
        return discover()

    if args.refresh_radar and not args.no_refresh_radar:
        import subprocess

        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent / "vox_radar_board.py"),
            ],
            cwd=str(Path.home() / ".hermes" / "scripts"),
            check=False,
        )

    text = build_card()
    print(text)
    print("---")
    print(f"Wrote {OUT_MD}")

    if args.dry or args.no_send:
        print("dry-run: not sent")
        return 0

    ok, info = send_broadcast(text)
    if ok:
        print(f"broadcast OK {info}")
        return 0
    print(f"broadcast FAIL: {info}")
    # still success for card generation; exit 1 so cron surfaces send issues
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
