#!/usr/bin/env python3
"""
Vox Spreadsheet Builder — Creates Master Dashboard + Weekly Archive
with REAL tabs using raw Google Sheets API.

Usage:
    python3 vox_create_tabs.py --dashboard    # Create Master Dashboard
    python3 vox_create_tabs.py --archive      # Create Weekly Archive
    python3 vox_create_tabs.py --both         # Create both
"""
import os, sys, json, argparse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── CONFIG ──────────────────────────────────────────────────
FOLDER_ID = "1WGA75hx1BquHxnQHgKn_6I4I4MV_8bw6"

DASHBOARD_TABS = [
    "📊 Portfolio Snapshot",
    "🎯 Active Plays",
    "📈 Fresh Grades",
    "🧠 LLM Council",
    "🇺🇸 Trump Tracker",
    "⚖️ Position Sizer",
    "⏰ Monday Schedule",
]

ARCHIVE_TABS = [
    "📅 Weekly Snapshots",
    "🏦 Broker Breakdown",
    "📊 Asset Allocation",
    "💰 P&L History",
    "📈 Compound Growth",
    "📓 Trade Journal",
]

# ── AUTH ────────────────────────────────────────────────────
def get_service():
    """Build Sheets API service from Composio OAuth token."""
    # Try to find Composio's stored token
    token_paths = [
        os.path.expanduser("~/.composio/auth/google-sheets/token.json"),
        os.path.expanduser("~/.composio/auth/google-drive/token.json"),
        os.path.expanduser("~/.composio/auth/google/token.json"),
    ]

    creds = None
    for path in token_paths:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            # Composio stores tokens differently — try to extract
            if isinstance(data, dict):
                if "access_token" in data:
                    creds = Credentials(token=data["access_token"])
                elif "token" in data:
                    creds = Credentials(token=data["token"])
            break

    if not creds:
        # Fallback: try to use gcloud or service account
        print("❌ No OAuth token found. Run Composio auth first.")
        sys.exit(1)

    return build("sheets", "v4", credentials=creds)

# ── CREATE SPREADSHEET ──────────────────────────────────────
def create_spreadsheet(service, title, tabs, folder_id=None):
    """Create spreadsheet with multiple tabs."""
    print(f"\n📝 Creating: {title}")

    # Build sheet properties for each tab
    sheets = []
    for i, tab_name in enumerate(tabs):
        sheets.append({
            "properties": {
                "title": tab_name,
                "index": i,
                "gridProperties": {
                    "rowCount": 1000,
                    "columnCount": 26
                }
            }
        })

    body = {
        "properties": {
            "title": title,
            "locale": "en_US",
            "timeZone": "America/Mexico_City"
        },
        "sheets": sheets
    }

    spreadsheet = service.spreadsheets().create(body=body).execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

    print(f"  ✅ Created: {url}")

    # Move to folder if specified
    if folder_id:
        drive_service = build("drive", "v3", credentials=service._http.credentials)
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=folder_id,
            removeParents="root",
            fields="id, parents"
        ).execute()
        print(f"  ✅ Moved to folder")

    return spreadsheet_id, url

# ── POPULATE DATA ───────────────────────────────────────────
def populate_tab(service, spreadsheet_id, tab_name, data_rows):
    """Write data to a specific tab."""
    range_name = f"'{tab_name}'!A1"
    body = {
        "values": data_rows
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body=body
    ).execute()
    print(f"  ✅ Populated: {tab_name}")

