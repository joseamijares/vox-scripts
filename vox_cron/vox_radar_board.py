#!/usr/bin/env python3
"""
VOX Radar Board — single merged intelligence file (NOT a decision council).

Panels:
  A) AUM WoW / MoM + sleeve Δ
  B) Earnings radar (held + Outside watch this week)
  C) AI Disruption Ledger (score + flags)
  D) Short sleeve candidates (policy-capped, not auto-trade)
  E) Optional soft synthesis footnote (never SSOT)

Writes:
  Obsidian brain/Radar-Board-LATEST.md
  ~/.hermes/cron/output/brain/RadarBoard-LATEST.json
  snapshots under output/brain/radar_aum_snaps.json

Usage:
  python3 vox_cron/vox_radar_board.py
  python3 vox_cron/vox_radar_board.py --no-synth
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
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

try:
    from vox_portfolio_policy import sleeve_for, SLEEVE_TARGETS
except Exception:
    def sleeve_for(t: str) -> str:
        return "OTHER"
    SLEEVE_TARGETS = {}

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT_JSON_DIR = Path.home() / ".hermes" / "cron" / "output" / "brain"
RADAR_MD = OBS / "Radar-Board-LATEST.md"
RADAR_JSON = OUT_JSON_DIR / "RadarBoard-LATEST.json"
SNAP = OUT_JSON_DIR / "radar_aum_snaps.json"
OUTSIDE_JSON = OUT_JSON_DIR / "OutsideIdeas-LATEST.json"

JUNK = {
    "MIRROR_TOTAL", "CASH", "GBM O", "BI 270121", "TOTAL", "VAULTA", "KITE", "FF",
}
CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX",
    "DOT", "BONK", "PENGU", "VAULTA", "VANA", "MORPHO", "KAITO", "NIGHT",
}

# Short sleeve policy (fraction of AUM gross short notionals target max)
SHORT_GROSS_MAX = 0.08  # 8%
SHORT_NAME_MAX = 0.02   # 2% per name

# Curated AI disruption ledger — score 0-100 (higher = more disruption risk / better short thesis attention)
# stance: long_veto | long_caution | short_candidate | watch
AI_DISRUPTION_LEDGER: list[dict[str, Any]] = [
    {
        "ticker": "CHGG",
        "name": "Chegg",
        "score": 92,
        "stance": "short_candidate",
        "thesis": "Homework/tutoring commoditized by free LLMs; structural demand destruction.",
        "kill": "Sustained paid-user growth + pricing power vs free AI tutors for 2+ qtrs.",
        "metrics": ["subscribers", "guidance", "ARPU"],
    },
    {
        "ticker": "DUOL",
        "name": "Duolingo",
        "score": 78,
        "stance": "long_veto",
        "thesis": "Free ChatGPT/LLM language practice compresses willingness-to-pay; streak app moat may thin.",
        "kill": "Bookings/DAU acceleration + clear AI-native product that expands ARPU 2 qtrs.",
        "metrics": ["DAU", "bookings", "paid conversion"],
    },
    {
        "ticker": "COUR",
        "name": "Coursera",
        "score": 70,
        "stance": "long_caution",
        "thesis": "Content/credential middle layer faces AI course generators + employer skepticism.",
        "kill": "Enterprise seats + degrees mix prove AI-resistant for 2 qtrs.",
        "metrics": ["enterprise NRR", "degrees"],
    },
    {
        "ticker": "UDMY",
        "name": "Udemy",
        "score": 72,
        "stance": "long_caution",
        "thesis": "Long-tail course marketplace easily substituted by AI-generated learning paths.",
        "kill": "UB growth + take-rate stability with AI tools as complement not substitute.",
        "metrics": ["UB NRR", "marketplace GMV"],
    },
    {
        "ticker": "STACK",
        "name": "Clear Secure / alt ed proxies skip",
        "score": 0,
        "stance": "watch",
        "thesis": "placeholder skip",
        "kill": "",
        "metrics": [],
        "disabled": True,
    },
    {
        "ticker": "YELP",
        "name": "Yelp",
        "score": 62,
        "stance": "watch",
        "thesis": "Local search/discovery challenged by AI answer engines.",
        "kill": "Ad revenue re-accel with AI referral share stable.",
        "metrics": ["ad rev", "traffic"],
    },
    {
        "ticker": "MTCH",
        "name": "Match Group",
        "score": 58,
        "stance": "watch",
        "thesis": "Social/AI companions may pressure dating engagement over multi-year.",
        "kill": "Tinder/Hinge paying users reaccelerate; AI is feature not substitute.",
        "metrics": ["payers", "ARPU"],
    },
    {
        "ticker": "ZG",
        "name": "Zillow",
        "score": 55,
        "stance": "watch",
        "thesis": "AI listing/search summaries may compress lead gen; still asset-heavy marketplace.",
        "kill": "Premier agent demand holds with AI UX as add-on.",
        "metrics": ["visits", "premier agent"],
    },
    {
        "ticker": "CARG",
        "name": "CarGurus",
        "score": 52,
        "stance": "watch",
        "thesis": "Vertical search vulnerable to AI shopping agents over time.",
        "kill": "Dealer ROI + leads stable through AI cycle.",
        "metrics": ["leads", "dealers"],
    },
    {
        "ticker": "OPEN",
        "name": "Opendoor",
        "score": 65,
        "stance": "long_caution",
        "thesis": "iBuying model fragile; AI pricing doesn't fix inventory/spread risk.",
        "kill": "Consistent positive unit economics 4 qtrs.",
        "metrics": ["spreads", "volumes"],
    },
    {
        "ticker": "WIX",
        "name": "Wix",
        "score": 60,
        "stance": "long_caution",
        "thesis": "DIY web builders face AI site generators; must own AI or lose SMB entry.",
        "kill": "AI product attaches and ARPU up 2 qtrs.",
        "metrics": ["creations", "ARPU"],
    },
    {
        "ticker": "SQSP",
        "name": "Squarespace",
        "score": 58,
        "stance": "long_caution",
        "thesis": "Same AI site-gen pressure as Wix class.",
        "kill": "Subs + ARPU hold with AI tooling leadership.",
        "metrics": ["subs", "ARPU"],
    },
    {
        "ticker": "PATH",
        "name": "UiPath",
        "score": 68,
        "stance": "long_caution",
        "thesis": "RPA layer at risk as foundation models absorb simple automation workflows.",
        "kill": "ARR reaccel + AI agents sold as platform expansion not replacement.",
        "metrics": ["ARR", "net retention"],
    },
    {
        "ticker": "AI",
        "name": "C3.ai",
        "score": 48,
        "stance": "watch",
        "thesis": "Ironically AI-named; product truth varies — monitor, not auto short.",
        "kill": "Consistent large deal conversion.",
        "metrics": ["RPO", "deals"],
    },
    {
        "ticker": "BBAI",
        "name": "BigBear.ai",
        "score": 50,
        "stance": "watch",
        "thesis": "Small AI narrative name — hygiene noise risk.",
        "kill": "Real contract backlog growth.",
        "metrics": ["backlog"],
    },
    {
        "ticker": "SOUN",
        "name": "SoundHound",
        "score": 45,
        "stance": "watch",
        "thesis": "Voice AI crowded; bigtech can absorb use cases.",
        "kill": "Automotive design-wins scale with margins.",
        "metrics": ["royalties", "design wins"],
    },
    {
        "ticker": "DV",
        "name": "DoubleVerify",
        "score": 40,
        "stance": "watch",
        "thesis": "Ad verification still needed in AI-content flood — possible beneficiary not victim.",
        "kill": "n/a victim thesis weak",
        "metrics": ["rev growth"],
    },
    {
        "ticker": "MAN",
        "name": "ManpowerGroup",
        "score": 66,
        "stance": "long_caution",
        "thesis": "Staffing/recruiting disrupted as AI screening + freelance platforms compress mid-skill placement.",
        "kill": "Placement volumes + pricing stabilize with AI tools as attach.",
        "metrics": ["placements", "gross profit"],
    },
    {
        "ticker": "RHI",
        "name": "Robert Half",
        "score": 64,
        "stance": "long_caution",
        "thesis": "Professional staffing faces AI skill matching and reduced corporate headcount cycles.",
        "kill": "Perm placement rebound with rising bill rates 2 qtrs.",
        "metrics": ["bill rates", "temps"],
    },
    {
        "ticker": "TRI",
        "name": "Thomson Reuters",
        "score": 42,
        "stance": "watch",
        "thesis": "Legal/tax content could be AI-pressured long-term but sticky enterprise workflows buffer near term.",
        "kill": "n/a strong short — more AI attach story",
        "metrics": ["recurring rev"],
    },
    {
        "ticker": "RELX",
        "name": "RELX",
        "score": 40,
        "stance": "watch",
        "thesis": "Info services moat; AI is more feature than killer near term.",
        "kill": "n/a",
        "metrics": ["subscriptions"],
    },
    {
        "ticker": "EEFT",
        "name": "Euronet",
        "score": 48,
        "stance": "watch",
        "thesis": "Payments rails less AI-killed; monitor only.",
        "kill": "n/a",
        "metrics": ["tx volume"],
    },
    {
        "ticker": "RNG",
        "name": "RingCentral",
        "score": 63,
        "stance": "long_caution",
        "thesis": "UCaaS commoditized; AI meeting agents from bigtech pressure seat pricing.",
        "kill": "NRR reaccel + AI attach lifts ARPU 2 qtrs.",
        "metrics": ["NRR", "seats"],
    },
    {
        "ticker": "ZM",
        "name": "Zoom",
        "score": 55,
        "stance": "watch",
        "thesis": "Video commoditized but AI companion could defend; not clean short.",
        "kill": "Enterprise seats grow with AI bundle.",
        "metrics": ["enterprise"],
    },
    {
        "ticker": "PTON",
        "name": "Peloton",
        "score": 60,
        "stance": "long_caution",
        "thesis": "Content/subscription fitness faces free AI coaching + hardware fatigue (not pure AI kill).",
        "kill": "Paid subs reaccel + positive FCF sustained.",
        "metrics": ["subs", "FCF"],
    },
    {
        "ticker": "NYT",
        "name": "New York Times",
        "score": 50,
        "stance": "watch",
        "thesis": "News summarizers pressure casual traffic; brand + games + cooking buffer.",
        "kill": "Digital sub growth holds with AI search share stable.",
        "metrics": ["digital subs"],
    },
]


SHORT_THESIS_OUT = OBS / "Short-Thesis-Stubs-LATEST.md"


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def http_json(url: str, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "VOX-Radar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def load_snaps() -> list[dict]:
    if not SNAP.exists():
        return []
    try:
        return json.loads(SNAP.read_text()).get("snaps", [])
    except Exception:
        return []


def save_snap(snap: dict) -> None:
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    snaps = [s for s in load_snaps() if s.get("day") != snap["day"]]
    snaps.append(snap)
    snaps = sorted(snaps, key=lambda s: s["day"])[-40:]
    SNAP.write_text(json.dumps({"snaps": snaps}, indent=2) + "\n")
    SNAP.chmod(0o600)


def nearest_snap(snaps: list[dict], on_or_before: str) -> dict | None:
    prior = [s for s in snaps if s.get("day") and s["day"] <= on_or_before]
    return prior[-1] if prior else None


def fmt_delta(cur: float, prev: float | None) -> str:
    if prev is None or prev <= 0:
        return "n/a"
    d = cur - prev
    pct = d / prev * 100.0
    sign = "+" if d >= 0 else ""
    arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
    return f"{arrow} {sign}${d:,.0f} ({sign}{pct:.1f}%)"


def book_snapshot(cur) -> dict:
    cur.execute(
        """
        SELECT ticker, shares,
               COALESCE(live_price, 0) live_price,
               COALESCE(live_value_usd, live_value, 0) v,
               grade, sector, day_chg_pct
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        ORDER BY COALESCE(live_value_usd, live_value, 0) DESC
        """
    )
    rows = cur.fetchall()
    aum = sum(float(r["v"] or 0) for r in rows)
    sleeves: dict[str, float] = defaultdict(float)
    sectors: dict[str, float] = defaultdict(float)
    held = []
    for r in rows:
        t = (r["ticker"] or "").strip().upper()
        v = float(r["v"] or 0)
        if t in JUNK or " " in t:
            sleeves["JUNK_SHELL"] += v
            continue
        sl = sleeve_for(t)
        sleeves[sl] += v
        sec = (r.get("sector") or "Other").strip() or "Other"
        if t in CRYPTO:
            sec = "Crypto"
        sectors[sec] += v
        held.append(
            {
                "ticker": t,
                "v": v,
                "w": (v / aum * 100.0) if aum else 0,
                "grade": r.get("grade"),
                "sleeve": sl,
                "sector": sec,
                "day_chg_pct": r.get("day_chg_pct"),
            }
        )
    sleeve_pct = {k: (v / aum * 100.0 if aum else 0) for k, v in sleeves.items()}
    sector_pct = {k: (v / aum * 100.0 if aum else 0) for k, v in sectors.items()}
    return {
        "aum": aum,
        "n": len(held),
        "held": held,
        "sleeves": dict(sleeves),
        "sleeve_pct": sleeve_pct,
        "sectors": dict(sectors),
        "sector_pct": sector_pct,
        "held_set": {h["ticker"] for h in held},
    }


def panel_a_aum(book: dict, day: str) -> dict:
    snaps = load_snaps()
    wow_day = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    mom_day = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    wow = nearest_snap(snaps, wow_day)
    mom = nearest_snap(snaps, mom_day)

    aum = book["aum"]
    sleeve_now = book["sleeve_pct"]
    sleeve_deltas = {}
    if wow and wow.get("sleeve_pct"):
        for k in set(sleeve_now) | set(wow["sleeve_pct"]):
            sleeve_deltas[k] = round(sleeve_now.get(k, 0) - float(wow["sleeve_pct"].get(k, 0)), 2)

    # top contributors vs prior week values if present
    contrib = []
    if wow and wow.get("top"):
        prev_map = {x["ticker"]: x.get("v", 0) for x in wow["top"]}
        for h in book["held"][:40]:
            pv = prev_map.get(h["ticker"])
            if pv is None:
                continue
            dlt = h["v"] - float(pv)
            if abs(dlt) >= 200:
                contrib.append({"ticker": h["ticker"], "dlt": dlt, "v": h["v"]})
        contrib.sort(key=lambda x: -abs(x["dlt"]))

    panel = {
        "day": day,
        "aum": aum,
        "n": book["n"],
        "wow": {
            "vs_day": wow.get("day") if wow else None,
            "prev_aum": wow.get("aum") if wow else None,
            "delta_str": fmt_delta(aum, wow.get("aum") if wow else None),
        },
        "mom": {
            "vs_day": mom.get("day") if mom else None,
            "prev_aum": mom.get("aum") if mom else None,
            "delta_str": fmt_delta(aum, mom.get("aum") if mom else None),
        },
        "sleeve_pct": sleeve_now,
        "sleeve_delta_wow_pp": sleeve_deltas,
        "sector_pct_top": dict(sorted(book["sector_pct"].items(), key=lambda kv: -kv[1])[:6]),
        "contributors": contrib[:8],
        "baseline_note": None if wow else "WoW baseline will populate after ~7 days of snaps",
    }

    # persist snap (top 25 for contrib next week)
    save_snap(
        {
            "day": day,
            "aum": aum,
            "n": book["n"],
            "sleeve_pct": sleeve_now,
            "sector_pct": book["sector_pct"],
            "top": [{"ticker": h["ticker"], "v": h["v"], "w": h["w"]} for h in book["held"][:25]],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    return panel


def fetch_earnings_finnhub(tickers: list[str], start: str, end: str) -> list[dict]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    url = (
        "https://finnhub.io/api/v1/calendar/earnings"
        f"?from={start}&to={end}&token={urllib.parse.quote(key)}"
    )
    try:
        data = http_json(url, timeout=25)
    except Exception as e:
        return [{"error": f"finnhub {e}"}]
    cal = data.get("earningsCalendar") if isinstance(data, dict) else None
    if not isinstance(cal, list):
        return []
    want = set(tickers)
    out = []
    for row in cal:
        sym = (row.get("symbol") or "").upper()
        if sym not in want:
            continue
        out.append(
            {
                "ticker": sym,
                "date": row.get("date"),
                "time": row.get("hour") or "",
                "epsEstimated": row.get("epsEstimate"),
                "epsActual": row.get("epsActual"),
                "revenueEstimated": row.get("revenueEstimate"),
                "revenueActual": row.get("revenueActual"),
                "source": "finnhub",
                "reported": row.get("epsActual") is not None,
            }
        )
    return out


def fetch_earnings_fmp(tickers: list[str], start: str, end: str) -> list[dict]:
    key = os.environ.get("FMP_API_KEY", "").strip()
    if not key:
        return []
    out = []
    # bulk calendar then filter
    url = (
        "https://financialmodelingprep.com/api/v3/earning_calendar"
        f"?from={start}&to={end}&apikey={urllib.parse.quote(key)}"
    )
    try:
        data = http_json(url, timeout=25)
    except Exception as e:
        return [{"error": f"fmp_calendar {e}"}]
    if not isinstance(data, list):
        return []
    want = set(tickers)
    for row in data:
        sym = (row.get("symbol") or "").upper()
        if sym in want:
            out.append(
                {
                    "ticker": sym,
                    "date": row.get("date"),
                    "time": row.get("time") or row.get("when") or "",
                    "epsEstimated": row.get("epsEstimated"),
                    "revenueEstimated": row.get("revenueEstimated"),
                    "source": "fmp",
                }
            )
    return out


def fetch_earnings_yahoo_one(ticker: str) -> dict | None:
    """Best-effort next earnings via Yahoo quoteSummary."""
    url = (
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(ticker)}"
        f"?modules=calendarEvents"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 VOX-Radar/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
        res = (data.get("quoteSummary") or {}).get("result") or []
        if not res:
            return None
        cal = (res[0].get("calendarEvents") or {}).get("earnings") or {}
        dates = cal.get("earningsDate") or []
        if not dates:
            return None
        d0 = dates[0]
        if isinstance(d0, dict):
            fmt = d0.get("fmt") or ""
            raw = d0.get("raw")
        else:
            fmt, raw = str(d0), None
        return {
            "ticker": ticker,
            "date": fmt,
            "raw": raw,
            "epsEstimated": (cal.get("earningsAverage") or {}).get("raw")
            if isinstance(cal.get("earningsAverage"), dict)
            else cal.get("earningsAverage"),
            "source": "yahoo",
        }
    except Exception:
        return None


def panel_b_earnings(book: dict, day: str) -> dict:
    start = day
    end = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
    held = [h["ticker"] for h in book["held"] if h["ticker"] not in CRYPTO][:80]

    watch = []
    if OUTSIDE_JSON.exists():
        try:
            oj = json.loads(OUTSIDE_JSON.read_text())
            for bucket in ("tier_a", "tier_b"):
                for i in oj.get(bucket) or []:
                    t = (i.get("ticker") or "").upper()
                    if t and t not in held:
                        watch.append(t)
        except Exception:
            pass
    # always watch mega names that move book beta
    mega = ["GOOGL", "GOOG", "MSFT", "AAPL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX"]
    universe = []
    seen = set()
    for t in held + watch[:25] + mega:
        if t not in seen and t not in JUNK:
            seen.add(t)
            universe.append(t)

    # Prefer Finnhub (works headless); FMP/Yahoo often 401/403 in this env
    events = fetch_earnings_finnhub(universe, start, end)
    if not events or any(e.get("error") for e in events):
        events = fetch_earnings_fmp(universe, start, end)
    if events and not any(e.get("error") for e in events):
        by_t = {e["ticker"]: e for e in events if e.get("ticker")}
    else:
        by_t = {}
        material = [h["ticker"] for h in book["held"] if h["w"] >= 1.5][:20]
        for t in material + [x for x in mega if x in book["held_set"] or x in watch]:
            if t in by_t:
                continue
            one = fetch_earnings_yahoo_one(t)
            if one and one.get("date"):
                by_t[t] = one

    held_ev, watch_ev = [], []
    for t, e in sorted(by_t.items(), key=lambda kv: str(kv[1].get("date") or "")):
        tag = "REPORTED" if e.get("reported") else "UPCOMING"
        if t in book["held_set"]:
            w = next((h["w"] for h in book["held"] if h["ticker"] == t), 0)
            e2 = {**e, "book_w": round(w, 2), "bucket": "held", "status": tag}
            held_ev.append(e2)
        else:
            e2 = {**e, "bucket": "watch", "status": tag}
            watch_ev.append(e2)

    return {
        "window": {"from": start, "to": end},
        "held": held_ev[:20],
        "watch": watch_ev[:15],
        "count": len(held_ev) + len(watch_ev),
        "source_priority": "finnhub>fmp>yahoo",
    }


def panel_c_disruption(book: dict) -> dict:
    held = book["held_set"]
    rows = []
    for item in AI_DISRUPTION_LEDGER:
        if item.get("disabled") or not item.get("ticker") or item.get("score", 0) <= 0:
            continue
        t = item["ticker"].upper()
        in_book = t in held
        w = next((h["w"] for h in book["held"] if h["ticker"] == t), 0.0)
        rows.append(
            {
                **{k: item[k] for k in ("ticker", "name", "score", "stance", "thesis", "kill", "metrics")},
                "in_book": in_book,
                "book_w": round(w, 2),
                "outside_action": (
                    "VETO_LONG"
                    if item["stance"] in ("long_veto", "short_candidate") and item["score"] >= 70
                    else "FLAG_CAUTION"
                    if item["stance"] == "long_caution" or item["score"] >= 55
                    else "WATCH"
                ),
            }
        )
    rows.sort(key=lambda r: -r["score"])
    book_hits = [r for r in rows if r["in_book"]]
    veto_list = [r["ticker"] for r in rows if r["outside_action"] == "VETO_LONG"]
    caution = [r["ticker"] for r in rows if r["outside_action"] == "FLAG_CAUTION"]
    return {
        "entries": rows,
        "book_hits": book_hits,
        "outside_veto": veto_list,
        "outside_caution": caution,
        "note": "Disruption scores are curated risk flags — not auto-trade. Hygiene grades do not model AI product death.",
    }


def panel_d_shorts(book: dict, disruption: dict) -> dict:
    """Short candidates from disruption ledger — not held preferred; size caps only."""
    aum = book["aum"] or 1.0
    cands = []
    for r in disruption["entries"]:
        if r["score"] < 65:
            continue
        if r["stance"] not in ("short_candidate", "long_veto", "long_caution"):
            continue
        # Prefer not held; if held, that's reduce/avoid long not short-against unless veto high
        role = "short_new"
        if r["in_book"]:
            if r["score"] >= 80:
                role = "trim_or_avoid_long"  # don't pile short on top of long without explicit decision
            else:
                role = "avoid_add_long"
        max_notional = aum * SHORT_NAME_MAX
        cands.append(
            {
                "ticker": r["ticker"],
                "score": r["score"],
                "role": role,
                "thesis": r["thesis"],
                "kill": r["kill"],
                "in_book": r["in_book"],
                "suggested_max_notional": round(max_notional, 0),
                "suggested_max_w": SHORT_NAME_MAX * 100,
            }
        )
    cands.sort(key=lambda x: (-x["score"], x["ticker"]))
    return {
        "policy": {
            "gross_short_max_pct": SHORT_GROSS_MAX * 100,
            "per_name_max_pct": SHORT_NAME_MAX * 100,
            "horizon": "weeks–months · not day-trade",
            "rules": [
                "Thesis + kill criteria required before any short",
                "Prefer AI-disruption / broken model over low hygiene grade alone",
                "Multi-broker never a cover/hold reason",
                "No auto-trade — list is candidate only",
                "Do not short quality compounders on narrative alone",
            ],
        },
        "candidates": cands[:12],
        "gross_budget_usd": round(aum * SHORT_GROSS_MAX, 0),
    }


def panel_e_synth(board: dict, enable: bool) -> dict:
    """Optional short soft synthesis via OpenRouter DeepSeek — footnote only, never SSOT."""
    if not enable:
        return {"enabled": False, "text": None, "note": "synth skipped"}
    if os.environ.get("VOX_RADAR_NO_LLM") == "1":
        return {"enabled": False, "text": None, "note": "VOX_RADAR_NO_LLM=1"}

    a = board["aum"]
    b = board["earnings"]
    c = board["disruption"]
    d = board["shorts"]
    news = board.get("news") or {}
    prompt = (
        "VOX soft footnote only. Max 6 short bullets. No trades. No council voice.\n"
        "Mandate: balanced quality compounders; grades=hygiene; disruption can veto Outside longs;\n"
        "shorts are candidates only under 8% gross cap. Never override Ops Decision Object.\n\n"
        f"AUM: ${a['aum']:,.0f} WoW {a['wow']['delta_str']} MoM {a['mom']['delta_str']}\n"
        f"Sleeves: {json.dumps(a.get('sleeve_pct', {}), default=str)[:400]}\n"
        f"Earnings held: {json.dumps(b.get('held', [])[:8], default=str)[:600]}\n"
        f"AI veto: {c.get('outside_veto')}\n"
        f"Short cands: {[x['ticker'] for x in d.get('candidates', [])[:6]]}\n"
        f"News: {json.dumps((news.get('headlines') or [])[:6], default=str)[:500]}\n"
        "Write: 1) AUM read 2) earnings risk 3) AI long veto 4) short patience 5) one blind spot.\n"
    )
    try:
        from vox_utils import call_openrouter

        result = call_openrouter(
            system_prompt="Terse VOX risk footnote writer. No markdown headers. Soft only. Output final bullets only.",
            user_prompt=prompt,
            model=os.environ.get("VOX_RADAR_MODEL", "deepseek/deepseek-chat"),
            max_tokens=450,
            temperature=0.25,
            script_name="vox_radar_board",
            notes="radar panel E soft synth",
        )
        text = ""
        if isinstance(result, dict):
            for k in ("content", "text", "response", "reasoning"):
                val = result.get(k)
                if val and str(val).strip() and str(val).strip() != "None":
                    text = str(val).strip()
                    # if only reasoning, take last non-empty paragraph-ish
                    if k == "reasoning" and "\n" in text:
                        parts = [p.strip() for p in text.split("\n") if p.strip()]
                        # prefer lines that look like bullets
                        bullets = [p for p in parts if p.startswith(("-", "•", "*")) or p[0].isdigit()]
                        text = "\n".join(bullets[-8:] if bullets else parts[-6:])
                    break
            if not text:
                choices = result.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    text = str(msg.get("content") or msg.get("reasoning") or "").strip()
            if not text and result.get("message"):
                text = str(result["message"]).strip()
        else:
            text = str(result or "").strip()
        if text and not text.startswith("("):
            return {
                "enabled": True,
                "text": text[:1200],
                "note": "soft only — not SSOT",
                "model": os.environ.get("VOX_RADAR_MODEL", "deepseek/deepseek-chat"),
            }
        return {"enabled": False, "text": None, "note": f"empty synth: {text[:120]}"}
    except Exception as e:
        return {"enabled": False, "text": None, "note": f"synth failed: {e}"}


def panel_news(book: dict) -> dict:
    """Finnhub headlines + breaking snip — feeds synth/weekly, not SSOT."""
    headlines = []
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if key:
        try:
            data = http_json(
                f"https://finnhub.io/api/v1/news?category=general&token={urllib.parse.quote(key)}",
                timeout=20,
            )
            if isinstance(data, list):
                for i in data[:10]:
                    headlines.append(
                        {
                            "title": str(i.get("headline") or "")[:140],
                            "source": i.get("source"),
                            "kind": "general",
                        }
                    )
        except Exception as e:
            headlines.append({"title": f"(general news err {e})", "source": "", "kind": "err"})
        # company for material held + earnings today
        syms = [h["ticker"] for h in book["held"] if h["w"] >= 2.0][:8]
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=2)
        for sym in syms:
            try:
                url = (
                    f"https://finnhub.io/api/v1/company-news?symbol={sym}"
                    f"&from={start.isoformat()}&to={end.isoformat()}&token={urllib.parse.quote(key)}"
                )
                data = http_json(url, timeout=12)
                if isinstance(data, list) and data:
                    headlines.append(
                        {
                            "title": str(data[0].get("headline") or "")[:140],
                            "source": data[0].get("source"),
                            "kind": f"held:{sym}",
                        }
                    )
            except Exception:
                pass

    breaking_path = Path.home() / "Documents/Obsidian/VOX/vox/memory/decisions/Breaking-LATEST.md"
    breaking_snip = ""
    if breaking_path.exists():
        breaking_snip = breaking_path.read_text(errors="replace")[:900]

    return {
        "headlines": [h for h in headlines if h.get("title")][:16],
        "breaking_snip": breaking_snip,
        "note": "News is context only — Ops Decision Object still SSOT",
    }


def write_short_thesis_stubs(board: dict) -> Path:
    """One stub per short candidate — thesis + kill; not auto-trade."""
    day = board["day"]
    cands = (board.get("shorts") or {}).get("candidates") or []
    pol = (board.get("shorts") or {}).get("policy") or {}
    lines = [
        f"# Short Thesis Stubs — {day}",
        "",
        "_Candidates only · not auto-trade · multi-broker never a cover reason_",
        f"_Caps: gross {pol.get('gross_short_max_pct')}% · name {pol.get('per_name_max_pct')}% · {pol.get('horizon')}_",
        "",
    ]
    if not cands:
        lines.append("_No candidates above score threshold._")
    for i, c in enumerate(cands, 1):
        lines += [
            f"## {i}. {c['ticker']} · score {c['score']} · {c.get('role')}",
            f"- **Thesis:** {c.get('thesis')}",
            f"- **Kill / reverse:** {c.get('kill')}",
            f"- **In book:** {c.get('in_book')} · suggested max ~${c.get('suggested_max_notional', 0):,.0f} ({c.get('suggested_max_w')}%)",
            f"- **Status:** watchlist — require borrow/liquidity check before any short",
            f"- **Invalidation log:** _(empty — fill when opened)_",
            "",
        ]
    lines += [
        "## Rules",
        "1. No short from hygiene grade alone",
        "2. Prefer AI-disruption / broken model (Radar C)",
        "3. Do not short QUALITY_HOLD on narrative alone",
        "4. Size inside SHORT sleeve cap in portfolio_policy",
        "",
        f"Source: Radar Board D · {board.get('generated_at')}",
        "",
    ]
    OBS.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    SHORT_THESIS_OUT.write_text(text)
    (OBS / f"Short-Thesis-Stubs-{day}.md").write_text(text)
    return SHORT_THESIS_OUT


def render_md(board: dict) -> str:
    day = board["day"]
    a, b, c, d, e = board["aum"], board["earnings"], board["disruption"], board["shorts"], board["synth"]
    lines = [
        f"# Radar Board — {day}",
        "",
        "_One board · many panels · **not a decision council** · Ops Decision Object remains SSOT_",
        "",
        "## A · AUM & sleeves",
        f"- **AUM:** ${a['aum']:,.0f} · n={a['n']}",
        f"- **WoW:** {a['wow']['delta_str']}"
        + (f" vs {a['wow']['vs_day']}" if a['wow'].get('vs_day') else ""),
        f"- **MoM:** {a['mom']['delta_str']}"
        + (f" vs {a['mom']['vs_day']}" if a['mom'].get('vs_day') else ""),
    ]
    if a.get("baseline_note"):
        lines.append(f"- _{a['baseline_note']}_")
    # sleeves
    sp = a.get("sleeve_pct") or {}
    top_sl = sorted(sp.items(), key=lambda kv: -kv[1])[:8]
    if top_sl:
        lines.append("- **Sleeves now:** " + " · ".join(f"{k} {v:.1f}%" for k, v in top_sl))
    sd = a.get("sleeve_delta_wow_pp") or {}
    if sd:
        movers = sorted(sd.items(), key=lambda kv: -abs(kv[1]))[:6]
        lines.append(
            "- **Sleeve Δ WoW (pp):** "
            + " · ".join(f"{k} {v:+.1f}" for k, v in movers if abs(v) >= 0.3)
            or "- **Sleeve Δ WoW:** small"
        )
    if a.get("contributors"):
        lines.append("- **Name $ contributors (vs prior snap):**")
        for x in a["contributors"][:6]:
            lines.append(f"  - {x['ticker']} {x['dlt']:+,.0f}")

    lines += ["", "## B · Earnings radar (this week)"]
    lines.append(f"- Window `{b['window']['from']}` → `{b['window']['to']}` · events={b['count']}")
    if b.get("held"):
        lines.append("- **Held reporting:**")
        for e_ in b["held"][:10]:
            st = e_.get("status") or ""
            lines.append(
                f"  - **{e_['ticker']}** {e_.get('date')} {e_.get('time') or ''} · "
                f"book {e_.get('book_w', 0):.1f}% · {st} · {e_.get('source')}"
            )
    else:
        lines.append("- **Held reporting:** _none detected in window (or calendar sparse)_")
    if b.get("watch"):
        lines.append("- **Watch (Outside/mega):** " + ", ".join(
            f"{e_['ticker']} {e_.get('date')}" for e_ in b["watch"][:8]
        ))

    lines += ["", "## C · AI disruption ledger"]
    lines.append(f"- _{c.get('note')}_")
    lines.append(f"- **Outside VETO longs:** {', '.join(c.get('outside_veto') or []) or '—'}")
    lines.append(f"- **Outside CAUTION:** {', '.join(c.get('outside_caution') or []) or '—'}")
    if c.get("book_hits"):
        lines.append("- **In book:**")
        for r in c["book_hits"][:8]:
            lines.append(f"  - **{r['ticker']}** score {r['score']} {r['stance']} w={r['book_w']}% — {r['thesis'][:100]}")
    lines.append("- **Top ledger:**")
    for r in c.get("entries", [])[:8]:
        flag = r["outside_action"]
        lines.append(f"  - {r['ticker']} {r['score']} {flag} — {r['thesis'][:90]}")

    lines += ["", "## D · Short sleeve (candidates only)"]
    pol = d.get("policy") or {}
    lines.append(
        f"- Cap gross **{pol.get('gross_short_max_pct')}%** · per name **{pol.get('per_name_max_pct')}%** · {pol.get('horizon')}"
    )
    lines.append(f"- Budget ~${d.get('gross_budget_usd', 0):,.0f}")
    for rule in (pol.get("rules") or [])[:5]:
        lines.append(f"  - {rule}")
    if d.get("candidates"):
        lines.append("- **Candidates:**")
        for x in d["candidates"][:8]:
            lines.append(
                f"  - **{x['ticker']}** score {x['score']} · {x['role']} · max~${x['suggested_max_notional']:,.0f} — {x['thesis'][:80]}"
            )
    else:
        lines.append("- _No short candidates above threshold_")

    lines += ["", "## E · Soft synthesis (footnote · not SSOT)"]
    if e.get("text"):
        lines.append(e["text"])
        if e.get("model"):
            lines.append(f"_model: {e.get('model')}_")
    else:
        lines.append(f"_No synth — {e.get('note')}_")

    n = board.get("news") or {}
    lines += ["", "## News context (not SSOT)"]
    lines.append(f"- _{n.get('note')}_")
    for h in (n.get("headlines") or [])[:8]:
        lines.append(f"- [{h.get('kind') or '—'}] {h.get('title')}")
    if n.get("breaking_snip"):
        lines.append("- Breaking snip present (see decisions/Breaking-LATEST)")

    lines += [
        "",
        "## How to use",
        "1. **Ops Card Decision Object** still decides capital actions",
        "2. Weekly broadcast pulls A/B/C/D snips from this board",
        "3. Outside must honor VETO list (AI disruption)",
        "4. Shorts only with thesis+kill; see Short-Thesis-Stubs-LATEST",
        "5. No multi-agent council — this file is the merged radar",
        "",
        f"JSON: `{RADAR_JSON}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def telegram_snip(board: dict) -> str:
    a, b, c, d, e = board["aum"], board["earnings"], board["disruption"], board["shorts"], board["synth"]
    lines = [
        f"RADAR {board['day']}",
        f"AUM ${a['aum']:,.0f} · WoW {a['wow']['delta_str']} · MoM {a['mom']['delta_str']}",
    ]
    sp = a.get("sleeve_pct") or {}
    if sp:
        top = sorted(sp.items(), key=lambda kv: -kv[1])[:5]
        lines.append("Sleeves: " + " · ".join(f"{k} {v:.0f}%" for k, v in top))
    if b.get("held"):
        lines.append(
            "Earn held: "
            + " · ".join(f"{x['ticker']} {x.get('date')}" for x in b["held"][:6])
        )
    elif b.get("watch"):
        lines.append(
            "Earn watch: "
            + " · ".join(f"{x['ticker']} {x.get('date')}" for x in b["watch"][:5])
        )
    else:
        lines.append("Earn: none detected this window")
    veto = c.get("outside_veto") or []
    lines.append("AI veto longs: " + (", ".join(veto[:8]) if veto else "—"))
    sc = [x["ticker"] for x in (d.get("candidates") or [])[:5]]
    lines.append("Short cands: " + (", ".join(sc) if sc else "—"))
    news = board.get("news") or {}
    hs = [h.get("title") for h in (news.get("headlines") or []) if h.get("title")][:2]
    if hs:
        lines.append("News: " + " | ".join(hs)[:200])
    if e.get("text"):
        bits = [ln.strip() for ln in e["text"].splitlines() if ln.strip()][:2]
        if bits:
            lines.append("Note: " + " | ".join(bits)[:220])
    return "\n".join(lines)


def build(enable_synth: bool = True) -> dict:
    day = datetime.now().strftime("%Y-%m-%d")
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    book = book_snapshot(cur)
    conn.close()

    aum_p = panel_a_aum(book, day)
    earn_p = panel_b_earnings(book, day)
    dis_p = panel_c_disruption(book)
    short_p = panel_d_shorts(book, dis_p)
    news_p = panel_news(book)

    board = {
        "day": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aum": aum_p,
        "earnings": earn_p,
        "disruption": dis_p,
        "shorts": short_p,
        "news": news_p,
        "synth": {"enabled": False, "text": None, "note": "pending"},
        "not_council": True,
        "ssot": "Ops Decision Object — this board is radar only",
    }
    board["synth"] = panel_e_synth(board, enable=enable_synth)
    board["telegram_snip"] = telegram_snip(board)
    write_short_thesis_stubs(board)

    OBS.mkdir(parents=True, exist_ok=True)
    OUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    md = render_md(board)
    RADAR_MD.write_text(md)
    # dated archive
    (OBS / f"Radar-Board-{day}.md").write_text(md)
    RADAR_JSON.write_text(json.dumps(board, indent=2, default=str) + "\n")
    RADAR_JSON.chmod(0o600)
    (OUT_JSON_DIR / f"RadarBoard-{day}.json").write_text(
        json.dumps(board, indent=2, default=str) + "\n"
    )
    return board


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-synth", action="store_true")
    args = ap.parse_args()
    board = build(enable_synth=not args.no_synth)
    print(board["telegram_snip"])
    print("---")
    print(f"Wrote {RADAR_MD}")
    print(f"Wrote {RADAR_JSON}")
    print(
        f"AUM ${board['aum']['aum']:,.0f} · earn {board['earnings']['count']} · "
        f"veto {board['disruption']['outside_veto']} · shorts {len(board['shorts']['candidates'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
