#!/usr/bin/env python3
"""VOX Portfolio Brain — full book dashboard + sectors + L/M/S strategies.

Not a day-trading bot. Mandate: top-tier balanced ~20% aim.
Driver (VOX) plans; user executes.

Outputs:
  - ~/.hermes/cron/output/brain/Brain-YYYY-MM-DD.{md,json,html}
  - Obsidian vox/memory/brain/ (Brain-LATEST + dated + SectorMap + Tracker)
  - Updates thesis stubs for material actions
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
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
    NAME_CAPS,
    SLEEVE_TARGETS,
    classify_action,
    normalize_ticker,
    sleeve_for,
    sleeve_snapshot,
)

HERMES = Path.home() / ".hermes"
OUT = HERMES / "cron" / "output" / "brain"
OBS_BRAIN = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "brain"
OBS_THESES = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "theses"
MIN_ACTION_WEIGHT = 2.5
MIN_DUST_USD = 80.0

# Sector fallback map when DB sector missing
SECTOR_HINTS = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "GOOG": "Technology",
    "AMZN": "Consumer Discretionary", "META": "Communication", "NVDA": "Technology",
    "TSM": "Technology", "AMD": "Technology", "AVGO": "Technology", "MU": "Technology",
    "SMH": "Technology", "CRWD": "Technology", "DDOG": "Technology", "SNOW": "Technology",
    "SHOP": "Technology", "ESTC": "Technology", "IBM": "Technology", "ORCL": "Technology",
    "CRM": "Technology", "QLYS": "Technology", "OKTA": "Technology", "CRDO": "Technology",
    "NBIS": "Technology", "APP": "Technology", "SPOT": "Communication", "SE": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary", "MELI": "Consumer Discretionary", "COST": "Consumer Staples",
    "WMT": "Consumer Staples", "MNST": "Consumer Staples", "HD": "Consumer Discretionary",
    "VOO": "Index", "QQQ": "Index", "VTI": "Index", "SPY": "Index", "IWM": "Index",
    "BTC": "Crypto", "ETH": "Crypto", "XRP": "Crypto", "TRX": "Crypto", "BNB": "Crypto",
    "DOGE": "Crypto", "SOL": "Crypto", "COIN": "Financials", "HOOD": "Financials",
    "C": "Financials", "AXS": "Financials", "APH": "Industrials", "GE": "Industrials",
    "LMT": "Industrials", "XLE": "Energy", "XOM": "Energy", "CVX": "Energy", "CEG": "Utilities",
    "OKLO": "Utilities", "IONQ": "Technology", "SPCX": "Industrials", "OSCR": "Healthcare",
    "LLY": "Healthcare", "CRSP": "Healthcare", "ARKG": "Healthcare", "POET": "Technology",
    "NUTX": "Healthcare", "DASH": "Consumer Discretionary", "BIDU": "Technology",
    "MIRROR_TOTAL": "Copy", "CBRS": "Index",
}


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
    if len(pw) < 5:
        raise RuntimeError("DB password missing")
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        dbname=os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("PGUSER", "postgres"),
        password=pw,
        connect_timeout=20,
    )
    return conn, conn.cursor(cursor_factory=RealDictCursor)


def f(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        return None if v != v else v
    except Exception:
        return None


def assign_horizon(sleeve: str, decision: str, grade: Optional[float], ticker: str) -> str:
    """LONG / MEDIUM / SHORT — not day-trade."""
    t = normalize_ticker(ticker)
    if decision in ("SELL",) and sleeve in ("EXIT", "CRYPTO_ALT"):
        return "SHORT"  # cleanup window weeks–months
    if decision == "TRIM" and sleeve in ("CRYPTO_ALT", "EXIT", "THEME"):
        return "SHORT"
    if sleeve in ("QUALITY", "INDEX"):
        return "LONG"
    if sleeve == "CRYPTO_CORE":
        return "LONG"
    if sleeve == "COPY":
        return "MEDIUM"
    if sleeve == "MOMENTUM":
        return "MEDIUM"
    if sleeve == "THEME":
        return "MEDIUM" if (grade or 0) >= 50 else "SHORT"
    if decision in ("BUY", "ACCUMULATE") or (grade or 0) >= 65:
        return "MEDIUM"
    if (grade or 0) < 48:
        return "SHORT"
    return "MEDIUM"


def horizon_note(h: str) -> str:
    return {
        "LONG": "3–7+ years · compound / index core · ignore noise",
        "MEDIUM": "3–18 months · thesis + momentum · rebalance quarterly",
        "SHORT": "weeks–1 quarter · cleanup / size-cut / thesis-break · NOT day-trade",
    }.get(h, "")


def load_book(cur) -> Tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
    cur.execute(
        """
        SELECT ticker, shares, avg_cost, live_price, live_value, live_value_usd,
               grade, council, brokers, sector, currency
        FROM positions
        WHERE COALESCE(live_value_usd, 0) > 0 OR COALESCE(shares, 0) > 0
        ORDER BY COALESCE(live_value_usd, 0) DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    # broker health
    cur.execute(
        """
        SELECT broker, COUNT(*) n, COALESCE(SUM(live_value_usd),0) v, MAX(last_sync_at) last
        FROM broker_positions GROUP BY broker
        """
    )
    brokers = {r["broker"]: dict(r) for r in cur.fetchall()}
    # regime
    regime = {}
    try:
        cur.execute("SELECT * FROM market_regime ORDER BY created_at DESC NULLS LAST LIMIT 1")
        r = cur.fetchone()
        if r:
            regime = dict(r)
    except Exception:
        cur.connection.rollback()

    aum = sum(f(r.get("live_value_usd")) or 0 for r in rows) or 1.0
    book = []
    for r in rows:
        t = normalize_ticker(r.get("ticker") or "")
        v = f(r.get("live_value_usd")) or 0
        w = 100.0 * v / aum
        g = f(r.get("grade"))
        council = r.get("council")
        brokers_list = r.get("brokers") or []
        if isinstance(brokers_list, str):
            brokers_list = [brokers_list]
        action = classify_action(
            t, g, council, v, w, n_brokers=len(brokers_list), min_weight_pct=MIN_ACTION_WEIGHT
        )
        sector = (r.get("sector") or SECTOR_HINTS.get(t) or "Unknown").strip() or "Unknown"
        sleeve = action.get("sleeve") or sleeve_for(t)
        horizon = assign_horizon(sleeve, action.get("decision") or "HOLD", g, t)
        cap = NAME_CAPS.get(t)
        book.append(
            {
                "ticker": t,
                "shares": f(r.get("shares")) or 0,
                "price": f(r.get("live_price")),
                "value_usd": round(v, 2),
                "weight_pct": round(w, 2),
                "grade": int(g) if g is not None else None,
                "council": council,
                "brokers": list(brokers_list),
                "sector": sector,
                "sleeve": sleeve,
                "horizon": horizon,
                "decision": action.get("decision"),
                "reasons": action.get("reasons") or [],
                "keep": action.get("keep") or [],
                "alert": bool(action.get("alert")),
                "label": action.get("label"),
                "cap_pct": round(cap * 100, 1) if cap else None,
                "over_cap": bool(cap and w > cap * 100 + 0.5),
            }
        )
    meta = {"brokers": brokers, "regime": regime, "aum": aum}
    return book, aum, meta