# ── DASHBOARD DATA ──────────────────────────────────────────
def get_dashboard_data():
    """Return dict of tab_name -> rows for Master Dashboard."""
    return {
        "📊 Portfolio Snapshot": [
            ["🎯 VOX MASTER DASHBOARD"],
            ["Last Updated: 2026-05-23 | Portfolio: $196,072 | USD/MXN: 17.31"],
            [""],
            ["━" * 30],
            ["📊 PORTFOLIO SNAPSHOT"],
            ["━" * 30],
            [""],
            ["Broker", "Value USD", "% Total", "WoW Change", "Status"],
            ["eToro", "$84,259", "43.0%", "—", "🟢 Live API"],
            ["GBM Main", "$74,071", "37.8%", "—", "🟢 Excel Export"],
            ["Binance", "$19,866", "10.1%", "—", "🟢 Live API"],
            ["GBM USA", "$14,540", "7.4%", "—", "🟢 Excel Export"],
            ["Schwab", "$1,661", "0.8%", "—", "🟡 Manual"],
            ["IBKR", "$1,270", "0.6%", "—", "🟡 Manual"],
            ["Revolut", "$404", "0.2%", "—", "🟡 Manual"],
            ["Bitso", "$0", "0.0%", "—", "🟢 Live API"],
            [""],
            ["TOTAL AUM", "$196,072", "100%", "", ""],
            [""],
            ["━" * 30],
            ["🚨 HEALTH SCORE: 38/100 (UNHEALTHY / SPECULATIVE)"],
            ["━" * 30],
            [""],
            ["Metric", "Score", "Status"],
            ["Diversification", "30/100", "🔴 CRITICAL — 70%+ Tech"],
            ["Concentration", "25/100", "🔴 CRITICAL — Top 5 = 25%"],
            ["Currency Risk", "60/100", "🟡 FAIR — 100% USD"],
            ["Broker Risk", "20/100", "🔴 CRITICAL — 90% in 2 brokers"],
            ["Sector Allocation", "20/100", "🔴 CRITICAL — Zero defensive"],
            [""],
            ["━" * 30],
            ["💰 CASH FLOW THIS WEEK"],
            ["━" * 30],
            [""],
            ["Category", "Amount"],
            ["Sells (BYND + OSCR)", "$176"],
            ["Trims (TSLA + CRWD + AMD)", "$8,900"],
            ["Potential Exits (SHOP)", "$5,200"],
            ["Total Cash Freed", "$10,576 — $15,776"],
            [""],
            ["━" * 30],
            ["📈 TARGET ALLOCATION (90-Day Plan)"],
            ["━" * 30],
            [""],
            ["Category", "Current", "Target", "Delta", "Action"],
            ["US Broad ETFs (VOO/VTI)", "5%", "25%", "+20%", "BUY"],
            ["International (VXUS)", "0%", "10%", "+10%", "BUY"],
            ["Individual Tech/Growth", "50%+", "25%", "-25%", "TRIM"],
            ["MXN Fixed Income", "0%", "10%", "+10%", "BUY"],
            ["USD Cash/Short Bonds", "0.2%", "8%", "+8%", "BUILD"],
            ["Speculative/Single Names", "10%", "7%", "-3%", "TRIM"],
            ["eToro Residual", "48%", "15%", "-33%", "LIQUIDATE"],
        ],

        "🎯 Active Plays": [
            ["🎯 ACTIVE PLAYS"],
            ["Monday May 26, 2026 | Status: PENDING EXECUTION"],
            [""],
            ["━" * 20],
            ["🔴 PLAY #1 — SELL JUNK"],
            ["━" * 20],
            ["Ticker", "Action", "Shares", "Value", "Broker", "Price", "Rationale", "Grade", "Status"],
            ["BYND", "SELL ALL", "—", "$26", "eToro", "$0.77", "Memorial position, harvest loss", "—", "⬜"],
            ["OSCR", "SELL ALL", "117.5", "$150", "GBM USA", "$22.64", "Too small, adds complexity", "—", "⬜"],
            [""],
            ["━" * 20],
            ["🟡 PLAY #2 — TRIM OVEREXTENDED"],
            ["━" * 20],
            ["Ticker", "Action", "Value", "Broker", "Price", "Rationale", "Grade", "RSI", "Status"],
            ["TSLA", "TRIM", "$3,500", "GBM Main", "$426.01", "Reduce ~$9,200→~$5,700. MACD down", "64", "RSI 58.4", "⬜"],
            ["CRWD", "TRIM", "$3,400", "GBM Main", "$663.46", "RSI 87.4 OVERBOUGHT. 6% = gambling", "65", "RSI 87.4", "⬜"],
            ["AMD", "TRIM", "$2,000", "eToro/GBM USA", "$467.51", "Weakest triad link. RSI 72.6", "59", "RSI 72.6", "⬜"],
            [""],
            ["━" * 20],
            ["🟠 PLAY #3 — BROKEN THESIS"],
            ["━" * 20],
            ["Ticker", "Action", "Value", "Broker", "Price", "Rationale", "Grade", "Status"],
            ["SHOP", "CONSIDER EXIT", "$5,200", "GBM Main", "$103.00", "Grade 49 AVOID. Below EMAs, MACD bearish", "49", "⬜"],
            ["META", "TRIM OR HOLD", "—", "GBM USA/eToro", "$610.26", "Grade 53 AVOID. Below EMAs. User call", "53", "⬜"],
            [""],
            ["━" * 20],
            ["🟢 PLAY #4 — HOLD CONVICTION"],
            ["━" * 20],
            ["Ticker", "Action", "Value", "Broker", "Price", "Rationale", "Grade"],
            ["GOOGL", "HOLD", "$7,700", "GBM Main", "$382.97", "Best risk/reward in Mag7", "63"],
            ["TSM", "HOLD", "$8,600", "GBM Main", "—", "Core AI infra", "—"],
            ["NVDA", "HOLD", "$15,600", "GBM Main", "$215.33", "Thesis intact. Hold through earnings", "64"],
            ["AAPL", "HOLD", "—", "eToro", "$308.82", "Overbought but strong. Don't add", "65"],
            ["MSFT", "HOLD", "—", "eToro", "$418.57", "Steady", "63"],
            ["IREN", "HOLD", "$637", "Schwab/IBKR", "$56.83", "Lottery ticket. Do NOT add", "—"],
            [""],
            ["━" * 20],
            ["⛔ PLAY #5 — NO NEW BUYS"],
            ["━" * 20],
            ["Reason:", "All grades 49-66 (NEUTRAL/AVOID). Council NEUTRAL everywhere. No BULLISH consensus."],
            ["Action:", "Build cash. Wait for grade >70 + Council BULLISH."],
            ["Cash Target:", "$10,576 (trims) + $5,376 (SHOP exit) = ~$16,000 dry powder"],
            [""],
            ["━" * 20],
            ["👁️ PLAY #6 — WATCHLIST"],
            ["━" * 20],
            ["Ticker", "Trigger", "Current", "Grade", "Limit Order", "Stop", "Target", "Rationale"],
            ["GS", "$950-960", "$996.73", "66", "Limit @ $955", "$980", "$1,050", "Pullback to EMA21 or grade >70"],
            ["LLY", "$980-1000", "$1,065", "66", "Limit @ $990", "$1,040", "$1,150", "Pullback to support or grade >70"],
            ["XOM", "$150", "$154.92", "66", "Limit @ $150", "$148", "$165", "Energy rotation signal"],
            ["BAC", "$49", "$51.49", "58", "Limit @ $49", "$47", "$56", "Grade improvement + rally"],
        ],

        "📈 Fresh Grades": [
            ["📊 FRESH GRADES"],
            ["May 23, 2026 | Re-run with live Polygon prices | Portfolio: $196,000"],
            [""],
            ["Ticker", "Grade", "Rec", "Price", "RSI", "Trend", "Key Signal"],
            ["GS", 66, "NEUTRAL", "$996.73", "RSI 66.3", "Bullish EMA", "Near 20-day highs, Fed-sensitive"],
            ["LLY", 66, "NEUTRAL", "$1,065.00", "RSI 68.2", "Bullish EMA", "Obesity drug momentum, ~50x P/E"],
            ["XOM", 66, "NEUTRAL", "$154.92", "RSI 52.2", "Bullish EMA", "Energy, Buffett stake"],
            ["AAPL", 65, "NEUTRAL", "$308.82", "RSI 78.3 OVERBOUGHT", "Bullish EMA", "Near 20-day highs"],
            ["CRWD", 65, "NEUTRAL", "$663.46", "RSI 87.4 OVERBOUGHT", "Bullish EMA", "#1 conviction but extended"],
            ["NVDA", 64, "NEUTRAL", "$215.33", "RSI 53.6", "Bullish EMA", "MACD turning down"],
            ["TSLA", 64, "NEUTRAL", "$426.01", "RSI 58.4", "Bullish EMA", "MACD turning down"],
            ["GOOGL", 63, "NEUTRAL", "$382.97", "RSI 57.5", "Bullish EMA", "MACD turning down"],
            ["MSFT", 63, "NEUTRAL", "$418.57", "RSI 54.9", "Bullish EMA", "MACD turning down"],
            ["MS", 62, "NEUTRAL", "$201.03", "RSI 67.1", "Bullish EMA", "Near 20-day highs"],
            ["OXY", 62, "NEUTRAL", "$58.81", "RSI 53.0", "Bullish EMA", "Energy play"],
            ["AMD", 59, "NEUTRAL", "$467.51", "RSI 72.6 OVERBOUGHT", "Bullish EMA", "Weakest triad link"],
            ["META", 53, "AVOID", "$610.26", "RSI 45.5", "BEARISH EMA", "Below EMAs, MACD bearish"],
            ["SHOP", 49, "AVOID", "$103.00", "RSI 41.7", "BEARISH EMA", "Below EMAs, MACD bearish, wide stop"],
            [""],
            ["THRESHOLDS:", "85+ = STRONG BUY | 70-84 = MODERATE BUY | 55-69 = NEUTRAL | <55 = AVOID"],
        ],

        "🧠 LLM Council": [
            ["🧠 LLM COUNCIL v2"],
            ["May 23, 2026 | Cost: ~$0.05-0.10/query | Models: Claude + GPT-4o + Grok 4.3"],
            [""],
            ["Ticker", "Grade", "Fundamental", "Technical", "Sentiment", "Risk", "Contrarian", "Consensus", "Action"],
            ["GS", 66, "NEUTRAL", "NEUTRAL", "NEUTRAL", "REDUCE/Quarter", "BEARISH", "NEUTRAL", "No action"],
            ["LLY", 66, "BEARISH", "NEUTRAL", "NEUTRAL", "APPROVE/Half", "BEARISH", "NEUTRAL", "No action"],
            ["CRWD", 65, "NEUTRAL", "NEUTRAL", "NEUTRAL", "REDUCE/Quarter", "BEARISH", "NEUTRAL", "No action"],
            ["TSLA", 64, "NEUTRAL", "NEUTRAL", "BEARISH", "REDUCE/Quarter", "BEARISH", "NEUTRAL", "No action"],
            [""],
            ["KEY INSIGHT:", "Council consistently NEUTRAL-to-BEARISH. No BULLISH consensus anywhere."],
            ["", "Contrarians flag overvaluation. Risk managers say REDUCE/Quarter on all."],
            [""],
            ["LOGIC:", "BULLISH >=3 → Strong buy | BEARISH >=3 → Avoid | Mixed → Neutral"],
        ],

        "🇺🇸 Trump Tracker": [
            ["🇺🇸 TRUMP TRACKER"],
            ["Scan: May 22, 2026 7:32 PM | Tweets: 12 | High Impact: 0 | Medium: 0"],
            [""],
            ["VERDICT: No policy risk affecting trades Monday"],
            [""],
            ["Date", "Text", "Impact", "Sectors"],
            ["2026-05-22", "https://t.co/LU644jFVH2", "LOW", "—"],
            ["2026-05-19", "Horrible Congressman Thomas Massie...", "LOW", "—"],
            ["2026-05-22", "RT @WhiteHouse: President Trump Delivers Remarks", "LOW", "—"],
            [""],
            ["No high-impact policy tweets. All general/political content."],
        ],

        "⚖️ Position Sizer": [
            ["⚖️ POSITION SIZER"],
            ["Portfolio: $196,000 | Risk/Trade: 1.0% ($1,960)"],
            [""],
            ["Ticker", "Entry", "Stop", "Target", "R/R", "Full Size", "@ Grade 66", "Max Loss", "Max Gain"],
            ["GS", "$996.73", "$980", "$1,050", "1:3.2", "19 sh ($18,938)", "9 sh ($8,971)", "$318", "$1,012"],
            ["LLY", "$1,065", "$1,040", "$1,150", "1:3.4", "18 sh ($19,170)", "9 sh ($9,585)", "$450", "$1,530"],
            [""],
            ["GRADE ADJUSTMENTS:"],
            ["85+ (Strong Buy)", "→ Full size"],
            ["70-84 (Moderate)", "→ Reduce 25%"],
            ["55-69 (Neutral)", "→ Reduce 50% or SKIP"],
            ["<55 (Avoid)", "→ NO POSITION"],
            [""],
            ["STATUS: All grades 49-66 → No positions for entry Monday"],
        ],

        "⏰ Monday Schedule": [
            ["⏰ MONDAY SCHEDULE"],
            ["May 26, 2026"],
            [""],
            ["Time (ET)", "Action", "Tool/Script"],
            ["8:00 AM", "Trump tracker scan", "trump_tracker.py"],
            ["8:00 AM", "Alert system scan", "vox_smart_alerts_v8.py"],
            ["8:30 AM", "Volume scanner", "volume_scanner.py"],
            ["9:00 AM", "Politician tracker", "politician_tracker_v2.py"],
            ["9:30 AM", "Market open — monitor only", "—"],
            ["10:00 AM", "Swing screener refresh", "swing_screener.py"],
            ["12:00 PM", "Midday check — grades if >2% move", "grade_system.py"],
            ["2:00 PM", "Afternoon scan", "—"],
            ["3:30 PM", "Power hour — grade break 70?", "grade_system.py"],
            ["4:00 PM", "Close review + X momentum", "x_momentum_tracker.py"],
            [""],
            ["EXECUTE TODAY:"],
            ["⬜ Sell BYND (all)", "eToro"],
            ["⬜ Sell OSCR (all)", "GBM USA"],
            ["⬜ Trim TSLA ($3,500)", "GBM Main"],
            ["⬜ Trim CRWD ($3,400)", "GBM Main"],
            ["⬜ Trim AMD ($2,000)", "eToro/GBM USA"],
            ["⬜ Consider SHOP exit (grade 49)", "GBM Main"],
            ["⬜ Hold GOOGL, TSM, NVDA, AAPL, MSFT, IREN", "—"],
            ["⬜ NO new buys — all grades NEUTRAL", "—"],
        ],
    }

