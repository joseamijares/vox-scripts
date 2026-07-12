#!/usr/bin/env python3
"""Rebuild consolidated `positions` from `broker_positions` (JOS-190).

Rules:
- Sum per ticker across brokers (shares, live_value_usd)
- Skip CASH; include MIRROR_TOTAL as its own line
- Map A → VAULTA (never Agilent)
- Prefer latest non-null grade/council/sector from any broker row
- Zero out consolidated tickers no longer held
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_portfolio_policy import normalize_ticker  # noqa: E402

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db():
    pwd = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    if not pwd or len(pwd) < 8:
        env = Path.home() / ".hermes" / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("DB_PASSWORD=") or line.startswith("PGPASSWORD="):
                    pwd = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        dbname=os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("PGUSER", "postgres"),
        password=pwd,
        connect_timeout=20,
    )


def rebuild() -> dict:
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        """
        SELECT broker, ticker, shares, live_price, avg_cost,
               COALESCE(live_value_usd, live_value, 0) AS value_usd,
               grade, council, sector
        FROM broker_positions
        WHERE ticker NOT IN ('CASH')
          AND (
            COALESCE(shares, 0) > 0
            OR (ticker = 'MIRROR_TOTAL' AND COALESCE(live_value_usd, live_value, 0) > 0)
          )
        """
    )
    rows = cur.fetchall()

    agg = defaultdict(lambda: {
        "shares": 0.0,
        "value": 0.0,
        "brokers": set(),
        "grade": None,
        "council": None,
        "sector": None,
        "price_num": 0.0,
        "price_den": 0.0,
        "cost_num": 0.0,
        "cost_den": 0.0,
    })

    for r in rows:
        raw = r["ticker"]
        # Drop false Agilent if still present as A with zero intent
        t = normalize_ticker(raw)
        if raw == "A" and t == "VAULTA":
            # only if this row is the crypto mislabel — if somehow real A appears, still map
            pass
        if raw == "A" and float(r["value_usd"] or 0) == 0 and float(r["shares"] or 0) == 0:
            continue

        a = agg[t]
        sh = float(r["shares"] or 0)
        val = float(r["value_usd"] or 0)
        a["shares"] += sh
        a["value"] += val
        a["brokers"].add(r["broker"])
        if r.get("live_price") and sh > 0:
            a["price_num"] += float(r["live_price"]) * sh
            a["price_den"] += sh
        if r.get("avg_cost") and sh > 0:
            a["cost_num"] += float(r["avg_cost"]) * sh
            a["cost_den"] += sh
        if r.get("grade") is not None and a["grade"] is None:
            a["grade"] = int(r["grade"]) if float(r["grade"]) == int(float(r["grade"])) else float(r["grade"])
        if r.get("council") and not a["council"]:
            a["council"] = r["council"]
        if r.get("sector") and not a["sector"]:
            a["sector"] = r["sector"]

    # Policy overrides for known names
    if "VAULTA" in agg:
        agg["VAULTA"]["sector"] = "Crypto"
        if not agg["VAULTA"]["council"] or agg["VAULTA"]["council"] in ("SELL", "REMOVED"):
            agg["VAULTA"]["council"] = "HOLD"
        if agg["VAULTA"]["grade"] is None:
            agg["VAULTA"]["grade"] = 45
    if "SPCX" in agg:
        agg["SPCX"]["sector"] = "SpaceX"
        # Don't force SELL on SpaceX from stale council
        if agg["SPCX"]["council"] == "SELL" and (agg["SPCX"]["grade"] or 0) < 50:
            # keep grade but note — follow-up policy handles action
            pass
    if "COST" in agg and agg["COST"]["council"] == "SELL":
        # quality compounder — neutralize auto SELL for consolidated display
        agg["COST"]["council"] = "HOLD"
    if "APH" in agg and agg["APH"]["council"] == "SELL":
        # multi-broker quality industrial — neutralize bare SELL
        if (agg["APH"]["grade"] or 0) >= 50:
            agg["APH"]["council"] = "HOLD"

    live_tickers = set(agg.keys())
    # Never keep bare A in consolidated
    live_tickers.discard("A")

    upserted = 0
    for t, a in agg.items():
        if t == "A":
            continue
        if a["value"] <= 0 and a["shares"] <= 0 and t != "MIRROR_TOTAL":
            continue
        price = (a["price_num"] / a["price_den"]) if a["price_den"] else (
            (a["value"] / a["shares"]) if a["shares"] else 0
        )
        avg_cost = (a["cost_num"] / a["cost_den"]) if a["cost_den"] else None
        brokers = sorted(a["brokers"])

        # Check if positions has brokers array column
        cur.execute(
            """
            INSERT INTO positions (ticker, shares, live_price, live_value, live_value_usd,
                                   grade, council, sector, brokers, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                shares = EXCLUDED.shares,
                live_price = EXCLUDED.live_price,
                live_value = EXCLUDED.live_value,
                live_value_usd = EXCLUDED.live_value_usd,
                grade = COALESCE(EXCLUDED.grade, positions.grade),
                council = COALESCE(EXCLUDED.council, positions.council),
                sector = COALESCE(EXCLUDED.sector, positions.sector),
                brokers = EXCLUDED.brokers,
                updated_at = NOW()
            """,
            (
                t,
                a["shares"],
                price,
                a["value"],
                a["value"],
                a["grade"],
                a["council"] or ("MIRROR" if t == "MIRROR_TOTAL" else None),
                a["sector"],
                brokers,
            ),
        )
        upserted += 1

    # Zero removed holdings (keep row for history but zero value)
    cur.execute("SELECT ticker FROM positions WHERE COALESCE(shares,0) > 0 OR COALESCE(live_value_usd,0) > 0")
    existing = {r["ticker"] for r in cur.fetchall()}
    zeroed = 0
    for t in existing - live_tickers:
        cur.execute(
            """
            UPDATE positions
            SET shares = 0, live_value = 0, live_value_usd = 0,
                council = CASE WHEN ticker = 'A' THEN 'REMOVED' ELSE council END,
                updated_at = NOW()
            WHERE ticker = %s
            """,
            (t,),
        )
        zeroed += cur.rowcount

    # Explicitly kill false Agilent
    cur.execute(
        """
        UPDATE positions
        SET shares = 0, live_value = 0, live_value_usd = 0, council = 'REMOVED', updated_at = NOW()
        WHERE ticker = 'A' AND COALESCE(shares,0) > 0
        """
    )
    if cur.rowcount:
        zeroed += cur.rowcount

    conn.commit()

    cur.execute(
        """
        SELECT COUNT(*) n, COALESCE(SUM(live_value_usd),0) aum
        FROM positions
        WHERE COALESCE(shares,0) > 0 OR (ticker='MIRROR_TOTAL' AND COALESCE(live_value_usd,0)>0)
        """
    )
    summary = dict(cur.fetchone())
    conn.close()

    out = {
        "upserted": upserted,
        "zeroed": zeroed,
        "active": int(summary["n"]),
        "aum": float(summary["aum"]),
        "tickers": sorted(live_tickers),
        "ts": datetime.now().isoformat(),
    }
    print(f"✅ Rebuilt positions: {upserted} upserted, {zeroed} zeroed, active={out['active']}, AUM=${out['aum']:,.2f}")
    return out


if __name__ == "__main__":
    rebuild()
