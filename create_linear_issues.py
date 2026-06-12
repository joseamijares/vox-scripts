#!/usr/bin/env python3
"""
Create Linear issues for VOX Broker Sync & Data Architecture project
"""

import json
import os
import subprocess

API_KEY = os.environ.get("LINEAR_API_KEY", "")
TEAM_ID = "7d2f102c-55b1-44f4-b09c-d4582b542c37"
PROJECT_ID = "dedd5bcb-7d88-476c-992a-de758de988bf"

# State IDs
STATE_TODO = "129cb0ab-2717-4413-b6d2-bd15a0530569"
STATE_BACKLOG = "aaa2deef-e95e-4a10-9867-96aeeaa012c8"
STATE_IN_PROGRESS = "ce9155f9-b178-42e4-aa53-4504ce288d84"

def create_issue(title, description, priority=3, state_id=None):
    """Create a Linear issue."""
    query = {
        "query": "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { identifier title url } } }",
        "variables": {
            "input": {
                "teamId": TEAM_ID,
                "projectId": PROJECT_ID,
                "title": title,
                "description": description,
                "priority": priority,
                "stateId": state_id or STATE_TODO
            }
        }
    }
    
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://api.linear.app/graphql",
         "-H", f"Authorization: {API_KEY}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(query)],
        capture_output=True, text=True
    )
    
    data = json.loads(result.stdout)
    if data.get("data", {}).get("issueCreate", {}).get("success"):
        issue = data["data"]["issueCreate"]["issue"]
        print(f"  ✅ {issue['identifier']}: {issue['title']}")
        return issue
    else:
        print(f"  ❌ Failed: {title}")
        print(f"     Error: {data}")
        return None

