#!/usr/bin/env python3
"""VOX Intelligence Suite — multi-domain research with quiet alerts.

Modes:
  policy     — Trump / tariffs / policy + markets (Google News RSS + synthesis)
  influencers— key X/market voices via news RSS + optional X when available
  social     — Reddit WSB/stocks RSS + retail sentiment synthesis
  weather    — NOAA alerts → equity/sector map
  breaking   — shock monitor (Trump/war/Hormuz/oil/disaster) + portfolio impact
  morning    — merge all + VOX DB (macro/sector/insider/portfolio) → one brief
  all        — run policy+influencers+social+weather+breaking collectors only

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

# Macro-shock themes → queries + sleeve/sector proxies for portfolio mapping
BREAKING_THEMES = {
    "trump_policy": {
        "queries": [
            "Trump executive order markets",
            "Trump tariff announcement stocks",
            "Trump Fed OR Warsh markets",
        ],
        "keywords": ["trump", "tariff", "executive order", "white house", "trade war"],
        "severity_boost": 1,
        "sleeves": ["policy", "tech", "semis", "china"],
        "proxies": ["SMH", "QQQ", "FXI", "EEM"],
    },
    "war_geopolitics": {
        "queries": [
            "war markets oil defense stocks",
            "Israel Iran conflict markets",
            "Russia Ukraine escalation oil",
            "Taiwan China military markets",
        ],
        "keywords": ["war", "missile", "invasion", "airstrike", "escalation", "conflict", "military"],
        "severity_boost": 2,
        "sleeves": ["defense", "energy", "risk_off"],
        "proxies": ["XLE", "ITA", "GLD", "TLT"],
    },
    "hormuz_oil": {
        "queries": [
            "Strait of Hormuz oil disruption",
            "Hormuz shipping blockade oil price",
            "Persian Gulf oil tanker attack",
            "Saudi Aramco Hormuz oil supply",
        ],
        "keywords": ["hormuz", "strait of hormuz", "oil supply", "tanker", "persian gulf", "brent", "crude spike"],
        "severity_boost": 3,
        "sleeves": ["energy", "shipping", "inflation"],
        "proxies": ["XLE", "XOM", "CVX", "USO", "BNO"],
    },
    "oil_energy_shock": {
        "queries": [
            "oil price spike markets",
            "OPEC emergency meeting oil",
            "crude oil supply cut markets",
        ],
        "keywords": ["oil price", "brent", "wti", "opec", "crude", "energy crisis"],
        "severity_boost": 2,
        "sleeves": ["energy", "inflation", "airlines"],
        "proxies": ["XLE", "XOM", "CVX", "DAL", "UAL"],
    },
    "natural_disaster": {
        "queries": [
            "hurricane landfall oil refinery",
            "earthquake tsunami markets",
            "major wildfire california markets",
            "catastrophic flood insurance markets",
        ],
        "keywords": ["hurricane", "earthquake", "tsunami", "wildfire", "catastrophic", "landfall", "category 4", "category 5"],
        "severity_boost": 2,
        "sleeves": ["insurance", "utilities", "energy", "retail"],
        "proxies": ["PGR", "CB", "ALL", "XLU", "HD"],
    },
    "market_structure_shock": {
        "queries": [
            "circuit breaker stock market halt",
            "bank failure markets",
            "emergency Fed intervention markets",
            "flash crash markets",
        ],
        "keywords": ["circuit breaker", "trading halt", "bank failure", "emergency rate", "flash crash", "liquidity crisis"],
        "severity_boost": 3,
        "sleeves": ["risk_off", "financials", "broad_market"],
        "proxies": ["SPY", "XLF", "TLT", "GLD"],
    },
}

# Holding keyword → theme exposure (substring match on ticker or known map)
HOLDING_THEME_HINTS = {
    # energy / oil beta
    "XOM": ["hormuz_oil", "oil_energy_shock", "war_geopolitics"],
    "CVX": ["hormuz_oil", "oil_energy_shock", "war_geopolitics"],
    "XLE": ["hormuz_oil", "oil_energy_shock", "war_geopolitics"],
    "OXY": ["hormuz_oil", "oil_energy_shock"],
    "COP": ["hormuz_oil", "oil_energy_shock"],
    "VLO": ["hormuz_oil", "oil_energy_shock", "natural_disaster"],
    "MPC": ["hormuz_oil", "oil_energy_shock", "natural_disaster"],
    "PSX": ["hormuz_oil", "oil_energy_shock", "natural_disaster"],
    # crypto risk-on
    "BTC": ["market_structure_shock", "trump_policy"],
    "BTC-USD": ["market_structure_shock", "trump_policy"],
    "ETH": ["market_structure_shock"],
    "ETH-USD": ["market_structure_shock"],
    "XRP": ["market_structure_shock", "trump_policy"],
    "TRX": ["market_structure_shock"],
    "BNB": ["market_structure_shock"],
    "COIN": ["market_structure_shock", "trump_policy"],
    "MSTR": ["market_structure_shock"],
    # tech / semis / AI
    "NVDA": ["trump_policy", "war_geopolitics"],
    "AMD": ["trump_policy", "war_geopolitics"],
    "TSM": ["trump_policy", "war_geopolitics"],
    "SMH": ["trump_policy", "war_geopolitics"],
    "AVGO": ["trump_policy"],
    "META": ["trump_policy"],
    "QQQ": ["trump_policy", "market_structure_shock"],
    "SPY": ["market_structure_shock", "trump_policy", "war_geopolitics"],
    "VOO": ["market_structure_shock", "trump_policy"],
    "TSLA": ["trump_policy"],
    "SPCX": ["trump_policy"],
    # defense
    "LMT": ["war_geopolitics"],
    "RTX": ["war_geopolitics"],
    "NOC": ["war_geopolitics"],
    "GD": ["war_geopolitics"],
    "PLTR": ["war_geopolitics"],
    # utilities / insurers
    "NEE": ["natural_disaster"],
    "DUK": ["natural_disaster"],
    "SO": ["natural_disaster"],
    "CEG": ["natural_disaster"],
    "VST": ["natural_disaster"],
    "PGR": ["natural_disaster"],
    "CB": ["natural_disaster"],
    "ALL": ["natural_disaster"],
    # china ADRs
    "BIDU": ["trump_policy", "war_geopolitics"],
    "BABA": ["trump_policy", "war_geopolitics"],
    "PDD": ["trump_policy"],
    "JD": ["trump_policy"],
}

DEDUPE_PATH = OUT / "breaking_dedupe.json"


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



def collect_breaking() -> Dict[str, Any]:
    """Scan shock themes (Trump/war/Hormuz/oil/disaster/structure) via Google News RSS."""
    themes_out: Dict[str, Any] = {}
    flat: List[Dict[str, str]] = []
    for theme, cfg in BREAKING_THEMES.items():
        items: List[Dict[str, str]] = []
        # Cap queries for cron latency (first 2 per theme are highest-signal)
        for q in cfg["queries"][:2]:
            for it in google_news(q, 5):
                it = dict(it)
                it["theme"] = theme
                it["query"] = q
                items.append(it)
                flat.append(it)
        # de-dupe within theme by title
        seen = set()
        uniq = []
        for it in items:
            k = (it.get("title") or "").lower().strip()
            if not k or k in seen:
                continue
            seen.add(k)
            uniq.append(it)
        themes_out[theme] = {
            "count": len(uniq),
            "items": uniq[:12],
            "severity_boost": cfg["severity_boost"],
            "proxies": cfg["proxies"],
            "sleeves": cfg["sleeves"],
        }
    return {
        "type": "breaking",
        "ts": _now(),
        "themes": themes_out,
        "items": flat[:80],
        "theme_counts": {k: v["count"] for k, v in themes_out.items()},
    }


def load_full_portfolio() -> List[Dict[str, Any]]:
    """All active positions with weights for shock impact."""
    rows: List[Dict[str, Any]] = []
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        pwd = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
        if not pwd:
            envp = Path.home() / ".hermes" / ".env"
            if envp.exists():
                for line in envp.read_text().splitlines():
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
        cur.execute(
            """
            SELECT ticker,
                   COALESCE(shares, 0) AS shares,
                   COALESCE(live_value_usd, live_value, 0) AS v,
                   grade, council
            FROM positions
            WHERE (COALESCE(shares,0) > 0 OR (ticker='MIRROR_TOTAL' AND COALESCE(live_value_usd,0)>0))
              AND COALESCE(live_value_usd, live_value, 0) > 0
            ORDER BY v DESC NULLS LAST
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        return [{"_error": str(e)}]
    total = sum(float(r.get("v") or 0) for r in rows) or 1.0
    for r in rows:
        r["weight_pct"] = round(100.0 * float(r.get("v") or 0) / total, 2)
        r["v"] = float(r.get("v") or 0)
    return rows


