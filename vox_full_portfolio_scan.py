#!/usr/bin/env python3
"""
Vox Full Portfolio Scan — Grades ALL positions in one run
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime

# Your complete portfolio from memory
PORTFOLIO = [
    # Core Holdings
    "VOO", "AAPL", "MSFT", "0700.HK", "BRK.B",
    # Growth
    "TSLA", "CRWD", "AMD", "NVDA", "OKLO", "CEG", "DELL",
    # Value/Dividend
    "JPM", "BAC", "XOM", "CVX", "O",
    # International
    "INDA", "EWZ", "EWW", "FXI",
    # Crypto
    "BTC", "ETH", "BNB", "SOL",
    # Small Cap/Speculative
    "POET", "JMIA", "IONQ", "RKLB", "BE", "GEV", "SMCI",
    # Sector ETFs
    "XLK", "SMH", "XLE", "XLF", "XLI", "XLV",
    # Other
    "OSCR", "BYND", "PLTR", "COIN", "SQ", "SHOP",
    # Mexican positions (GBM)
    "ALSEA.MX", "BIMBO.MX", "CEMEX.MX", "GMEXICO.MX",
    # More...
    "AMAT", "MU", "LLY", "PANW", "ANET", "VST", "COHR",
    "META", "GOOGL", "NFLX", "UBER", "ABNB", "SNOW",
    "NET", "DDOG", "MDB", "CRWD", "S", "ZS",
    "FTNT", "CYBR", "SPLK", "NOW", "CRM",
]

def run_grade(ticker):
    """Run grade_system.py on a ticker and return result."""
    try:
        result = subprocess.run(
            ["python3", "grade_system.py", ticker, "196000"],
            cwd=Path.home() / ".hermes" / "scripts",
            capture_output=True,
            text=True,
            timeout=30
        )
        # Parse grade from output
        for line in result.stdout.split("\n"):
            if "TOTAL GRADE" in line:
                # Extract grade from line like "TOTAL GRADE     | ████████░░░░░░░░░░░░ | 58.0/100"
                parts = line.split("|")
                if len(parts) >= 3:
                    grade_str = parts[2].strip().split("/")[0]
                    return float(grade_str)
        return None
    except Exception as e:
        print(f"  Error grading {ticker}: {e}")
        return None

def main():
    print("=" * 70)
    print("📊 VOX FULL PORTFOLIO SCAN")
    print("=" * 70)
    print(f"Scanning {len(PORTFOLIO)} positions...")
    print()
    
    results = []
    
    for i, ticker in enumerate(PORTFOLIO, 1):
        print(f"[{i}/{len(PORTFOLIO)}] Grading {ticker}...")
        grade = run_grade(ticker)
        if grade:
            results.append({"ticker": ticker, "grade": grade})
            print(f"  → Grade: {grade}")
        else:
            print(f"  → Failed to grade")
        print()
    
    # Sort by grade
    results.sort(key=lambda x: x["grade"], reverse=True)
    
    print("=" * 70)
    print("📊 FULL PORTFOLIO GRADES (Ranked)")
    print("=" * 70)
    
    strong_buy = [r for r in results if r["grade"] >= 70]
    moderate_buy = [r for r in results if 55 <= r["grade"] < 70]
    avoid = [r for r in results if r["grade"] < 55]
    
    print(f"\n🟢 STRONG BUY (70+): {len(strong_buy)}")
    for r in strong_buy:
        print(f"   {r['ticker']:8} | Grade: {r['grade']:.1f}")
    
    print(f"\n🟡 MODERATE BUY (55-69): {len(moderate_buy)}")
    for r in moderate_buy:
        print(f"   {r['ticker']:8} | Grade: {r['grade']:.1f}")
    
    print(f"\n🔴 AVOID (<55): {len(avoid)}")
    for r in avoid:
        print(f"   {r['ticker']:8} | Grade: {r['grade']:.1f}")
    
    # Save results
    out_path = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_positions": len(PORTFOLIO),
            "graded": len(results),
            "strong_buy": strong_buy,
            "moderate_buy": moderate_buy,
            "avoid": avoid
        }, f, indent=2)
    
    print(f"\n💾 Saved to portfolio_grades.json")
    print(f"\nSummary: {len(strong_buy)} strong, {len(moderate_buy)} moderate, {len(avoid)} avoid")

if __name__ == "__main__":
    main()
