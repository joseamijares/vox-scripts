#!/usr/bin/env python3
"""Grade all owned positions and produce process-driven SELL/TRIM list.
Multi-broker ownership is NEVER a sell reason.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

for line in (Path.home() / ".hermes" / ".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not v.startswith("***"):
            os.environ[k] = v
            if k in ("DB_PASSWORD", "PGPASSWORD"):
                os.environ["DB_PASSWORD"] = v
                os.environ["PGPASSWORD"] = v

import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf

CRYPTO = {
    "BTC", "ETH", "BNB", "XRP", "DOGE", "SOL", "TRX", "ADA", "HBAR", "AVAX", "LINK",
    "DOT", "MATIC", "SHIB", "BONK", "PENGU", "KAITO", "KITE", "MORPHO", "FF", "NXPC",
    "NIGHT", "XPL", "ALLO", "VANA", "HUMA", "VAULTA", "BNB-USD", "DOGE-USD", "SOL-USD",
    "ETH-USD", "BTC-USD",
}
ETFS = {"VOO", "QQQ", "VTI", "SPY", "IWM", "SMH", "SPCX", "CBRS", "NAFTRAC", "NAFTRAC ISHRS"}
DEFENSIVE = {"COST", "WMT", "PG", "KO", "JNJ", "PEP", "XOM", "VZ", "PFE", "MO", "MDLZ", "KVUE", "CL", "KMB"}


def main():
    conn = psycopg2.connect(
        host="acela.proxy.rlwy.net",
        port=35577,
        dbname="railway",
        user="postgres",
        password=os.environ.get("PGPASSWORD"),
        connect_timeout=20,
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        """
        SELECT broker, ticker, shares, COALESCE(live_value_usd, live_value, 0) AS value_usd,
               grade, council, sector
        FROM broker_positions
        WHERE ticker NOT IN ('CASH', 'A')
          AND (
            COALESCE(shares,0) > 0
            OR (ticker='MIRROR_TOTAL' AND COALESCE(live_value_usd,0) > 0)
          )
        """
    )
    bp = list(cur.fetchall())

    cur.execute(
        "SELECT ticker, grade, council, sector, brokers, COALESCE(live_value_usd,live_value,0) val FROM positions"
    )
    pos = {r["ticker"]: dict(r) for r in cur.fetchall()}

    cur.execute(
        """
        SELECT ticker, unified_grade, action, vox_grade, tech_score
        FROM unified_grades WHERE computed_at > NOW() - INTERVAL '14 days'
        """
    )
    uni = {r["ticker"]: dict(r) for r in cur.fetchall()}

    cur.execute(
        """
        SELECT DISTINCT ON (ticker) ticker, vox_grade, technical_score, fundamental_score
        FROM vox_grades ORDER BY ticker, generated_at DESC
        """
    )
    vox = {r["ticker"]: dict(r) for r in cur.fetchall()}

    cur.execute(
        """
        SELECT DISTINCT ON (ticker) ticker, consensus, final_action, risk_veto
        FROM council_deliberations ORDER BY ticker, timestamp DESC
        """
    )
    council = {r["ticker"]: dict(r) for r in cur.fetchall()}

    cur.execute(
        "SELECT ticker, score FROM technical_signals WHERE computed_at > NOW() - INTERVAL '7 days'"
    )
    tech = {r["ticker"]: dict(r) for r in cur.fetchall()}

    by = defaultdict(
        lambda: {
            "value": 0.0,
            "shares": 0.0,
            "brokers": set(),
            "grade_bp": None,
            "council_bp": None,
            "sector_bp": None,
        }
    )
    for r in bp:
        t = r["ticker"]
        by[t]["value"] += float(r["value_usd"] or 0)
        by[t]["shares"] += float(r["shares"] or 0)
        by[t]["brokers"].add(r["broker"])
        if r.get("grade") is not None and by[t]["grade_bp"] is None:
            by[t]["grade_bp"] = float(r["grade"])
        if r.get("council") and not by[t]["council_bp"]:
            by[t]["council_bp"] = r["council"]
        if r.get("sector") and not by[t]["sector_bp"]:
            by[t]["sector_bp"] = r["sector"]

    aum = sum(v["value"] for v in by.values()) or 1.0
    rows = []

    for t, d in by.items():
        if t == "MIRROR_TOTAL":
            rows.append(
                {
                    "ticker": t,
                    "value": round(d["value"], 2),
                    "weight": round(d["value"] * 100 / aum, 2),
                    "brokers": sorted(d["brokers"]),
                    "n_brokers": 1,
                    "asset": "COPY",
                    "grade": None,
                    "vox": None,
                    "uni": None,
                    "fund": None,
                    "tech": None,
                    "council": "MIRROR",
                    "sell_score": 0,
                    "decision": "HOLD_BUCKET",
                    "reasons": ["Copy book — manage people size, not ticker SELL"],
                    "keep": ["Intentional copy trading"],
                }
            )
            continue

        p, u, v, c, te = pos.get(t, {}), uni.get(t, {}), vox.get(t, {}), council.get(t, {}), tech.get(t, {})
        vox_g = float(v["vox_grade"]) if v.get("vox_grade") is not None else None
        uni_g = float(u["unified_grade"]) if u.get("unified_grade") is not None else None
        pos_g = float(p["grade"]) if p.get("grade") is not None else None
        bp_g = d["grade_bp"]

        conflict = False
        if vox_g is not None and uni_g is not None and abs(vox_g - uni_g) >= 12:
            grade = round(vox_g * 0.6 + uni_g * 0.4, 1)
            conflict = True
        elif vox_g is not None:
            grade = vox_g
        elif pos_g is not None:
            grade = pos_g
        elif bp_g is not None:
            grade = bp_g
        elif uni_g is not None:
            grade = uni_g
        else:
            grade = None

        action_c = str(c.get("final_action") or c.get("consensus") or p.get("council") or d["council_bp"] or "").upper()
        action_u = str(u.get("action") or "").upper()
        fund = float(v["fundamental_score"]) if v.get("fundamental_score") is not None else None
        tech_s = None
        if te.get("score") is not None:
            tech_s = float(te["score"])
        elif v.get("technical_score") is not None:
            tech_s = float(v["technical_score"])
        elif u.get("tech_score") is not None:
            tech_s = float(u["tech_score"])

        is_crypto = t in CRYPTO or str(d["sector_bp"] or "").lower() == "crypto" or t.endswith("-USD")
        if t in ETFS:
            asset = "ETF"
        elif is_crypto:
            asset = "CRYPTO"
        else:
            asset = "STOCK"

        sell = 0
        reasons = []
        keep = []

        if grade is not None:
            if grade < 40:
                sell += 35
                reasons.append(f"very weak grade {grade}")
            elif grade < 48:
                sell += 22
                reasons.append(f"weak grade {grade}")
            elif grade < 55:
                sell += 10
                reasons.append(f"soft grade {grade}")
            elif grade >= 65:
                sell -= 15
                keep.append(f"solid grade {grade}")
            elif grade >= 58:
                sell -= 8
                keep.append(f"OK grade {grade}")

        if action_c == "SELL":
            sell += 15
            reasons.append("system SELL flag")
        elif action_c == "TRIM":
            sell += 8
            reasons.append("system TRIM flag")
        elif action_c in ("BUY", "STRONG_BUY", "ACCUMULATE", "CORE BUY"):
            sell -= 12
            keep.append(action_c)

        if action_u == "SELL":
            sell += 10
            reasons.append("unified SELL")
        elif action_u in ("BUY", "STRONG_BUY"):
            sell -= 8
            keep.append(f"unified {action_u}")

        if c.get("risk_veto"):
            sell += 8
            reasons.append("risk veto")

        if fund is not None:
            if fund < 45:
                sell += 12
                reasons.append(f"weak fund {fund}")
            elif fund >= 75:
                sell -= 10
                keep.append(f"strong fund {fund}")

        if tech_s is not None:
            if tech_s < 45:
                sell += 8
                reasons.append(f"weak tech {tech_s}")
            elif tech_s >= 70:
                sell -= 5
                keep.append(f"strong tech {tech_s}")

        if t in DEFENSIVE:
            sell += 18
            reasons.append("defensive/plain vs aggressive mandate")

        if is_crypto:
            if t in ("BTC", "ETH"):
                sell -= 12
                keep.append("core crypto beta")
            elif t == "BNB":
                sell += 2
                reasons.append("exchange-token crypto")
            else:
                sell += 10
                reasons.append("non-core crypto alt")

        if conflict:
            sell += 5
            reasons.append("grade conflict")

        # n_brokers intentionally ignored as a sell input

        if sell >= 40:
            decision = "SELL"
        elif sell >= 26:
            decision = "TRIM"
        elif sell >= 14:
            decision = "WATCH"
        else:
            decision = "HOLD"

        if grade is not None and grade >= 60 and decision == "SELL":
            decision = "WATCH"
            reasons.append("grade>=60 blocks hard SELL")
        if grade is not None and grade >= 58 and decision == "SELL" and t not in DEFENSIVE:
            decision = "TRIM"
            reasons.append("grade>=58 softens to TRIM")

        # APH special: quality industrial; multi-broker is fine
        if t == "APH" and grade is not None and grade >= 54:
            decision = "HOLD" if grade >= 58 else "WATCH"
            keep = keep + ["quality compounder; multi-broker ownership is fine"]
            reasons = [x for x in reasons if "broker" not in x.lower()]

        rows.append(
            {
                "ticker": t,
                "value": round(d["value"], 2),
                "weight": round(d["value"] * 100 / aum, 2),
                "shares": round(d["shares"], 4),
                "brokers": sorted(d["brokers"]),
                "n_brokers": len(d["brokers"]),
                "asset": asset,
                "grade": grade,
                "vox": vox_g,
                "uni": uni_g,
                "fund": fund,
                "tech": tech_s,
                "council": action_c or None,
                "sell_score": sell,
                "decision": decision,
                "reasons": reasons,
                "keep": keep,
            }
        )

    # Light live tape for stocks/ETFs
    for r in rows:
        t = r["ticker"]
        if r["asset"] in ("CRYPTO", "COPY") or " " in t or len(t) > 8:
            continue
        try:
            hist = yf.Ticker(t).history(period="6mo")
            if hist is None or hist.empty:
                continue
            closes = [float(x) for x in hist["Close"].tolist()]
            last = closes[-1]

            def ret(n):
                if len(closes) <= n:
                    return None
                return round((last / closes[-n - 1] - 1) * 100, 1)

            r["px"] = round(last, 2)
            r["ret_1m"] = ret(21)
            r["ret_3m"] = ret(63)
            if r.get("ret_3m") is not None and r["ret_3m"] <= -25 and r["decision"] == "HOLD":
                r["decision"] = "WATCH"
                r["sell_score"] += 8
                r["reasons"] = r["reasons"] + ["broken tape 3m"]
            if r.get("ret_3m") is not None and r["ret_3m"] >= 50:
                r["keep"] = r["keep"] + [f"momentum 3m +{r['ret_3m']}%"]
        except Exception:
            pass
        time.sleep(0.02)

    rows.sort(key=lambda x: (-x["sell_score"], -x["value"]))
    sells = [r for r in rows if r["decision"] == "SELL"]
    trims = [r for r in rows if r["decision"] == "TRIM"]
    watch = [r for r in rows if r["decision"] == "WATCH"]
    holds = [r for r in rows if r["decision"] in ("HOLD", "HOLD_BUCKET")]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aum": round(aum, 2),
        "n": len(rows),
        "sells": sells,
        "trims": trims,
        "watch": watch,
        "holds": holds,
        "all": rows,
    }
    out_dir = Path.home() / ".hermes" / "cron" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "owned_grade_sell_20260712.json").write_text(json.dumps(out, indent=2, default=str))

    md = []
    md.append(f"# Owned Portfolio Grade and Sell Review — {datetime.now().strftime('%Y-%m-%d')}")
    md.append("")
    md.append(f"**Broker-rollup AUM:** ${aum:,.0f} | **lines:** {len(rows)}")
    md.append("")
    md.append("## Rules")
    md.append("- Multi-broker ownership is NEVER a sell reason")
    md.append("- Sells need weak grade / weak fund / mandate mismatch / non-core crypto")
    md.append("- Copy trading managed as MIRROR bucket")
    md.append("- BTC/ETH = core crypto beta, not automatic stock exits")
    md.append("")
    md.append("## SELL (I would exit)")
    md.append("| Ticker | Grade | Value | Wt% | Brokers | Why |")
    md.append("|--------|------:|------:|----:|---------|-----|")
    for r in sorted(sells, key=lambda x: -x["value"]):
        why = "; ".join(r["reasons"][:3]) or "process sell"
        md.append(
            f"| **{r['ticker']}** | {r['grade']} | ${r['value']:,.0f} | {r['weight']}% | {', '.join(r['brokers'])} | {why} |"
        )
    if not sells:
        md.append("| — | | | | | no hard sells |")

    md.append("")
    md.append("## TRIM (cut size, keep some)")
    md.append("| Ticker | Grade | Value | Wt% | Brokers | Why |")
    md.append("|--------|------:|------:|----:|---------|-----|")
    for r in sorted(trims, key=lambda x: -x["value"]):
        why = "; ".join(r["reasons"][:3])
        md.append(
            f"| **{r['ticker']}** | {r['grade']} | ${r['value']:,.0f} | {r['weight']}% | {', '.join(r['brokers'])} | {why} |"
        )
    if not trims:
        md.append("| — | | | | | none |")

    md.append("")
    md.append("## WATCH")
    md.append("| Ticker | Grade | Value | Wt% | Notes |")
    md.append("|--------|------:|------:|----:|-------|")
    for r in sorted(watch, key=lambda x: -x["value"])[:20]:
        notes = "; ".join((r["reasons"] or r["keep"])[:2])
        md.append(f"| {r['ticker']} | {r['grade']} | ${r['value']:,.0f} | {r['weight']}% | {notes} |")

    md.append("")
    md.append("## HOLD / CORE (largest)")
    md.append("| Ticker | Grade | Value | Wt% | Brokers | Thesis |")
    md.append("|--------|------:|------:|----:|---------|--------|")
    for r in sorted([x for x in holds if x["ticker"] != "MIRROR_TOTAL"], key=lambda x: -x["value"])[:25]:
        thesis = "; ".join((r["keep"] or ["hold"])[:2])
        md.append(
            f"| **{r['ticker']}** | {r['grade']} | ${r['value']:,.0f} | {r['weight']}% | {', '.join(r['brokers'])} | {thesis} |"
        )
    for r in holds:
        if r["ticker"] == "MIRROR_TOTAL":
            md.append(
                f"| **MIRROR_TOTAL** | — | ${r['value']:,.0f} | {r['weight']}% | eToro | copy people bucket |"
            )

    md.append("")
    md.append("## Full owned grade table")
    md.append("| Ticker | Class | Grade | Decision | Value | Brokers |")
    md.append("|--------|-------|------:|----------|------:|---------|")
    order = {"SELL": 0, "TRIM": 1, "WATCH": 2, "HOLD": 3, "HOLD_BUCKET": 4}
    for r in sorted(rows, key=lambda x: (order.get(x["decision"], 9), -(x["grade"] or 0), -x["value"])):
        md.append(
            f"| {r['ticker']} | {r['asset']} | {r['grade']} | {r['decision']} | ${r['value']:,.0f} | {', '.join(r['brokers'])} |"
        )

    text = "\n".join(md) + "\n"
    md_path = out_dir / "owned_sell_review_20260712.md"
    md_path.write_text(text)
    obs = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "daily"
    obs.mkdir(parents=True, exist_ok=True)
    (obs / "Owned-Sell-Review-2026-07-12.md").write_text(text)

    print(text)
    print("COUNTS", {k: len(out[k]) for k in ("sells", "trims", "watch", "holds")})
    aph = next(r for r in rows if r["ticker"] == "APH")
    print("APH", json.dumps(aph, default=str))
    conn.close()


if __name__ == "__main__":
    main()
