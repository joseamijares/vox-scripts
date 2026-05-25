#!/usr/bin/env python3
import subprocess, json

COMPOSIO = "/Users/jos/.composio/composio"
P_ID = "1VpCMR9NAK0TfW43XMQn0jDvI114c2E6Hc4rpu7VguNo"
T_ID = "1O66XpOhacNCJhia8QpHu0RAIFvYozAD8a1tslY808iA"

def run(cmd, data):
    args = json.dumps(data)
    c = [COMPOSIO, "execute", cmd, "-d", args]
    r = subprocess.run(c, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except:
        return {"err": r.stdout[:300]}

# ========== PORTFOLIO TRACKER ==========

dashboard = [
    ["OPENCLAW PORTFOLIO", "", "", "", "", "", "", "", "", ""],
    ["Real-Time Command Center", "", "", "", "", "", "", "", "", ""],
    [""],
    ["📅 Snapshot", "2026-05-22", "", "🎯 Target", "20.0%", "", "📊 Risk", "HIGH / AGGRESSIVE"],
    ["💰 Total AUM", "$196,072.06", "", "📈 YTD", "+6.46%", "", "🏷️ Style", "GROWTH / THEMES"],
    ["📉 WoW", "+$11,895", "", "💵 Rate", "17.31", "", "🔔 Rebal", "2026-06-01"],
    [""],
    ["═══ BROKER BREAKDOWN ═══", "", "", "", "═══ ASSET CLASS ═══", "", "", ""],
    ["Broker", "Value", "%", "Status", "Class", "Value", "%", ""],
    ["eToro", 84258.94, "43.0%", "🟢 Live", "Social Trading", 84258.94, "43.0%", ""],
    ["GBM Main", 74071.21, "37.8%", "🟢 Manual", "Mexican Equities", 74071.21, "37.8%", ""],
    ["Binance", 19866.10, "10.1%", "🟢 API", "Crypto", "19866", "10.1%", ""],
    ["GBM USA", 14539.94, "7.4%", "🟡 Manual", "US Equities", 17471.29, "8.9%", ""],
    ["Schwab", 1661.35, "0.8%", "🟡 Manual", "Savings", 404.39, "0.2%", ""],
    ["IBKR", 1270.00, "0.7%", "🟡 Manual", "", "", "", ""],
    ["Revolut", 404.39, "0.2%", "🟢 API", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["═══ CONVICTION TRADES ═══", "", "", "", "", "", "", ""],
    ["Ticker", "Theme", "Conviction", "Action", "Entry", "Current", "Stop", "Status"],
    ["CEG", "Energy AI", "9/10", "BUY", 150, "~150", 120, "NO POSITION"],
    ["VST", "Energy AI", "9/10", "BUY", 110, "~110", 85, "NO POSITION"],
    ["NVDA", "AI Supply", "8/10", "ACCUM", 140, "~140", 110, "NO POSITION"],
    ["SOL", "Crypto", "7/10", "ACCUM", 85, 86.73, 65, "HOLDING"],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": P_ID,
    "range": "'🎯 Dashboard'!A1:H24",
    "values": dashboard,
    "value_input_option": "RAW"
})
print("Dashboard:", r.get("successful", False))

# Weekly Snapshots
snapshots = [
    ["DATE", "TOTAL AUM", "ETORO", "GBM MAIN", "GBM USA", "BINANCE", "SCHWAB", "IBKR", "REVOLUT", "BITSO", "WOW $", "WOW %", "SPX", "BTC", "NOTES"],
    ["2026-05-22", 196072.06, 84258.94, 74071.21, 14539.94, 19866.10, 1661.35, 1270.00, 404.39, 0.12, 11895.84, 6.46, "—", 76973.25, "Baseline"],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ["═══ ALL WEEKS ═══"],
    ["[Auto-populated every Friday 9 AM]"],
]
r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": P_ID,
    "range": "'📊 Weekly Snapshots'!A1:O5",
    "values": snapshots,
    "value_input_option": "RAW"
})
print("Weekly:", r.get("successful", False))

