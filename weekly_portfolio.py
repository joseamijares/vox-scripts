#!/usr/bin/env python3
"""
Weekly Portfolio Snapshot
- Refreshes Binance (and any future live APIs)
- Reads all broker JSONs (handles different formats)
- Calculates WoW changes vs last snapshot
- Generates summary output for Telegram + optional Drive/Sheets
"""

import json, os, sys, subprocess
from pathlib import Path
from datetime import datetime, timedelta

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
SNAPSHOT_DIR = SCRIPTS_DIR / "snapshots"
USD_MXN_RATE = 17.31


def run_binance():
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "binance_api.py")],
            capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  ⚠️ Binance refresh failed: {e}")
        return False


def extract_total(data, name):
    """Extract total USD from any broker JSON format."""
    if not data:
        return 0

    if name == "etoro":
        try:
            cp = data.get("clientPortfolio", {})
            # Direct positions
            positions = cp.get("positions", [])
            direct = sum(p.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0) for p in positions)
            # Mirror/copy trading positions
            mirrors = cp.get("mirrors", [])
            mirror_total = 0
            for m in mirrors:
                m_positions = m.get("positions", [])
                mirror_total += sum(p.get("unrealizedPnL", {}).get("exposureInAccountCurrency", 0) for p in m_positions)
            return direct + mirror_total
        except:
            if "total_value_usd" in data:
                return float(data["total_value_usd"])
            return 0

    elif name == "binance":
        return data.get("total_usd", 0)

    elif name == "bitso":
        # Bitso format: balances[] with value_usd
        balances = data.get("balances", [])
        return sum(b.get("value_usd", 0) for b in balances)

    elif name in ("ibkr", "schwab"):
        return data.get("portfolio_summary", {}).get("total_value", 0)

    elif name == "gbm_main":
        mxn_total = data.get("portfolio_summary", {}).get("total_value_mxn", 0)
        return mxn_total / USD_MXN_RATE if mxn_total else 0

    elif name == "gbm_usa":
        return data.get("portfolio_summary", {}).get("total_value_usd", 0)

    elif name == "revolut":
        # Priority: USD value, then MXN converted
        usd = data.get("portfolio_summary", {}).get("total_value_usd", 0)
        mxn = data.get("portfolio_summary", {}).get("total_value_mxn", 0)
        return usd if usd else (mxn / USD_MXN_RATE if mxn else 0)

    else:
        # Generic fallback
        for key in ["total_usd", "total_value_usd", "total_value", "value_usd", "total"]:
            if key in data:
                return float(data[key])
        return 0


def load_broker_total(name):
    """Load a broker JSON and extract total."""
    path = SCRIPTS_DIR / f"{name}_portfolio.json"
    if path.exists():
        try:
            data = json.load(open(path))
            return extract_total(data, name)
        except Exception as e:
            print(f"  ⚠️ Error reading {name}: {e}")
            return 0
    return 0


def load_last_snapshot():
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    files = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"), reverse=True)
    if files:
        try:
            return json.load(open(files[0]))
        except:
            pass
    return None


def save_snapshot(data):
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    path = SNAPSHOT_DIR / f"snapshot_{date_str}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def compute_changes(current, previous):
    if not previous:
        return {}
    changes = {}
    for broker, data in current.get("by_broker", {}).items():
        prev_val = previous.get("by_broker", {}).get(broker, {}).get("value_usd", 0)
        curr_val = data.get("value_usd", 0)
        change_usd = curr_val - prev_val
        change_pct = (change_usd / prev_val * 100) if prev_val > 0 else 0
        changes[broker] = {
            "previous": round(prev_val, 2),
            "current": round(curr_val, 2),
            "change_usd": round(change_usd, 2),
            "change_pct": round(change_pct, 2)
        }
    prev_total = previous.get("grand_total_usd", 0)
    curr_total = current.get("grand_total_usd", 0)
    changes["TOTAL"] = {
        "previous": round(prev_total, 2),
        "current": round(curr_total, 2),
        "change_usd": round(curr_total - prev_total, 2),
        "change_pct": round((curr_total - prev_total) / prev_total * 100, 2) if prev_total > 0 else 0
    }
    return changes