def sector_map(book: List[Dict], aum: float) -> List[Dict]:
    values: Dict[str, float] = defaultdict(float)
    names: Dict[str, List[str]] = defaultdict(list)
    for p in book:
        if p["ticker"] == "MIRROR_TOTAL":
            s = "Copy"
        else:
            s = str(p.get("sector") or "Unknown")
        values[s] += float(p.get("value_usd") or 0)
        names[s].append(str(p["ticker"]))
    rows = []
    for s, val in sorted(values.items(), key=lambda x: -x[1]):
        pct = 100.0 * val / aum if aum else 0.0
        bar_len = int(round(pct / 2))
        bar = "█" * bar_len + "░" * max(0, 20 - bar_len)
        rows.append(
            {
                "sector": s,
                "value_usd": round(val, 2),
                "weight_pct": round(pct, 2),
                "count": len(names[s]),
                "top": names[s][:6],
                "bar": bar,
            }
        )
    return rows


def plan_actions(book: List[Dict], aum: float) -> Dict[str, List[Dict]]:
    sells, trims, buys, holds_long, watches = [], [], [], [], []
    for p in book:
        d = p["decision"]
        item = {
            "ticker": p["ticker"],
            "weight_pct": p["weight_pct"],
            "value_usd": p["value_usd"],
            "grade": p["grade"],
            "horizon": p["horizon"],
            "sleeve": p["sleeve"],
            "reasons": p["reasons"],
            "keep": p["keep"],
            "brokers": p["brokers"],
            "alert": p["alert"] or (d == "SELL" and p["value_usd"] >= 300),
        }
        if d == "SELL":
            sells.append(item)
        elif d == "TRIM":
            trims.append(item)
        elif d in ("HOLD", "HOLD_BUCKET") and p["horizon"] == "LONG":
            holds_long.append(item)
        elif d in ("WATCH",):
            watches.append(item)
        # Buys = high grade not overweight, or underweight quality/index
        if (
            p["sleeve"] in ("QUALITY", "INDEX", "MOMENTUM")
            and (p["grade"] or 0) >= 62
            and d in ("HOLD", "WATCH")
            and not p.get("over_cap")
            and p["weight_pct"] < 6
            and p["ticker"] not in ("MIRROR_TOTAL",)
        ):
            buys.append({**item, "action": "ADD_ON_WEAKNESS", "note": "quality/momentum — accumulate dips, no chase"})

    # Material first
    sells.sort(key=lambda x: -x["value_usd"])
    trims.sort(key=lambda x: -x["weight_pct"])
    buys.sort(key=lambda x: -(x.get("grade") or 0))
    return {
        "sell": sells,
        "trim": trims,
        "add_on_weakness": buys[:12],
        "core_long": holds_long[:20],
        "watch": watches[:15],
        "material_sell": [s for s in sells if s["weight_pct"] >= MIN_ACTION_WEIGHT or s["value_usd"] >= 500],
        "material_trim": [t for t in trims if t["weight_pct"] >= MIN_ACTION_WEIGHT],
    }


