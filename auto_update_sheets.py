#!/usr/bin/env python3
"""
Auto-update Google Sheets from weekly snapshot JSON
Run after weekly_portfolio.py to push data to Sheets
"""
import json, subprocess, os, sys
from datetime import datetime

os.environ['PATH'] = os.path.expanduser('~/.composio') + ':' + os.environ['PATH']
SPREADSHEET_ID = "1VpCMR9NAK0TfW43XMQn0jDvI114c2E6Hc4rpu7VguNo"

def composio_exec(cmd, data):
    args_json = json.dumps(data)
    bash_cmd = f'export PATH="$HOME/.composio:$PATH" && composio execute "{cmd}" -d \'{args_json}\''
    result = subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"parse_error": True}

def main():
    # Load latest snapshot
    snapshot_file = sys.argv[1] if len(sys.argv) > 1 else "snapshots/snapshot_20260522.json"
    
    try:
        with open(snapshot_file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Snapshot not found: {snapshot_file}")
        return
    
    total = data.get("total_usd", 0)
    brokers = data.get("by_broker", {})
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    
    # Build row for Weekly Snapshots tab
    row = [
        date,
        total,
        brokers.get("eToro", {}).get("total", 0),
        brokers.get("gbm_main", {}).get("total", 0),
        brokers.get("gbm_usa", {}).get("total", 0),
        brokers.get("binance", {}).get("total", 0),
        brokers.get("schwab", {}).get("total", 0),
        brokers.get("ibkr", {}).get("total", 0),
        brokers.get("revolut", {}).get("total", 0),
        data.get("wow_change_usd", 0),
        data.get("wow_change_pct", 0),
        "Auto-updated"
    ]
    
    r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": "'Weekly Snapshots'!A2:L2",
        "values": [row],
        "value_input_option": "RAW"
    })
    
    if r.get("successful"):
        print(f"✅ Sheets updated: {date} | ${total:,.2f}")
    else:
        print(f"❌ Sheets update failed: {r}")

if __name__ == "__main__":
    main()
