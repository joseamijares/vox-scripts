#!/usr/bin/env python3
"""
Vox Suggested Plays Pipeline
- Runs swing screener on watchlist
- Grades top setups (0-100)
- Runs LLM Council for consensus
- Only surfaces grade 80+ plays
- Pushes to Google Sheets '⚡ Suggested Plays' tab
"""
import json, os, sys, subprocess
from datetime import datetime

# Import existing tools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_screener():
    """Run swing screener, return strong setups."""
    print("🔍 Running swing screener...")
    try:
        result = subprocess.run(
            ["python3", "swing_screener.py"],
            capture_output=True, text=True, timeout=120
        )
        # Parse output — screener saves to screener_results.json
        with open("screener_results.json") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️ Screener failed: {e}")
        return {"setups": []}

def grade_setup(ticker):
    """Run grade system on ticker."""
    print(f"📊 Grading {ticker}...")
    try:
        result = subprocess.run(
            ["python3", "grade_system.py", ticker],
            capture_output=True, text=True, timeout=60
        )
        with open("grade_results.json") as f:
            grades = json.load(f)
            for g in grades:
                if g.get("ticker") == ticker:
                    return g
        return None
    except Exception as e:
        print(f"  ⚠️ Grade failed: {e}")
        return None

def run_council(ticker):
    """Run LLM Council on ticker."""
    print(f"🧠 Council for {ticker}...")
    try:
        result = subprocess.run(
            ["python3", "llm_council.py", ticker],
            capture_output=True, text=True, timeout=120
        )
        with open("llm_council_v2_results.json") as f:
            council = json.load(f)
            return council.get(ticker, {})
    except Exception as e:
        print(f"  ⚠️ Council failed: {e}")
        return {}

def main():
    print("⚡ Vox Suggested Plays Pipeline")
    print("=" * 50)
    
    # Step 1: Screener
    screener = run_screener()
    setups = screener.get("setups", [])
    print(f"  Found {len(setups)} setups")
    
    # Step 2: Grade each
    graded = []
    for setup in setups[:15]:  # Top 15
        ticker = setup.get("ticker")
        grade = grade_setup(ticker)
        if grade and grade.get("grade", 0) >= 80:
            council = run_council(ticker)
            graded.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "ticker": ticker,
                "setup": setup.get("setup", "—"),
                "grade": grade.get("grade", 0),
                "council": council.get("consensus", "—"),
                "price": grade.get("price", "—"),
                "target": "—",
                "stop": "—",
                "risk_pct": "—",
                "conviction": "HIGH" if grade.get("grade", 0) >= 85 else "MODERATE",
                "status": "SUGGESTED",
                "notes": f"RSI: {grade.get('rsi', '—')}, EMA: {grade.get('ema', '—')}"
            })
            print(f"  ✅ {ticker}: Grade {grade.get('grade')} — {council.get('consensus', 'N/A')}")
        else:
            print(f"  ⬜ {ticker}: Grade {grade.get('grade', 'N/A') if grade else 'N/A'} — skipped")
    
    # Step 3: Save
    output = {
        "generated": datetime.now().isoformat(),
        "plays": graded,
        "count": len(graded)
    }
    with open("vox_suggested_plays.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ {len(graded)} A+ plays saved to vox_suggested_plays.json")
    return output

if __name__ == "__main__":
    main()
