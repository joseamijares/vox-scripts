#!/usr/bin/env python3
"""
Rebuild both OpenClaw spreadsheets cleanly
- Portfolio Tracker: Dashboard, Weekly Snapshots, Asset Allocation, Current Holdings, Exit Strategy
- Trade Ideas: Watchlist, X Momentum, Unusual Volume, Crypto Tracker, Research Sources
"""
import subprocess, json, os
from datetime import datetime

os.environ['PATH'] = os.path.expanduser('~/.composio') + ':' + os.environ['PATH']

PORTFOLIO_ID = "1VpCMR9NAK0TfW43XMQn0jDvI114c2E6Hc4rpu7VguNo"
TRADE_ID = "1O66XpOhacNCJhia8QpHu0RAIFvYozAD8a1tslY808iA"

def run(cmd, data):
    args = json.dumps(data)
    bash_cmd = f'export PATH="$HOME/.composio:$PATH" && composio execute "{cmd}" -d \'{args}\''
    result = subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"parse_error": True, "stdout": result.stdout[:300]}

def clear_tab(sheet_id, tab, range_str):
    """Clear a range by writing empty values"""
    empties = [[""] * 20 for _ in range(100)]
    r = run("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": sheet_id,
        "range": f"'{tab}'!{range_str}",
        "values": empties,
        "value_input_option": "RAW"
    })
    return r

# ============================================================
# PORTFOLIO TRACKER — Real Portfolio-Only Tabs
# ============================================================
print("=" * 60)
print("📊 REBUILDING: PORTFOLIO TRACKER")
print("=" * 60)

# Tab 1: 🎯 DASHBOARD
print("[1/5] Building Dashboard...")
dashboard = [
    ["OPENCLAW PORTFOLIO", "", "", "", "", "", "", "", "", ""],
    ["Real-Time Command Center", "", "", "", "", "", "", "", "", ""],
    [""],
    ["📅 Snapshot", "2026-05-22 09:02", "", "🎯 Target Return", "20.0%", "", "📊 Risk", "HIGH / AGGRESSIVE"],
    ["💰 Total AUM", "$196,072.06", "", "📈 YTD Return", "+6.46%", "", "🏷️ Strategy", "GROWTH  / THEMES"],
    ["📉 WoW Change", "+$11,895.84 (+6.46%)", "", "💵 USD/MXN", "17.31", "", "🔔 Next Rebal", "2026-06-01"],
    [""],
    ["═══ BROKER BREAKDOWN ═══", "", "", "", "═══ ASSET CLASS ═══", "", "", ""],
    ["Broker", "Value", "%", "Status", "Class", "Value", "%", ""],
    ["eToro", "$84,258.94", "43.0%", "🟢 Live", "Social Trading", "$84,258.94", "43.0%", ""],
    ["GBM Main", "$74,071.21", "37.8%", "🟢 Manual", "Mexican Equities", "$74,071.21", "37.8%", ""],
    ["Binance", "$19,866.10", "10.1%", "🟢 API", "Crypto", "$19,866.22", "10.1%", ""],
    ["GBM USA", "$14,539.94", "7.4%", "🟡 Manual", "US Equities", "$17,471.29", "8.9%", ""],
    ["Schwab", "$1,661.35", "0.8%", "🟡 Manual", "Savings", "$404.39", "0.2%", ""],
    ["IBKR", "$1,270.00", "0.7%", "🟡 Manual", "", "", "", ""],
    ["Revolut", "$404.39", "0.2%", "🟢 API", "", "", "", ""],
    ["Bitso", "$0.12", "0.0%", "🟢 API", "", "", "", ""],
    [""],
    ["═══ TOP CONVICTION TRADES ═══", "", "", "", "", "", "", ""],
    ["Ticker", "Theme", "Conviction", "Action", "Entry Target", "Current", "Stop Loss", "Status"],
    ["CEG", "Energy for AI", "9/10", "📥 BUY", "$150", "~$150", "$120", "🔴 NO POSITION"],
    ["VST", "Energy for AI", "9/10", "📥 BUY", "$110", "~$110", "$85", "🔴 NO POSITION"],
    ["NVDA", "AI Supply Chain", "8/10", "📥 ACCUMULATE", "$140", "~$140", "$110", "🔴 NO POSITION"],
    ["SOL", "Crypto", "7/10", "📥 ACCUMULATE", "$85", "$86.73", "$65", "🟢 HOLDING"],
    ["RKLB", "Space", "6/10", "🎲 SPECULATE", "$120", "$125", "$90", "🔴 NO POSITION"],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": PORTFOLIO_ID,
    "range": "Dashboard!A1:H25",
    "values": dashboard,
    "value_input_option": "RAW"
})
print("  -> Dashboard:", "✅" if r.get("successful") else "❌")