def strategies_block(book: List[Dict], sleeves: Dict, sectors: List[Dict]) -> Dict[str, Any]:
    by_h = defaultdict(list)
    for p in book:
        by_h[p["horizon"]].append(p)
    out = {}
    for h in ("LONG", "MEDIUM", "SHORT"):
        items = sorted(by_h.get(h, []), key=lambda x: -x["value_usd"])
        val = sum(p["value_usd"] for p in items)
        out[h] = {
            "note": horizon_note(h),
            "value_usd": round(val, 2),
            "weight_pct": round(100 * val / (sum(p["value_usd"] for p in book) or 1), 2),
            "count": len(items),
            "top": [
                {
                    "ticker": p["ticker"],
                    "weight_pct": p["weight_pct"],
                    "decision": p["decision"],
                    "grade": p["grade"],
                    "sleeve": p["sleeve"],
                }
                for p in items[:12]
            ],
            "rules": {
                "LONG": [
                    "Do not sell quality compounders on noise",
                    "Rebalance only on sleeve drift or thesis break",
                    "Add on multi-week weakness, never FOMO daily spikes",
                ],
                "MEDIUM": [
                    "Thesis must be written (Setup / Trigger / Invalidation)",
                    "If thesis breaks → pivot or exit within 1–4 weeks",
                    "Size caps apply; no single satellite > soft cap",
                ],
                "SHORT": [
                    "Cleanup / trim only — no lottery tickets",
                    "Exit dust crypto alts and failed themes",
                    "Not day-trading: min hold days unless thesis shattered",
                ],
            }[h],
        }
    # Sleeve drift priorities
    drift = sorted(
        (sleeves.get("sleeves") or []),
        key=lambda r: abs(r.get("gap_pp") or 0),
        reverse=True,
    )[:6]
    out["sleeve_priorities"] = drift
    out["sector_tilt"] = sectors[:8]
    return out


