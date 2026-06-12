#!/usr/bin/env python3
"""
VOX 6-Layer Trading Harness
Runs full multi-signal analysis on portfolio + watchlist.
Outputs structured JSON for dashboard and Telegram reports.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

DASHBOARD_URL = "https://web-production-9e321.up.railway.app"


def api_get(path: str) -> dict:
    url = f"{DASHBOARD_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print(f"ERROR fetching {path}: {e}")
        return {}


def api_post(path: str, payload: dict) -> dict:
    url = f"{DASHBOARD_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print(f"ERROR posting {path}: {e}")
        return {}


def layer0_data_audit(positions: list, watchlist: list) -> dict:
    aum = sum(p.get("live_value", 0) for p in positions)
    graded = [p for p in positions if p.get("grade") and p.get("grade") > 0]
    ungraded = [p for p in positions if not p.get("grade") or p.get("grade") == 0]
    stale = [p for p in positions if not p.get("updated_at")]
    return {
        "status": "ok" if len(stale) < 5 else "warning",
        "total_positions": len(positions),
        "total_watchlist": len(watchlist),
        "aum": round(aum, 2),
        "graded_positions": len(graded),
        "ungraded_positions": len(ungraded),
        "stale_positions": len(stale),
        "notes": [
            f"AUM: ${aum:,.2f}",
            f"Graded: {len(graded)}/{len(positions)}",
            f"Watchlist: {len(watchlist)} tickers",
        ],
    }


def layer1_portfolio_state(positions: list) -> dict:
    aum = sum(p.get("live_value", 0) for p in positions)
    sectors: dict[str, float] = {}
    for p in positions:
        s = p.get("sector") or "Unclassified"
        sectors[s] = sectors.get(s, 0) + p.get("live_value", 0)

    sector_pct = {s: round(v / aum * 100, 2) if aum else 0 for s, v in sectors.items()}
    top10 = sorted(positions, key=lambda x: -x.get("live_value", 0))[:10]
    weak = [p for p in positions if (p.get("grade") or 0) < 45 and p.get("grade")]
    sell_council = [p for p in positions if p.get("council") == "SELL"]
    gaps = [s for s, pct in sector_pct.items() if pct < 5 and s not in ("None", "Unclassified")]

    return {
        "aum": round(aum, 2),
        "sector_allocation": sector_pct,
        "top_holdings": [
            {"ticker": p.get("ticker"), "value": p.get("live_value"), "grade": p.get("grade"), "council": p.get("council")}
            for p in top10
        ],
        "weak_positions": [
            {"ticker": p.get("ticker"), "value": p.get("live_value"), "grade": p.get("grade")}
            for p in weak
        ],
        "sell_council": [p.get("ticker") for p in sell_council],
        "sector_gaps": gaps,
    }


def layer2_famous_traders(watchlist: list, positions: list) -> dict:
    owned = {p.get("ticker") for p in positions}
    ft = [w for w in watchlist if w.get("sector") == "Famous Traders"]
    missing = [w for w in ft if w.get("ticker") not in owned]
    present = [w for w in ft if w.get("ticker") in owned]
    top_missing = sorted(missing, key=lambda x: -(x.get("grade") or 0))[:15]
    return {
        "total_famous_trader_tickers": len(ft),
        "owned_by_user": len(present),
        "missing_from_portfolio": len(missing),
        "top_missing": [
            {"ticker": w.get("ticker"), "grade": w.get("grade"), "entry": w.get("entry"), "target": w.get("target")}
            for w in top_missing
        ],
    }


def layer3_supply_chain(watchlist: list) -> dict:
    thematic_sectors = ["AI Infrastructure", "Quantum", "Space", "Cybersecurity", "Security", "Nuclear"]
    result = {}
    for sector in thematic_sectors:
        tickers = [w for w in watchlist if w.get("sector") == sector]
        top = sorted(tickers, key=lambda x: -(x.get("grade") or 0))[:3]
        result[sector] = {
            "count": len(tickers),
            "top_tickers": [
                {"ticker": w.get("ticker"), "grade": w.get("grade"), "target": w.get("target")}
                for w in top
            ],
        }
    return result


def layer4_weather() -> dict:
    try:
        rows = api_get("/api/weather").get("risks", [])
    except Exception:
        rows = []
    return {
        "active_risks": len(rows),
        "risks": [
            {"region": r.get("region"), "type": r.get("risk_type"), "severity": r.get("severity")}
            for r in rows[:5]
        ],
        "themes": list({r.get("risk_type") for r in rows if r.get("risk_type")}),
    }


def layer5_macro() -> dict:
    data = api_get("/api/regime")
    # API may return {regime: {...}} or {regime: {...}, ...}
    regime = data.get("regime") or data
    if isinstance(regime, str):
        return {
            "regime": regime,
            "confidence": data.get("confidence", 0),
            "vix_level": data.get("vix_level", 0),
            "spy_trend": data.get("spy_trend", "UNKNOWN"),
            "notes": data.get("notes", ""),
        }
    return {
        "regime": regime.get("regime", "UNKNOWN") if isinstance(regime, dict) else "UNKNOWN",
        "confidence": regime.get("confidence", 0) if isinstance(regime, dict) else 0,
        "vix_level": regime.get("vix_level", 0) if isinstance(regime, dict) else 0,
        "spy_trend": regime.get("spy_trend", "UNKNOWN") if isinstance(regime, dict) else "UNKNOWN",
        "notes": regime.get("notes", "") if isinstance(regime, dict) else "",
    }


def layer6_technical_fundamental(candidates: list) -> list:
    """Placeholder: in production, this calls yfinance for each candidate."""
    # For now, return candidate list with existing grades
    return [
        {
            "ticker": c.get("ticker"),
            "grade": c.get("grade") or 0,
            "sector": c.get("sector"),
            "entry": c.get("entry"),
            "target": c.get("target"),
            "stop": c.get("stop"),
        }
        for c in candidates
    ]


def cross_layer_synthesis(layers: dict, candidates: list) -> list:
    """Find tickers that appear in multiple layers and rank them."""
    ft_tickers = {c["ticker"] for c in layers["layer2"]["top_missing"]}
    sc_tickers = set()
    for sector_data in layers["layer3"].values():
        for t in sector_data["top_tickers"]:
            sc_tickers.add(t["ticker"])

    weather_themes = set(layers["layer4"]["themes"])
    macro_regime = layers["layer5"]["regime"]

    scored = []
    for c in candidates:
        ticker = c.get("ticker")
        grade = c.get("grade") or 0
        layers_hit = 0
        hit_reasons = []

        if grade >= 60:
            layers_hit += 1
            hit_reasons.append("strong grade")
        if ticker in ft_tickers:
            layers_hit += 1
            hit_reasons.append("famous trader")
        if ticker in sc_tickers:
            layers_hit += 1
            hit_reasons.append("supply chain leader")
        if c.get("sector") in ["Energy", "Utilities", "Agriculture"] and weather_themes:
            layers_hit += 1
            hit_reasons.append("weather exposed")
        if macro_regime in ["BULL", "RISK_ON"] and grade >= 55:
            layers_hit += 1
            hit_reasons.append("macro aligned")

        composite = (layers_hit * 10) + grade
        scored.append({
            "ticker": ticker,
            "grade": grade,
            "sector": c.get("sector"),
            "layers_hit": layers_hit,
            "composite": composite,
            "hit_reasons": hit_reasons,
            "entry": c.get("entry"),
            "target": c.get("target"),
            "stop": c.get("stop"),
        })

    scored.sort(key=lambda x: -x["composite"])
    return scored


def generate_action_plan(synthesis: list, portfolio: list, aum: float) -> dict:
    owned = {p.get("ticker") for p in portfolio}
    buy_candidates = [s for s in synthesis if s["composite"] >= 70 and s["grade"] >= 60 and s["ticker"] not in owned]
    sell_candidates = [p for p in portfolio if (p.get("grade") or 0) < 45 and p.get("grade")]
    trim_candidates = [p for p in portfolio if (p.get("grade") or 0) >= 80]

    return {
        "buy": buy_candidates[:5],
        "sell": [
            {"ticker": p.get("ticker"), "value": p.get("live_value"), "grade": p.get("grade")}
            for p in sell_candidates[:5]
        ],
        "trim": [
            {"ticker": p.get("ticker"), "value": p.get("live_value"), "grade": p.get("grade")}
            for p in trim_candidates[:5]
        ],
        "watch": [s for s in synthesis if 55 <= s["composite"] < 70][:5],
    }


def main():
    print("=" * 60)
    print("VOX 6-LAYER TRADING HARNESS")
    print(f"Run at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    positions_data = api_get("/api/positions")
    watchlist_data = api_get("/api/watchlist")

    positions = positions_data.get("positions", [])
    watchlist = watchlist_data.get("watchlist", [])

    # Layer 0
    print("\n[LAYER 0] Data Audit...")
    layer0 = layer0_data_audit(positions, watchlist)
    print(f"  AUM: ${layer0['aum']:,.2f}")
    print(f"  Positions: {layer0['total_positions']}, Watchlist: {layer0['total_watchlist']}")

    # Layer 1
    print("\n[LAYER 1] Portfolio State...")
    layer1 = layer1_portfolio_state(positions)
    print(f"  Top holding: {layer1['top_holdings'][0]['ticker']} (${layer1['top_holdings'][0]['value']:,.2f})")
    print(f"  Sector gaps: {', '.join(layer1['sector_gaps']) or 'None'}")
    print(f"  Weak positions: {len(layer1['weak_positions'])}")

    # Layer 2
    print("\n[LAYER 2] Famous Traders...")
    layer2 = layer2_famous_traders(watchlist, positions)
    print(f"  Famous trader tickers: {layer2['total_famous_trader_tickers']}")
    print(f"  Missing from portfolio: {layer2['missing_from_portfolio']}")
    print(f"  Top missing: {', '.join(t['ticker'] for t in layer2['top_missing'][:5])}")

    # Layer 3
    print("\n[LAYER 3] Supply Chain Sectors...")
    layer3 = layer3_supply_chain(watchlist)
    for sector, data in layer3.items():
        if data["count"] > 0:
            top = data["top_tickers"][0] if data["top_tickers"] else {}
            print(f"  {sector}: {data['count']} tickers, top: {top.get('ticker', 'N/A')} (grade {top.get('grade', 'N/A')})")

    # Layer 4
    print("\n[LAYER 4] Weather Patterns...")
    layer4 = layer4_weather()
    print(f"  Active risks: {layer4['active_risks']}")
    print(f"  Themes: {', '.join(layer4['themes']) or 'None'}")

    # Layer 5
    print("\n[LAYER 5] Macro Trends...")
    layer5 = layer5_macro()
    print(f"  Regime: {layer5['regime']} (confidence: {layer5['confidence']})")
    print(f"  VIX: {layer5['vix_level']}, SPY trend: {layer5['spy_trend']}")

    # Layer 6 (candidate scoring from existing data)
    print("\n[LAYER 6] Technical + Fundamental...")
    candidates = watchlist + positions
    layer6 = layer6_technical_fundamental(candidates)
    print(f"  Candidates scored: {len(layer6)}")

    # Cross-layer synthesis
    print("\n[CROSS-LAYER SYNTHESIS]...")
    layers = {
        "layer0": layer0,
        "layer1": layer1,
        "layer2": layer2,
        "layer3": layer3,
        "layer4": layer4,
        "layer5": layer5,
        "layer6": layer6,
    }
    synthesis = cross_layer_synthesis(layers, candidates)
    print(f"  Top composite score: {synthesis[0]['ticker']} ({synthesis[0]['composite']}) — layers: {synthesis[0]['layers_hit']}")

    # Action plan
    action_plan = generate_action_plan(synthesis, positions, layer1["aum"])

    # Final report
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": layers,
        "synthesis": synthesis[:20],
        "action_plan": action_plan,
    }

    output_path = "/Users/jos/.hermes/scripts/vox_harness_report.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n✅ Harness report saved to {output_path}")
    print("\n--- TOP BUY CANDIDATES ---")
    for b in action_plan["buy"][:5]:
        print(f"  BUY {b['ticker']} — composite {b['composite']} — reasons: {', '.join(b['hit_reasons'])}")
    print("\n--- SELL CANDIDATES ---")
    for s in action_plan["sell"]:
        print(f"  SELL {s['ticker']} — grade {s['grade']} — value ${s['value']:,.2f}")


if __name__ == "__main__":
    main()
