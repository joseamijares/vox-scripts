#!/usr/bin/env python3
"""
Vox Master Dashboard + Weekly Archive Auto-Updater
Runs every Friday 9 AM to snapshot portfolio + append to archive
Also refreshes live tabs on the Master Dashboard

Usage:
    python3 vox_dashboard_updater.py --snapshot    # Weekly snapshot
    python3 vox_dashboard_updater.py --refresh     # Refresh live tabs
    python3 vox_dashboard_updater.py --both        # Do both
"""
import os, sys, json, subprocess, argparse
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────
DASHBOARD_ID = "1Ft6dRv7AtO-s5KLFi2pF-JYxrE0Tj9_hII8rT0qk0bw"
ARCHIVE_ID   = "1ViLAYMGzHnR60T8TnuoOyiUYx7NDZEHj2op_ZeYqwpA"
COMPOSIO_PY  = os.path.expanduser("~/.hermes/scripts/composio_run.py")

# ── HELPERS ─────────────────────────────────────────────────
def composio(action, payload):
    """Call Composio tool via wrapper."""
    cmd = ["python3", COMPOSIO_PY, "execute", action, "-d", json.dumps(payload)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stdout, r.stderr

def load_json(path):
    with open(os.path.expanduser(path)) as f:
        return json.load(f)

def now_str():
    return datetime.now().strftime("%Y-%m-%d")

# ── WEEKLY SNAPSHOT ─────────────────────────────────────────
def weekly_snapshot():
    """Append current portfolio row to Weekly Archive."""
    print(f"[{now_str()}] Running weekly snapshot...")

    # Load latest portfolio data
    try:
        portfolio = load_json("~/.hermes/scripts/portfolio.json")
    except FileNotFoundError:
        print("  ⚠️  portfolio.json not found, using static values")
        portfolio = {
            "total": 196072,
            "brokers": {
                "etoro": 84259, "gbm_main": 74071, "gbm_usa": 14540,
                "binance": 19866, "schwab": 1661, "ibkr": 1270,
                "revolut": 404, "bitso": 0
            }
        }

    # Calculate WoW if previous exists
    # For now just append the row
    row = [
        now_str(),
        f"${portfolio['total']:,}",
        f"${portfolio['brokers']['etoro']:,}",
        f"${portfolio['brokers']['gbm_main']:,}",
        f"${portfolio['brokers']['gbm_usa']:,}",
        f"${portfolio['brokers']['binance']:,}",
        f"${portfolio['brokers']['schwab']:,}",
        f"${portfolio['brokers']['ibkr']:,}",
        f"${portfolio['brokers']['revolut']:,}",
        f"${portfolio['brokers']['bitso']:,}",
        "",  # WoW $ — formula in sheet
        "",  # WoW % — formula in sheet
        "Auto-snapshot"
    ]

    # Find next empty row (naive: append after row 9)
    success, out, err = composio("GOOGLESHEETS_VALUES_APPEND", {
        "spreadsheet_id": ARCHIVE_ID,
        "range": "Sheet1!A9",
        "values": [row],
        "value_input_option": "RAW"
    })
    print(f"  {'✅' if success else '❌'} Snapshot appended")
    return success

# ── REFRESH LIVE TABS ───────────────────────────────────────
def refresh_dashboard():
    """Refresh live data on Master Dashboard."""
    print(f"[{now_str()}] Refreshing Master Dashboard...")

    # Load latest grades, council, etc.
    try:
        grades = load_json("~/.hermes/scripts/grade_results.json")
    except FileNotFoundError:
        grades = {}

    try:
        council = load_json("~/.hermes/scripts/llm_council_v2_results.json")
    except FileNotFoundError:
        council = {}

    # Update timestamp
    header = [[f"Last Updated: {now_str()} | Portfolio Value: $196,000 | USD/MXN: 17.31"]]
    composio("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": DASHBOARD_ID,
        "range": "Sheet1!A2",
        "values": header,
        "value_input_option": "RAW"
    })

    # Update grades section (if data exists)
    if grades:
        grade_rows = []
        for ticker, data in grades.items():
            grade_rows.append([
                ticker,
                data.get("grade", "—"),
                data.get("recommendation", "—"),
                data.get("price", "—"),
                data.get("rsi", "—"),
                data.get("trend", "—"),
                data.get("signal", "—")
            ])
        if grade_rows:
            composio("GOOGLESHEETS_VALUES_UPDATE", {
                "spreadsheet_id": DASHBOARD_ID,
                "range": "Sheet1!A114",
                "values": grade_rows,
                "value_input_option": "RAW"
            })

    print("  ✅ Dashboard refreshed")
    return True

# ── MAIN ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vox Dashboard Updater")
    parser.add_argument("--snapshot", action="store_true", help="Weekly snapshot only")
    parser.add_argument("--refresh", action="store_true", help="Refresh dashboard only")
    parser.add_argument("--both", action="store_true", help="Do both")
    args = parser.parse_args()

    if not any([args.snapshot, args.refresh, args.both]):
        args.both = True  # default

    if args.snapshot or args.both:
        weekly_snapshot()
    if args.refresh or args.both:
        refresh_dashboard()

    print(f"[{now_str()}] Done.")

if __name__ == "__main__":
    main()