def ensure_thesis(ticker: str, decision: str, reasons: List[str]) -> None:
    OBS_THESES.mkdir(parents=True, exist_ok=True)
    path = OBS_THESES / f"{ticker}.md"
    if path.exists():
        return
    day = datetime.now().strftime("%Y-%m-%d")
    path.write_text(
        f"""---
ticker: "{ticker}"
status: "active"
horizon: "medium"
decision: "{decision}"
generated_at: "{datetime.now().isoformat()}"
---

# Thesis — {ticker}

**Status:** active · Decision bias: {decision}

## Setup
- Opened from Portfolio Brain on {day}
- Reasons: {'; '.join(reasons) if reasons else '_tbd_'}

## Trigger
- _Add entry / add-on levels_

## Invalidation
- _Thesis break → pivot or exit (ok to change)_

## Horizon
- Prefer LONG/MEDIUM unless cleanup SHORT

## Notes
- Multi-broker ownership is never a sell reason
"""
    )


def bar_chart_md(sectors: List[Dict]) -> str:
    lines = ["```", "SECTOR WEIGHTS", ""]
    for s in sectors:
        lines.append(f"{s['sector'][:18]:18} {s['bar']} {s['weight_pct']:5.1f}%  ${s['value_usd']:,.0f}")
    lines.append("```")
    return "\n".join(lines)


