#!/usr/bin/env python3
"""VOX Portfolio Dashboard generator.

Sources:
- positions: consolidated book (grades/council/AUM view)
- broker_positions: per-broker truth + sync freshness

Outputs:
- ~/.hermes/scripts/vox_cron/portfolio_dashboard.json
- Obsidian daily PortfolioDashboard note
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap  # noqa: F401

import psycopg2

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
OUT_JSON = SCRIPT_DIR / "vox_cron" / "portfolio_dashboard.json"
MIN_SELL_WEIGHT_PCT = 2.5

# Integration map for dashboard health
BROKER_META = {
    "eToro": {"mode": "API + price updater", "manual": False},
    "Binance": {"mode": "API", "manual": False},
    "Bitso": {"mode": "API", "manual": False},
    "GBM Main": {"mode": "Manual Excel", "manual": True},
    "GBM USA": {"mode": "Manual Excel", "manual": True},
    "Schwab": {"mode": "Manual Excel/Photo", "manual": True},
    "IBKR": {"mode": "Manual Excel/Photo", "manual": True},
}


def get_db_connection():
    pwd = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    if not pwd or len(pwd) < 10:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("PGPASSWORD=") or line.startswith("DB_PASSWORD="):
                    pwd = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        database=os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("PGUSER", "postgres"),
        password=pwd,
        connect_timeout=20,
    )


def _f(x):
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None


def generate_dashboard_data():
    conn = get_db_connection()
    cur = conn.cursor()

    # ---- Consolidated positions ----
    cur.execute(
        """
        SELECT
            p.ticker,
            p.shares,
            p.live_price,
            CASE
                WHEN p.live_value_usd IS NOT NULL
                     AND p.live_value_usd::text <> 'NaN'
                     AND p.live_value_usd > 0
                THEN p.live_value_usd
                ELSE p.live_value
            END AS value_usd,
            COALESCE(p.grade, u.unified_grade) AS grade,
            COALESCE(p.council, u.action) AS council,
            p.sector,
            p.brokers,
            p.updated_at,
            u.unified_grade,
            u.vox_grade,
            u.tech_score
        FROM positions p
        LEFT JOIN unified_grades u ON u.ticker = p.ticker
        WHERE (
            COALESCE(p.shares, 0) > 0
            OR (p.ticker = 'MIRROR_TOTAL' AND COALESCE(p.live_value_usd, p.live_value, 0) > 0)
          )
          AND COALESCE(
            NULLIF(CASE WHEN p.live_value_usd::text = 'NaN' THEN NULL ELSE p.live_value_usd END, 0),
            NULLIF(p.live_value, 0),
            0
          ) > 0
        ORDER BY value_usd DESC NULLS LAST
        """
    )

    all_positions = []
    for row in cur.fetchall():
        (
            ticker, shares, price, value, grade, council, sector, brokers,
            updated_at, unified_grade, vox_grade, tech_score
        ) = row
        all_positions.append({
            "ticker": ticker,
            "shares": _f(shares) or 0,
            "price": _f(price) or 0,
            "value_usd": _f(value) or 0,
            "grade": _f(grade),
            "council": council,
            "sector": sector,
            "brokers": list(brokers) if brokers else [],
            "last_sync": updated_at.isoformat() if updated_at else None,
            "unified_grade": _f(unified_grade),
            "vox_grade": _f(vox_grade),
            "tech_score": _f(tech_score),
        })

    grand_total = sum(p["value_usd"] for p in all_positions)
    for p in all_positions:
        p["weight_pct"] = round(p["value_usd"] * 100 / grand_total, 2) if grand_total else 0

    # ---- Broker positions truth ----
    cur.execute(
        """
        SELECT broker, ticker, shares, avg_cost, live_price,
               COALESCE(live_value_usd, live_value, 0) AS value_usd,
               currency, grade, council, sector, source,
               last_sync_at, updated_at, price_source
        FROM broker_positions
        WHERE ticker NOT IN ('CASH')
          AND (
            COALESCE(shares, 0) > 0
            OR (ticker = 'MIRROR_TOTAL' AND COALESCE(live_value_usd, live_value, 0) > 0)
          )
        ORDER BY broker, value_usd DESC NULLS LAST
        """
    )
    broker_rows = cur.fetchall()
    broker_summary = {}
    broker_positions = defaultdict(list)
    for row in broker_rows:
        (
            broker, ticker, shares, avg_cost, live_price, value_usd,
            currency, grade, council, sector, source,
            last_sync_at, updated_at, price_source
        ) = row
        item = {
            "ticker": ticker,
            "shares": _f(shares) or 0,
            "avg_cost": _f(avg_cost),
            "price": _f(live_price) or 0,
            "value_usd": _f(value_usd) or 0,
            "currency": currency,
            "grade": _f(grade),
            "council": council,
            "sector": sector,
            "source": source,
            "last_sync": last_sync_at.isoformat() if last_sync_at else None,
            "last_price_update": updated_at.isoformat() if updated_at else None,
            "price_source": price_source,
        }
        broker_positions[broker].append(item)

    now = datetime.now(timezone.utc)
    for broker, items in broker_positions.items():
        total = sum(i["value_usd"] for i in items)
        grades = [i["grade"] for i in items if i["grade"] is not None]
        syncs = [i["last_sync"] for i in items if i["last_sync"]]
        prices = [i["last_price_update"] for i in items if i["last_price_update"]]
        last_sync = max(syncs) if syncs else None
        last_price = max(prices) if prices else None

        def age_days(iso):
            if not iso:
                return None
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return (now - dt).total_seconds() / 86400
            except Exception:
                return None

        sync_age = age_days(last_sync)
        price_age = age_days(last_price)
        meta = BROKER_META.get(broker, {"mode": "Unknown", "manual": True})
        # For API brokers, price freshness can keep health OK even if share-sync is older.
        # For manual brokers, share-sync age is authoritative.
        ref_age = sync_age
        if not meta.get("manual"):
            ages = [a for a in (sync_age, price_age) if a is not None]
            ref_age = min(ages) if ages else None

        if ref_age is None:
            health = "UNKNOWN"
        elif ref_age <= 2:
            health = "FRESH"
        elif ref_age <= 10:
            health = "AGING"
        else:
            health = "STALE"

        needs_manual = False
        if meta.get("manual"):
            needs_manual = health in ("STALE", "AGING", "UNKNOWN", "MISSING")
        else:
            # API broker: only flag manual help if both share-sync and prices are stale
            needs_manual = (sync_age is None or sync_age > 14) and (price_age is None or price_age > 3)

        broker_summary[broker] = {
            "positions": len(items),
            "total_usd": round(total, 2),
            "avg_grade": round(sum(grades) / len(grades), 1) if grades else None,
            "last_sync": last_sync,
            "last_price_update": last_price,
            "sync_age_days": round(sync_age, 1) if sync_age is not None else None,
            "price_age_days": round(price_age, 1) if price_age is not None else None,
            "health": health,
            "integration_mode": meta["mode"],
            "needs_manual_update": needs_manual,
            "top_positions": sorted(items, key=lambda x: x["value_usd"], reverse=True)[:10],
        }

    # Ensure all known brokers appear even if empty
    for broker, meta in BROKER_META.items():
        if broker not in broker_summary:
            broker_summary[broker] = {
                "positions": 0,
                "total_usd": 0,
                "avg_grade": None,
                "last_sync": None,
                "last_price_update": None,
                "sync_age_days": None,
                "price_age_days": None,
                "health": "MISSING",
                "integration_mode": meta["mode"],
                "needs_manual_update": True,
                "top_positions": [],
            }

    # ---- Action buckets (mandate-aware; multi-broker never a sell reason) ----
    try:
        from vox_portfolio_policy import classify_action, sleeve_snapshot, sleeve_for
    except ImportError:
        from pathlib import Path as _P
        import sys as _sys
        _sys.path.insert(0, str(_P.home() / ".hermes" / "scripts" / "vox_cron"))
        from vox_portfolio_policy import classify_action, sleeve_snapshot, sleeve_for

    sell_actions = []
    trim_actions = []
    hold_strong = []
    watch_actions = []
    for p in all_positions:
        g = p.get("grade")
        c = (p.get("council") or "").upper()
        w = p.get("weight_pct") or 0
        n_brokers = len(p.get("brokers") or [])
        decision = classify_action(
            p["ticker"], g, c, p["value_usd"], w, n_brokers=n_brokers,
            min_weight_pct=MIN_SELL_WEIGHT_PCT,
        )
        row = {
            "ticker": decision["ticker"],
            "grade": g,
            "council": c,
            "value_usd": p["value_usd"],
            "weight_pct": w,
            "brokers": p["brokers"],
            "decision": decision["decision"],
            "sleeve": decision["sleeve"],
            "reasons": decision.get("reasons") or [],
            "keep": decision.get("keep") or [],
            "label": decision.get("label"),
        }
        if decision["decision"] == "SELL":
            if w >= MIN_SELL_WEIGHT_PCT or p["value_usd"] >= 200:
                sell_actions.append(row)
            else:
                row["note"] = f"below {MIN_SELL_WEIGHT_PCT}% weight — noise filter"
                trim_actions.append(row)
        elif decision["decision"] == "TRIM":
            if w >= MIN_SELL_WEIGHT_PCT or p["value_usd"] >= 400:
                trim_actions.append(row)
        elif decision["decision"] == "WATCH":
            watch_actions.append(row)
        elif decision["decision"] in ("HOLD", "HOLD_BUCKET") and (
            c in ("BUY", "STRONG_BUY", "ACCUMULATE", "CORE BUY") or (g is not None and g >= 60) or decision["sleeve"] in ("QUALITY", "INDEX")
        ):
            if w >= 1.0:
                hold_strong.append(row)

    sell_actions.sort(key=lambda x: -x["value_usd"])
    trim_actions.sort(key=lambda x: -x["value_usd"])
    hold_strong.sort(key=lambda x: -x["value_usd"])
    watch_actions.sort(key=lambda x: -x["value_usd"])

    sleeve_data = sleeve_snapshot(
        [{"ticker": p["ticker"], "value_usd": p["value_usd"]} for p in all_positions],
        grand_total,
    )

    all_grades = [p["grade"] for p in all_positions if p["grade"] is not None]
    councils = defaultdict(float)
    for p in all_positions:
        if p["council"] and p["value_usd"] > 0:
            councils[p["council"]] += p["value_usd"]

    graded = [p for p in all_positions if p["grade"] is not None]
    top_grades = sorted(graded, key=lambda x: x["grade"], reverse=True)[:10]
    bottom_grades = sorted(graded, key=lambda x: x["grade"])[:10]

    broker_book_total = sum(v["total_usd"] for v in broker_summary.values())
    stale_brokers = [b for b, v in broker_summary.items() if v["health"] in ("STALE", "MISSING", "UNKNOWN")]

    dashboard_data = {
        "generated_at": datetime.now().isoformat(),
        "grand_total": round(grand_total, 2),
        "broker_book_total": round(broker_book_total, 2),
        "note": "grand_total uses consolidated positions; broker_book_total sums broker_positions (can double-count multi-broker names if not de-duped).",
        "mandate": "top-tier balanced ~20% aim; quality compounders OK; multi-broker never a sell reason",
        "total_positions": len(all_positions),
        "avg_grade": round(sum(all_grades) / len(all_grades), 1) if all_grades else 0,
        "grade_distribution": {
            "A (80-100)": len([g for g in all_grades if g >= 80]),
            "B (60-79)": len([g for g in all_grades if 60 <= g < 80]),
            "C (40-59)": len([g for g in all_grades if 40 <= g < 60]),
            "D (0-39)": len([g for g in all_grades if g < 40]),
        },
        "council_distribution": dict(councils),
        "broker_summary": broker_summary,
        "stale_brokers": stale_brokers,
        "manual_update_needed": [b for b, v in broker_summary.items() if v.get("needs_manual_update")],
        "sleeve_snapshot": sleeve_data,
        "actions": {
            "min_weight_pct": MIN_SELL_WEIGHT_PCT,
            "sell_now": sell_actions,
            "trim_review": [t for t in trim_actions if not t.get("note")],
            "noise_small_sells": [t for t in trim_actions if t.get("note")],
            "watch": watch_actions[:20],
            "core_holds": hold_strong[:15],
            "policy": "vox_portfolio_policy.py",
        },
        "top_grades": top_grades,
        "bottom_grades": bottom_grades,
        "all_positions": sorted(all_positions, key=lambda x: x["value_usd"], reverse=True)[:80],
        "integration_status": {
            b: {
                "mode": meta["mode"],
                "manual": meta["manual"],
                "health": broker_summary.get(b, {}).get("health"),
                "total_usd": broker_summary.get(b, {}).get("total_usd"),
                "sync_age_days": broker_summary.get(b, {}).get("sync_age_days"),
            }
            for b, meta in BROKER_META.items()
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(dashboard_data, indent=2, default=str))

    # Obsidian mirror
    try:
        obsidian = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "daily"
        obsidian.mkdir(parents=True, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        md = [
            f"# Portfolio Dashboard — {day}",
            "",
            f"- Generated: `{dashboard_data['generated_at']}`",
            f"- Consolidated AUM: **${dashboard_data['grand_total']:,.0f}**",
            f"- Positions: **{dashboard_data['total_positions']}**",
            f"- Avg grade: **{dashboard_data['avg_grade']:.1f}**",
            f"- Stale brokers: **{', '.join(stale_brokers) if stale_brokers else 'none'}**",
            "",
            "## Broker health",
            "",
            "| Broker | Mode | Health | Value | Sync age (d) | Manual? |",
            "|--------|------|--------|-------|--------------|---------|",
        ]
        for b, v in sorted(broker_summary.items(), key=lambda x: -x[1]["total_usd"]):
            md.append(
                f"| {b} | {v['integration_mode']} | {v['health']} | ${v['total_usd']:,.0f} | "
                f"{v['sync_age_days'] if v['sync_age_days'] is not None else '—'} | "
                f"{'YES' if v['needs_manual_update'] else 'no'} |"
            )

        md += ["", f"## SELL now (≥{MIN_SELL_WEIGHT_PCT}% weight)", ""]
        if sell_actions:
            for s in sell_actions:
                md.append(
                    f"- **{s['ticker']}** grade {s['grade']} {s['council']} "
                    f"${s['value_usd']:,.0f} ({s['weight_pct']}%) — {s['brokers']}"
                )
        else:
            md.append("- None above weight threshold")

        md += ["", f"## TRIM review (≥{MIN_SELL_WEIGHT_PCT}% weight)", ""]
        trims = dashboard_data["actions"]["trim_review"]
        if trims:
            for s in trims:
                md.append(
                    f"- **{s['ticker']}** grade {s['grade']} {s['council']} "
                    f"${s['value_usd']:,.0f} ({s['weight_pct']}%)"
                )
        else:
            md.append("- None")

        md += ["", "## Top holdings", ""]
        for p in all_positions[:12]:
            md.append(
                f"- {p['ticker']}: ${p['value_usd']:,.0f} ({p['weight_pct']}%) "
                f"grade {p['grade']} {p['council']} {p['brokers']}"
            )

        md += [
            "",
            "## How to update manual brokers",
            "- GBM Main / GBM USA: send Excel export",
            "- Schwab / IBKR: send Excel or clear screenshot",
            "- Bitso/eToro/Binance: API path (auto when credentials healthy)",
            "",
            f"Raw JSON: `{OUT_JSON}`",
        ]
        path = obsidian / f"PortfolioDashboard-{day}.md"
        path.write_text("\n".join(md) + "\n")
        print(f"✅ Obsidian snapshot: {path}")
    except Exception as e:
        print(f"Obsidian mirror warning: {e}")

    conn.close()
    print(f"✅ Dashboard data saved to {OUT_JSON}")
    return dashboard_data


if __name__ == "__main__":
    data = generate_dashboard_data()
    print("\n📊 Portfolio Dashboard Generated")
    print(f"Consolidated AUM: ${data['grand_total']:,.2f}")
    print(f"Positions: {data['total_positions']}")
    print(f"Avg grade: {data['avg_grade']:.1f}")
    print(f"Stale brokers: {', '.join(data['stale_brokers']) or 'none'}")
    print(f"SELL now (≥{MIN_SELL_WEIGHT_PCT}%): {len(data['actions']['sell_now'])}")
    for s in data["actions"]["sell_now"][:8]:
        print(f"  • {s['ticker']} {s['council']} ${s['value_usd']:,.0f} ({s['weight_pct']}%)")
