#!/usr/bin/env python3
"""
VOX Risk Manager Agent
Analyzes portfolio concentration, correlation, drawdown.
Checks position sizing vs portfolio. Outputs: risk flags, sizing recommendations.

Usage:
    python3 risk_manager.py analyze
    python3 risk_manager.py check --ticker TSLA --size 10000
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

POSITIONS_FILE = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"


def load_portfolio():
    """Load portfolio data"""
    if not POSITIONS_FILE.exists():
        return None
    with open(POSITIONS_FILE) as f:
        return json.load(f)


def analyze_concentration(portfolio: Dict) -> Dict:
    """Analyze position concentration"""
    positions = portfolio.get("positions", [])
    total_value = portfolio.get("total_value", sum(p.get("value", 0) for p in positions))
    
    if not positions or total_value == 0:
        return {"error": "No positions"}
    
    # Sort by value
    sorted_pos = sorted(positions, key=lambda x: x.get("value", 0), reverse=True)
    
    # Top 5 concentration
    top5_value = sum(p["value"] for p in sorted_pos[:5])
    top5_pct = top5_value / total_value * 100
    
    # Largest position
    largest = sorted_pos[0]
    largest_pct = largest["value"] / total_value * 100
    
    # Flags
    flags = []
    if largest_pct > 10:
        flags.append(f"Largest position {largest['ticker']} is {largest_pct:.1f}% of portfolio (max 10%)")
    if top5_pct > 50:
        flags.append(f"Top 5 positions = {top5_pct:.1f}% (high concentration)")
    
    return {
        "top5_pct": top5_pct,
        "largest_position": {
            "ticker": largest["ticker"],
            "value": largest["value"],
            "pct": largest_pct,
        },
        "flags": flags,
        "risk_level": "HIGH" if largest_pct > 15 else "MEDIUM" if largest_pct > 10 else "LOW",
    }


def analyze_sector_risk(portfolio: Dict) -> Dict:
    """Analyze sector concentration"""
    positions = portfolio.get("positions", [])
    total_value = portfolio.get("total_value", sum(p.get("value", 0) for p in positions))
    
    # Group by sector
    sectors = {}
    for pos in positions:
        sector = pos.get("sector", "Unknown")
        if sector not in sectors:
            sectors[sector] = 0
        sectors[sector] += pos.get("value", 0)
    
    # Find largest sector
    largest_sector = max(sectors.items(), key=lambda x: x[1])
    largest_sector_pct = largest_sector[1] / total_value * 100
    
    flags = []
    if largest_sector_pct > 30:
        flags.append(f"Largest sector {largest_sector[0]} is {largest_sector_pct:.1f}% (max 30%)")
    
    return {
        "sectors": {k: round(v / total_value * 100, 1) for k, v in sectors.items()},
        "largest_sector": {
            "name": largest_sector[0],
            "pct": largest_sector_pct,
        },
        "flags": flags,
    }


def analyze_crypto_risk(portfolio: Dict) -> Dict:
    """Analyze crypto exposure"""
    positions = portfolio.get("positions", [])
    total_value = portfolio.get("total_value", sum(p.get("value", 0) for p in positions))
    
    crypto_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE", "XRP", "ADA", "TRX", "SUI"]
    crypto_value = sum(p["value"] for p in positions if p["ticker"] in crypto_tickers)
    crypto_pct = crypto_value / total_value * 100 if total_value > 0 else 0
    
    flags = []
    if crypto_pct > 10:
        flags.append(f"Crypto exposure {crypto_pct:.1f}% exceeds 10% limit")
    elif crypto_pct > 5:
        flags.append(f"Crypto exposure {crypto_pct:.1f}% (monitor)")
    
    return {
        "crypto_value": crypto_value,
        "crypto_pct": crypto_pct,
        "flags": flags,
        "risk_level": "HIGH" if crypto_pct > 15 else "MEDIUM" if crypto_pct > 10 else "LOW",
    }


def analyze_drawdown(portfolio: Dict) -> Dict:
    """Analyze current drawdowns"""
    positions = portfolio.get("positions", [])
    
    losers = [p for p in positions if p.get("pnl", 0) < 0]
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    
    # Biggest losers
    biggest_losers = sorted(losers, key=lambda x: x["pnl"])[:5]
    
    flags = []
    total_loss = sum(p["pnl"] for p in losers)
    if total_loss < -10000:
        flags.append(f"Total unrealized losses: ${total_loss:,.0f}")
    
    return {
        "unrealized_pnl": total_pnl,
        "loser_count": len(losers),
        "biggest_losers": [
            {"ticker": p["ticker"], "pnl": p["pnl"], "value": p["value"]}
            for p in biggest_losers
        ],
        "flags": flags,
    }


def check_position_size(ticker: str, proposed_size: float, portfolio: Dict) -> Dict:
    """Check if proposed position size is appropriate"""
    total_value = portfolio.get("total_value", 0)
    positions = portfolio.get("positions", [])
    
    # Current position
    current = next((p for p in positions if p["ticker"] == ticker), None)
    current_value = current["value"] if current else 0
    
    # After addition
    new_value = current_value + proposed_size
    new_pct = new_value / total_value * 100 if total_value > 0 else 0
    
    # Recommendations
    max_pct = 10  # Max 10% per position
    recommended = total_value * 0.05  # 5% recommended
    
    flags = []
    if new_pct > max_pct:
        flags.append(f"Position would be {new_pct:.1f}% (max {max_pct}%)")
    
    return {
        "ticker": ticker,
        "current_value": current_value,
        "proposed_size": proposed_size,
        "new_value": new_value,
        "new_pct": new_pct,
        "recommended_size": recommended,
        "max_size": total_value * max_pct / 100,
        "flags": flags,
        "approved": len(flags) == 0,
    }


def analyze_portfolio():
    """Full portfolio risk analysis"""
    portfolio = load_portfolio()
    if not portfolio:
        print("❌ No portfolio data")
        return
    
    print("\n⚠️ RISK MANAGER ANALYSIS")
    print("=" * 60)
    
    # Concentration
    concentration = analyze_concentration(portfolio)
    print(f"\n📊 CONCENTRATION")
    print(f"   Top 5: {concentration['top5_pct']:.1f}% of portfolio")
    print(f"   Largest: {concentration['largest_position']['ticker']} ({concentration['largest_position']['pct']:.1f}%)")
    print(f"   Risk: {concentration['risk_level']}")
    for flag in concentration["flags"]:
        print(f"   ⚠️ {flag}")
    
    # Sector
    sector = analyze_sector_risk(portfolio)
    print(f"\n🏭 SECTORS")
    print(f"   Largest: {sector['largest_sector']['name']} ({sector['largest_sector']['pct']:.1f}%)")
    for flag in sector["flags"]:
        print(f"   ⚠️ {flag}")
    
    # Crypto
    crypto = analyze_crypto_risk(portfolio)
    print(f"\n💰 CRYPTO")
    print(f"   Exposure: {crypto['crypto_pct']:.1f}% (${crypto['crypto_value']:,.0f})")
    print(f"   Risk: {crypto['risk_level']}")
    for flag in crypto["flags"]:
        print(f"   ⚠️ {flag}")
    
    # Drawdown
    drawdown = analyze_drawdown(portfolio)
    print(f"\n📉 DRAWDOWN")
    print(f"   Unrealized P&L: ${drawdown['unrealized_pnl']:+,.0f}")
    print(f"   Losers: {drawdown['loser_count']} positions")
    if drawdown["biggest_losers"]:
        print(f"   Biggest losers:")
        for loser in drawdown["biggest_losers"]:
            print(f"      {loser['ticker']}: ${loser['pnl']:+,.0f}")
    for flag in drawdown["flags"]:
        print(f"   ⚠️ {flag}")
    
    # Overall risk score
    risk_score = 0
    if concentration["risk_level"] == "HIGH":
        risk_score += 3
    elif concentration["risk_level"] == "MEDIUM":
        risk_score += 1
    
    if crypto["risk_level"] == "HIGH":
        risk_score += 2
    elif crypto["risk_level"] == "MEDIUM":
        risk_score += 1
    
    if drawdown["unrealized_pnl"] < -20000:
        risk_score += 2
    elif drawdown["unrealized_pnl"] < -10000:
        risk_score += 1
    
    print(f"\n🎯 OVERALL RISK SCORE: {risk_score}/10")
    if risk_score >= 7:
        print("   🔴 HIGH RISK - Action required")
    elif risk_score >= 4:
        print("   🟡 MEDIUM RISK - Monitor closely")
    else:
        print("   🟢 LOW RISK - Within parameters")
    
    # Save
    output_file = Path.home() / ".hermes" / "scripts" / "vox_risk_analysis.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "concentration": concentration,
            "sector": sector,
            "crypto": crypto,
            "drawdown": drawdown,
            "risk_score": risk_score,
        }, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Risk Manager")
    parser.add_argument("--ticker", help="Check position size")
    parser.add_argument("--size", type=float, help="Proposed position size")
    
    args = parser.parse_args()
    
    if args.ticker and args.size:
        portfolio = load_portfolio()
        if portfolio:
            result = check_position_size(args.ticker, args.size, portfolio)
            print(json.dumps(result, indent=2))
    else:
        analyze_portfolio()


if __name__ == "__main__":
    main()