def render_markdown(payload: Dict[str, Any]) -> str:
    day = payload["date"]
    aum = payload["aum"]
    book = payload["positions"]
    actions = payload["actions"]
    strat = payload["strategies"]
    sectors = payload["sectors"]
    sleeves = payload["sleeves"]["sleeves"]
    brokers = payload["meta"]["brokers"]

    lines = [
        f"# VOX Portfolio Brain — {day}",
        "",
        f"**Role:** VOX plans · you execute  \n**Style:** Balanced ~20% aim · **not day-trading**  \n**AUM:** ${aum:,.0f} · **Positions:** {len(book)}  \n**Generated:** {payload['generated_at']}",
        "",
        "## Operating system",
        "1. **LONG** compounders + index — hold through noise",
        "2. **MEDIUM** thesis names — rebalance quarterly; pivot if thesis breaks",
        "3. **SHORT** cleanup only — weeks, not minutes",
        "4. Alerts/actions material only if **≥2.5% weight** (or junk ≥$500)",
        "5. Multi-broker ownership is **never** a sell reason",
        "",
        "## Broker map",
        "| Broker | Value | Positions | Last sync |",
        "|--------|------:|----------:|-----------|",
    ]
    for b, m in sorted(brokers.items(), key=lambda x: -float(x[1].get("v") or 0)):
        lines.append(f"| {b} | ${float(m.get('v') or 0):,.0f} | {m.get('n')} | {m.get('last')} |")

    lines += ["", "## Sector allocation", bar_chart_md(sectors), ""]
    lines += [
        "| Sector | Weight | Value | # | Top |",
        "|--------|-------:|------:|--:|-----|",
    ]
    for s in sectors:
        lines.append(
            f"| {s['sector']} | {s['weight_pct']:.1f}% | ${s['value_usd']:,.0f} | {s['count']} | {', '.join(s['top'])} |"
        )

    lines += ["", "## Sleeve drift vs target", "| Sleeve | Now % | Target % | Gap pp | Gap $ |", "|--------|------:|---------:|-------:|------:|"]
    for s in sorted(sleeves, key=lambda x: x["sleeve"]):
        lines.append(
            f"| {s['sleeve']} | {s['now_pct']:.1f}% | {s['target_pct']:.1f}% | {s['gap_pp']:+.1f} | ${s['gap_usd']:+,.0f} |"
        )

    # Strategies
    for h in ("LONG", "MEDIUM", "SHORT"):
        block = strat[h]
        lines += [
            "",
            f"## Strategy — {h} ({block['weight_pct']:.1f}% · ${block['value_usd']:,.0f})",
            f"_{block['note']}_",
            "",
            "**Rules:**",
        ]
        for r in block["rules"]:
            lines.append(f"- {r}")
        lines += ["", "| Ticker | W% | Grade | Decision | Sleeve |", "|--------|---:|------:|----------|--------|"]
        for p in block["top"]:
            lines.append(
                f"| {p['ticker']} | {p['weight_pct']:.1f}% | {p['grade'] or '—'} | {p['decision']} | {p['sleeve']} |"
            )

    # Actions
    lines += ["", "## Execute this week (driver plan)", "### Material SELL / cleanup"]
    mat = actions["material_sell"] or actions["sell"][:8]
    if not mat:
        lines.append("- _None material_")
    for a in mat[:10]:
        why = "; ".join(a["reasons"][:2]) if a["reasons"] else "mandate cleanup"
        flag = "🔔" if a.get("alert") else "·"
        lines.append(
            f"- {flag} **{a['ticker']}** {a['weight_pct']:.1f}% (${a['value_usd']:,.0f}) g{a['grade']} — {why}"
        )

    lines.append("")
    lines.append("### Material TRIM")
    mt = actions["material_trim"] or actions["trim"][:8]
    if not mt:
        lines.append("- _None material_")
    for a in mt[:10]:
        why = "; ".join(a["reasons"][:2]) if a["reasons"] else "size"
        lines.append(f"- **{a['ticker']}** {a['weight_pct']:.1f}% — {why}")

    lines += ["", "### ADD on weakness (no chase)", "_Only if capital freed from cleanup / cash_"]
    for a in actions["add_on_weakness"][:8]:
        lines.append(
            f"- **{a['ticker']}** g{a['grade']} {a['sleeve']} {a['weight_pct']:.1f}% — {a.get('note','accumulate dips')}"
        )

    # Full book
    lines += [
        "",
        "## Full positions tracker",
        "| Ticker | W% | Value | Grade | Council | Sleeve | Horizon | Decision | Brokers |",
        "|--------|---:|------:|------:|---------|--------|---------|----------|---------|",
    ]
    for p in book:
        br = ",".join(p["brokers"][:3]) if p["brokers"] else "—"
        lines.append(
            f"| {p['ticker']} | {p['weight_pct']:.2f}% | ${p['value_usd']:,.0f} | {p['grade'] if p['grade'] is not None else '—'} | "
            f"{p['council'] or '—'} | {p['sleeve']} | {p['horizon']} | **{p['decision']}** | {br} |"
        )

    lines += [
        "",
        "## Weekly pull checklist",
        "- [ ] GBM Main Excel",
        "- [ ] GBM USA Excel",
        "- [ ] Schwab CSV/export",
        "- [ ] IBKR screenshot/CSV",
        "- [ ] Confirm API brokers (eToro/Binance/Bitso) healthy",
        "- [ ] Review Breaking-LATEST + sleeve drift",
        "- [ ] Update theses for any pivot",
        "",
        "## How VOX uses this brain daily",
        "1. Read Brain-LATEST + Breaking-LATEST + data health",
        "2. Respect LONG core — do not churn",
        "3. Push SHORT cleanups and MEDIUM rebalance only",
        "4. Suggest plays you execute — VOX does not auto-trade",
        "",
        f"_Source: vox_portfolio_brain.py · mandate vox_portfolio_policy.py_",
    ]
    return "\n".join(lines) + "\n"


