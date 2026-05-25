#!/usr/bin/env python3
import subprocess, json, os

os.environ['PATH'] = os.path.expanduser('~/.composio') + ':' + os.environ['PATH']
SPREADSHEET_ID = "1VpCMR9NAK0TfW43XMQn0jDvI114c2E6Hc4rpu7VguNo"

def composio_exec(cmd, data):
    args_json = json.dumps(data)
    bash_cmd = f'export PATH="$HOME/.composio:$PATH" && composio execute "{cmd}" -d \'{args_json}\''
    result = subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"raw": result.stdout[:300], "stderr": result.stderr[:300], "error": "parse failed"}

# Rename Sheet1 to Dashboard
print("Renaming Sheet1...")
r = composio_exec("GOOGLESHEETS_UPDATE_SHEET_PROPERTIES", {
    "spreadsheetId": SPREADSHEET_ID,
    "updateSheetProperties": {"properties": {"sheetId": 0, "title": "🎯 Dashboard"}, "fields": "title"}}
)
print("Rename:", r.get("successful", r.get("error", "unknown")))

# Dashboard
dashboard = [
    ["🎯 OPENCLAW PORTFOLIO — COMMAND CENTER", "", "", "", "", "", "", ""],
    [""],
    ["📅 Snapshot Date", "2026-05-22", "", "Target Return", "20%", "", "Risk Profile", "HIGH"],
    ["💰 Total AUM", "$196,072.06", "", "USD/MXN Rate", "17.31", "", "Weeks Tracked", "1"],
    ["📈 WoW Change", "+$11,895.84 (+6.46%)", "", "Next Snapshot", "2026-05-29", "", "", ""],
    [""],
    ["BROKER", "VALUE", "% AUM", "STATUS", "", "ASSET CLASS", "VALUE", "% AUM"],
    ["eToro", "84258.94", "43.0%", "🟢 Connected", "", "Social Trading", "84258.94", "43.0%"],
    ["GBM Main", "74071.21", "37.8%", "🟢 Manual", "", "Mexican Equities", "74071.21", "37.8%"],
    ["Binance", "19866.10", "10.1%", "🟢 API Live", "", "Crypto", "19866.22", "10.1%"],
    ["GBM USA", "14539.94", "7.4%", "🟡 Manual", "", "US Equities", "17471.29", "8.9%"],
    ["Schwab", "1661.35", "0.8%", "🟡 Manual", "", "Savings", "404.39", "0.2%"],
    ["IBKR", "1270.00", "0.7%", "🟡 Manual", "", "", "", ""],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "🎯 Dashboard!A1:H13",
    "values": dashboard,
    "value_input_option": "RAW"
})
print("Dashboard:", r.get("successful", r.get("error", "unknown")))

# Weekly Snapshots
snapshots = [
    ["Date", "Total AUM", "eToro", "GBM Main", "GBM USA", "Binance", "Schwab", "IBKR", "Revolut", "WoW $", "WoW %", "Notes"],
    ["2026-05-22", 196072.06, 84258.94, 74071.21, 14539.94, 19866.10, 1661.35, 1270.00, 404.39, 11895.84, 6.46, "Initial snapshot"],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "📊 Weekly Snapshots!A1:L2",
    "values": snapshots,
    "value_input_option": "RAW"
})
print("Snapshots:", r.get("successful", r.get("error", "unknown")))

# Watchlist
watchlist = [
    ["Ticker", "Theme", "Conviction", "Entry Target", "Current", "Stop Loss", "Size", "Status", "Source"],
    ["CEG", "Energy for AI", 9, 150, "", 120, "", "📌 Research", "Council"],
    ["VST", "Energy for AI", 9, 110, "", 85, "", "📌 Research", "Council"],
    ["NVDA", "AI Supply Chain", 8, 140, "", 110, "", "📌 Research", "Council"],
    ["AVGO", "AI Supply Chain", 7, 220, "", 180, "", "📌 Research", "Council"],
    ["SOL", "Crypto", 7, 85, "", 65, "", "📌 Research", "Council"],
    ["RKLB", "Space", 6, 120, "", 90, "", "🎲 Speculative", "Council"],
    ["ASTS", "Space", 6, "", "", "", "", "📌 Research", "U.S. News"],
    ["LUNR", "Space", 5, "", "", "", "", "📌 Research", "U.S. News"],
    ["VRT", "AI Infrastructure", 7, "", "", "", "", "📌 Research", "Zacks"],
    ["LRCX", "Semi Equipment", 7, "", "", "", "", "📌 Research", "Yahoo Finance"],
    ["MRVL", "Networking", 6, "", "", "", "", "📌 Research", "Reddit"],
    ["MU", "Memory/HBM", 6, "", "", "", "", "📌 Research", "Reddit"],
    ["CEG", "Energy for AI", 9, 150, "", 120, "", "📌 Research", "Zacks Energy"],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "👁️ Watchlist!A1:I13",
    "values": watchlist,
    "value_input_option": "RAW"
})
print("Watchlist:", r.get("successful", r.get("error", "unknown")))