def _headline_theme_hits(title: str, summary: str = "") -> List[str]:
    text = f"{title} {summary}".lower()
    hits = []
    for theme, cfg in BREAKING_THEMES.items():
        if any(kw in text for kw in cfg["keywords"]):
            hits.append(theme)
    return hits


def score_breaking_raw(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic severity before LLM — keyword + multi-source clustering."""
    theme_scores: Dict[str, float] = {t: 0.0 for t in BREAKING_THEMES}
    scored_items: List[Dict[str, Any]] = []
    critical_hits = 0
    for theme, block in (payload.get("themes") or {}).items():
        boost = float(block.get("severity_boost") or 1)
        for it in block.get("items") or []:
            title = it.get("title") or ""
            summary = it.get("summary") or ""
            hits = _headline_theme_hits(title, summary)
            if not hits:
                hits = [theme]
            tl = f"{title} {summary}".lower()
            # Base low; only escalation language lifts score materially
            base = 0.6
            if any(
                w in tl
                for w in (
                    "blockade",
                    "closed",
                    "closure",
                    "attack",
                    "invasion",
                    "airstrike",
                    "emergency",
                    "halt",
                    "category 5",
                    "category 4",
                    "strike on",
                    "strikes on",
                    "missile",
                    "centcom",
                    "landfall",
                    "circuit breaker",
                    "bank failure",
                    "nuclear",
                )
            ):
                base += 3.5
                critical_hits += 1
            elif any(w in tl for w in ("disruption", "escalat", "war", "tariff", "hurricane", "hormuz", "opec cut")):
                base += 1.5
            if any(w in tl for w in ("could", "may", "might", "talks", "risk of", "warns")):
                base *= 0.55  # soft language discount
            score = base * (1.0 + 0.15 * min(boost, 3))
            for h in hits:
                theme_scores[h] = theme_scores.get(h, 0) + score
            scored_items.append({**it, "themes": hits, "shock_score": round(score, 2)})
    scored_items.sort(key=lambda x: -x.get("shock_score", 0))
    # Normalize: average-ish of top theme rather than unbounded sum
    top_theme_score = max(theme_scores.values()) if theme_scores else 0
    # Cap inflation from many weak headlines
    top_item = scored_items[0]["shock_score"] if scored_items else 0
    combined = 0.55 * top_theme_score + 0.45 * (top_item * 3)
    if critical_hits >= 3 and top_item >= 3.0:
        severity = "critical"
    elif combined >= 14 or (critical_hits >= 2 and top_item >= 2.5):
        severity = "high"
    elif combined >= 7 or critical_hits >= 1:
        severity = "med"
    else:
        severity = "low"
    active = sorted(
        [{"theme": t, "score": round(s, 2)} for t, s in theme_scores.items() if s >= 3.0],
        key=lambda x: -x["score"],
    )
    return {
        "theme_scores": {k: round(v, 2) for k, v in theme_scores.items()},
        "active_themes": active,
        "severity_heuristic": severity,
        "top_items": scored_items[:15],
        "top_score": round(combined, 2),
        "critical_hits": critical_hits,
    }


def map_portfolio_impact(
    portfolio: List[Dict[str, Any]],
    active_themes: List[Dict[str, Any]],
    synth_tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Map active shock themes onto held names + weights."""
    if portfolio and portfolio[0].get("_error"):
        return {"error": portfolio[0]["_error"], "exposed": [], "exposed_weight_pct": 0.0}
    theme_set = {a["theme"] for a in active_themes}
    synth_tickers = {t.upper() for t in (synth_tickers or [])}
    exposed = []
    for p in portfolio:
        t = (p.get("ticker") or "").upper()
        if t in ("MIRROR_TOTAL",):
            continue
        themes = set(HOLDING_THEME_HINTS.get(t, []))
        # crypto/usd pairs
        base = t.replace("-USD", "")
        if base != t:
            themes |= set(HOLDING_THEME_HINTS.get(base, []))
            themes |= set(HOLDING_THEME_HINTS.get(t, []))
        # generic sleeves
        if any(x in t for x in ("BTC", "ETH", "XRP", "DOGE", "SOL", "BNB", "TRX", "HBAR")):
            themes |= {"market_structure_shock", "trump_policy"}
        if t in synth_tickers:
            # LLM named the ticker — only attach high-signal themes for that name, not all themes
            if t in ("SPY", "VOO", "QQQ", "IWM"):
                themes |= theme_set & {
                    "market_structure_shock",
                    "trump_policy",
                    "war_geopolitics",
                    "oil_energy_shock",
                    "hormuz_oil",
                }
            else:
                themes |= theme_set & set(HOLDING_THEME_HINTS.get(t, []))
                if not themes:
                    themes |= theme_set & {"trump_policy", "war_geopolitics", "market_structure_shock"}
        hit = sorted(themes & theme_set)
        if not hit:
            continue
        exposed.append(
            {
                "ticker": t,
                "weight_pct": p.get("weight_pct", 0),
                "value": p.get("v", 0),
                "grade": p.get("grade"),
                "council": p.get("council"),
                "themes": hit,
            }
        )
    exposed.sort(key=lambda x: -float(x.get("weight_pct") or 0))
    weight = round(sum(float(x.get("weight_pct") or 0) for x in exposed), 2)
    # decision rules
    decisions = []
    if weight >= 15 or any(a.get("score", 0) >= 10 for a in active_themes):
        decisions.append("PORTFOLIO DIAGNOSTIC REQUIRED — open sleeve review")
    if "hormuz_oil" in theme_set or "oil_energy_shock" in theme_set:
        decisions.append("Energy/oil shock: stress XOM/CVX/crypto beta; do not auto-sell multi-broker names")
    if "war_geopolitics" in theme_set:
        decisions.append("Geo risk-off: check defense vs growth beta; barbell per conflict playbook")
    if "trump_policy" in theme_set:
        decisions.append("Policy/tariff: re-check semis/China ADRs (TSM/AMD/BIDU) and SPY/QQQ beta")
    if "natural_disaster" in theme_set:
        decisions.append("Disaster: insurers/utilities/refiners path — monitor only unless landfall critical")
    if "market_structure_shock" in theme_set:
        decisions.append("Structure shock: size risk, halt new aggression until tape stabilizes")
    # mandate filter note
    big = [e for e in exposed if float(e.get("weight_pct") or 0) >= 2.5]
    return {
        "exposed": exposed[:25],
        "exposed_weight_pct": weight,
        "material_holdings_ge_2_5pct": big,
        "decisions": decisions,
        "active_theme_names": sorted(theme_set),
    }


def load_breaking_dedupe() -> Dict[str, Any]:
    if DEDUPE_PATH.exists():
        try:
            return json.loads(DEDUPE_PATH.read_text())
        except Exception:
            pass
    return {"fingerprints": {}, "last_alert_ts": None}


def save_breaking_dedupe(state: Dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # prune > 36h
    now = time.time()
    fps = state.get("fingerprints") or {}
    state["fingerprints"] = {k: v for k, v in fps.items() if now - float(v) < 36 * 3600}
    DEDUPE_PATH.write_text(json.dumps(state, indent=2))


def breaking_fingerprint(synth: Dict[str, Any], impact: Dict[str, Any]) -> str:
    parts = [
        synth.get("headline") or "",
        ",".join(sorted(impact.get("active_theme_names") or [])),
        ",".join(sorted(t.get("ticker", "") for t in (impact.get("material_holdings_ge_2_5pct") or [])[:8])),
        str(synth.get("severity") or ""),
    ]
    raw = "|".join(parts).lower()
    return re.sub(r"\s+", " ", raw)[:240]


def run_breaking(force: bool = False) -> Tuple[str, bool]:
    payload = collect_breaking()
    raw = score_breaking_raw(payload)
    portfolio = load_full_portfolio()
    # LLM synth with raw scores
    synth_payload = {
        "raw_scores": raw,
        "theme_counts": payload.get("theme_counts"),
        "top_items": raw.get("top_items"),
        "portfolio_sample": [
            {k: p.get(k) for k in ("ticker", "weight_pct", "grade", "council", "v")}
            for p in portfolio[:20]
            if not p.get("_error")
        ],
    }
    synth = synthesize("breaking", synth_payload)
    # elevate severity from heuristic if higher
    order = {"low": 0, "med": 1, "high": 2, "critical": 3}
    h = raw.get("severity_heuristic") or "low"
    s = (synth.get("severity") or "low").lower()
    if s not in order:
        s = "low"
    if order.get(h, 0) > order.get(s, 0):
        synth["severity"] = h
        s = h
    impact = map_portfolio_impact(
        portfolio,
        raw.get("active_themes") or [],
        synth.get("tickers") or [],
    )
    # Material rules: alert Telegram only for high/critical, or med with real book impact
    sev_ok = s in ("high", "critical")
    med_with_book = s == "med" and (
        (impact.get("exposed_weight_pct") or 0) >= 12.0
        or len(impact.get("material_holdings_ge_2_5pct") or []) >= 2
    )
    material = bool(sev_ok or med_with_book or force)
    if s == "critical":
        material = True
    # Ignore pure low-signal
    if s == "low" and not force:
        material = False

    # merge decisions into actions
    actions = list(synth.get("actions") or [])
    for d in impact.get("decisions") or []:
        if d not in actions:
            actions.append(d)
    synth["actions"] = actions[:8]
    synth["portfolio_impact"] = impact
    synth["raw_scores"] = {
        "severity_heuristic": raw.get("severity_heuristic"),
        "top_score": raw.get("top_score"),
        "active_themes": raw.get("active_themes"),
    }

    report = format_telegram("breaking", synth)
    # portfolio block
    if impact.get("exposed"):
        report += "\n\n**Portfolio exposure to shock themes:** "
        report += f"`{impact.get('exposed_weight_pct', 0):.1f}%` book weight\n"
        for e in impact["exposed"][:10]:
            report += (
                f"• **{e['ticker']}** {e.get('weight_pct', 0):.1f}% "
                f"g{e.get('grade')} {e.get('council')} — {', '.join(e.get('themes') or [])}\n"
            )
        big = impact.get("material_holdings_ge_2_5pct") or []
        if big:
            report += "\n**≥2.5% names in blast radius:** " + ", ".join(
                f"{x['ticker']} ({x['weight_pct']}%)" for x in big
            )
    if impact.get("decisions"):
        report += "\n\n**Decision hooks:**\n"
        for d in impact["decisions"]:
            report += f"→ {d}\n"
    report += "\n_Breaking shock monitor · acts only on material portfolio impact_"

    # dedupe
    state = load_breaking_dedupe()
    fp = breaking_fingerprint(synth, impact)
    last = (state.get("fingerprints") or {}).get(fp)
    is_dup = last is not None and (time.time() - float(last) < 6 * 3600)
    if is_dup and not force and material:
        # still save artifact, stay quiet on telegram
        save_artifact("breaking", {"payload": payload, "raw": raw, "impact": impact}, synth, report)
        save_breaking_decision(synth, impact, quiet=True)
        return ("", False)

    save_artifact("breaking", {"payload": payload, "raw": raw, "impact": impact}, synth, report)
    save_breaking_decision(synth, impact, quiet=not material)

    if material:
        state.setdefault("fingerprints", {})[fp] = time.time()
        state["last_alert_ts"] = _now()
        save_breaking_dedupe(state)
        return (report, True)
    # low signal archive only
    return ("", False)


def save_breaking_decision(synth: Dict[str, Any], impact: Dict[str, Any], quiet: bool = False) -> None:
    """Write Obsidian decision note so compound/diagnostics can act."""
    day = _day()
    dec_dir = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    path = dec_dir / f"Breaking-{day}.md"
    lines = [
        "---",
        f"type: breaking_shock",
        f"generated_at: \"{_now()}\"",
        f"severity: \"{synth.get('severity', 'low')}\"",
        f"material: {str(bool(synth.get('material', True))).lower()}",
        f"exposed_weight_pct: {impact.get('exposed_weight_pct', 0)}",
        f"quiet: {str(quiet).lower()}",
        "---",
        "",
        f"# Breaking Shock Diagnostic — {day}",
        "",
        f"**Headline:** {synth.get('headline', '')}",
        f"**Severity:** `{synth.get('severity', 'low')}`",
        f"**Exposed book weight:** {impact.get('exposed_weight_pct', 0)}%",
        "",
        "## Themes",
    ]
    for a in (synth.get("raw_scores") or {}).get("active_themes") or impact.get("active_theme_names") or []:
        if isinstance(a, dict):
            lines.append(f"- {a.get('theme')}: score {a.get('score')}")
        else:
            lines.append(f"- {a}")
    lines += ["", "## Portfolio blast radius", ""]
    for e in (impact.get("exposed") or [])[:15]:
        lines.append(
            f"- [[{e['ticker']}]] {e.get('weight_pct')}% grade {e.get('grade')} "
            f"{e.get('council')} — {', '.join(e.get('themes') or [])}"
        )
    lines += ["", "## Decision hooks", ""]
    for d in impact.get("decisions") or synth.get("actions") or []:
        lines.append(f"- [ ] {d}")
    lines += ["", "## Bullets", ""]
    for b in (synth.get("bullets") or [])[:10]:
        lines.append(f"- {b}")
    path.write_text("\n".join(lines) + "\n")
    # also rolling latest pointer
    (dec_dir / "Breaking-LATEST.md").write_text(path.read_text())


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
        "Ignore noise. Prefer quality compounders + sector leaders over meme noise unless extreme. "
        "If mode=breaking: severity critical/high for Hormuz closure, war escalation, major disaster landfall, "
        "market halt/bank failure; list concrete held-ticker risks and actions. Never invent holdings."
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
    if mode == "morning":
        parts = payload.get("domain_synth") or {}
        for name, synth in parts.items():
            if not isinstance(synth, dict):
                continue
            if synth.get("headline"):
                bullets.append(f"[{name}] {synth.get('headline')}")
            for b in (synth.get("bullets") or [])[:2]:
                bullets.append(f"[{name}] {b}")
            tickers.extend(synth.get("tickers") or [])
        ctx = payload.get("vox_context") or {}
        for s in (ctx.get("sector_proxies") or [])[:4]:
            bullets.append(f"Tape {s.get('ticker')}: {s.get('d1_pct')}%")
        return {
            "material": True,
            "severity": "med" if bullets else "low",
            "bullets": bullets[:8] or ["Markets open — review sleeve drift + quality core"],
            "tickers": sorted(set(tickers))[:15],
            "actions": ["Review portfolio follow-up", "Check policy/tariff headlines"],
            "headline": "Morning intelligence merge",
            "err": err,
        }
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
    if mode == "breaking":
        raw = payload.get("raw_scores") or {}
        for it in (raw.get("top_items") or payload.get("top_items") or [])[:6]:
            bullets.append(it.get("title") or str(it)[:120])
            tickers.extend(it.get("themes") or [])
        for a in raw.get("active_themes") or []:
            bullets.append(f"Theme {a.get('theme')}: score {a.get('score')}")
        for p in (payload.get("portfolio_sample") or [])[:5]:
            tickers.append(p.get("ticker") or "")
        sev = raw.get("severity_heuristic") or ("med" if bullets else "low")
        return {
            "material": sev in ("high", "critical", "med"),
            "severity": sev,
            "bullets": bullets[:8] or ["No material macro shocks detected"],
            "tickers": [t for t in tickers if t][:15],
            "actions": ["Run portfolio diagnostic if severity high+"],
            "headline": f"Breaking shocks — {sev}",
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
        "breaking": "🚨",
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
        "breaking": collect_breaking,
    }
    if mode == "morning":
        return run_morning(force=force)
    if mode == "breaking":
        return run_breaking(force=force)
    if mode == "all":
        msgs = []
        any_mat = False
        for m in ("policy", "influencers", "social", "weather", "breaking"):
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
    for m in ("policy", "influencers", "social", "weather", "breaking"):
        p = OUT / f"{m}_{day}.json"
        if p.exists():
            try:
                parts[m] = json.loads(p.read_text()).get("synth")
            except Exception:
                pass
        else:
            # collect fresh (breaking not forced — keep quiet unless material)
            msg, _ = run_mode(m, force=(m != "breaking"))
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
        choices=["policy", "influencers", "social", "weather", "breaking", "morning", "all"],
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