# ── ARCHIVE DATA ────────────────────────────────────────────
def get_archive_data():
    """Return dict of tab_name -> rows for Weekly Archive."""
    return {
        "📅 Weekly Snapshots": [
            ["📈 VOX WEEKLY ARCHIVE"],
            ["Historical portfolio data — appended every Friday 9 AM"],
            [""],
            ["━" * 25],
            ["WEEKLY SNAPSHOTS"],
            ["━" * 25],
            [""],
            ["Date", "Total AUM", "eToro", "GBM Main", "GBM USA", "Binance", "Schwab", "IBKR", "Revolut", "Bitso", "WoW $", "WoW %", "Notes"],
            ["2026-05-22", "$196,072", "$84,259", "$74,071", "$14,540", "$19,866", "$1,661", "$1,270", "$404", "$0", "—", "—", "Baseline"],
            [""],
            ["— Next row auto-appended by cron every Friday —"],
        ],

        "🏦 Broker Breakdown": [
            ["🏦 BROKER BREAKDOWN"],
            ["Per-broker detail — updated weekly"],
            [""],
            ["━" * 25],
            ["BROKER BREAKDOWN"],
            ["━" * 25],
            [""],
            ["Date", "Broker", "Value USD", "Value MXN", "% Total", "Positions", "Top Holding", "Top Value", "Cash", "API Status"],
            ["2026-05-22", "eToro", "$84,259", "$1,458,523", "43.0%", "285 + 2 mirrors", "AMD", "—", "$307", "🟢 Live"],
            ["2026-05-22", "GBM Main", "$74,071", "$1,282,173", "37.8%", "—", "CRWD", "$179,746 MXN", "—", "🟢 Excel"],
            ["2026-05-22", "Binance", "$19,866", "$343,880", "10.1%", "—", "BTC", "—", "—", "🟢 Live"],
            ["2026-05-22", "GBM USA", "$14,540", "$251,686", "7.4%", "—", "AMD", "$4,152", "$17", "🟢 Excel"],
            ["2026-05-22", "Schwab", "$1,661", "$28,758", "0.8%", "—", "IREN", "$232", "—", "🟡 Manual"],
            ["2026-05-22", "IBKR", "$1,270", "$21,984", "0.6%", "—", "AMD", "$454", "$5", "🟡 Manual"],
            ["2026-05-22", "Revolut", "$404", "$7,000", "0.2%", "—", "Savings", "$404", "$404", "🟡 Manual"],
            ["2026-05-22", "Bitso", "$0", "$0", "0.0%", "—", "ETH dust", "$0", "$0", "🟢 Live"],
        ],

        "📊 Asset Allocation": [
            ["📊 ASSET ALLOCATION"],
            ["Current vs Target — updated weekly"],
            [""],
            ["━" * 25],
            ["ASSET ALLOCATION"],
            ["━" * 25],
            [""],
            ["Date", "Asset Class", "Value", "% Total", "Target %", "Delta", "Action Needed"],
            ["2026-05-22", "Social Trading (eToro)", "$84,259", "43.0%", "15%", "+28%", "LIQUIDATE"],
            ["2026-05-22", "Mexican Broker (GBM Main)", "$74,071", "37.8%", "35%", "+3%", "HOLD"],
            ["2026-05-22", "US Brokers (IBKR+Schwab+GBM USA)", "$17,471", "8.9%", "25%", "-16%", "BUILD"],
            ["2026-05-22", "Crypto Exchanges", "$19,866", "10.1%", "5%", "+5%", "TRIM"],
            ["2026-05-22", "Savings (Revolut)", "$404", "0.2%", "5%", "-5%", "BUILD"],
            [""],
            ["TARGET ALLOCATION (90-Day):"],
            ["US Broad ETFs (VOO/VTI)", "5%", "→", "25%"],
            ["International (VXUS)", "0%", "→", "10%"],
            ["Individual Tech/Growth", "50%+", "→", "25%"],
            ["MXN Fixed Income", "0%", "→", "10%"],
            ["USD Cash/Short Bonds", "0.2%", "→", "8%"],
            ["Speculative/Single Names", "10%", "→", "7%"],
            ["eToro Residual", "48%", "→", "15%"],
        ],

        "💰 P&L History": [
            ["💰 P&L HISTORY"],
            ["Closed trades log"],
            [""],
            ["━" * 25],
            ["P&L HISTORY"],
            ["━" * 25],
            [""],
            ["Date", "Trade ID", "Ticker", "Action", "Entry", "Exit", "Shares", "P&L $", "P&L %", "Grade at Entry", "Council", "Status", "Notes"],
            ["2026-05-22", "WDC_20260522", "WDC", "BUY", "$486.46", "$500.00", "5", "$67.70", "+2.78%", "—", "—", "CLOSED", "Test trade"],
            [""],
            ["— Log executions here after Monday trades —"],
        ],

        "📈 Compound Growth": [
            ["📈 COMPOUND GROWTH TRACKER"],
            ["Performance metrics — auto-calculated from Weekly Snapshots"],
            [""],
            ["━" * 25],
            ["COMPOUND GROWTH"],
            ["━" * 25],
            [""],
            ["Date", "AUM", "WoW $", "WoW %", "MoM $", "MoM %", "YTD $", "YTD %", "CAGR", "Drawdown", "Max Drawdown", "Sharpe", "Notes"],
            ["2026-05-22", "$196,072", "—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "Baseline"],
            [""],
            ["— Auto-calculated from Weekly Snapshots —"],
            [""],
            ["FORMULAS:"],
            ["WoW % = (Current - Previous) / Previous"],
            ["MoM % = (Current - 4w ago) / 4w ago"],
            ["CAGR = (Current / Initial)^(52/weeks) - 1"],
            ["Drawdown = (Peak - Current) / Peak"],
        ],

        "📓 Trade Journal": [
            ["📓 TRADE JOURNAL"],
            ["Full execution log with stops, targets, rationale"],
            [""],
            ["━" * 25],
            ["TRADE JOURNAL"],
            ["━" * 25],
            [""],
            ["ID", "Date", "Ticker", "Action", "Entry", "Stop", "Target", "Shares", "Value", "Grade", "Council", "Status", "Exit Price", "P&L", "Notes"],
            ["WDC_001", "2026-05-22", "WDC", "BUY", "$486.46", "$450", "$550", "5", "$2,432", "—", "—", "CLOSED", "$500.00", "+$67.70", "Test trade"],
            [""],
            ["— Log all executions here —"],
        ],
    }

# ── MAIN ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vox Spreadsheet Builder")
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--both", action="store_true")
    args = parser.parse_args()

    if not any([args.dashboard, args.archive, args.both]):
        args.both = True

    service = get_service()

    if args.dashboard or args.both:
        sid, url = create_spreadsheet(service, "🎯 Vox Master Dashboard", DASHBOARD_TABS, FOLDER_ID)
        data = get_dashboard_data()
        for tab_name, rows in data.items():
            populate_tab(service, sid, tab_name, rows)
        print(f"\n✅ MASTER DASHBOARD: {url}")

    if args.archive or args.both:
        sid, url = create_spreadsheet(service, "📈 Vox Weekly Archive", ARCHIVE_TABS, FOLDER_ID)
        data = get_archive_data()
        for tab_name, rows in data.items():
            populate_tab(service, sid, tab_name, rows)
        print(f"\n✅ WEEKLY ARCHIVE: {url}")

if __name__ == "__main__":
    main()
