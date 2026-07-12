#!/usr/bin/env python3
"""VOX Intelligence Suite — multi-domain research with quiet alerts.

Modes:
  policy     — Trump / tariffs / policy + markets (Google News RSS + synthesis)
  influencers— key X/market voices via news RSS + optional X when available
  social     — Reddit WSB/stocks RSS + retail sentiment synthesis
  weather    — NOAA alerts → equity/sector map
  morning    — merge all + VOX DB (macro/sector/insider/portfolio) → one brief
  all        — run policy+influencers+social+weather collectors only

Design:
  - No paid research keys required (1P may be down)
  - OpenRouter synthesis (deepseek workhorse; grok if configured)
  - Quiet: empty stdout when nothing material (for no_agent crons)
  - Always write JSON artifacts under ~/.hermes/cron/output/intel/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

# load .env
_env = Path.home() / ".hermes" / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        if _line and not _line.startswith("#") and "=" in _line:
            k, v = _line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
try:
    from vox_utils import call_openrouter
except Exception:
    call_openrouter = None  # type: ignore

OUT = Path.home() / ".hermes" / "cron" / "output" / "intel"
OBS = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "intel"
UA = {"User-Agent": "Mozilla/5.0 (compatible; VOX-Intel/1.0; research)"}

# Default influencer / policy accounts (news proxies + agent X later)
INFLUENCERS = [
    "realDonaldTrump",
    "POTUS",
    "elonmusk",
    "unusual_whales",
    "DeItaone",
    "FirstSquawk",
    "zerohedge",
    "WatcherGuru",
    "Tier10k",
    "CryptoCapo_",
    "saylor",
]

# Weather → sector/ticker map (skill-aligned)
WEATHER_MAP = {
    "hurricane": ["VLO", "MPC", "PSX", "XOM", "CVX", "HD", "LOW", "CB", "PGR"],
    "heat": ["NEE", "DUK", "SO", "D", "CEG", "VST", "GNRC"],
    "cold": ["UNG", "KMI", "WMB", "LNG"],
    "drought": ["DE", "NTR", "MOS", "CTVA", "ADM"],
    "flood": ["PGR", "CB", "ALL", "TRV"],
    "winter storm": ["HD", "LOW", "WMT", "COST"],
    "fire": ["PGR", "CB", "PCG", "EIX"],
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _get(url: str, timeout: int = 25) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


def parse_rss(url: str, limit: int = 12) -> List[Dict[str, str]]:
    r = _get(url)
    if not r:
        return []
    items = []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    # RSS 2.0
    for item in root.findall(".//item")[: limit * 2]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = re.sub("<[^<]+?>", "", item.findtext("description") or "")[:280]
        if title:
            items.append({"title": title, "link": link, "published": pub, "summary": desc})
        if len(items) >= limit:
            break
    if items:
        return items
    # Atom (Reddit)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns)[:limit]:
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else ""
        pub = entry.findtext("a:updated", default="", namespaces=ns) or ""
        summary = re.sub(
            "<[^<]+?>",
            "",
            entry.findtext("a:content", default="", namespaces=ns)
            or entry.findtext("a:summary", default="", namespaces=ns)
            or "",
        )[:280]
        if title:
            items.append({"title": title, "link": link, "published": pub, "summary": summary})
    return items[:limit]


def google_news(query: str, limit: int = 10) -> List[Dict[str, str]]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    return parse_rss(url, limit=limit)


def collect_policy() -> Dict[str, Any]:
    buckets = {
        "trump_tariffs": google_news("Trump tariffs markets OR trade war OR China tariffs", 10),
        "fed_policy": google_news("Federal Reserve rate OR Powell markets", 8),
        "geopolitics": google_news("geopolitics oil markets OR war markets", 8),
        "regulation": google_news("SEC crypto regulation OR AI regulation stocks", 6),
    }
    flat = []
    for k, v in buckets.items():
        for it in v:
            it = dict(it)
            it["bucket"] = k
            flat.append(it)
    return {"type": "policy", "ts": _now(), "items": flat, "counts": {k: len(v) for k, v in buckets.items()}}


def collect_influencers() -> Dict[str, Any]:
    # News proxy for handles (X API optional later)
    items = []
    queries = [
        "unusual whales OR DeItaone markets",
        "Elon Musk markets OR Tesla OR SpaceX stock",
        "Bitcoin crypto whale OR Michael Saylor",
        "First Squawk markets breaking",
    ]
    for q in queries:
        for it in google_news(q, 5):
            it = dict(it)
            it["bucket"] = "influencer_news"
            items.append(it)
    return {
        "type": "influencers",
        "ts": _now(),
        "watchlist": INFLUENCERS,
        "items": items[:25],
        "note": "News proxies for X voices; Hermes x_search agent cron supplements live posts",
    }


def collect_social() -> Dict[str, Any]:
    wsb = parse_rss("https://www.reddit.com/r/wallstreetbets/.rss", 15)
    # secondary via Google if stocks rss blocked
    stocks = parse_rss("https://www.reddit.com/r/stocks/.rss", 8)
    if not stocks:
        stocks = google_news("reddit stocks OR wallstreetbets OR r/stocks", 8)
    investing = google_news("retail investors options flow OR meme stocks", 6)
    tickers = defaultdict(int)
    ticker_re = re.compile(r"\b[A-Z]{2,5}\b")
    stop = {
        "THE", "AND", "FOR", "YOU", "ARE", "BUT", "NOT", "ALL", "CAN", "CEO", "IPO",
        "USD", "USA", "CEO", "ETF", "ATH", "IMO", "LOL", "WSB", "SEC", "FDA", "AI",
        "GDP", "CPI", "FOMC", "CEO", "CEO", "AM", "PM", "DD", "YOLO", "EPS", "PE",
    }
    for it in wsb + stocks:
        text = f"{it.get('title','')} {it.get('summary','')}"
        for t in ticker_re.findall(text):
            if t not in stop and not t.isdigit():
                tickers[t] += 1
    top_tickers = sorted(tickers.items(), key=lambda x: -x[1])[:15]
    return {
        "type": "social",
        "ts": _now(),
        "wsb": wsb,
        "stocks": stocks,
        "retail_news": investing,
        "hot_tickers": [{"ticker": t, "mentions": n} for t, n in top_tickers],
    }


def collect_weather() -> Dict[str, Any]:
    r = requests.get(
        "https://api.weather.gov/alerts/active",
        params={"status": "actual", "message_type": "alert"},
        headers={**UA, "Accept": "application/geo+json", "User-Agent": "(vox-intel, local)"},
        timeout=30,
    )
    alerts = []
    if r.status_code == 200:
        for f in (r.json().get("features") or [])[:80]:
            props = f.get("properties") or {}
            event = props.get("event") or ""
            sev = props.get("severity") or ""
            urgency = props.get("urgency") or ""
            area = props.get("areaDesc") or ""
            headline = props.get("headline") or props.get("description", "")[:200]
            if sev in ("Extreme", "Severe") or event.lower() in (
                "hurricane warning",
                "hurricane watch",
                "tropical storm warning",
                "heat advisory",
                "excessive heat warning",
                "blizzard warning",
                "ice storm warning",
                "red flag warning",
                "storm surge warning",
                "tornado warning",
            ):
                alerts.append(
                    {
                        "event": event,
                        "severity": sev,
                        "urgency": urgency,
                        "area": area[:120],
                        "headline": headline[:220],
                    }
                )
    # Map to tickers
    mapped = []
    for a in alerts[:20]:
        ev = (a["event"] or "").lower()
        hits = []
        for key, tickers in WEATHER_MAP.items():
            if key in ev or key in (a.get("headline") or "").lower():
                hits.extend(tickers)
        mapped.append({**a, "tickers": sorted(set(hits))[:8]})
    return {
        "type": "weather",
        "ts": _now(),
        "alert_count": len(alerts),
        "alerts": mapped[:15],
        "material": len(alerts) > 0,
    }


def load_vox_context() -> Dict[str, Any]:
    """Pull lightweight DB context for morning brief."""
    ctx: Dict[str, Any] = {}
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        pwd = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
        if not pwd:
            for line in (Path.home() / ".hermes" / ".env").read_text().splitlines():
                if line.startswith("DB_PASSWORD=") or line.startswith("PGPASSWORD="):
                    pwd = line.split("=", 1)[1].strip().strip('"')
                    break
        conn = psycopg2.connect(
            host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
            port=int(os.environ.get("PGPORT", "35577")),
            dbname=os.environ.get("PGDATABASE", "railway"),
            user=os.environ.get("PGUSER", "postgres"),
            password=pwd,
            connect_timeout=15,
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(
                """
                SELECT ticker, COALESCE(live_value_usd, live_value, 0) v, grade, council
                FROM positions
                WHERE COALESCE(shares,0) > 0 OR (ticker='MIRROR_TOTAL' AND COALESCE(live_value_usd,0)>0)
                ORDER BY v DESC NULLS LAST LIMIT 15
                """
            )
            ctx["top_positions"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            ctx["positions_err"] = str(e)
        try:
            cur.execute(
                """
                SELECT * FROM market_regime ORDER BY generated_at DESC NULLS LAST LIMIT 1
                """
            )
            row = cur.fetchone()
            if row:
                ctx["regime"] = {k: row[k] for k in row.keys() if k in list(row.keys())[:12]}
        except Exception:
            pass
        try:
            cur.execute(
                """
                SELECT ticker, unified_grade, action FROM unified_grades
                WHERE unified_grade >= 70
                ORDER BY unified_grade DESC NULLS LAST LIMIT 10
                """
            )
            ctx["top_grades"] = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass
        conn.close()
    except Exception as e:
        ctx["db_err"] = str(e)
    # sector proxies
    try:
        import yfinance as yf

        proxies = {
            "SPY": "market",
            "QQQ": "tech",
            "XLF": "financials",
            "XLE": "energy",
            "XLU": "utilities",
            "SMH": "semis",
            "IWM": "smallcap",
            "BTC-USD": "crypto",
        }
        moves = []
        for t, label in proxies.items():
            try:
                tk = yf.Ticker(t)
                h = tk.history(period="5d")
                if len(h) >= 2:
                    last = float(h["Close"].iloc[-1])
                    prev = float(h["Close"].iloc[-2])
                    d1 = (last / prev - 1) * 100
                    moves.append({"ticker": t, "label": label, "last": round(last, 2), "d1_pct": round(d1, 2)})
            except Exception:
                pass
        ctx["sector_proxies"] = moves
    except Exception as e:
        ctx["yf_err"] = str(e)
    return ctx


def synthesize(mode: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """LLM synthesis → structured bullets + material flag."""
    if call_openrouter is None:
        return _heuristic_synth(mode, payload)

    system = (
        "You are VOX research officer for a top-tier balanced portfolio (~20% aim). "
        "Be concise, specific, ticker-aware. No hype. "
        "Return STRICT JSON with keys: material (bool), severity (low|med|high), "
        "bullets (list of strings, max 8), tickers (list), actions (list of short strings), "
        "headline (string)."
    )
    user = (
        f"Mode: {mode}\nDate: {_day()}\n"
        f"Data JSON:\n{json.dumps(payload, default=str)[:14000]}\n\n"
        "Flag material=true only if investable / portfolio-relevant within days-weeks. "
        "Ignore noise. Prefer quality compounders + sector leaders over meme noise unless extreme."
    )
    try:
        # Prefer cheap workhorse; grok via OR as secondary path if primary fails
        result = None
        last_err = None
        for model in (
            os.environ.get("VOX_INTEL_MODEL", "deepseek/deepseek-v4-pro"),
            "deepseek/deepseek-v4-flash",
            "x-ai/grok-4.3",
        ):
            try:
                result = call_openrouter(
                    system_prompt=system,
                    user_prompt=user,
                    model=model,
                    max_tokens=900,
                    temperature=0.2,
                    script_name=f"vox_intel_{mode}",
                    notes=f"intel mode={mode}",
                )
                if result and result.get("content"):
                    break
            except Exception as e:
                last_err = e
                result = None
        text = (result or {}).get("content") or ""
        m = re.search(r"\{[\s\S]*\}", text or "")
        if m:
            data = json.loads(m.group(0))
            data["raw_model"] = True
            data["model_used"] = (result or {}).get("model")
            return data
        if last_err:
            return _heuristic_synth(mode, payload, err=str(last_err))
    except Exception as e:
        return _heuristic_synth(mode, payload, err=str(e))
    return _heuristic_synth(mode, payload)


def _heuristic_synth(mode: str, payload: Dict[str, Any], err: str = "") -> Dict[str, Any]:
    bullets = []
    tickers = []
    if mode == "weather":
        for a in (payload.get("alerts") or [])[:5]:
            bullets.append(f"{a.get('severity')}: {a.get('event')} — {a.get('area','')[:60]}")
            tickers.extend(a.get("tickers") or [])
        material = len(payload.get("alerts") or []) > 0
        sev = "high" if any(a.get("severity") == "Extreme" for a in payload.get("alerts") or []) else (
            "med" if material else "low"
        )
        return {
            "material": material,
            "severity": sev,
            "bullets": bullets or ["No severe weather alerts"],
            "tickers": sorted(set(tickers))[:12],
            "actions": ["Monitor weather-sensitive names"] if material else [],
            "headline": f"Weather: {len(payload.get('alerts') or [])} severe alerts",
            "err": err,
        }
    items = payload.get("items") or payload.get("wsb") or []
    for it in items[:6]:
        bullets.append(it.get("title") or str(it)[:120])
    if payload.get("hot_tickers"):
        tickers = [x["ticker"] for x in payload["hot_tickers"][:8]]
    return {
        "material": len(bullets) >= 3,
        "severity": "med" if bullets else "low",
        "bullets": bullets[:8],
        "tickers": tickers,
        "actions": [],
        "headline": f"{mode}: {len(bullets)} items",
        "err": err,
    }


def format_telegram(mode: str, synth: Dict[str, Any], extra: str = "") -> str:
    icon = {
        "policy": "🏛️",
        "influencers": "📡",
        "social": "🗣️",
        "weather": "🌦️",
        "morning": "🌅",
    }.get(mode, "🔎")
    lines = [
        f"{icon} **VOX Intel — {mode.upper()} — {_day()}**",
        f"**{synth.get('headline', mode)}** · severity `{synth.get('severity', 'low')}`",
        "",
    ]
    for b in (synth.get("bullets") or [])[:8]:
        lines.append(f"• {b}")
    if synth.get("tickers"):
        lines.append("")
        lines.append("**Tickers:** " + ", ".join(synth["tickers"][:15]))
    if synth.get("actions"):
        lines.append("")
        lines.append("**Actions:**")
        for a in synth["actions"][:5]:
            lines.append(f"→ {a}")
    if extra:
        lines.append("")
        lines.append(extra)
    lines.append("")
    lines.append("_Quiet intel · top-tier balanced mandate_")
    return "\n".join(lines)


def save_artifact(mode: str, payload: Dict[str, Any], synth: Dict[str, Any], report: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    OBS.mkdir(parents=True, exist_ok=True)
    day = _day()
    path = OUT / f"{mode}_{day}.json"
    path.write_text(json.dumps({"payload": payload, "synth": synth, "ts": _now()}, indent=2, default=str))
    (OUT / f"{mode}_{day}.md").write_text(report + "\n")
    (OBS / f"{mode}-{day}.md").write_text(report + "\n")
    return path


def run_mode(mode: str, force: bool = False) -> Tuple[str, bool]:
    """Returns (stdout_message, material). Empty message if quiet."""
    collectors = {
        "policy": collect_policy,
        "influencers": collect_influencers,
        "social": collect_social,
        "weather": collect_weather,
    }
    if mode == "morning":
        return run_morning(force=force)
    if mode == "all":
        msgs = []
        any_mat = False
        for m in ("policy", "influencers", "social", "weather"):
            msg, mat = run_mode(m, force=force)
            if msg:
                msgs.append(msg)
            any_mat = any_mat or mat
        return ("\n\n---\n\n".join(msgs) if msgs else "", any_mat)

    payload = collectors[mode]()
    synth = synthesize(mode, payload)
    material = bool(synth.get("material")) or force
    # weather: only alert if severe
    if mode == "weather" and not payload.get("alerts") and not force:
        save_artifact(mode, payload, synth, f"VOX Intel weather {_day()}: no severe alerts")
        return ("", False)

    # Social: only material if hot tickers overlap known liquid names or shock keywords
    if mode == "social" and not force:
        hot = {h["ticker"] for h in (payload.get("hot_tickers") or [])}
        interesting = hot & {
            "NVDA", "TSLA", "SPY", "QQQ", "AMD", "META", "AAPL", "MSFT", "GOOGL",
            "AMZN", "COST", "SPCX", "BTC", "ETH", "CRWD", "COIN", "MSTR", "PLTR",
            "GME", "AMC", "RDDT", "HOOD", "SMCI", "ARM", "AVGO", "TSM",
        }
        shock = any(
            k in (b or "").upper()
            for b in (synth.get("bullets") or [])
            for k in ("CRASH", "HALT", "BANKRUPT", "SQUEEZE", "FDA", "TARIFF")
        )
        if not interesting and not shock:
            synth["material"] = False
            report = format_telegram(mode, synth)
            save_artifact(mode, payload, synth, report)
            return ("", False)

    report = format_telegram(mode, synth)
    save_artifact(mode, payload, synth, report)
    if not material and not force:
        return ("", False)
    return (report, True)


def run_morning(force: bool = False) -> Tuple[str, bool]:
    # Load today's artifacts if present
    day = _day()
    parts = {}
    for m in ("policy", "influencers", "social", "weather"):
        p = OUT / f"{m}_{day}.json"
        if p.exists():
            try:
                parts[m] = json.loads(p.read_text()).get("synth")
            except Exception:
                pass
        else:
            # collect fresh
            msg, _ = run_mode(m, force=True)
            p = OUT / f"{m}_{day}.json"
            if p.exists():
                parts[m] = json.loads(p.read_text()).get("synth")

    ctx = load_vox_context()
    bundle = {"domain_synth": parts, "vox_context": ctx}
    synth = synthesize("morning", bundle)
    # Always produce morning brief on schedule
    material = True
    report = format_telegram("morning", synth)
    # add sector tape
    if ctx.get("sector_proxies"):
        report += "\n\n**Tape (1d):** " + ", ".join(
            f"{x['ticker']} {x['d1_pct']:+.1f}%" for x in ctx["sector_proxies"]
        )
    if ctx.get("top_positions"):
        report += "\n**Book top:** " + ", ".join(
            f"{p['ticker']}" for p in ctx["top_positions"][:8]
        )
    save_artifact("morning", bundle, synth, report)
    return (report, material)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "mode",
        choices=["policy", "influencers", "social", "weather", "morning", "all"],
    )
    ap.add_argument("--force", action="store_true", help="Always print even if low signal")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    msg, material = run_mode(args.mode, force=args.force or args.mode == "morning")
    if args.json:
        print(json.dumps({"material": material, "message": msg, "ts": _now()}))
        return 0
    # no_agent quiet pattern
    if msg:
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