def render_html(payload: Dict[str, Any]) -> str:
    """Self-contained HTML dashboard for local open."""
    day = payload["date"]
    aum = payload["aum"]
    book = payload["positions"]
    sectors = payload["sectors"]
    actions = payload["actions"]

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    sec_rows = "".join(
        f"<tr><td>{esc(s['sector'])}</td><td>{s['weight_pct']:.1f}%</td>"
        f"<td>${s['value_usd']:,.0f}</td><td>{s['count']}</td>"
        f"<td style='font-family:monospace'>{esc(s['bar'])}</td></tr>"
        for s in sectors
    )
    pos_rows = "".join(
        f"<tr class='{esc(p['decision']).lower()}'><td><b>{esc(p['ticker'])}</b></td>"
        f"<td>{p['weight_pct']:.2f}%</td><td>${p['value_usd']:,.0f}</td>"
        f"<td>{p['grade'] if p['grade'] is not None else '—'}</td>"
        f"<td>{esc(p['council'] or '—')}</td><td>{esc(p['sleeve'])}</td>"
        f"<td>{esc(p['horizon'])}</td><td><b>{esc(p['decision'])}</b></td>"
        f"<td>{esc(','.join(p['brokers'] or []))}</td></tr>"
        for p in book
    )
    max_sec = max((s["weight_pct"] for s in sectors), default=1) or 1
    bars = "".join(
        f"<div class='bar-row'><span class='lab'>{esc(s['sector'][:14])}</span>"
        f"<div class='bar' style='width:{max(4, 100*s['weight_pct']/max_sec):.0f}%'></div>"
        f"<span class='pct'>{s['weight_pct']:.1f}%</span></div>"
        for s in sectors[:12]
    )
    sells = "".join(
        f"<li><b>{esc(a['ticker'])}</b> {a['weight_pct']:.1f}% — {esc('; '.join(a['reasons'][:2]))}</li>"
        for a in (actions["material_sell"] or actions["sell"])[:12]
    ) or "<li>None material</li>"
    adds = "".join(
        f"<li><b>{esc(a['ticker'])}</b> g{a['grade']} — {esc(a.get('note',''))}</li>"
        for a in actions["add_on_weakness"][:10]
    ) or "<li>None</li>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>VOX Portfolio Brain {esc(day)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