# Asset Allocation
alloc = [
    ["CURRENT vs TARGET ALLOCATION", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["Asset Class", "Current $", "Current %", "Target %", "Gap", "Action", "Priority"],
    ["Social Trading", 84258.94, "43.0%", "5%", "-38.0%", "SELL → buy US growth", "🔴 URGENT"],
    ["Mexican Equities", 74071.21, "37.8%", "15%", "-22.8%", "SELL → buy AI energy", "🔴 URGENT"],
    ["Crypto", 19866.10, "10.1%", "20%", "+9.9%", "ADD SOL + ETH stake", "🟡 BUILD"],
    ["US Equities", 17471.29, "8.9%", "35%", "+26.1%", "BUY NVDA AVGO VRT", "🟡 BUILD"],
    ["Savings", 404.39, "0.2%", "5%", "+4.8%", "Grow to $10K", "🟡 BUILD"],
    ["Cash", 0, "0%", "10%", "+10%", "Hold for dips", "🟢 WAIT"],
    ["Energy AI", 0, "0%", "15%", "+15%", "NEW: Buy CEG + VST", "🟢 NEW"],
    ["Space", 0, "0%", "5%", "+5%", "NEW: RKLB spec", "🟢 NEW"],
    ["", "", "", "", "", "", ""],
    ["═══ REBALANCE PLAN ═══"],
    ["Step", "Action", "$", "", "", "", ""],
    ["1", "Trim eToro → $20K", "Free $64K", "", "", "", ""],
    ["2", "Trim GBM Main → $30K", "Free $44K", "", "", "", ""],
    ["3", "Buy CEG $29K", "via Schwab", "", "", "", ""],
    ["4", "Buy VST $14.5K", "via Schwab", "", "", "", ""],
    ["5", "Buy NVDA $16K", "via Schwab/GBM", "", "", "", ""],
    ["6", "Add SOL $10K", "via Binance", "", "", "", ""],
]
r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": P_ID,
    "range": "'🏛️ Asset Allocation'!A1:G20",
    "values": alloc,
    "value_input_option": "RAW"
})
print("Allocation:", r.get("successful", False))

# Current Holdings
holdings = [
    ["CURRENT HOLDINGS & EXIT STRATEGY", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", ""],
    ["Asset", "Position", "Entry", "Current", "P&L", "% P&L", "Sell Target", "Stop Loss", "Action"],
    ["═══ BINANCE ═══", "", "", "", "", "", "", "", ""],
    ["BTC", "0.153", "~$72K avg", 76973, "—", "—", "$120K", "$60K", "HOLD/ADD"],
    ["ETH", "2.457", "~$2.1K", 2121, "—", "—", "$4K", "$1.5K", "HOLD+STAKE"],
    ["BNB", "1.730", "—", 660, "—", "—", "$800", "$500", "HOLD"],
    ["SOL", "6.299", "~$87", 87, "—", "—", "$150", "$50", "ACCUMULATE"],
    ["DOGE", "4,186", "—", 0.11, "—", "—", "$0.25", "$0.06", "HOLD"],
    ["═══ ETORO ═══", "", "", "", "", "", "", "", ""],
    ["Copy-Trader A", "~$5,728", "—", "—", "—", "—", "Watch perf", "-15% dd", "MONITOR"],
    ["Copy-Trader B", "~$6,153", "—", "—", "—", "—", "Watch perf", "-15% dd", "MONITOR"],
    ["Direct Positions", "~$72,377", "—", "—", "—", "—", "TBD", "", "REDUCE"],
    ["═══ GBM MAIN ═══", "", "", "", "", "", "", "", ""],
    ["Mexican Equities", "$74,071", "—", "—", "—", "—", "Trim to $30K", "", "REDUCE"],
    ["═══ SCHWAB/IBKR ═══", "", "", "", "", "", "", "", ""],
    ["[CEG / VST / NVDA]", "$1,931", "—", "—", "—", "—", "CEG→$200", "", "BUY"],
]
r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": P_ID,
    "range": "'🏷️ Current Holdings'!A1:I17",
    "values": holdings,
    "value_input_option": "RAW"
})
print("Holdings:", r.get("successful", False))

# Exit Strategy
exit_tab = [
    ["EXIT STRATEGY & RISK MGMT", "", "", "", "", ""],
    ["", "", "", "", "", ""],
    ["Position", "Sell Trigger", "TP1", "TP2", "Stop Loss", "Notes"],
    ["CEG", "Core holding", "$200 (33%)", "$250 (67%)", "$120 (-20%)", "Trim on spikes"],
    ["VST", "Core holding", "$160 (45%)", "$200 (82%)", "$85 (-23%)", "Trim on spikes"],
    ["NVDA", "Trim 50% run", "$210 (50%)", "$280 (100%)", "$110 (-21%)", "Trim 1/3 each"],
    ["SOL", "Trim on spike", "$120 (38%)", "$180 (107%)", "$50 (-42%)", "Trailing stop"],
    ["RKLB", "Spec only", "$180 (50%)", "Exit", "$90 (-25%)", "Small pos"],
    ["BTC", "HODL", "$120K (56%)", "$180K (134%)", "$60K (-22%)", "Core"],
    ["ETH", "HODL", "$4K (89%)", "$6K (183%)", "$1.5K (-29%)", "Core"],
    ["", "", "", "", "", ""],
    ["═══ REBALANCE RULES ═══"],
    ["Rule", "Trigger", "Action"],
    ["Overweight", ">125% target", "Sell to target"],
    ["Underweight", "<75% target", "Buy dip"],
    ["Stop hit", "Stop triggered", "Sell 100%"],
    ["Profit", "+50% from entry", "Sell 25%"],
    ["Monthly", "Last Friday", "Council review"],
]
r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": P_ID,
    "range": "'🚪 Exit Strategy'!A1:C17",
    "values": exit_tab,
    "value_input_option": "RAW"
})
print("Exit:", r.get("successful", False))

print("\n📊 PORTFOLIO TRACKER DONE!")
