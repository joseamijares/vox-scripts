#!/usr/bin/env python3
"""
VOX Weekly Opportunities
Generates top 10 cross-layer opportunities for the week.
Run Sundays at 7 PM CT via cron.

This is a simplified version that reads from existing VOX tables.
For full 6-layer scoring, run the vox-python modules separately.
"""
import json
import os
import sys
from datetime import datetime

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "railway")


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def fetch_top_sp500(cur):
    """Top graded S&P 500 tickers not in portfolio."""
    cur.execute("""
        SELECT g.ticker, g.vox_grade AS grade, g.technical_score, g.fundamental_score,
               g.macro_score, g.sector_score, g.weather_score, g.sentiment_score,
               u.sector, u.security
        FROM sp500_grades g
        JOIN sp500_universe u ON g.ticker = u.ticker
        LEFT JOIN positions p ON g.ticker = p.ticker
        WHERE g.vox_grade >= 70 AND p.ticker IS NULL
        ORDER BY g.vox_grade DESC
        LIMIT 10
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_sector_leaders(cur):
    """Current sector leaders."""
    cur.execute("""
        SELECT sector, ticker, rank, momentum_score, change_5d_pct
        FROM sp500_sector_leaders
        WHERE rank <= 3
        ORDER BY sector, rank
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_watchlist_gems(cur):
    """High-grade watchlist tickers not in portfolio."""
    cur.execute("""
        SELECT w.ticker, w.grade, w.council, w.sector
        FROM watchlist w
        LEFT JOIN positions p ON w.ticker = p.ticker
        WHERE w.grade >= 75 AND p.ticker IS NULL
        ORDER BY w.grade DESC
        LIMIT 10
    """)
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_macro_regime(cur):
    cur.execute(
        "SELECT regime, confidence FROM market_regime ORDER BY created_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    return {"regime": row[0], "score": row[1]} if row else {"regime": "UNKNOWN", "score": 0}


def generate_weekly_opportunities():
    conn = get_db()
    cur = conn.cursor()

    sp500 = fetch_top_sp500(cur)
    sectors = fetch_sector_leaders(cur)
    watchlist = fetch_watchlist_gems(cur)
    macro = fetch_macro_regime(cur)

    conn.close()

    # Combine and deduplicate by ticker
    seen = set()
    combined = []

    for source, items in [
        ("watchlist", watchlist),
        ("sp500", sp500),
        ("sector_leader", sectors),
    ]:
        for item in items:
            ticker = item.get("ticker")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            item["source"] = source
            combined.append(item)

    # Sort by grade descending
    combined.sort(key=lambda x: x.get("grade", 0) or 0, reverse=True)
    top10 = combined[:10]

    report = {
        "type": "weekly_opportunities",
        "generated_at": datetime.utcnow().isoformat(),
        "macro_regime": macro,
        "top_10": top10,
        "sector_leaders": sectors[:15],
        "watchlist_gems": watchlist[:5],
        "sp500_top": sp500[:5],
    }

    return report


def format_digest(report):
    lines = [
        f"# 📊 VOX Weekly Opportunities — {report['generated_at'][:10]}",
        "",
        f"**Macro Regime:** {report['macro_regime']['regime']} (score: {report['macro_regime']['score']})",
        "",
        "## Top 10 Cross-Layer Opportunities",
    ]

    for i, opp in enumerate(report["top_10"], 1):
        ticker = opp.get("ticker", "N/A")
        grade = opp.get("grade", "N/A")
        source = opp.get("source", "unknown")
        sector = opp.get("sector", "")
        price = opp.get("current_price")
        lines.append(
            f"{i}. `{ticker}` — grade {grade} | source: {source}"
            + (f" | sector: {sector}" if sector else "")
            + (f" | price: ${price:.2f}" if price else "")
        )

    if report["sector_leaders"]:
        lines.extend(["", "## Sector Leaders"])
        for s in report["sector_leaders"][:10]:
            lines.append(
                f"- `{s.get('sector')}` #{s.get('rank')}: `{s.get('ticker')}` "
                f"(momentum: {s.get('momentum_score')}, 5d: {s.get('change_5d_pct'):.2f}%)"
            )

    lines.append(f"\n_Generated at {report['generated_at']}_")
    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_weekly_opportunities()

    out_path = os.path.expanduser("~/.hermes/scripts/vox_cron/vox_weekly_opportunities.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(format_digest(report))
    sys.exit(0)
