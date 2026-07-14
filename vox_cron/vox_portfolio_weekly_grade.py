#!/usr/bin/env python3
"""VOX Portfolio Weekly Grade & Research Scan

Re-grades every held position with the live grader, syncs positions + unified
scores, writes a portfolio research report into the Brain/dashboard, and is
safe for a weekly cron (all holdings, not day-trading).

Usage:
  python3 vox_portfolio_weekly_grade.py           # full run
  python3 vox_portfolio_weekly_grade.py --limit 20
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_portfolio_policy import (  # noqa: E402
    classify_action,
    normalize_ticker,
    sleeve_for,
)

HERMES = Path.home() / ".hermes"
OUT = HERMES / "cron" / "output" / "brain"
OBS = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "brain"
DASH_JSON = HERMES / "scripts" / "vox_cron" / "portfolio_dashboard.json"

CRYPTO_YF = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "XRP": "XRP-USD",
    "TRX": "TRX-USD",
    "BNB": "BNB-USD",
    "DOGE": "DOGE-USD",
    "SOL": "SOL-USD",
    "ADA": "ADA-USD",
    "HBAR": "HBAR-USD",
    "BONK": "BONK-USD",
    "PENGU": "PENGU-USD",
    "KAITO": "KAITO-USD",
    "KITE": "KITE-USD",
    "NIGHT": "NIGHT-USD",
    "NXPC": "NXPC-USD",
}

SKIP = {"MIRROR_TOTAL", "CASH", "BI 270121", "GBM O", "VAULTA", "SPCX"}  # no reliable Yahoo


def load_env() -> None:
    envp = HERMES / ".env"
    if not envp.exists():
        return
    for line in envp.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    load_env()
    pw = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        dbname=os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("PGUSER", "postgres"),
        password=pw,
        connect_timeout=20,
    )


def yf_symbol(ticker: str) -> str:
    t = normalize_ticker(ticker)
    if t in CRYPTO_YF:
        return CRYPTO_YF[t]
    if t.endswith("-USD"):
        return t
    return t


def get_portfolio_tickers(cur) -> List[Tuple[str, float]]:
    cur.execute(
        """
        SELECT ticker, COALESCE(live_value_usd, 0) AS v
        FROM positions
        WHERE COALESCE(live_value_usd, 0) > 0
        ORDER BY v DESC
        """
    )
    out = []
    for r in cur.fetchall():
        t = normalize_ticker(r["ticker"] if isinstance(r, dict) else r[0])
        v = float(r["v"] if isinstance(r, dict) else r[1])
        if t and t not in SKIP:
            out.append((t, v))
    return out


def grade_all(tickers: List[str], sleep_s: float = 0.8) -> List[Dict[str, Any]]:
    from vox_live_grader import grade_ticker

    results = []
    n = len(tickers)
    for i, t in enumerate(tickers, 1):
        ysym = yf_symbol(t)
        print(f"  [{i}/{n}] {t}" + (f" via {ysym}" if ysym != t else "") + "...", end="", flush=True)
        try:
            # grade under Yahoo symbol but store under portfolio ticker when crypto
            if ysym != t:
                # temporary grade under ysym then copy to t
                r = grade_ticker(ysym, timeout_secs=15)
                if r and r.get("grade") is not None:
                    # re-insert under portfolio ticker
                    _store_alias_grade(t, ysym, r)
                    r = {**r, "ticker": t, "yahoo": ysym}
                results.append(r or {"ticker": t, "failed": True})
            else:
                r = grade_ticker(t, timeout_secs=15)
                results.append(r or {"ticker": t, "failed": True})
            g = (results[-1] or {}).get("grade")
            a = (results[-1] or {}).get("action")
            if (results[-1] or {}).get("timeout"):
                print(" TIMEOUT")
            elif (results[-1] or {}).get("failed") or g is None:
                print(" FAIL")
            elif (results[-1] or {}).get("updated"):
                print(f" ok {g} {a} (unchanged)")
            else:
                print(f" NEW {g} {a}")
        except Exception as e:
            print(f" ERR {e}")
            results.append({"ticker": t, "error": str(e)})
        time.sleep(sleep_s)
    return results


def _store_alias_grade(portfolio_ticker: str, yahoo: str, result: Dict) -> None:
    """Copy latest yahoo grade into portfolio ticker row."""
    load_env()
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT vox_grade, action, current_price, technical_score, fundamental_score,
               macro_score, sentiment_score, momentum_score, data_hash, catalysts
        FROM vox_grades WHERE ticker = %s ORDER BY generated_at DESC LIMIT 1
        """,
        (yahoo,),
    )
    row = cur.fetchone()
    import hashlib

    short_hash = hashlib.md5(f"{portfolio_ticker}:{yahoo}:{result.get('grade')}".encode()).hexdigest()[:8]
    if not row:
        g = result.get("grade")
        if g is None:
            conn.close()
            return
        cur.execute(
            """
            INSERT INTO vox_grades (
                ticker, name, vox_grade, action, current_price,
                technical_score, fundamental_score, macro_score, sentiment_score,
                momentum_score, data_hash, catalysts, generated_at
            ) VALUES (%s,%s,%s,%s,%s,50,50,50,50,0,%s,%s,NOW())
            """,
            (
                portfolio_ticker,
                portfolio_ticker,
                g,
                result.get("action") or "HOLD",
                None,
                short_hash,
                f"crypto alias of {yahoo}",
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO vox_grades (
                ticker, name, vox_grade, action, current_price,
                technical_score, fundamental_score, macro_score, sentiment_score,
                momentum_score, data_hash, catalysts, generated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (
                portfolio_ticker,
                portfolio_ticker,
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7] or 0,
                short_hash,
                f"alias of {yahoo}: {(row[9] or '')[:120]}",
            ),
        )
    conn.commit()
    conn.close()


def sync_positions_and_unified(cur, conn) -> int:
    """Set positions.grade/council from latest vox_grades; upsert unified_grades for holdings."""
    # unified_grades has no UNIQUE(ticker) — always use row-wise update/insert
    return sync_positions_fallback(cur, conn)


def sync_positions_fallback(cur, conn) -> int:
    """If ON CONFLICT fails (no unique), update unified row-by-row."""
    cur.execute(
        """
        WITH latest AS (
          SELECT DISTINCT ON (ticker)
            ticker, vox_grade, action, technical_score
          FROM vox_grades
          ORDER BY ticker, generated_at DESC
        )
        UPDATE positions p SET
          grade = ROUND(l.vox_grade)::int,
          council = COALESCE(l.action, p.council),
          updated_at = NOW()
        FROM latest l WHERE p.ticker = l.ticker AND COALESCE(p.live_value_usd,0) > 0
        """
    )
    n = cur.rowcount
    cur.execute(
        """
        SELECT p.ticker, l.vox_grade, l.action, l.technical_score
        FROM positions p
        JOIN (
          SELECT DISTINCT ON (ticker) ticker, vox_grade, action, technical_score
          FROM vox_grades ORDER BY ticker, generated_at DESC
        ) l ON l.ticker = p.ticker
        WHERE COALESCE(p.live_value_usd,0) > 0
        """
    )
    for ticker, vg, action, tech in cur.fetchall():
        cur.execute("SELECT ticker FROM unified_grades WHERE ticker = %s", (ticker,))
        if cur.fetchone():
            cur.execute(
                """
                UPDATE unified_grades SET
                  unified_grade = ROUND(COALESCE(%s,50) * 0.55 + COALESCE(sp500_grade, %s, 50) * 0.25 + COALESCE(tech_score, %s, 50) * 0.20, 1),
                  action = %s,
                  vox_grade = %s,
                  tech_score = COALESCE(%s, tech_score),
                  computed_at = NOW(),
                  vox_source = 'port_weekly'
                WHERE ticker = %s
                """,
                (vg, vg, tech, (action or "HOLD")[:20], vg, tech, ticker),
            )
        else:
            cur.execute(
                """
                INSERT INTO unified_grades (ticker, unified_grade, action, vox_grade, tech_score, computed_at, vox_source)
                VALUES (%s, %s, %s, %s, %s, NOW(), 'port_weekly')
                """,
                (ticker, vg, (action or "HOLD")[:20], vg, tech),
            )
    conn.commit()
    return n


def collect_research(cur) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT p.ticker, p.shares, p.live_value_usd, p.grade, p.council, p.brokers, p.sector,
               u.unified_grade, u.vox_grade, u.sp500_grade, u.tech_score, u.action AS uni_action,
               l.technical_score, l.fundamental_score, l.macro_score, l.sentiment_score,
               l.current_price, l.catalysts, l.generated_at AS graded_at
        FROM positions p
        LEFT JOIN unified_grades u ON u.ticker = p.ticker
        LEFT JOIN LATERAL (
          SELECT * FROM vox_grades vg WHERE vg.ticker = p.ticker
          ORDER BY generated_at DESC LIMIT 1
        ) l ON TRUE
        WHERE COALESCE(p.live_value_usd, 0) > 0 AND p.ticker <> 'MIRROR_TOTAL'
        ORDER BY p.live_value_usd DESC
        """
    )
    aum = 0.0
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        aum += float(r.get("live_value_usd") or 0)
    aum = aum or 1.0
    out = []
    for r in rows:
        t = normalize_ticker(r["ticker"])
        v = float(r.get("live_value_usd") or 0)
        w = 100.0 * v / aum
        g = r.get("grade") or r.get("unified_grade") or r.get("vox_grade")
        g = float(g) if g is not None else None
        council = r.get("council") or r.get("uni_action")
        decision = classify_action(t, g, council, v, w)
        # composite research score 0-100
        tech = float(r["technical_score"] or 50)
        fund = float(r["fundamental_score"] or 50)
        macro = float(r["macro_score"] or 50)
        sent = float(r["sentiment_score"] or 50)
        research_score = round(tech * 0.30 + fund * 0.25 + macro * 0.20 + sent * 0.15 + (g or 50) * 0.10, 1)
        out.append(
            {
                "ticker": t,
                "value_usd": round(v, 2),
                "weight_pct": round(w, 2),
                "grade": int(g) if g is not None else None,
                "research_score": research_score,
                "technical": round(tech, 1),
                "fundamental": round(fund, 1),
                "macro": round(macro, 1),
                "sentiment": round(sent, 1),
                "unified": float(r["unified_grade"]) if r.get("unified_grade") is not None else None,
                "vox": float(r["vox_grade"]) if r.get("vox_grade") is not None else None,
                "council": council,
                "decision": decision.get("decision"),
                "sleeve": decision.get("sleeve") or sleeve_for(t),
                "reasons": decision.get("reasons") or [],
                "keep": decision.get("keep") or [],
                "brokers": list(r.get("brokers") or []),
                "sector": r.get("sector"),
                "price": float(r["current_price"]) if r.get("current_price") is not None else None,
                "catalysts": r.get("catalysts"),
                "graded_at": str(r.get("graded_at") or ""),
            }
        )
    return out


def write_report(rows: List[Dict[str, Any]], grade_stats: Dict[str, Any]) -> Dict[str, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    OBS.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    aum = sum(r["value_usd"] for r in rows) or 1.0

    # Attach research_score into dashboard JSON if present
    if DASH_JSON.exists():
        try:
            dash = json.loads(DASH_JSON.read_text())
            by_t = {r["ticker"]: r for r in rows}
            for p in dash.get("positions") or []:
                t = normalize_ticker(p.get("ticker") or "")
                if t in by_t:
                    p["research_score"] = by_t[t]["research_score"]
                    p["technical"] = by_t[t]["technical"]
                    p["fundamental"] = by_t[t]["fundamental"]
                    p["macro"] = by_t[t]["macro"]
                    p["sentiment"] = by_t[t]["sentiment"]
                    p["grade"] = by_t[t]["grade"]
                    p["portfolio_decision"] = by_t[t]["decision"]
            dash["portfolio_research"] = {
                "generated_at": datetime.now().isoformat(),
                "aum": aum,
                "graded": grade_stats,
                "avg_research_score": round(sum(r["research_score"] for r in rows) / max(len(rows), 1), 1),
                "avg_grade": round(sum((r["grade"] or 0) for r in rows) / max(len(rows), 1), 1),
            }
            DASH_JSON.write_text(json.dumps(dash, indent=2, default=str))
        except Exception as e:
            print(f"dashboard json patch warn: {e}")

    # Markdown report
    lines = [
        f"# Portfolio Research Grades — {day}",
        "",
        f"**AUM:** ${aum:,.0f} · **Names:** {len(rows)}  ",
        f"**Avg grade:** {sum((r['grade'] or 0) for r in rows)/max(len(rows),1):.1f} · "
        f"**Avg research score:** {sum(r['research_score'] for r in rows)/max(len(rows),1):.1f}",
        "",
        f"_Graded: {grade_stats}_",
        "",
        "## Scoring model",
        "- **Grade (0–100):** live technical 30% + fundamental 25% + macro/sector 20% + sentiment 15% + base 10%",
        "- **Research score:** same layers + current grade blend — used on dashboard",
        "- **Mandate decision:** quality compounders protected; multi-broker never a sell reason; actions ≥2.5% for alerts",
        "",
        "## Full book (by weight)",
        "| Ticker | W% | Value | Grade | Research | Tech | Fund | Macro | Sent | Sleeve | Decision |",
        "|--------|---:|------:|------:|---------:|-----:|-----:|------:|-----:|--------|----------|",
    ]
    for r in sorted(rows, key=lambda x: -x["weight_pct"]):
        lines.append(
            f"| {r['ticker']} | {r['weight_pct']:.2f}% | ${r['value_usd']:,.0f} | "
            f"{r['grade'] if r['grade'] is not None else '—'} | **{r['research_score']}** | "
            f"{r['technical']:.0f} | {r['fundamental']:.0f} | {r['macro']:.0f} | {r['sentiment']:.0f} | "
            f"{r['sleeve']} | **{r['decision']}** |"
        )

    # Buckets
    top = [r for r in rows if (r["grade"] or 0) >= 65]
    weak = [r for r in rows if (r["grade"] or 0) < 45 and r["value_usd"] >= 200]
    lines += ["", f"## Strong (≥65) — {len(top)} names"]
    for r in sorted(top, key=lambda x: -(x["grade"] or 0))[:15]:
        lines.append(f"- **{r['ticker']}** g{r['grade']} research {r['research_score']} · {r['weight_pct']}% · {r['sleeve']}")
    lines += ["", f"## Weak (<45, ≥$200) — {len(weak)} names"]
    for r in sorted(weak, key=lambda x: x["grade"] or 0)[:20]:
        why = "; ".join(r["reasons"][:2]) if r["reasons"] else r["decision"]
        lines.append(f"- **{r['ticker']}** g{r['grade']} · ${r['value_usd']:,.0f} · {why}")

    lines += [
        "",
        "## Layer leaders",
        f"- Best technical: {max(rows, key=lambda x: x['technical'])['ticker']} ({max(r['technical'] for r in rows):.0f})",
        f"- Best fundamental: {max(rows, key=lambda x: x['fundamental'])['ticker']} ({max(r['fundamental'] for r in rows):.0f})",
        f"- Best macro: {max(rows, key=lambda x: x['macro'])['ticker']} ({max(r['macro'] for r in rows):.0f})",
        "",
        "## Next steps",
        "1. Review weak names under mandate (not auto-sell quality)",
        "2. Run Portfolio Brain for L/M/S execute plan",
        "3. Weekly re-scan cron keeps this fresh",
        "",
        f"_Generated by vox_portfolio_weekly_grade.py · {datetime.now().isoformat()}_",
    ]
    md = "\n".join(lines) + "\n"
    paths = {
        "md": OUT / f"PortfolioGrades-{day}.md",
        "json": OUT / f"PortfolioGrades-{day}.json",
        "obs": OBS / f"PortfolioGrades-{day}.md",
        "obs_latest": OBS / "PortfolioGrades-LATEST.md",
    }
    payload = {
        "date": day,
        "aum": aum,
        "grade_stats": grade_stats,
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    paths["md"].write_text(md)
    paths["json"].write_text(json.dumps(payload, indent=2, default=str))
    paths["obs"].write_text(md)
    paths["obs_latest"].write_text(md)

    # Compact Telegram summary
    summary = [
        f"📊 **Portfolio Weekly Grades — {day}**",
        f"AUM **${aum:,.0f}** · {len(rows)} names · avg grade "
        f"**{sum((r['grade'] or 0) for r in rows)/max(len(rows),1):.0f}** · research "
        f"**{sum(r['research_score'] for r in rows)/max(len(rows),1):.0f}**",
        f"Engine: {grade_stats.get('new',0)} new · {grade_stats.get('unchanged',0)} unchanged · "
        f"{grade_stats.get('fail',0)} fail · {grade_stats.get('timeout',0)} timeout",
        "",
        "**Top research scores:**",
    ]
    for r in sorted(rows, key=lambda x: -x["research_score"])[:8]:
        summary.append(f"· {r['ticker']} research **{r['research_score']}** g{r['grade']} {r['decision']}")
    summary.append("**Weak (≥$200):**")
    for r in sorted(weak, key=lambda x: x["grade"] or 0)[:6]:
        summary.append(f"· {r['ticker']} g{r['grade']} ${r['value_usd']:,.0f}")
    if not weak:
        summary.append("· none material")
    summary.append(f"\nFull: Obsidian `memory/brain/PortfolioGrades-LATEST`")
    paths["summary"] = "\n".join(summary)
    return {k: (str(v) if k != "summary" else v) for k, v in paths.items()}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="grade only top N by value (0=all)")
    ap.add_argument("--skip-grade", action="store_true", help="only sync/report from existing grades")
    ap.add_argument("--sleep", type=float, default=0.7)
    args = ap.parse_args()

    load_env()
    # ensure password for live grader
    if not os.environ.get("DB_PASSWORD") and os.environ.get("PGPASSWORD"):
        os.environ["DB_PASSWORD"] = os.environ["PGPASSWORD"]

    conn = connect()
    cur = conn.cursor()
    from psycopg2.extras import RealDictCursor

    cur = conn.cursor(cursor_factory=RealDictCursor)
    pairs = get_portfolio_tickers(cur)
    if args.limit:
        pairs = pairs[: args.limit]
    tickers = [t for t, _ in pairs]
    print(f"Portfolio grade scan: {len(tickers)} tickers")

    stats = {"new": 0, "unchanged": 0, "fail": 0, "timeout": 0, "error": 0}
    if not args.skip_grade:
        # live grader needs plain password env
        os.environ.setdefault("PGPASSWORD", os.environ.get("DB_PASSWORD", ""))
        results = grade_all(tickers, sleep_s=args.sleep)
        for r in results:
            if not r:
                stats["fail"] += 1
            elif r.get("timeout"):
                stats["timeout"] += 1
            elif r.get("failed") or r.get("error"):
                stats["fail"] += 1
            elif r.get("updated"):
                stats["unchanged"] += 1
            elif r.get("grade") is not None:
                stats["new"] += 1
            else:
                stats["fail"] += 1
    else:
        print("Skipping live grade — using existing vox_grades")

    # sync
    cur2 = conn.cursor()
    try:
        n = sync_positions_and_unified(cur2, conn)
        print(f"Synced positions rows: {n}")
    except Exception as e:
        conn.rollback()
        print(f"Unified upsert failed ({e}); fallback…")
        n = sync_positions_fallback(cur2, conn)
        print(f"Fallback synced: {n}")

    cur = conn.cursor(cursor_factory=RealDictCursor)
    rows = collect_research(cur)
    conn.close()

    paths = write_report(rows, stats)
    print(paths.get("summary", ""))

    # Refresh brain + dashboard generators
    try:
        from vox_portfolio_brain import build, publish

        publish(build())
        print("Portfolio Brain refreshed")
    except Exception as e:
        print(f"brain refresh warn: {e}")
    try:
        from generate_dashboard import generate_dashboard_data, write_outputs

        # generate_dashboard may only have generate_dashboard_data
        data = generate_dashboard_data()
        # patch research into data
        by_t = {r["ticker"]: r for r in rows}
        for p in data.get("positions") or []:
            t = normalize_ticker(p.get("ticker") or "")
            if t in by_t:
                p["research_score"] = by_t[t]["research_score"]
                p["technical"] = by_t[t]["technical"]
                p["fundamental"] = by_t[t]["fundamental"]
        out = HERMES / "scripts" / "vox_cron" / "portfolio_dashboard.json"
        # re-read if generate wrote already
        if out.exists():
            dash = json.loads(out.read_text())
            for p in dash.get("positions") or []:
                t = normalize_ticker(p.get("ticker") or "")
                if t in by_t:
                    p["research_score"] = by_t[t]["research_score"]
                    p["layer_scores"] = {
                        "technical": by_t[t]["technical"],
                        "fundamental": by_t[t]["fundamental"],
                        "macro": by_t[t]["macro"],
                        "sentiment": by_t[t]["sentiment"],
                    }
                    p["research_grade"] = by_t[t]["grade"]
            dash["portfolio_research_scan"] = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "avg_research_score": round(sum(r["research_score"] for r in rows) / max(len(rows), 1), 1),
                "count": len(rows),
            }
            out.write_text(json.dumps(dash, indent=2, default=str))
            print("Dashboard JSON enriched with research scores")
        # re-run dashboard writer for Obsidian
        import generate_dashboard as gd

        if hasattr(gd, "main"):
            # run via subprocess style
            pass
    except Exception as e:
        print(f"dashboard enrich warn: {e}")

    # Always regenerate Obsidian portfolio dashboard note
    try:
        import subprocess

        subprocess.run(
            [sys.executable, str(HERMES / "scripts" / "vox_cron" / "generate_dashboard.py")],
            timeout=120,
            check=False,
        )
    except Exception as e:
        print(f"generate_dashboard warn: {e}")

    print("DONE", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
