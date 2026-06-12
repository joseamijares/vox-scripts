#!/usr/bin/env python3
"""
VOX Alert Validator v1.0
Prevents hallucinated alerts by validating all claims against Railway Postgres.

All alerts must pass through this validator before being sent to the user.
"""

import json
import urllib.request
import re
from datetime import datetime

DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"

# Sanity check thresholds
MAX_REASONABLE_GAIN_PCT = 500  # Flag anything claiming >500% gain
MAX_REASONABLE_POSITION_PCT = 50  # Flag anything claiming >50% of portfolio


def fetch_positions():
    """Fetch live positions from Railway Postgres."""
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/positions")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("positions", [])
    except Exception as e:
        print(f"❌ Failed to fetch positions: {e}")
        return []


def validate_alert(alert_text: str) -> dict:
    """
    Validate an alert against actual portfolio data.
    
    Returns: {
        "valid": bool,
        "errors": [list of validation failures],
        "warnings": [list of suspicious claims],
        "position_data": {ticker: actual_data}
    }
    """
    positions = fetch_positions()
    if not positions:
        return {
            "valid": False,
            "errors": ["Could not fetch live position data for validation"],
            "warnings": [],
            "position_data": {}
        }
    
    # Build ticker lookup
    ticker_map = {p["ticker"]: p for p in positions}
    total_aum = sum(p.get("live_value", 0) for p in positions)
    
    errors = []
    warnings = []
    position_data = {}
    
    # Extract tickers mentioned in alert (simple regex-like approach)
    words = alert_text.replace("$", " ").replace("(", " ").replace(")", " ").split()
    mentioned_tickers = set()
    for word in words:
        clean = word.strip().upper()
        if clean in ticker_map:
            mentioned_tickers.add(clean)
    
    for ticker in mentioned_tickers:
        pos = ticker_map[ticker]
        position_data[ticker] = pos
        
        live_value = pos.get("live_value", 0)
        shares = pos.get("shares", 0)
        avg_cost = pos.get("avg_cost")
        live_price = pos.get("live_price", 0)
        
        # Calculate actual P&L
        if avg_cost and shares > 0:
            cost_basis = shares * avg_cost
            pnl_pct = ((live_value - cost_basis) / cost_basis) * 100 if cost_basis > 0 else 0
        else:
            pnl_pct = 0
        
        portfolio_pct = (live_value / total_aum * 100) if total_aum > 0 else 0
        
        # Check for suspicious gain claims in alert text
        alert_upper = alert_text.upper()
        
        # Look for percentage claims near ticker
        ticker_escaped = re.escape(ticker)
        pct_patterns = [
            rf"{ticker_escaped}\s+(?:up|gain|\+)\s*(\d+)%",
            rf"{ticker_escaped}\s+.*?(\d+)%",
            rf"(\d+)%\s+.*?(?:{ticker_escaped}|gain|profit)",
        ]
        
        claimed_gain = None
        for pattern in pct_patterns:
            try:
                matches = re.findall(pattern, alert_upper)
                for match in matches:
                    try:
                        val = int(match)
                        if val > 10:  # Only consider significant claims
                            claimed_gain = val
                            break
                    except:
                        pass
                if claimed_gain:
                    break
            except re.error:
                continue
        
        # Also check for "X" claims like "233x"
        x_patterns = [
            rf"{ticker_escaped}\s+.*?(\d+)x",
            rf"(\d+)x\s+.*?(?:{ticker_escaped}|gain|return)",
        ]
        claimed_multiplier = None
        for pattern in x_patterns:
            try:
                matches = re.findall(pattern, alert_upper)
                for match in matches:
                    try:
                        val = int(match)
                        if val > 2:
                            claimed_multiplier = val
                            break
                    except:
                        pass
                if claimed_multiplier:
                    break
            except re.error:
                continue
        
        # Validate claims
        if claimed_gain and abs(claimed_gain - pnl_pct) > 50:
            errors.append(
                f"{ticker}: Claimed gain {claimed_gain}% but actual is {pnl_pct:+.1f}%"
            )
        
        if claimed_multiplier:
            # Convert multiplier to percentage for comparison
            implied_pct = (claimed_multiplier - 1) * 100
            if abs(implied_pct - pnl_pct) > 50:
                errors.append(
                    f"{ticker}: Claimed {claimed_multiplier}x return but actual is {pnl_pct:+.1f}%"
                )
        
        # Check for unreasonable claims even if not explicitly matched
        if pnl_pct > MAX_REASONABLE_GAIN_PCT:
            warnings.append(
                f"{ticker}: Actual gain {pnl_pct:.1f}% exceeds sanity threshold ({MAX_REASONABLE_GAIN_PCT}%)"
            )
        
        if portfolio_pct > MAX_REASONABLE_POSITION_PCT:
            warnings.append(
                f"{ticker}: Position {portfolio_pct:.1f}% exceeds sanity threshold ({MAX_REASONABLE_POSITION_PCT}%)"
            )
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "position_data": position_data
    }


def format_validation_report(result: dict, alert_text: str) -> str:
    """Format validation result as markdown."""
    lines = [
        "# VOX Alert Validation Report",
        f"**Time:** {datetime.now().isoformat()}",
        f"**Status:** {'✅ VALID' if result['valid'] else '❌ REJECTED'}",
        "",
        "## Original Alert",
        f"> {alert_text[:500]}",
        "",
    ]
    
    if result["errors"]:
        lines.append("## ❌ Validation Errors")
        for err in result["errors"]:
            lines.append(f"- {err}")
        lines.append("")
    
    if result["warnings"]:
        lines.append("## ⚠️ Warnings")
        for warn in result["warnings"]:
            lines.append(f"- {warn}")
        lines.append("")
    
    if result["position_data"]:
        lines.append("## 📊 Actual Position Data")
        for ticker, pos in result["position_data"].items():
            lines.append(f"\n**{ticker}:**")
            lines.append(f"- Value: ${pos.get('live_value', 0):,.2f}")
            lines.append(f"- Price: ${pos.get('live_price', 0):,.2f}")
            if pos.get('avg_cost'):
                pnl = (pos['live_value'] - (pos['shares'] * pos['avg_cost']))
                pnl_pct = (pnl / (pos['shares'] * pos['avg_cost'])) * 100 if pos['shares'] * pos['avg_cost'] > 0 else 0
                lines.append(f"- P&L: ${pnl:,.2f} ({pnl_pct:+.1f}%)")
            lines.append(f"- Grade: {pos.get('grade', 'N/A')}")
            lines.append(f"- Council: {pos.get('council', 'N/A')}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        alert_text = " ".join(sys.argv[1:])
    else:
        # Test with the fake alert
        alert_text = """
        VOX ALERTS — 2 Action Required
        TE up 951% on data center battery play - trim position
        Massive gain on tiny 0.2% position creates asymmetric risk
        Action: Sell 50% at market open, lock $2,135 profit
        
        DDOG upgrade momentum validates 233x position
        233x unrealized gain on $2.5K position creates massive portfolio impact risk
        Action: Monitor for profit-taking levels above current gains
        """
    
    result = validate_alert(alert_text)
    report = format_validation_report(result, alert_text)
    print(report)
    
    sys.exit(0 if result["valid"] else 1)