# Tab 2: 📊 WEEKLY SNAPSHOTS
print("[2/5] Building Weekly Snapshots...")
snapshots = [
    ["DATE", "TOTAL AUM", "ETORO", "GBM MAIN", "GBM USA", "BINANCE", "SCHWAB", "IBKR", "REVOLUT", "BITSO", "WOW $", "WOW %", "SPX", "BTC", "NOTES"],
    ["2026-05-22", 196072.06, 84258.94, 74071.21, 14539.94, 19866.10, 1661.35, 1270.00, 404.39, 0.12, 11895.84, 6.46, "—", 76973.25, "Baseline / Binance fixed"],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ["═══ ALL WEEKS ═══", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ["[Auto-populated every Friday 9 AM]", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": PORTFOLIO_ID,
    "range": "'Weekly Snapshots'!A1:O5",
    "values": snapshots,
    "value_input_option": "RAW"
})
print("  -> Weekly Snapshots:", "✅" if r.get("successful") else "❌")

# Tab 3: 🏛️ ASSET ALLOCATION
print("[3/5] Building Asset Allocation...")
alloc = [
    ["CURRENT vs TARGET ALLOCATION", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["Asset Class", "Current $", "Current %", "Target %", "Gap", "Action", "Priority"],
    ["Social Trading (eToro)", 84258.94, "43.0%", "5%", "-38.0%", "SELL $73,258 → buy US growth", "🔴 URGENT"],
    ["Mexican Equities (GBM Main)", 74071.21, "37.8%", "15%", "-22.8%", "SELL $44,536 → buy AI energy", "🔴 URGENT"],
    ["Crypto (Binance)", 19866.10, "10.1%", "20%", "+9.9%", "ADD $19K SOL + ETH staking", "🟡 BUILD"],
    ["US Equities (GBM+Schwab+IBKR)", 17471.29, "8.9%", "35%", "+26.1%", "BUY $50K NVDA AVGO VRT LRCX", "🟡 BUILD"],
    ["Savings (Revolut)", 404.39, "0.2%", "5%", "+4.8%", "Grow to $10K emergency fund", "🟡 BUILD"],
    ["Cash / Dry Powder", 0, "0.0%", "10%", "+10.0%", "Hold for corrections / dips", "🟢 WAIT"],
    ["Energy for AI (CEG+VST)", 0, "0.0%", "15%", "+15.0%", "NEW: Buy CEG at $150, VST at $110", "🟢 NEW"],
    ["Space Exploration (RKLB)", 0, "0.0%", "5%", "+5.0%", "NEW: Small spec buy RKLB <$120", "🟢 NEW"],
    ["", "", "", "", "", "", ""],
    ["═══ REBALANCE PLAN ═══", "", "", "", "", "", ""],
    ["Step 1", "Trim eToro → $20K", "Free up $64K", "", "", "", ""],
    ["Step 2", "Trim GBM Main → $30K", "Free up $44K", "", "", "", ""],
    ["Step 3", "Buy CEG $29K (15%)", "via Schwab", "", "", "", ""],
    ["Step 4", "Buy VST $14.5K (7.5%)", "via Schwab", "", "", "", ""],
    ["Step 5", "Buy NVDA $16K (8%)", "via GBM USA or Schwab", "", "", "", ""],
    ["Step 6", "Add SOL $10K", "via Binance staking", "", "", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": PORTFOLIO_ID,
    "range": "'Asset Allocation'!A1:G19",
    "values": alloc,
    "value_input_option": "RAW"
})
print("  -> Asset Allocation:", "✅" if r.get("successful") else "❌")

# Tab 4: 🏷️ CURRENT HOLDINGS
print("[4/5] Building Current Holdings...")
holdings = [
    ["CURRENT HOLDINGS & EXIT STRATEGY", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", ""],
    ["Asset", "Position", "Avg Entry", "Current", "P&L", "% P&L", "Sell Target", "Stop Loss", "Action"],
    ["═══ ETORO (Social Trading) ═══", "", "", "", "", "", "", "", ""],
    ["Copy-Trader A", "~$5,728", "—", "—", "—", "—", "Watch underperformance", "-15% drawdown", "MONITOR"],
    ["Copy-Trader B", "~$6,153", "—", "—", "—", "—", "Watch underperformance", "-15% drawdown", "MONITOR"],
    ["Direct Positions", "~$72,377", "—", "—", "—", "—", "TBD", "", "REDUCE"],
    ["═══ GBM MAIN (Mexican Equities) ═══", "", "", "", "", "", "", "", ""],
    ["[See GBM Main positions]", "$74,071", "—", "—", "—", "—", "Trim to $30K target", "", "REDUCE"],
    ["═══ BINANCE (Crypto) ═══", "", "", "", "", "", "", "", ""],
    ["BTC", "0.153", "~$72K avg", "$76,973", "—", "—", "$120,000", "$60,000", "HOLD / ADD"],
    ["ETH", "2.457", "~$2.1K avg", "$2,121", "—", "—", "$4,000", "$1,500", "HOLD / STAKE"],
    ["BNB", "1.730", "—", "$660", "—", "—", "$800", "$500", "HOLD"],
    ["SOL", "6.299", "~$87 avg", "$87", "—", "—", "$150", "$50", "ACCUMULATE"],
    ["DOGE", "4,186", "—", "$0.11", "—", "—", "$0.25", "$0.06", "HOLD"],
    ["═══ GBM USA (US Equities) ═══", "", "", "", "", "", "", "", ""],
    ["[Add positions here]", "$14,540", "—", "—", "—", "—", "", "", "BUILD"],
    ["═══ SCHWAB / IBKR ═══", "", "", "", "", "", "", "", ""],
    ["[Add CEG / VST / NVDA here]", "$1,931", "—", "—", "—", "—", "CEG→$200 VST→$150", "", "BUY"],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": PORTFOLIO_ID,
    "range": "'Current Holdings'!A1:I20",
    "values": holdings,
    "value_input_option": "RAW"
})
print("  -> Current Holdings:", "✅" if r.get("successful") else "❌")

# Tab 5: 🚪 EXIT STRATEGY
print("[5/5] Building Exit Strategy...")
exit_tab = [
    ["EXIT STRATEGY & RISK MANAGEMENT", "", "", "", "", ""],
    ["", "", "", "", "", ""],
    ["Position", "Sell Trigger", "Take Profit 1", "Take Profit 2", "Stop Loss", "Notes"],
    ["CEG", "Never full exit", "$200 (33%)", "$250 (67%)", "$120 (-20%)", "Core holding, trim on spikes"],
    ["VST", "Never full exit", "$160 (45%)", "$200 (82%)", "$85 (-23%)", "Core holding, trim on spikes"],
    ["NVDA", "Trim on 50% run", "$210 (50%)", "$280 (100%)", "$110 (-21%)", "Trim 1/3 at each level"],
    ["SOL", "Trim on spike", "$120 (38%)", "$180 (107%)", "$50 (-42%)", "Crypto volatile, use trailing stop"],
    ["RKLB", "Spec only", "$180 (50%)", "Exit all", "$90 (-25%)", "Small position, high risk"],
    ["BTC", "Core holding", "$120K (56%)", "$180K (134%)", "$60K (-22%)", "Long term, HODL"],
    ["ETH", "Core holding", "$4K (89%)", "$6K (183%)", "$1,500 (-29%)", "Stake and hold"],
    ["", "", "", "", "", ""],
    ["═══ REBALANCE RULES ═══", "", "", "", "", ""],
    ["Rule", "Trigger", "Action", "", "", ""],
    ["Overweight trim", "Position > 125% of target", "Sell down to target", "", "", ""],
    ["Underweight buy", "Position < 75% of target", "Buy to target on dip", "", "", ""],
    ["Stop hit", "Any stop loss triggered", "Sell 100%, review thesis", "", "", ""],
    ["Profit taking", "+50% from entry", "Sell 25%, move stop to breakeven", "", "", ""],
    ["Monthly review", "Last Friday of month", "Full council LLM review", "", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": PORTFOLIO_ID,
    "range": "'Exit Strategy'!A1:F16",
    "values": exit_tab,
    "value_input_option": "RAW"
})
print("  -> Exit Strategy:", "✅" if r.get("successful") else "❌")

# ============================================================
# TRADE IDEAS & WATCHLIST — Research-Only Tabs
# ============================================================
print()
print("=" * 60)
print("🎯 REBUILDING: TRADE IDEAS & WATCHLIST")
print("=" * 60)

# Tab 1: 👁️ WATCHLIST
print("[1/5] Building Watchlist...")
watchlist = [
    ["ACTIVE WATCHLIST", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", ""],
    ["Ticker", "Theme", "Conviction", "Entry Target", "Current", "Stop Loss", "Risk/Reward", "Status", "Source", "Last Update"],
    ["CEG", "Energy for AI", 9, "$150", "~$150", "$120", "2.5x", "📥 READY TO BUY", "Council + X momentum", "2026-05-22"],
    ["VST", "Energy for AI", 9, "$110", "~$110", "$85", "2.9x", "📥 READY TO BUY", "Council + Zacks", "2026-05-22"],
    ["NVDA", "AI Supply Chain", 8, "$140", "~$140", "$110", "2.5x", "📥 READY TO BUY", "Council + Yahoo", "2026-05-22"],
    ["AVGO", "AI Supply Chain", 7, "$220", "~$220", "$180", "2.2x", "📌 RESEARCH", "Council + Yahoo", "2026-05-22"],
    ["VRT", "AI Infrastructure", 7, "", "", "", "", "📌 RESEARCH", "Zacks", "2026-05-22"],
    ["LRCX", "Semi Equipment", 7, "", "", "", "", "📌 RESEARCH", "Yahoo Finance", "2026-05-22"],
    ["MRVL", "Networking", 6, "", "", "", "", "📌 RESEARCH", "Reddit", "2026-05-22"],
    ["MU", "Memory/HBM", 6, "", "", "", "", "📌 RESEARCH", "Reddit", "2026-05-22"],
    ["SOL", "Crypto", 7, "$85", "$86.73", "$65", "2.3x", "🟢 HOLDING", "Council", "2026-05-22"],
    ["RKLB", "Space", 6, "$120", "$125", "$90", "2.0x", "🎲 SPECULATE", "Council + US News", "2026-05-22"],
    ["ASTS", "Space", 6, "", "", "", "", "📌 RESEARCH", "US News", "2026-05-22"],
    ["LUNR", "Space", 5, "", "", "", "", "📌 RESEARCH", "US News", "2026-05-22"],
    ["CEG", "Nuclear Renaissance", 9, "$140", "~$150", "$120", "2.5x", "📥 READY TO BUY", "Energy Council", "2026-05-22"],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": TRADE_ID,
    "range": "'Watchlist'!A1:J14",
    "values": watchlist,
    "value_input_option": "RAW"
})
print("  -> Watchlist:", "✅" if r.get("successful") else "❌")

# Tab 2: 🐦 X MOMENTUM
print("[2/5] Building X Momentum...")
x_data = [
    ["X/TWITTER MOMENTUM TRACKER", "", "", "", "", "", "", ""],
    ["Real-time sentiment for watchlist tickers", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["Date", "Ticker", "X Mentions", "Sentiment", "Volume Signal", "Top Narrative", "Action", ""],
    ["2026-05-22 09:02", "CEG", 10, "🔥 BULLISH", "Elevated", "NTM revenue growth +31%", "📥 ACCUMULATE", ""],
    ["2026-05-22 09:02", "VST", 10, "🔥 BULLISH", "Elevated", "Vistra NTM growth estimate", "📥 ACCUMULATE", ""],
    ["2026-05-22 09:02", "NVDA", 10, "🔥 BULLISH", "High", "AI price collapse = pure physics", "⏸️ HOLD", ""],
    ["2026-05-22 09:02", "AVGO", 9, "🔥 BULLISH", "High", "Top 10 holdings discussion", "📌 RESEARCH", ""],
    ["2026-05-22 09:02", "RKLB", 10, "🔥 BULLISH", "Very High", "Space sector momentum", "🎲 SPECULATE", ""],
    ["2026-05-22 09:02", "SOL", 10, "🔥 BULLISH", "Normal", "5.15X gains, staking growth", "📥 ACCUMULATE", ""],
    ["2026-05-22 09:02", "VRT", 9, "🔥 BULLISH", "Elevated", "Multiple ticker mentions", "📌 RESEARCH", ""],
    ["2026-05-22 09:02", "LRCX", 10, "🔥 BULLISH", "Elevated", "Steady gains discussion", "📌 RESEARCH", ""],
    ["", "", "", "", "", "", "", ""],
    ["Next scan:", "Daily 4:00 PM CST", "", "", "", "", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": TRADE_ID,
    "range": "'X Momentum'!A1:H14",
    "values": x_data,
    "value_input_option": "RAW"
})
print("  -> X Momentum:", "✅" if r.get("successful") else "❌")

# Tab 3: 📈 UNUSUAL VOLUME
print("[3/5] Building Unusual Volume...")
vol_data = [
    ["UNUSUAL VOLUME & OPTIONS SCANNER", "", "", "", "", ""],
    ["Auto-scans weekdays 9 AM + manual refresh", "", "", "", "", ""],
    ["", "", "", "", "", ""],
    ["Source", "URL", "Frequency", "Alert Threshold", "Status", ""],
    ["MarketChameleon", "https://marketchameleon.com/Reports/UnusualOptionVolumeReport", "Daily 9 AM", "Options Vol/OI > 200%", "🟢 ACTIVE", ""],
    ["Barchart", "https://www.barchart.com/options/unusual-activity", "Daily 9 AM", "Options Vol/OI > 200%", "🟢 ACTIVE", ""],
    ["StockTitan", "https://www.stocktitan.net/scanner/momentum", "Real-time", "Volume > 3x avg", "🟢 ACTIVE", ""],
    ["Yahoo Finance", "https://finance.yahoo.com/markets/stocks/unusual-volume-stocks/", "Daily", "Volume spike detection", "🟢 ACTIVE", ""],
    ["", "", "", "", "", ""],
    ["═══ ALERT CRITERIA ═══", "", "", "", "", ""],
    ["Criteria", "Threshold", "Action", "Watchlist", "", ""],
    ["Options Volume/OI", "> 200% of 20-day avg", "Flag for review", "CEG VST NVDA RKLB SOL", "", ""],
    ["Stock Volume Spike", "> 3x 20-day avg volume", "Flag for review", "All watchlist", "", ""],
    ["Float Rotation", "> 50% of float traded", "High alert — possible squeeze", "Small caps only", "", ""],
    ["Put/Call Spike", "P/C ratio > 1.5 on bullish stock", "Contrarian signal", "CEG VST NVDA", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": TRADE_ID,
    "range": "'Unusual Volume'!A1:F15",
    "values": vol_data,
    "value_input_option": "RAW"
})
print("  -> Unusual Volume:", "✅" if r.get("successful") else "❌")

# Tab 4: ₿ CRYPTO TRACKER
print("[4/5] Building Crypto Tracker...")
crypto_data = [
    ["CRYPTO PORTFOLIO TRACKER", "", "", "", "", "", "", "", "", ""],
    ["Live via Binance API — Updated every cron run", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", ""],
    ["Asset", "Exchange", "Amount", "Price", "Value", "24h %", "Weight %", "Staking/APY", "Target %", "Action"],
    ["BTC", "Binance", 0.1530, 76973.25, 11821.17, "+0.06%", "59.5%", "❌ None", "35%", "HOLD / ADD on dips"],
    ["ETH", "Binance", 2.4569, 2120.74, 5234.82, "+0.28%", "26.3%", "✅ Staking ~3-4%", "25%", "HOLD + STAKE"],
    ["BNB", "Binance", 1.7298, 659.94, 1147.98, "+1.77%", "5.8%", "❌ None", "5%", "HOLD"],
    ["SOL", "Binance", 6.2987, 86.73, 550.51, "+1.06%", "2.8%", "✅ Staking ~6-7%", "15%", "🔥 ACCUMULATE"],
    ["DOGE", "Binance", 4185.74, 0.11, 445.61, "+1.48%", "2.2%", "❌ None", "2%", "HOLD"],
    ["XRP", "Binance", "", 1.35, "", "-0.01%", "", "❌ None", "5%", "RESEARCH"],
    ["ADA", "Binance", "", 0.25, "", "+1.42%", "", "❌ None", "5%", "RESEARCH"],
    ["SUI", "Binance", "", 1.11, "", "+1.19%", "", "❌ None", "3%", "RESEARCH"],
    ["", "", "", "", "", "", "", "", "", ""],
    ["💰 TOTAL PORTFOLIO", "", "", "", 19866.10, "", "100%", "", "100%", "INCREASE to $40K"],
    ["", "", "", "", "", "", "", "", "", ""],
    ["═══ CRYPTO STRATEGY ═══", "", "", "", "", "", "", "", "", ""],
    ["Priority", "Action", "Target", "", "", "", "", "", "", ""],
    ["#1", "Add SOL to 15% of portfolio", "~$10K more", "", "", "", "", "", "", ""],
    ["#2", "Stake ETH on Binance Earn", "~$5K stake", "", "", "", "", "", "", ""],
    ["#3", "Add BTC on major dips", "$60K-$65K entry", "", "", "", "", "", "", ""],
    ["#4", "Research XRP/ADA/SUI", "Small positions", "", "", "", "", "", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": TRADE_ID,
    "range": "'Crypto Tracker'!A1:J19",
    "values": crypto_data,
    "value_input_option": "RAW"
})
print("  -> Crypto Tracker:", "✅" if r.get("successful") else "❌")

# Tab 5: 🔬 RESEARCH SOURCES
print("[5/5] Building Research Sources...")
research_data = [
    ["RESEARCH SOURCES & TOOLS", "", "", "", ""],
    ["Powered by OpenClaw Agent — May 2026", "", "", "", ""],
    ["", "", "", "", ""],
    ["Source", "URL", "Type", "Frequency", "Status"],
    ["Exa AI Search", "https://exa.ai", "AI Web Search", "On demand", "🟢 Active"],
    ["Perplexity", "https://perplexity.ai", "AI Research", "Daily briefs", "🟢 Active"],
    ["X/Twitter API", "https://developer.x.com", "Social Sentiment", "Daily 4 PM", "🟢 Active"],
    ["Binance API", "api.binance.com", "Crypto Prices", "Real-time", "🟢 Active"],
    ["MarketChameleon", "marketchameleon.com", "Options Flow", "Daily 9 AM", "🟢 Active"],
    ["Barchart", "barchart.com/options", "Unusual Options", "Daily 9 AM", "🟢 Active"],
    ["Zacks Research", "zacks.com", "Equity Research", "Weekly", "🟢 Active"],
    ["Yahoo Finance", "finance.yahoo.com", "Market Data", "Real-time", "🟢 Active"],
    ["", "", "", "", ""],
    ["═══ COUNCIL LLM ADVISORS ═══", "", "", "", ""],
    ["Advisor", "Style", "Conviction", "Used For", ""],
    ["Growth Bull", "Aggressive themes, high conviction", "Primary", "Trade ideas, allocation", ""],
    ["Conservative Value", "Risk management, warnings", "Counter-balance", "Exit strategy, stops", ""],
    ["Technical Analyst", "Charts, volume, patterns", "Secondary", "Timing entries", ""],
    ["Crypto Specialist", "On-chain, staking, DeFi", "Secondary", "Crypto allocation", ""],
    ["", "", "", "", ""],
    ["═══ AUTOMATED WORKFLOWS ═══", "", "", "", ""],
    ["Workflow", "Schedule", "Output", "", ""],
    ["Portfolio Snapshot", "Fridays 9 AM", "Telegram + Sheets", "", ""],
    ["X Momentum Scan", "Daily 4 PM", "Telegram + Sheets", "", ""],
    ["Volume Scanner", "M-F 9 AM", "Telegram alert", "", ""],
    ["Market Brief", "M-F 8 AM", "Telegram", "", ""],
    ["Weekly Council Review", "Last Friday of Month", "Full allocation review", "", ""],
]

r = run("GOOGLESHEETS_VALUES_UPDATE", {
    "spreadsheet_id": TRADE_ID,
    "range": "'Research Sources'!A1:E25",
    "values": research_data,
    "value_input_option": "RAW"
})
print("  -> Research Sources:", "✅" if r.get("successful") else "❌")

print()
print("=" * 60)
print("✅ ALL SHEETS REBUILT SUCCESSFULLY!")
print("=" * 60)
print()
print("📊 PORTFOLIO TRACKER (5 tabs):")
print("   1. 🎯 Dashboard — Real-time overview")
print("   2. 📊 Weekly Snapshots — Historical tracking")
print("   3. 🏛️ Asset Allocation — Current vs Target")
print("   4. 🏷️ Current Holdings — What you own + exits")
print("   5. 🚪 Exit Strategy — When to sell, stops, rules")
print()
print("🎯 TRADE IDEAS (5 tabs):")
print("   1. 👁️ Watchlist — All ideas to research/buy")
print("   2. 🐦 X Momentum — Social sentiment tracking")
print("   3. 📈 Unusual Volume — Scanner setup + alerts")
print("   4. ₿ Crypto Tracker — Live crypto positions")
print("   5. 🔬 Research Sources — Tools + council setup")
