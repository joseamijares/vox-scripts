#!/usr/bin/env python3
"""
Unified Broker Dashboard — JOS-19
Aggregates all broker JSONs into one view.
"""

import json
import os
from pathlib import Path
from datetime import datetime


def load_json(path):
    """Load a JSON file if it exists."""
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return {}


def format_currency(value, currency="USD"):
    """Format currency value."""
    if currency == "USD":
        return f"${value:,.2f}"
    elif currency == "MXN":
        return f"${value:,.2f} MXN"
    return f"{value:,.2f}"


def build_dashboard():
    """Build unified dashboard from all broker JSONs."""
    scripts_dir = Path.home() / ".hermes" / "scripts"

    # Load unified portfolio (master file)
    portfolio = load_json(scripts_dir / "unified_portfolio.json")

    # Load individual broker files if they exist
    brokers = {
        "eToro": load_json(scripts_dir / "etoro_portfolio.json"),
        "Binance": load_json(scripts_dir / "binance_portfolio.json"),
        "Bitso": load_json(scripts_dir / "bitso_portfolio.json"),
        "IBKR": load_json(scripts_dir / "ibkr_portfolio.json"),
        "Schwab": load_json(scripts_dir / "schwab_portfolio.json"),
        "GBM": load_json(scripts_dir / "gbm_portfolio.json"),
        "Revolut": load_json(scripts_dir / "revolut_portfolio.json"),
    }

    # Build dashboard
    print("=" * 80)
    print("📊 VOX UNIFIED DASHBOARD")
    print("=" * 80)
    print(f"Last updated: {portfolio.get('last_updated', 'Unknown')}")
    print(f"USD/MXN rate: {portfolio.get('usd_mxn_rate', 'Unknown')}")
    print()

    # Totals
    total_usd = portfolio.get("grand_total_usd", 0)
    total_mxn = portfolio.get("grand_total_mxn", 0)

    print(f"💰 TOTAL AUM: {format_currency(total_usd)} / {format_currency(total_mxn, 'MXN')}")
    print()

    # By broker
    print("-" * 80)
    print("BY BROKER")
    print("-" * 80)

    by_broker = portfolio.get("by_broker", {})
    for broker_name, data in sorted(by_broker.items(), key=lambda x: x[1].get("value_usd", 0), reverse=True):
        value_usd = data.get("value_usd", 0)
        pct = data.get("pct_of_total", 0)
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"{broker_name:15} | {bar} | {format_currency(value_usd)} ({pct:.1f}%)")

    print()

    # By asset class
    print("-" * 80)
    print("BY ASSET CLASS")
    print("-" * 80)

    by_asset = portfolio.get("by_asset_class", {})
    total_asset = sum(by_asset.values()) if by_asset else 1
    for asset_class, value in sorted(by_asset.items(), key=lambda x: x[1], reverse=True):
        pct = value / total_asset * 100
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"{asset_class:20} | {bar} | {format_currency(value)} ({pct:.1f}%)")

    print()

    # Detailed positions (if available)
    print("-" * 80)
    print("DETAILED POSITIONS (Top 10)")
    print("-" * 80)

    all_positions = []
    for broker_name, broker_data in brokers.items():
        if not broker_data:
            continue
        positions = broker_data.get("positions", broker_data.get("assets", []))
        for pos in positions:
            all_positions.append({
                "broker": broker_name,
                "symbol": pos.get("symbol", pos.get("ticker", "?")),
                "name": pos.get("name", ""),
                "value": pos.get("value_usd", pos.get("market_value", 0)),
                "qty": pos.get("quantity", pos.get("qty", 0)),
            })

    # Sort by value
    all_positions.sort(key=lambda x: x["value"], reverse=True)

    for i, pos in enumerate(all_positions[:10], 1):
        print(f"{i:2}. {pos['symbol']:8} | {pos['broker']:10} | {pos['qty']:>10} | {format_currency(pos['value'])}")
        if pos["name"]:
            print(f"    {pos['name'][:60]}")

    print()

    # Grade alerts (if available)
    grade_path = scripts_dir / "grade_results.json"
    if grade_path.exists():
        print("-" * 80)
        print("RECENT GRADE ALERTS")
        print("-" * 80)
        try:
            with open(grade_path) as f:
                grades = json.load(f)
            recent = grades.get("grades", [])[-5:]
            for g in recent:
                emoji = "🟢" if g["total_grade"] >= 85 else "🟡" if g["total_grade"] >= 70 else "⚪" if g["total_grade"] >= 55 else "🔴"
                print(f"{emoji} {g['ticker']:8} | Grade: {g['total_grade']}/100 | {g['recommendation']}")
        except:
            pass
        print()

    # Trump alerts (if available)
    trump_path = scripts_dir / "trump_tracker_results.json"
    if trump_path.exists():
        print("-" * 80)
        print("RECENT POLICY ALERTS")
        print("-" * 80)
        try:
            with open(trump_path) as f:
                trump = json.load(f)
            high_impact = [t for t in trump.get("tweets", []) if t["classification"]["impact_score"] >= 7]
            for t in high_impact[:3]:
                print(f"🔴 {t['text'][:80]}...")
                print(f"   Sectors: {', '.join(t.get('affected_sectors', [])[:5])}")
        except:
            pass
        print()

    print("=" * 80)

    # Save dashboard to file
    dashboard_data = {
        "timestamp": datetime.now().isoformat(),
        "total_aum_usd": total_usd,
        "total_aum_mxn": total_mxn,
        "by_broker": by_broker,
        "by_asset_class": by_asset,
        "top_positions": all_positions[:20],
    }

    out_path = scripts_dir / "dashboard_snapshot.json"
    with open(out_path, "w") as f:
        json.dump(dashboard_data, f, indent=2)

    print(f"💾 Dashboard saved to: {out_path}")


def main():
    build_dashboard()


if __name__ == "__main__":
    main()
