#!/usr/bin/env python3
"""
VOX Morning Context — daily research pack before Ops Card.

Runs ~06:15 CT M–F. Writes:
  Obsidian memory/brain/Morning-Context-LATEST.md
  + dated archive

Sources (no AI slop):
  - Book sleeves / AUM / top holdings (DB)
  - Benchmarks & oil proxy (Yahoo chart): SPY QQQ IWM XLE TLT GLD VIX BTC-USD
  - Held big movers (positions day_chg)
  - FMP free: market news + (mega) profiles when available
  - Last breaking artifact if present
  - Optional DeepSeek synthesis focused on THIS book (OpenRouter)

Quiet on Telegram by default (local). Ops Card embeds a short section.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT_LATEST = OBS / "Morning-Context-LATEST.md"
ARCH = OBS / "ops-archive"
BREAKING_DIR = OBS  # may vary

BENCH = ["SPY", "QQQ", "IWM", "XLE", "TLT", "GLD", "BTC-USD"]
# ^VIX often needs different symbol
VIX_SYMS = ["^VIX", "VIX"]


def db():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 35577)),
        dbname=os.environ.get("DB_NAME", "railway"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=20,
    )
    return conn, conn.cursor(cursor_factory=RealDictCursor)


def yahoo_quote(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from vox_price_quote import live_quote

        return live_quote(symbol)
    except Exception:
        pass
    # fallback chart
    try:
        from vox_pricing_refresh import yahoo_chart

        meta, bars = yahoo_chart(symbol, range_="5d", interval="1d")
        if not bars:
            return None
        last = float(bars[-1]["close"])
        prev = float(bars[-2]["close"]) if len(bars) >= 2 else last
        chg = 100 * (last - prev) / prev if prev else None
        return {"ticker": symbol, "price": last, "change_pct": chg, "prev_close": prev}
    except Exception:
        return None


def book_snapshot(cur) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT ticker,
               COALESCE(live_value_usd, live_value, 0)::float AS v,
               COALESCE(day_chg_pct, 0)::float AS day_chg,
               price_asof, price_source
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    aum = sum(float(r["v"] or 0) for r in rows) or 1.0
    crypto = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "BNB", "TRX", "BONK"}
    techish = {
        "AAPL",
        "MSFT",
        "NVDA",
        "GOOGL",
        "GOOG",
        "META",
        "AMZN",
        "AVGO",
        "AMD",
        "TSLA",
        "CRM",
        "ADBE",
        "ORCL",
        "PLTR",
        "MU",
        "SMCI",
        "ANET",
        "ALAB",
    }
    energy = {"XLE", "XOM", "CVX", "COP", "OXY", "SLB", "XOP", "USO"}
    sleeves = {"tech": 0.0, "crypto": 0.0, "energy": 0.0, "other": 0.0}
    for r in rows:
        t = (r["ticker"] or "").upper()
        if t in ("MIRROR_TOTAL", "CASH") or " " in t:
            continue
        w = 100 * float(r["v"] or 0) / aum
        if t in crypto:
            sleeves["crypto"] += w
        elif t in energy:
            sleeves["energy"] += w
        elif t in techish:
            sleeves["tech"] += w
        else:
            sleeves["other"] += w
    held = [r for r in rows if (r["ticker"] or "").upper() not in ("MIRROR_TOTAL", "CASH") and " " not in (r["ticker"] or "")]
    movers = sorted(held, key=lambda x: abs(float(x.get("day_chg") or 0)), reverse=True)[:12]
    top = sorted(held, key=lambda x: float(x.get("v") or 0), reverse=True)[:12]
    return {
        "aum": aum,
        "n": len(held),
        "sleeves": sleeves,
        "movers": movers,
        "top": top,
    }


def fmp_news(limit: int = 12) -> List[Dict[str, str]]:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return []
    url = f"https://financialmodelingprep.com/stable/news/stock-latest?page=0&limit={limit}&apikey={key}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
        if not isinstance(data, list):
            return []
        out = []
        for item in data[:limit]:
            out.append(
                {
                    "title": str(item.get("title") or "")[:160],
                    "symbol": str(item.get("symbol") or item.get("site") or "")[:20],
                    "published": str(item.get("publishedDate") or item.get("date") or "")[:19],
                    "source": "fmp",
                }
            )
        return out
    except Exception as e:
        return [{"title": f"(FMP news unavailable: {e})", "symbol": "", "published": "", "source": "fmp_err"}]


def fmp_general_news(limit: int = 8) -> List[Dict[str, str]]:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return []
    url = f"https://financialmodelingprep.com/stable/news/general-latest?page=0&limit={limit}&apikey={key}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
        if not isinstance(data, list):
            return []
        return [
            {
                "title": str(i.get("title") or "")[:160],
                "symbol": str(i.get("site") or "")[:20],
                "published": str(i.get("publishedDate") or "")[:19],
                "source": "fmp",
            }
            for i in data[:limit]
        ]
    except Exception:
        return []


def finnhub_general_news(limit: int = 12) -> List[Dict[str, str]]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    url = f"https://finnhub.io/api/v1/news?category=general&token={key}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
        if not isinstance(data, list):
            return []
        out = []
        for i in data[:limit]:
            out.append(
                {
                    "title": str(i.get("headline") or "")[:160],
                    "symbol": str(i.get("source") or "")[:20],
                    "published": str(i.get("datetime") or "")[:19],
                    "source": "finnhub",
                }
            )
        return [x for x in out if x["title"]]
    except Exception as e:
        return [{"title": f"(Finnhub news unavailable: {e})", "symbol": "", "published": "", "source": "finnhub_err"}]


def finnhub_company_news(symbols: List[str], days: int = 3, per: int = 3) -> List[Dict[str, str]]:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return []
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    out: List[Dict[str, str]] = []
    for sym in symbols[:12]:
        url = (
            f"https://finnhub.io/api/v1/company-news?symbol={sym}"
            f"&from={start.isoformat()}&to={end.isoformat()}&token={key}"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read().decode())
            if not isinstance(data, list):
                continue
            for i in data[:per]:
                out.append(
                    {
                        "title": str(i.get("headline") or "")[:160],
                        "symbol": sym,
                        "published": str(i.get("datetime") or "")[:19],
                        "source": "finnhub",
                    }
                )
        except Exception:
            continue
        time.sleep(0.05)
    return out


def gather_news(held_top: List[str]) -> tuple:
    """Prefer live Finnhub when FMP free tier is 402/empty."""
    stock = fmp_news(12)
    gen = fmp_general_news(8)
    fmp_dead = (
        not stock
        or (stock and "unavailable" in (stock[0].get("title") or "").lower())
        or (stock and "402" in (stock[0].get("title") or ""))
    )
    if fmp_dead:
        gen = finnhub_general_news(12)
        stock = finnhub_company_news(held_top, days=4, per=2)
        if not stock:
            stock = [{"title": "(no company headlines)", "symbol": "", "published": "", "source": "none"}]
    return stock, gen


def load_breaking_snippet() -> str:
    # prefer latest decision / report file
    candidates = [
        Path.home() / "Documents/Obsidian/VOX/vox/memory/decisions/Breaking-LATEST.md",
        OBS / "Breaking-LATEST.md",
        OBS / "breaking-latest.md",
        Path.home() / "Documents/Obsidian/VOX/vox/memory/intel/Breaking-LATEST.md",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 40:
            return p.read_text()[:1200]
    # scan ops-archive for breaking
    if ARCH.exists():
        files = sorted(ARCH.glob("*breaking*"), key=lambda x: x.stat().st_mtime, reverse=True)
        if files:
            return files[0].read_text()[:1200]
    return ""


def synthesize(context_md: str) -> str:
    """Optional DeepSeek pass — book-focused bullets only."""
    if os.environ.get("VOX_MORNING_NO_LLM") == "1":
        return ""
    try:
        from vox_utils import call_openrouter

        system = (
            "You are VOX morning analyst for a multi-broker portfolio control tower. "
            "Hygiene + structure only. No FOMO, no day-trade spam."
        )
        user = (
            "Using ONLY the context below, write 8-12 tight bullets:\n"
            "- What matters for THIS book today (tech/crypto/energy gaps, concentration)\n"
            "- Macro / oil / risk in plain language\n"
            "- What NOT to chase\n"
            "- 3 watch items before the open\n"
            "Max 250 words. If data is thin, say so.\n\nCONTEXT:\n"
            + context_md[:9000]
        )
        result = call_openrouter(
            system_prompt=system,
            user_prompt=user,
            model=os.environ.get("VOX_MORNING_MODEL", "deepseek/deepseek-v4-flash"),
            max_tokens=500,
            temperature=0.2,
            script_name="vox_morning_context",
            notes="morning research pack",
        )
        if isinstance(result, dict):
            # common shapes
            for k in ("content", "text", "response"):
                if result.get(k):
                    return str(result[k]).strip()
            choices = result.get("choices") or []
            if choices:
                return str((choices[0].get("message") or {}).get("content") or "").strip()
            # maybe message field
            if result.get("message"):
                return str(result["message"]).strip()
        return str(result or "").strip()
    except Exception as e:
        return f"(synthesis skipped: {e})"


def fmt_pct(x) -> str:
    try:
        return f"{float(x):+.1f}%"
    except Exception:
        return "n/a"


def main() -> int:
    now = datetime.now(timezone.utc)
    OBS.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)

    # benchmarks
    bench_lines = []
    bench_data = {}
    for s in BENCH + VIX_SYMS:
        q = yahoo_quote(s)
        time.sleep(0.15)
        if not q or not q.get("price"):
            continue
        if s.startswith("^") and "VIX" in s:
            key = "VIX"
        else:
            key = s
        if key in bench_data and key == "VIX":
            continue
        bench_data[key] = q
        bench_lines.append(
            f"| {key} | {q['price']:.2f} | {fmt_pct(q.get('change_pct'))} |"
        )

    # book
    book = {"aum": 0, "n": 0, "sleeves": {}, "movers": [], "top": []}
    try:
        conn, cur = db()
        book = book_snapshot(cur)
        conn.close()
    except Exception as e:
        book["error"] = str(e)

    # held top tickers for company news
    held_syms = []
    for r in book.get("top") or []:
        if isinstance(r, dict) and r.get("ticker"):
            held_syms.append(str(r["ticker"]).upper())
        elif isinstance(r, (list, tuple)) and r:
            held_syms.append(str(r[0]).upper())
    if not held_syms:
        held_syms = ["GOOGL", "NVDA", "TSLA", "AMD", "META", "MSFT"]
    stock_news, gen_news = gather_news(held_syms)
    breaking = load_breaking_snippet()

    # raw context for LLM
    raw_bits = [
        f"Date UTC: {now.isoformat()}",
        f"AUM: {book.get('aum')} n={book.get('n')} sleeves={book.get('sleeves')}",
        "Benchmarks: "
        + ", ".join(
            f"{k} {v.get('price')} ({fmt_pct(v.get('change_pct'))})"
            for k, v in bench_data.items()
        ),
        "Top holdings: "
        + ", ".join(
            f"{r['ticker']} ${float(r['v']):.0f} d={fmt_pct(r.get('day_chg'))}"
            for r in book.get("top") or []
        ),
        "Movers: "
        + ", ".join(
            f"{r['ticker']} {fmt_pct(r.get('day_chg'))}"
            for r in book.get("movers") or []
        ),
        "Stock news: " + " | ".join(n["title"] for n in stock_news[:8]),
        "General news: " + " | ".join(n["title"] for n in gen_news[:6]),
        "Breaking snippet: " + breaking[:500],
    ]
    synth = synthesize("\n".join(raw_bits))

    sleeves = book.get("sleeves") or {}
    lines = [
        f"# Morning Context — {now.strftime('%Y-%m-%d')}",
        "",
        f"_Generated {now.strftime('%Y-%m-%d %H:%M UTC')} · research pack · not auto-trade_",
        "",
        "## Book",
        f"- AUM ~**${float(book.get('aum') or 0):,.0f}** · **{book.get('n')}** names",
        f"- Tech ~**{sleeves.get('tech', 0):.0f}%** · Crypto ~**{sleeves.get('crypto', 0):.0f}%** · Energy ~**{sleeves.get('energy', 0):.0f}%**",
        "",
        "## Markets (Yahoo day%)",
        "| Ticker | Last | Day% |",
        "|--------|-----:|-----:|",
        *bench_lines,
        "",
        "## Held movers (abs day%)",
    ]
    for r in book.get("movers") or []:
        lines.append(
            f"- **{r['ticker']}** {fmt_pct(r.get('day_chg'))} · ${float(r['v']):,.0f}"
        )
    if not book.get("movers"):
        lines.append("- (none / no day_chg yet — pre-market)")

    lines += ["", "## Top holdings"]
    for r in book.get("top") or []:
        lines.append(
            f"- {r['ticker']}: ${float(r['v']):,.0f} ({100*float(r['v'])/max(float(book.get('aum') or 1),1):.1f}%)"
        )

    lines += ["", "## News (Finnhub/FMP)"]
    srcs = sorted({n.get("source") or "?" for n in (stock_news + gen_news) if n.get("source")})
    if srcs:
        lines.append(f"_sources: {', '.join(srcs)}_")
    for n in stock_news[:10]:
        if n.get("title"):
            lines.append(f"- [{n.get('symbol') or '—'}] {n['title']}")
    if gen_news:
        lines.append("")
        lines.append("### General")
        for n in gen_news[:6]:
            if n.get("title"):
                lines.append(f"- {n['title']}")

    if breaking:
        lines += ["", "## Prior breaking snippet", "```", breaking[:900], "```"]

    # Intel spine digest (if present)
    intel = OBS / "Intel-Digest-LATEST.md"
    if intel.exists():
        ibody = [ln for ln in intel.read_text(errors="replace").splitlines() if ln.strip()]
        snip = []
        grab = False
        for ln in ibody:
            if "Book-relevant" in ln:
                grab = True
                continue
            if grab and ln.startswith("## ") and "Book" not in ln:
                break
            if grab:
                snip.append(ln)
            if len(snip) >= 8:
                break
        if snip:
            lines += ["", "## Intel spine digest (soft)", *snip[:8]]

    if synth:
        lines += ["", "## Analyst synthesis (DeepSeek · book-focused)", synth, ""]

    lines += [
        "",
        "## How to use",
        "- Soft context only — **Ops Card** still owns actions",
        "- X deep-dive: ask Hermes `x_search` on themes above",
        "- Do not chase overnight social narratives",
        "",
    ]

    text = "\n".join(lines) + "\n"
    OUT_LATEST.write_text(text)
    arch_path = ARCH / f"Morning-Context-{now.strftime('%Y-%m-%d')}.md"
    arch_path.write_text(text)

    # short stdout for cron log
    print(f"VOX MORNING {now.strftime('%Y-%m-%d')}")
    print(
        f"AUM ${float(book.get('aum') or 0):,.0f} · Tech {sleeves.get('tech',0):.0f}% · Energy {sleeves.get('energy',0):.0f}% · Crypto {sleeves.get('crypto',0):.0f}%"
    )
    print("Bench:", " · ".join(f"{k} {fmt_pct(v.get('change_pct'))}" for k, v in list(bench_data.items())[:6]))
    print(f"News {len(stock_news)}+{len(gen_news)} · synth={'yes' if synth and not synth.startswith('(') else 'no'}")
    print("Full:", OUT_LATEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
