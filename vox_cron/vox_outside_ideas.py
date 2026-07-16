#!/usr/bin/env python3
"""
VOX Outside-Book Ideas Scanner (JOS-208)
- Not-held only
- Anti-chase: block extended 3m / hot 1w unless BUY_DIPS
- Hygiene grades: ranking only, not auto-deploy
- Writes Outside-Ideas-LATEST.md + JSON
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))

DB = {
    "host": os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
    "port": int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
    "dbname": os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
    "user": os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
}

OBS = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "brain"
OUT_JSON = Path.home() / ".hermes" / "cron" / "output" / "brain"
CRYPTO_LIKE = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "BONK",
    "AVAX", "DOT", "LINK", "MATIC", "SHIB", "PEPE", "WIF", "PENGU", "MORPHO",
    "VANA", "VAULTA",
}


def connect():
    return psycopg2.connect(connect_timeout=20, **DB)


def held_tickers(cur):
    cur.execute(
        """
        SELECT DISTINCT UPPER(ticker) t
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 50
           OR COALESCE(shares, 0) > 0
        """
    )
    return {r["t"] for r in cur.fetchall() if r["t"]}


def ret_map(cur, days: int):
    """ticker -> return pct over ~days using price_history closes."""
    cur.execute(
        f"""
        WITH ranked AS (
          SELECT ticker, date, close,
                 ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) rn
          FROM price_history
          WHERE close IS NOT NULL AND close > 0
        ),
        latest AS (SELECT ticker, close AS c0 FROM ranked WHERE rn = 1),
        past AS (
          SELECT DISTINCT ON (ticker) ticker, close AS c1
          FROM price_history
          WHERE date <= CURRENT_DATE - INTERVAL '{int(days)} days'
            AND close IS NOT NULL AND close > 0
          ORDER BY ticker, date DESC
        )
        SELECT l.ticker, ((l.c0 - p.c1) / p.c1) * 100.0 AS ret
        FROM latest l
        JOIN past p ON p.ticker = l.ticker
        """
    )
    out = {}
    for r in cur.fetchall():
        try:
            out[r["ticker"].upper()] = float(r["ret"])
        except Exception:
            pass
    return out


def load_fmp_scores(cur) -> Dict[str, float]:
    try:
        cur.execute(
            """
            SELECT DISTINCT ON (ticker) UPPER(ticker) t, fund_score
            FROM fmp_fundamentals
            WHERE fund_score IS NOT NULL
            ORDER BY ticker, updated_at DESC NULLS LAST
            """
        )
        return {r["t"]: float(r["fund_score"]) for r in cur.fetchall() if r.get("t")}
    except Exception:
        return {}


def load_candidates(cur):
    cur.execute(
        """
        WITH latest AS (
          SELECT DISTINCT ON (ticker)
            ticker, vox_grade, technical_score, fundamental_score,
            macro_score, sentiment_score, action, generated_at, sector
          FROM vox_grades
          ORDER BY ticker, generated_at DESC
        )
        SELECT * FROM latest
        WHERE vox_grade IS NOT NULL
          AND generated_at > NOW() - INTERVAL '10 days'
          AND vox_grade >= 62
        ORDER BY vox_grade DESC
        LIMIT 400
        """
    )
    return cur.fetchall()


def research_score(row):
    t = float(row.get("technical_score") or 50)
    f = float(row.get("fundamental_score") or 50)
    m = float(row.get("macro_score") or 50)
    s = float(row.get("sentiment_score") or 50)
    g = float(row.get("vox_grade") or 50)
    # same blend as portfolio weekly grade spirit
    return 0.30 * t + 0.25 * f + 0.20 * m + 0.15 * s + 0.10 * g


def classify(row, ret_5, ret_63, fmp_score=None):
    t = row["ticker"].upper()
    r5 = ret_5.get(t)
    r63 = ret_63.get(t)
    chase = False
    flags = []
    if r63 is not None and r63 >= 50:
        chase = True
        flags.append(f"3m +{r63:.0f}%")
    if r5 is not None and r5 >= 12:
        chase = True
        flags.append(f"1w +{r5:.0f}%")
    # Extended runners: 3m still hot even if not ≥50, especially tech-hot
    tech = float(row.get("technical_score") or 50)
    if r63 is not None and r63 >= 35 and tech >= 85:
        chase = True
        flags.append(f"extended 3m +{r63:.0f}% tech{tech:.0f}")
    # Catching knives: sharp 1w dump after prior extension is not free money
    if r5 is not None and r5 <= -15 and r63 is not None and r63 >= 25:
        chase = True
        flags.append(f"knife 1w {r5:.0f}% after 3m +{r63:.0f}%")
    # Missing returns → cannot prove not-chase; never Tier A
    missing_ret = r63 is None and r5 is None
    if missing_ret:
        flags.append("no_price_hist")

    g = float(row.get("vox_grade") or 0)
    rs = research_score(row)
    fund = float(row.get("fundamental_score") or 50)
    tech = float(row.get("technical_score") or 50)
    # Tech 100 with no fund is often momentum cosplay
    if tech >= 95 and fund < 55:
        flags.append("tech_hot_fund_soft")

    # Phase 3 fund honesty
    if fmp_score is None:
        flags.append("fund=unknown")  # FMP free mid-cap gap
    else:
        flags.append(f"fmp={fmp_score:.0f}")

    if chase:
        tier = "C"
    elif missing_ret:
        tier = "B"
    # Tier A requires known fund path: either grade fund decent AND fmp present OR strong grade fund
    elif g >= 70 and fund >= 55 and rs >= 65 and tech < 98 and fmp_score is not None:
        tier = "A"
    elif g >= 70 and fund >= 70 and rs >= 68 and tech < 98:
        # grade fund hygiene strong enough without FMP
        tier = "A"
        flags.append("tierA_via_grade_fund")
    elif g >= 68 and fund >= 52 and rs >= 62 and fmp_score is not None:
        tier = "A"
    elif g >= 68 and fund >= 70 and rs >= 65:
        tier = "A"
        flags.append("tierA_via_grade_fund")
    elif g >= 65 and rs >= 60:
        tier = "B"
    else:
        tier = "B"
    return tier, chase, flags, rs, r5, r63


def main():
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    held = held_tickers(cur)
    ret_5 = ret_map(cur, 5)
    ret_63 = ret_map(cur, 63)
    fmp = load_fmp_scores(cur)
    rows = load_candidates(cur)
    conn.close()

    ideas = []
    for row in rows:
        t = (row["ticker"] or "").upper()
        if not t or t in held:
            continue
        if t in CRYPTO_LIKE:
            continue
        # skip obvious non-equities junk
        if len(t) > 6:
            continue
        fmp_score = fmp.get(t)
        tier, chase, flags, rs, r5, r63 = classify(row, ret_5, ret_63, fmp_score)
        ideas.append(
            {
                "ticker": t,
                "grade": float(row.get("vox_grade") or 0),
                "research": round(rs, 1),
                "tech": row.get("technical_score"),
                "fund": row.get("fundamental_score"),
                "fmp_fund": fmp_score,
                "fund_label": "known" if fmp_score is not None else "unknown",
                "macro": row.get("macro_score"),
                "sent": row.get("sentiment_score"),
                "action": row.get("action"),
                "sector": row.get("sector"),
                "tier": tier,
                "chase": chase,
                "flags": flags,
                "ret_1w": None if r5 is None else round(r5, 1),
                "ret_3m": None if r63 is None else round(r63, 1),
                "entry": "BUY_DIPS_ONLY" if chase else "NEW_IDEA",
            }
        )

    # rank: prefer non-chase, higher research, higher grade
    ideas.sort(
        key=lambda x: (
            0 if x["tier"] == "A" else 1 if x["tier"] == "B" else 2,
            1 if x["chase"] else 0,
            -x["research"],
            -x["grade"],
        )
    )

    tier_a = [i for i in ideas if i["tier"] == "A" and not i["chase"]][:8]
    tier_b = [i for i in ideas if i["tier"] == "B" and not i["chase"]][:10]
    dips = [i for i in ideas if i["chase"]][:8]

    day = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Outside Ideas — {day}",
        "",
        f"**Generated:** {now}",
        f"**Held excluded:** {len(held)} · **Candidates ranked:** {len(ideas)}",
        f"**FMP known:** {sum(1 for i in ideas if i.get('fund_label')=='known')} · **fund=unknown:** {sum(1 for i in ideas if i.get('fund_label')=='unknown')}",
        "",
        "> Grades = **hygiene / ranking**, not auto-deploy. Outside-book only. Anti-chase applied.",
        "> Bucket **B** in capital plan = new ideas. Bucket **A** = rebalance owned quality (not listed here).",
        "> **Fund honesty:** FMP free = mega only. Mid-caps without FMP are tagged `fund=unknown` (not fake precision).",
        "",
        "## Tier A — cleanest new ideas (prefer)",
        "",
        "| Ticker | Grade | Research | T | F | FMP | Entry | Notes |",
        "|--------|------:|---------:|--:|--:|-----:|-------|-------|",
    ]
    for i in tier_a:
        fmp_c = f"{i['fmp_fund']:.0f}" if i.get("fmp_fund") is not None else "unknown"
        lines.append(
            f"| **{i['ticker']}** | {i['grade']:.0f} | {i['research']:.1f} | "
            f"{i['tech'] or '—'} | {i['fund'] or '—'} | {fmp_c} | {i['entry']} | {i.get('sector') or ''} |"
        )
    if not tier_a:
        lines.append("| — | | | | | | | no clean A this run |")

    lines += [
        "",
        "## Tier B — secondary (size small; often fund=unknown)",
        "",
        "| Ticker | Grade | Research | FMP | Entry | Notes |",
        "|--------|------:|---------:|-----:|-------|-------|",
    ]
    for i in tier_b:
        fmp_c = f"{i['fmp_fund']:.0f}" if i.get("fmp_fund") is not None else "unknown"
        lines.append(
            f"| {i['ticker']} | {i['grade']:.0f} | {i['research']:.1f} | {fmp_c} | {i['entry']} | {i.get('sector') or ''} |"
        )

    lines += [
        "",
        "## Tier C — extended / chase (dips only or skip)",
        "",
        "| Ticker | Grade | Research | 1w | 3m | Flags |",
        "|--------|------:|---------:|---:|---:|-------|",
    ]
    for i in dips:
        lines.append(
            f"| {i['ticker']} | {i['grade']:.0f} | {i['research']:.1f} | "
            f"{i['ret_1w'] if i['ret_1w'] is not None else '—'} | "
            f"{i['ret_3m'] if i['ret_3m'] is not None else '—'} | "
            f"{', '.join(i['flags'])} |"
        )

    lines += [
        "",
        "## How Hermes should use this",
        "1. New capital → pick from **Tier A**, then B",
        "2. Never treat Tier C as market orders",
        "3. Prefer **FMP known** over fund=unknown when sizing",
        "4. Rebalance adds to **owned** quality are separate (Brain sleeve repair)",
        "5. Still not day-trading; size for balanced mandate",
        "6. Optional: FMP Starter unlocks mid-cap fund scores (not required)",
        "",
        f"JSON: `~/.hermes/cron/output/brain/OutsideIdeas-{day}.json`",
    ]

    OBS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.mkdir(parents=True, exist_ok=True)
    latest = OBS / "Outside-Ideas-LATEST.md"
    dated = OBS / f"Outside-Ideas-{day}.md"
    text = "\n".join(lines) + "\n"
    latest.write_text(text)
    dated.write_text(text)

    payload = {
        "day": day,
        "generated_at": now,
        "held_count": len(held),
        "tier_a": tier_a,
        "tier_b": tier_b,
        "dips_only": dips,
        "note": "Grades are hygiene only. Not auto-deploy.",
    }
    (OUT_JSON / f"OutsideIdeas-{day}.json").write_text(json.dumps(payload, indent=2, default=str))
    (OUT_JSON / "OutsideIdeas-LATEST.json").write_text(json.dumps(payload, indent=2, default=str))

    # Telegram-friendly short
    print(f"🌍 **VOX Outside Ideas — {day}**")
    print(f"Held excluded: {len(held)} · Grades = hygiene only")
    print("")
    print("**Tier A (new capital):**")
    for i in tier_a[:6]:
        print(f"· **{i['ticker']}** g{i['grade']:.0f} rs{i['research']:.0f} {i.get('sector') or ''}")
    if not tier_a:
        print("· (none clean — use Tier B or wait)")
    print("")
    print("**Tier B:** " + ", ".join(i["ticker"] for i in tier_b[:8]) if tier_b else "**Tier B:** —")
    if dips:
        print("**Dips only:** " + ", ".join(f"{i['ticker']}" for i in dips[:6]))
    print("")
    print(f"Full: Obsidian `memory/brain/Outside-Ideas-LATEST`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