# X Momentum
x_momentum = [
    ["Date", "Ticker", "X Mentions", "Sentiment", "Volume", "Price Action", "Narrative", "Action"],
    ["2026-05-22", "CEG", "High", "🔥 Bullish", "Elevated", "Down 30%", "AI energy demand", "📥 Accumulate"],
    ["2026-05-22", "VST", "High", "🔥 Bullish", "Elevated", "Down 33%", "Nuclear renaissance", "📥 Accumulate"],
    ["2026-05-22", "NVDA", "Very High", "⚖️ Mixed", "High", "Sideways", "AI chip demand", "⏸️ Hold/Add"],
    ["2026-05-22", "RKLB", "Very High", "🔥 Bullish", "Very High", "+415% YoY", "SpaceX IPO catalyst", "🎲 Speculative"],
    ["2026-05-22", "SOL", "High", "🔥 Bullish", "Normal", "+1%", "L1 staking growth", "📥 Accumulate"],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "🐦 X Momentum!A1:H5",
    "values": x_momentum,
    "value_input_option": "RAW"
})
print("X Momentum:", r.get("successful", r.get("error", "unknown")))

# Crypto Tracker
crypto = [
    ["Asset", "Exchange", "Amount", "Price", "Value", "24h %", "Weight %", "Staking/APY", "Target %"],
    ["BTC", "Binance", 0.1530, 76973.25, 11821.17, "+0.06%", "59.5%", "❌ No", "35%"],
    ["ETH", "Binance", 2.4569, 2120.74, 5234.82, "+0.28%", "26.3%", "✅ Yes", "25%"],
    ["BNB", "Binance", 1.7298, 659.94, 1147.98, "+1.77%", "5.8%", "❌ No", "5%"],
    ["SOL", "Binance", 6.2987, 86.73, 550.51, "+1.06%", "2.8%", "✅ Yes", "15%"],
    ["DOGE", "Binance", 4185.74, 0.11, 445.61, "+1.48%", "2.2%", "❌ No", "2%"],
    ["XRP", "Binance", "", 1.35, "", "-0.01%", "", "❌ No", "5%"],
    ["ADA", "Binance", "", 0.25, "", "+1.42%", "", "❌ No", "5%"],
    ["SUI", "Binance", "", 1.11, "", "+1.19%", "", "❌ No", "3%"],
    ["", "", "", "", "", "", "", "", ""],
    ["💰 TOTAL", "", "", "", 19866.10, "", "100%", "", "100%"],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "₿ Crypto Tracker!A1:I10",
    "values": crypto,
    "value_input_option": "RAW"
})
print("Crypto Tracker:", r.get("successful", r.get("error", "unknown")))

# Unusual Volume Scanner Setup
volume = [
    ["📈 UNUSUAL VOLUME SCANNER SETUP", "", "", "", "", "", "", ""],
    [""],
    ["Source", "URL", "Frequency", "Notes"],
    ["MarketChameleon", "https://marketchameleon.com/Reports/UnusualOptionVolumeReport", "Daily 9AM", "Options volume vs OI"],
    ["Barchart", "https://www.barchart.com/options/unusual-activity", "Daily 9AM", "Options unusual activity"],
    ["StockTitan", "https://www.stocktitan.net/scanner/momentum", "Real-time", "Live momentum scanner"],
    ["Yahoo Finance", "https://finance.yahoo.com/markets/stocks/unusual-volume-stocks/", "Daily", "Unusual volume stocks"],
    [""],
    ["ALERT CONFIGURATION", "", "", ""],
    ["Criteria", "Threshold", "Channel", ""],
    ["Options Volume/OI", "> 200%", "Telegram", ""],
    ["Stock Volume Spike", "> 3x avg", "Telegram", ""],
    ["Float Rotation", "> 50%", "Telegram", ""],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "📈 Unusual Volume!A1:D12",
    "values": volume,
    "value_input_option": "RAW"
})
print("Unusual Volume:", r.get("successful", r.get("error", "unknown")))

# Asset Allocation Target
target = [
    ["CURRENT vs TARGET ALLOCATION", "", "", "", "", ""],
    [""],
    ["Asset Class", "Current $", "Current %", "Target %", "Gap", "Action"],
    ["Social Trading (eToro)", 84258.94, "43.0%", "5%", "-38.0%", "🔴 REDUCE"],
    ["Mexican Equities (GBM Main)", 74071.21, "37.8%", "15%", "-22.8%", "🔴 REDUCE"],
    ["Crypto (Binance)", 19866.10, "10.1%", "20%", "+9.9%", "🟢 INCREASE"],
    ["US Equities (GBM USA + Schwab + IBKR)", 17471.29, "8.9%", "35%", "+26.1%", "🟢 INCREASE"],
    ["Savings (Revolut)", 404.39, "0.2%", "5%", "+4.8%", "🟢 INCREASE"],
    ["Cash/Opportunities", 0, "0%", "10%", "+10.0%", "🟢 BUILD"],
    ["Energy for AI", 0, "0%", "15%", "+15.0%", "🟢 NEW POSITION"],
    ["Space Exploration", 0, "0%", "10%", "+10.0%", "🟢 NEW POSITION"],
]

r = composio_exec("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": SPREADSHEET_ID,
    "range": "📊 Asset Allocation!A1:F10",
    "values": target,
    "value_input_option": "RAW"
})
print("Asset Allocation:", r.get("successful", r.get("error", "unknown")))

print("\n✅ ALL TABS POPULATED!")