body{{font-family:ui-sans-serif,system-ui,sans-serif;background:#0b1220;color:#e6edf7;margin:0;padding:24px;}}
h1,h2{{color:#7dd3fc}} a{{color:#93c5fd}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px;margin:12px 0;}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{border-bottom:1px solid #1f2937;padding:6px 8px;text-align:left}}
th{{color:#94a3b8;font-weight:600}}
tr.sell{{background:rgba(239,68,68,.08)}} tr.trim{{background:rgba(245,158,11,.08)}}
tr.hold,tr.hold_bucket{{background:transparent}}
.bar-row{{display:flex;align-items:center;gap:8px;margin:4px 0}}
.lab{{width:110px;font-size:12px;color:#94a3b8}}
.bar{{height:12px;background:linear-gradient(90deg,#0ea5e9,#22d3ee);border-radius:6px}}
.pct{{width:50px;font-size:12px}}
.kpi{{display:flex;gap:16px;flex-wrap:wrap}}
.kpi div{{background:#0f172a;padding:12px 16px;border-radius:10px;border:1px solid #1e293b}}
.muted{{color:#94a3b8;font-size:13px}}
</style></head><body>
<h1>VOX Portfolio Brain — {esc(day)}</h1>
<p class="muted">Balanced mandate · not day-trading · VOX plans · you execute · AUM <b>${aum:,.0f}</b> · {len(book)} positions</p>
<div class="kpi">
  <div><div class="muted">AUM</div><b>${aum:,.0f}</b></div>
  <div><div class="muted">Positions</div><b>{len(book)}</b></div>
  <div><div class="muted">LONG wt</div><b>{payload['strategies']['LONG']['weight_pct']:.1f}%</b></div>
  <div><div class="muted">MEDIUM wt</div><b>{payload['strategies']['MEDIUM']['weight_pct']:.1f}%</b></div>
  <div><div class="muted">SHORT wt</div><b>{payload['strategies']['SHORT']['weight_pct']:.1f}%</b></div>
</div>
<div class="card"><h2>Sectors</h2>{bars}
<table><thead><tr><th>Sector</th><th>W%</th><th>Value</th><th>#</th><th>Bar</th></tr></thead>
<tbody>{sec_rows}</tbody></table></div>
<div class="card"><h2>Execute — material SELL</h2><ul>{sells}</ul>
<h2>ADD on weakness</h2><ul>{adds}</ul></div>
<div class="card"><h2>Full positions</h2>
<table><thead><tr>
<th>Ticker</th><th>W%</th><th>Value</th><th>Grade</th><th>Council</th><th>Sleeve</th><th>Horizon</th><th>Decision</th><th>Brokers</th>
</tr></thead><tbody>{pos_rows}</tbody></table></div>
<p class="muted">Generated by vox_portfolio_brain.py</p>
</body></html>"""


def write_tracker(payload: Dict[str, Any]) -> str:
    """Compact tracker for daily compound consumption."""
    day = payload["date"]
    lines = [
        f"# Position Tracker — {day}",
        "",
        f"AUM ${payload['aum']:,.0f} · {len(payload['positions'])} names",
        "",
        "## Material actions",
    ]
    for a in payload["actions"]["material_sell"][:8]:
        lines.append(f"- SELL {a['ticker']} {a['weight_pct']}%")
    for a in payload["actions"]["material_trim"][:8]:
        lines.append(f"- TRIM {a['ticker']} {a['weight_pct']}%")
    if not payload["actions"]["material_sell"] and not payload["actions"]["material_trim"]:
        lines.append("- None ≥2.5%")
    lines += ["", "## Horizon mix"]
    for h in ("LONG", "MEDIUM", "SHORT"):
        s = payload["strategies"][h]
        lines.append(f"- {h}: {s['weight_pct']}% (${s['value_usd']:,.0f}) · {s['count']} names")
    return "\n".join(lines) + "\n"


def build() -> Dict[str, Any]:
    conn, cur = connect()
    book, aum, meta = load_book(cur)
    sectors = sector_map(book, aum)
    sleeves = sleeve_snapshot([{"ticker": p["ticker"], "value_usd": p["value_usd"]} for p in book], aum)
    actions = plan_actions(book, aum)
    strategies = strategies_block(book, sleeves, sectors)
    conn.close()

    day = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mandate": "top-tier balanced ~20% annual · not day-trading",
        "aum": round(aum, 2),
        "positions": book,
        "sectors": sectors,
        "sleeves": sleeves,
        "actions": actions,
        "strategies": strategies,
        "meta": {
            "brokers": {
                k: {
                    "n": int(v.get("n") or 0),
                    "v": float(v.get("v") or 0),
                    "last": str(v.get("last")),
                }
                for k, v in (meta.get("brokers") or {}).items()
            },
            "regime": {
                k: (str(v) if not isinstance(v, (int, float)) else v)
                for k, v in (meta.get("regime") or {}).items()
                if k in ("regime", "confidence", "description", "created_at", "vix_level")
            },
        },
        "rules": {
            "min_action_weight_pct": MIN_ACTION_WEIGHT,
            "multi_broker_never_sell_reason": True,
            "day_trading": False,
            "horizons": {
                "LONG": horizon_note("LONG"),
                "MEDIUM": horizon_note("MEDIUM"),
                "SHORT": horizon_note("SHORT"),
            },
        },
    }
    return payload


def publish(payload: Dict[str, Any]) -> Dict[str, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    OBS_BRAIN.mkdir(parents=True, exist_ok=True)
    day = payload["date"]
    md = render_markdown(payload)
    html = render_html(payload)
    tracker = write_tracker(payload)

    paths = {
        "json": OUT / f"Brain-{day}.json",
        "md": OUT / f"Brain-{day}.md",
        "html": OUT / f"Brain-{day}.html",
        "obs_md": OBS_BRAIN / f"Brain-{day}.md",
        "obs_latest": OBS_BRAIN / "Brain-LATEST.md",
        "obs_sectors": OBS_BRAIN / f"SectorMap-{day}.md",
        "obs_tracker": OBS_BRAIN / f"Tracker-{day}.md",
        "obs_tracker_latest": OBS_BRAIN / "Tracker-LATEST.md",
    }
    paths["json"].write_text(json.dumps(payload, indent=2, default=str))
    paths["md"].write_text(md)
    paths["html"].write_text(html)
    paths["obs_md"].write_text(md)
    paths["obs_latest"].write_text(md)
    paths["obs_tracker"].write_text(tracker)
    paths["obs_tracker_latest"].write_text(tracker)

    # sector note
    sec_md = [f"# Sector Map — {day}", "", bar_chart_md(payload["sectors"]), ""]
    for s in payload["sectors"]:
        sec_md.append(f"- **{s['sector']}** {s['weight_pct']}% · ${s['value_usd']:,.0f} · {', '.join(s['top'])}")
    paths["obs_sectors"].write_text("\n".join(sec_md) + "\n")
    (OBS_BRAIN / "SectorMap-LATEST.md").write_text("\n".join(sec_md) + "\n")

    # thesis stubs for material actions
    for a in payload["actions"]["material_sell"] + payload["actions"]["material_trim"]:
        ensure_thesis(a["ticker"], a.get("decision") or "REVIEW", a.get("reasons") or [])
    for a in payload["actions"]["add_on_weakness"][:5]:
        ensure_thesis(a["ticker"], "ADD_ON_WEAKNESS", a.get("reasons") or ["accumulate quality dips"])

    # weekly folder pointer
    weekly = Path.home() / "Documents/Obsidian/VOX/vox/memory/weekly"
    weekly.mkdir(parents=True, exist_ok=True)
    (weekly / f"Brain-Weekly-Pointer-{day}.md").write_text(
        f"# Weekly Brain Pointer — {day}\n\n- [[memory/brain/Brain-LATEST|Brain LATEST]]\n"
        f"- [[memory/brain/Tracker-LATEST|Tracker]]\n"
        f"- [[memory/brain/SectorMap-LATEST|Sectors]]\n"
        f"- [[memory/decisions/Breaking-LATEST|Breaking shocks]]\n"
        f"- Open HTML: `{paths['html']}`\n"
    )

    return {k: str(v) for k, v in paths.items()}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="no stdout summary (cron silent if empty)")
    args = ap.parse_args()

    payload = build()
    paths = publish(payload)

    if args.json_only:
        print(json.dumps({"aum": payload["aum"], "paths": paths}, indent=2))
        return 0

    # Telegram-friendly summary (always print — daily useful)
    aum = payload["aum"]
    s = payload["strategies"]
    lines = [
        f"🧠 **VOX Portfolio Brain — {payload['date']}**",
        f"AUM **${aum:,.0f}** · {len(payload['positions'])} positions · not day-trading",
        f"LONG {s['LONG']['weight_pct']:.0f}% · MED {s['MEDIUM']['weight_pct']:.0f}% · SHORT {s['SHORT']['weight_pct']:.0f}%",
        "",
        "**Material SELL:**",
    ]
    ms = payload["actions"]["material_sell"]
    if not ms:
        lines.append("· none ≥2.5%")
    for a in ms[:6]:
        lines.append(f"· {a['ticker']} {a['weight_pct']:.1f}% g{a['grade']}")
    lines.append("**Material TRIM:**")
    mt = payload["actions"]["material_trim"]
    if not mt:
        lines.append("· none ≥2.5%")
    for a in mt[:6]:
        lines.append(f"· {a['ticker']} {a['weight_pct']:.1f}%")
    lines.append("**ADD on weakness:**")
    for a in payload["actions"]["add_on_weakness"][:5]:
        lines.append(f"· {a['ticker']} g{a['grade']} {a['sleeve']}")
    lines += [
        "",
        f"Sectors top: " + ", ".join(f"{x['sector']} {x['weight_pct']:.0f}%" for x in payload["sectors"][:5]),
        f"Full: Obsidian `memory/brain/Brain-LATEST` · HTML `{paths['html']}`",
    ]
    if not args.quiet:
        print("\n".join(lines))
    else:
        # still print for deliver:origin jobs that want a pulse
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
