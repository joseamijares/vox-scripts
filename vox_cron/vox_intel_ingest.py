#!/usr/bin/env python3
"""
VOX Intel Spine — INGEST (Phase 1)

Collect book-mapped events into a daily JSONL bus. No LLM. No Telegram.

Sources:
  - Finnhub general news
  - Finnhub company news (material held + mega)
  - Finnhub earnings calendar (held + Outside A + mega)
  - Google News RSS: trump/tariff/policy, Fed/CPI, oil/Hormuz/geo

Writes:
  ~/.hermes/cron/output/intel/events_YYYY-MM-DD.jsonl
  ~/.hermes/cron/output/intel/events_LATEST.jsonl (copy)
  ~/.hermes/cron/output/intel/ingest_meta_LATEST.json

Usage:
  python3 vox_cron/vox_intel_ingest.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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

OUT_DIR = Path.home() / ".hermes" / "cron" / "output" / "intel"
OUTSIDE_JSON = Path.home() / ".hermes" / "cron" / "output" / "brain" / "OutsideIdeas-LATEST.json"
JUNK = {"MIRROR_TOTAL", "CASH", "GBM O", "BI 270121", "TOTAL", "VAULTA", "KITE", "FF"}
CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX",
    "DOT", "BONK", "PENGU", "VAULTA", "VANA", "MORPHO", "KAITO", "NIGHT",
}
MEGA = ["GOOGL", "GOOG", "MSFT", "AAPL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX"]

RSS_PACKS = [
    ("trump_policy", "Trump tariff OR Trump executive order OR Trump stocks OR trade war"),
    ("fed_macro", "Federal Reserve OR CPI inflation OR interest rates Fed"),
    ("oil_geo", "Strait of Hormuz OR Iran oil OR oil price OR OPEC"),
    ("market_structure", "stock market circuit breaker OR market crash OR selloff stocks"),
]


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
    req = urllib.request.Request(url, headers={"User-Agent": "VOX-IntelSpine/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def http_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "VOX-IntelSpine/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def eid(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]
    return h


def book_universe() -> tuple[list[dict], float, set[str]]:
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT UPPER(ticker) t,
               COALESCE(live_value_usd, live_value, 0)::float v,
               grade
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
                "grade": r.get("grade"),
            }
        )
    return held, aum, {h["ticker"] for h in held}


def outside_a() -> list[str]:
    if not OUTSIDE_JSON.exists():
        return []
    try:
        data = json.loads(OUTSIDE_JSON.read_text())
        return [
            str(i.get("ticker") or "").upper()
            for i in (data.get("tier_a") or [])
            if i.get("ticker")
        ]
    except Exception:
        return []


def finnhub_general(limit: int = 40) -> list[dict]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    url = f"https://finnhub.io/api/v1/news?category=general&token={urllib.parse.quote(key)}"
    try:
        data = http_json(url)
    except Exception as e:
        return [{"error": str(e), "source": "finnhub_general"}]
    out = []
    if not isinstance(data, list):
        return out
    for i in data[:limit]:
        title = str(i.get("headline") or "").strip()
        if not title:
            continue
        out.append(
            {
                "id": eid("fhg", title, str(i.get("id") or i.get("url") or "")),
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "finnhub_general",
                "theme": "general",
                "title": title[:240],
                "url": i.get("url") or "",
                "tickers": [],
                "severity": 1,
            }
        )
    return out


def finnhub_company(symbols: list[str], days: int = 2, per: int = 4) -> list[dict]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    out = []
    for sym in symbols:
        url = (
            f"https://finnhub.io/api/v1/company-news?symbol={urllib.parse.quote(sym)}"
            f"&from={start.isoformat()}&to={end.isoformat()}&token={urllib.parse.quote(key)}"
        )
        try:
            data = http_json(url, timeout=15)
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for i in data[:per]:
            title = str(i.get("headline") or "").strip()
            if not title:
                continue
            out.append(
                {
                    "id": eid("fhc", sym, title, str(i.get("id") or "")),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "source": "finnhub_company",
                    "theme": "company",
                    "title": title[:240],
                    "url": i.get("url") or "",
                    "tickers": [sym],
                    "severity": 2,
                }
            )
        time.sleep(0.04)
    return out


def finnhub_earnings(symbols: list[str], start: str, end: str) -> list[dict]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    url = (
        "https://finnhub.io/api/v1/calendar/earnings"
        f"?from={start}&to={end}&token={urllib.parse.quote(key)}"
    )
    try:
        data = http_json(url, timeout=30)
    except Exception as e:
        return [{"error": str(e), "source": "finnhub_earnings"}]
    cal = data.get("earningsCalendar") if isinstance(data, dict) else None
    if not isinstance(cal, list):
        return []
    want = set(symbols)
    out = []
    for row in cal:
        sym = (row.get("symbol") or "").upper()
        if sym not in want:
            continue
        reported = row.get("epsActual") is not None
        title = (
            f"EARNINGS {'REPORTED' if reported else 'UPCOMING'} {sym} "
            f"{row.get('date')} {row.get('hour') or ''} "
            f"epsEst={row.get('epsEstimate')} epsAct={row.get('epsActual')}"
        ).strip()
        out.append(
            {
                "id": eid("fhe", sym, str(row.get("date")), str(row.get("hour"))),
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "finnhub_earnings",
                "theme": "earnings",
                "title": title[:240],
                "url": "",
                "tickers": [sym],
                "severity": 3 if reported else 2,
                "meta": {
                    "date": row.get("date"),
                    "hour": row.get("hour"),
                    "epsEstimate": row.get("epsEstimate"),
                    "epsActual": row.get("epsActual"),
                    "revenueEstimate": row.get("revenueEstimate"),
                    "revenueActual": row.get("revenueActual"),
                    "reported": reported,
                },
            }
        )
    return out


def google_rss(theme: str, query: str, limit: int = 8) -> list[dict]:
    q = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        xml = http_text(url, timeout=20)
        root = ET.fromstring(xml)
    except Exception as e:
        return [{"error": f"rss {theme}: {e}", "source": "google_rss"}]
    out = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title:
            continue
        sev = 2
        tl = title.lower()
        if any(w in tl for w in ("crash", "war", "attack", "emergency", "circuit breaker")):
            sev = 3
        if theme == "trump_policy" and any(w in tl for w in ("tariff", "executive", "china")):
            sev = max(sev, 2)
        out.append(
            {
                "id": eid("rss", theme, title),
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "google_rss",
                "theme": theme,
                "title": title[:240],
                "url": link[:300],
                "tickers": [],
                "severity": sev,
            }
        )
    return out


def attach_book_weights(events: list[dict], held: list[dict]) -> list[dict]:
    wmap = {h["ticker"]: h["w"] for h in held}
    for e in events:
        if e.get("error"):
            continue
        ticks = e.get("tickers") or []
        e["book_w"] = round(sum(wmap.get(t, 0.0) for t in ticks), 3)
        # light keyword map to held mega names
        if not ticks and e.get("title"):
            title_u = e["title"].upper()
            hits = []
            for h in held[:40]:
                t = h["ticker"]
                if len(t) >= 3 and re.search(rf"\b{re.escape(t)}\b", title_u):
                    hits.append(t)
            # common names
            name_map = {
                "GOOGLE": "GOOGL",
                "ALPHABET": "GOOGL",
                "TESLA": "TSLA",
                "NVIDIA": "NVDA",
                "MICROSOFT": "MSFT",
                "AMAZON": "AMZN",
                "APPLE": "AAPL",
                "META": "META",
                "BITCOIN": "BTC",
            }
            for name, t in name_map.items():
                if name in title_u and t in wmap:
                    hits.append(t)
            hits = list(dict.fromkeys(hits))
            if hits:
                e["tickers"] = hits
                e["book_w"] = round(sum(wmap.get(t, 0.0) for t in hits), 3)
    return events


def main() -> int:
    day = datetime.now().strftime("%Y-%m-%d")
    start = day
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    held, aum, held_set = book_universe()
    material = [h["ticker"] for h in held if h["w"] >= 1.5 and h["ticker"] not in CRYPTO][:25]
    watch = outside_a()[:15]
    universe = []
    seen = set()
    for t in material + watch + MEGA + [h["ticker"] for h in held if h["w"] >= 2.5][:20]:
        if t not in seen and t not in JUNK:
            seen.add(t)
            universe.append(t)

    events: list[dict] = []
    errors = []
    chunks = [
        finnhub_general(35),
        finnhub_company(material[:15] + [t for t in MEGA if t in held_set][:8], days=2, per=3),
        finnhub_earnings(universe, start, end),
    ]
    for theme, q in RSS_PACKS:
        chunks.append(google_rss(theme, q, limit=8))
        time.sleep(0.15)

    for ch in chunks:
        for e in ch:
            if e.get("error"):
                errors.append(e)
            else:
                events.append(e)

    events = attach_book_weights(events, held)

    # dedupe by id
    by_id = {}
    for e in events:
        by_id[e["id"]] = e
    events = list(by_id.values())
    # sort severity then book_w
    events.sort(key=lambda e: (-int(e.get("severity") or 0), -float(e.get("book_w") or 0), e.get("title") or ""))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"events_{day}.jsonl"
    # append-safe: rewrite day file from this run (ingest is snapshot)
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e, default=str) + "\n")
    latest = OUT_DIR / "events_LATEST.jsonl"
    latest.write_text(path.read_text())
    meta = {
        "day": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aum": aum,
        "n_events": len(events),
        "n_errors": len(errors),
        "errors": errors[:10],
        "n_held": len(held),
        "universe_n": len(universe),
        "path": str(path),
    }
    (OUT_DIR / "ingest_meta_LATEST.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"INTEL INGEST {day}")
    print(f"events={len(events)} errors={len(errors)} aum=${aum:,.0f} universe={len(universe)}")
    themes = {}
    for e in events:
        themes[e.get("theme") or "?"] = themes.get(e.get("theme") or "?", 0) + 1
    print("themes:", themes)
    top = [e for e in events if (e.get("book_w") or 0) > 0][:5]
    if top:
        print("book-linked:")
        for e in top:
            print(f"  · {e.get('tickers')} w={e.get('book_w')} {e.get('title')[:80]}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