# Issues to create
issues = [
    # Phase 1: Broker Sync Foundation
    {
        "title": "[VOX] Fix eToro API position aggregation bug",
        "description": "eToro API returns positions with instrument IDs. Current aggregation logic fails when mapping IDs to symbols. Need to fix symbol extraction and handle duplicate positions (same ticker, multiple trades).\n\n**Acceptance Criteria:**\n- All eToro positions have correct ticker symbols\n- Duplicate positions aggregated by ticker\n- Mirror positions tracked separately\n- Total portfolio value matches eToro app",
        "priority": 1,
        "state": STATE_IN_PROGRESS
    },
    {
        "title": "[VOX] Add GBM Main/USA position parsing from JSON exports",
        "description": "GBM broker data is manual JSON exports. Need to parse individual stock positions from the export format and extract: ticker, shares, value, PnL, cost basis.\n\n**Current Status:**\n- GBM Main: $1,282,172 MXN total but 0 parsed positions\n- GBM USA: $14,539 total but 0 parsed positions\n\n**Acceptance Criteria:**\n- Parse SIC positions (US stocks)\n- Parse national positions (Mexican stocks)\n- Convert MXN to USD using live FX rate\n- Extract cash balances",
        "priority": 1,
        "state": STATE_TODO
    },
    {
        "title": "[VOX] Implement live FX conversion (MXN→USD)",
        "description": "GBM Main portfolio is in MXN. Need live FX conversion to USD for unified portfolio view.\n\n**Options:**\n1. Polygon.io FX API (if available)\n2. OpenExchangeRates API\n3. Manual daily rate update\n\n**Acceptance Criteria:**\n- USD/MXN rate fetched daily\n- All MXN values converted to USD in unified view\n- Rate stored with timestamp for audit",
        "priority": 2,
        "state": STATE_TODO
    },
    {
        "title": "[VOX] Add Schwab API integration (replace manual JSON)",
        "description": "Schwab currently uses manual JSON export. Need to investigate Schwab API for automated sync.\n\n**Research Needed:**\n- Schwab OAuth2 API availability\n- Account aggregation API\n- Rate limits and permissions\n\n**Acceptance Criteria:**\n- Automated daily sync from Schwab\n- Position data matches Schwab app\n- Error handling for API failures",
        "priority": 3,
        "state": STATE_BACKLOG
    },
    {
        "title": "[VOX] Add IBKR API integration (replace manual JSON)",
        "description": "Interactive Brokers has a robust API. Need to implement automated sync for positions and PnL.\n\n**Research Needed:**\n- IBKR Client Portal API vs TWS API\n- Authentication flow\n- Position and account data endpoints\n\n**Acceptance Criteria:**\n- Automated daily sync from IBKR\n- Real-time position data\n- PnL tracking per position",
        "priority": 3,
        "state": STATE_BACKLOG
    },
    
    # Phase 2: Data Architecture
    {
        "title": "[VOX] Fix Supabase credentials for hybrid sync",
        "description": "Supabase sync failing with 401 Invalid API Key. Need to fix credentials and test connection.\n\n**Current Status:**\n- Anon key: fails with 401\n- Service role key: not configured\n- Tables may not exist\n\n**Acceptance Criteria:**\n- Supabase connection successful\n- watchlist_grades table created\n- portfolio_grades table created\n- intelligence_snapshots table created\n- Data syncs from Python scripts",
        "priority": 2,
        "state": STATE_TODO
    },
    {
        "title": "[VOX] Create Supabase schema for graded data",
        "description": "Design and create Supabase tables for watchlist grades, portfolio grades, and intelligence snapshots.\n\n**Schema Needed:**\n```sql\nwatchlist_grades: ticker, price, grade, signal, rsi, ema21, atr, buy_zone, stop_loss, target_1, target_2, risk_reward, graded_at\nportfolio_grades: ticker, price, entry_price, shares, live_value, live_pnl, pnl_pct, grade, signal, add_on_zone, trailing_stop, take_profit_1, take_profit_2, graded_at\nintelligence_snapshots: date, watchlist_count, portfolio_count, strong_buy, buy, hold, weak, trim, avoid, avg_grade, data\n```\n\n**Acceptance Criteria:**\n- All tables created with proper types\n- Indexes on ticker, grade, signal\n- RLS policies configured",
        "priority": 2,
        "state": STATE_TODO
    },
    {
        "title": "[VOX] Build dashboard API routes (SSR mode)",
        "description": "Current dashboard uses static export (output: 'export') which prevents API routes. Need to either:\n\n**Option A:** Switch to SSR mode\n- Requires Vercel paid plan for serverless functions\n- Enables /api/* routes\n- Real-time Supabase queries\n\n**Option B:** Keep static + rebuild\n- Free on Vercel\n- Rebuild after each pipeline run\n- JSON files as source of truth\n\n**Decision:** Start with Option B (static), migrate to Option A when needed.\n\n**Acceptance Criteria:**\n- Dashboard rebuilds automatically after pipeline\n- Data freshness < 15 minutes",
        "priority": 3,
        "state": STATE_BACKLOG
    },
    
    # Phase 3: Pipeline & Automation
    {
        "title": "[VOX] Add broker stale data detection and alerts",
        "description": "Manual brokers (GBM, Schwab, IBKR, Revolut, Bitso) need stale data detection. Alert when data hasn't been updated in >7 days.\n\n**Implementation:**\n- Track last_updated timestamp per broker\n- Compare against current date\n- Telegram alert for stale brokers\n- Dashboard indicator (🟡 → 🔴)\n\n**Acceptance Criteria:**\n- Stale detection runs daily\n- Alert sent when broker >7 days old\n- Dashboard shows stale indicator\n- User can snooze alerts",
        "priority": 2,
        "state": STATE_TODO
    },
    {
        "title": "[VOX] Integrate broker sync into unified pipeline",
        "description": "Current pipeline runs broker sync separately from alert pipeline. Need unified pipeline that:\n\n1. Syncs brokers (7 AM + 12 PM)\n2. Fetches live prices\n3. Grades watchlist + portfolio\n4. Runs research agents\n5. Generates alerts\n6. Copies data to dashboard\n7. Rebuilds dashboard\n\n**Acceptance Criteria:**\n- Single pipeline script\n- Clear step-by-step output\n- Error handling per step\n- Telegram notification on completion/failure",
        "priority": 2,
        "state": STATE_TODO
    },
    {
        "title": "[VOX] Add auto-rebuild dashboard after pipeline",
        "description": "After pipeline completes, automatically rebuild and deploy dashboard to Vercel.\n\n**Implementation:**\n- Add `npm run build && npx vercel --prod` to pipeline\n- Check for build errors\n- Verify deployment success\n- Fallback to manual if build fails\n\n**Acceptance Criteria:**\n- Dashboard auto-rebuilds after each pipeline\n- Build errors reported via Telegram\n- Deployment URL confirmed",
        "priority": 3,
        "state": STATE_BACKLOG
    },
    
    # Phase 4: Intelligence & Analytics
    {
        "title": "[VOX] Build portfolio drift detection",
        "description": "Detect when portfolio allocations drift from target weights. Alert when any position exceeds threshold.\n\n**Implementation:**\n- Target weights per sector/ticker\n- Current vs target comparison\n- Drift threshold (e.g., ±5%)\n- Rebalancing suggestions\n\n**Acceptance Criteria:**\n- Drift calculated daily\n- Alert when drift > threshold\n- Rebalancing trades suggested\n- Historical drift tracking",
        "priority": 3,
        "state": STATE_BACKLOG
    },
    {
        "title": "[VOX] Add portfolio correlation heatmap",
        "description": "Calculate correlations between portfolio positions to identify concentration risk.\n\n**Implementation:**\n- 60-day price correlation matrix\n- Heatmap visualization\n- Identify highly correlated pairs\n- Diversification score\n\n**Acceptance Criteria:**\n- Correlation matrix calculated weekly\n- Heatmap on dashboard\n- High correlation alerts (>0.8)\n- Diversification recommendations",
        "priority": 4,
        "state": STATE_BACKLOG
    },
    {
        "title": "[VOX] Implement position sizing optimizer",
        "description": "Suggest optimal position sizes based on Kelly criterion, volatility, and conviction.\n\n**Implementation:**\n- Kelly fraction per position\n- Volatility-adjusted sizing\n- Conviction multiplier\n- Risk budget allocation\n\n**Acceptance Criteria:**\n- Sizing recommendations per ticker\n- Risk budget visualization\n- Max drawdown estimation\n- Rebalancing signals",
        "priority": 4,
        "state": STATE_BACKLOG
    },
]

print("=" * 70)
print("Creating Linear issues for VOX Broker Sync & Data Architecture")
print("=" * 70)
print()

created = []
for issue_data in issues:
    issue = create_issue(
        issue_data["title"],
        issue_data["description"],
        issue_data["priority"],
        issue_data["state"]
    )
    if issue:
        created.append(issue)
    print()

print("=" * 70)
print(f"Created {len(created)} issues")
print("=" * 70)
for issue in created:
    print(f"  {issue['identifier']}: {issue['title']}")