def build_summary(unified, changes):
    lines = []
    lines.append("📊 *Weekly Portfolio Snapshot*")
    lines.append(f"📅 {unified.get('last_updated', 'Today')}")
    lines.append("")

    grand = unified.get("grand_total_usd", 0)
    grand_mxn = unified.get("grand_total_mxn", 0)
    lines.append(f"🏦 *Total AUM:* `${grand:,.2f}` (`${grand_mxn:,.2f}` MXN)")

    total_change = changes.get("TOTAL", {})
    if total_change:
        emoji = "🟢" if total_change["change_usd"] >= 0 else "🔴"
        lines.append(f"{emoji} *WoW Change:* `${total_change['change_usd']:+,.2f}` ({total_change['change_pct']:+.2f}%)")
    lines.append("")

    lines.append("*By Broker:*")
    for broker, data in sorted(unified.get("by_broker", {}).items(), key=lambda x: x[1]["value_usd"], reverse=True):
        pct = data.get("pct_of_total", 0)
        val = data["value_usd"]
        if val < 1:
            continue

        change = changes.get(broker, {})
        c_str = ""
        if change:
            c_emoji = "🟢" if change["change_usd"] >= 0 else "🔴"
            c_str = f" {c_emoji}{change['change_usd']:+,.0f}"

        bar_len = int(pct / 2.5)
        bar = "█" * bar_len
        lines.append(f"  `{broker:12}` `${val:>10,.2f}` ({pct:.1f}%) {bar}{c_str}")

    lines.append("")
    lines.append("*By Asset Class:*")
    for cls, val in unified.get("by_asset_class", {}).items():
        if val >= 1:
            lines.append(f"  `{cls:20}` `${val:>10,.2f}`")

    # Crypto top 5
    binance = None
    try:
        binance = json.load(open(SCRIPTS_DIR / "binance_portfolio.json"))
    except:
        pass
    if binance and binance.get("balances"):
        lines.append("")
        lines.append("*🔒 Binance Top 5:*")
        for b in binance["balances"][:5]:
            lines.append(f"  `{b['asset']:8}` {b['total']:.4f} × ${b['price_usd']:.2f} = `${b['value_usd']:,.2f}`")

    return "\n".join(lines)


def main():
    print("🔄 Running weekly portfolio snapshot...")

    # Refresh live brokers
    print("  → Refreshing Binance...")
    run_binance()

    # Load all broker totals
    brokers = {
        "eToro": load_broker_total("etoro"),
        "Binance": load_broker_total("binance"),
        "Bitso": load_broker_total("bitso"),
        "IBKR": load_broker_total("ibkr"),
        "Schwab": load_broker_total("schwab"),
        "GBM USA": load_broker_total("gbm_usa"),
        "GBM Main": load_broker_total("gbm_main"),
        "Revolut": load_broker_total("revolut"),
    }

    # Aggregate
    by_broker = {}
    grand_total = 0
    for name, val in brokers.items():
        by_broker[name] = {
            "value_usd": round(val, 2),
            "value_mxn": round(val * USD_MXN_RATE, 2),
            "pct_of_total": 0
        }
        grand_total += val

    # Percentages
    for name, data in by_broker.items():
        data["pct_of_total"] = round(data["value_usd"] / grand_total * 100, 2) if grand_total > 0 else 0

    # Asset classes
    by_asset_class = {
        "social_trading": by_broker.get("eToro", {}).get("value_usd", 0),
        "us_brokers": sum(by_broker.get(k, {}).get("value_usd", 0) for k in ["Schwab", "IBKR", "GBM USA"]),
        "mexican_broker": by_broker.get("GBM Main", {}).get("value_usd", 0),
        "crypto_exchanges": by_broker.get("Binance", {}).get("value_usd", 0) + by_broker.get("Bitso", {}).get("value_usd", 0),
        "savings": by_broker.get("Revolut", {}).get("value_usd", 0),
    }

    unified = {
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "usd_mxn_rate": USD_MXN_RATE,
        "grand_total_usd": round(grand_total, 2),
        "grand_total_mxn": round(grand_total * USD_MXN_RATE, 2),
        "by_broker": by_broker,
        "by_asset_class": {k: round(v, 2) for k, v in by_asset_class.items()}
    }

    # Compare with last week
    prev = load_last_snapshot()
    changes = compute_changes(unified, prev)

    # Save
    snapshot_path = save_snapshot(unified)
    print(f"  💾 Snapshot saved: {snapshot_path}")

    unified_path = SCRIPTS_DIR / "unified_portfolio.json"
    with open(unified_path, "w") as f:
        json.dump(unified, f, indent=2)

    # Build and print summary
    summary = build_summary(unified, changes)

    print("\n" + "=" * 65)
    print(summary)
    print("=" * 65)

    summary_path = SNAPSHOT_DIR / f"summary_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(summary_path, "w") as f:
        f.write(summary)
    print(f"\n  💾 Summary saved: {summary_path}")

    # Also output clean summary for cron capture
    print("\n---TELEGRAM_SUMMARY_START---")
    print(summary)
    print("---TELEGRAM_SUMMARY_END---")

    return summary, unified, changes


if __name__ == "__main__":
    main()
