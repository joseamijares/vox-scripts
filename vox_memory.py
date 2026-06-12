#!/usr/bin/env python3
"""
VOX Pattern Memory v1.0
Compounding intelligence database.

Stores not just WHAT happened but WHAT IT MEANS.
- Patterns: "BTC broke $65K → dumped 12% in 3 days"
- Theses: "Why I recommended XLF on May 15"
- Outcomes: "Grade 70+ NVDA → +15% in 2 weeks"
- Market regimes: "Fed pause → tech rally for 30 days"

Query: "What happened last time TSLA had grade 70 + volume spike?"
Answer: "3 similar cases: 2 won (+12%, +8%), 1 lost (-3%). Win rate 67%."
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

MEMORY_FILE = Path.home() / ".hermes" / "scripts" / "vox_memory.json"
DASHBOARD_FILE = Path.home() / "dev" / "vox-dashboard" / "public" / "vox_memory.json"


def load_memory():
    """Load pattern memory"""
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {
        "patterns": [],
        "theses": [],
        "outcomes": [],
        "regimes": [],
        "queries": [],
    }


def save_memory(data):
    """Save pattern memory"""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    if DASHBOARD_FILE.parent.exists():
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def add_pattern(ticker: str, pattern_type: str, trigger: str, outcome: str, 
                pnl_pct: float = None, timeframe_days: int = None, notes: str = ""):
    """Add a pattern to memory"""
    memory = load_memory()
    
    pattern = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "type": pattern_type,  # "breakout", "breakdown", "earnings", "fed_event", etc.
        "trigger": trigger,  # "BTC broke $65K", "Grade dropped to 40", etc.
        "outcome": outcome,  # "Dumped 12% in 3 days"
        "pnl_pct": pnl_pct,
        "timeframe_days": timeframe_days,
        "notes": notes,
    }
    
    memory["patterns"].append(pattern)
    save_memory(memory)
    
    print(f"✅ Pattern added: {ticker} — {trigger} → {outcome}")
    return pattern


def add_thesis(ticker: str, thesis: str, signals: List[str], 
               entry_price: float, exit_price: float = None, 
               pnl: float = None, reflection: str = ""):
    """Add a trade thesis to memory"""
    memory = load_memory()
    
    t = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "thesis": thesis,
        "signals": signals,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": pnl,
        "reflection": reflection,
    }
    
    memory["theses"].append(t)
    save_memory(memory)
    
    print(f"✅ Thesis added: {ticker} — {thesis[:50]}...")
    return t


def add_outcome(ticker: str, grade_at_entry: int, price_at_entry: float,
                price_current: float, days_held: int, pnl_pct: float,
                was_correct: bool):
    """Add a grade outcome to memory"""
    memory = load_memory()
    
    outcome = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "grade_at_entry": grade_at_entry,
        "price_at_entry": price_at_entry,
        "price_current": price_current,
        "days_held": days_held,
        "pnl_pct": pnl_pct,
        "was_correct": was_correct,
    }
    
    memory["outcomes"].append(outcome)
    save_memory(memory)
    
    print(f"✅ Outcome added: {ticker} Grade {grade_at_entry} → {pnl_pct:+.1f}% ({'✅' if was_correct else '❌'})")
    return outcome


def query_memory(query_type: str, ticker: str = None, min_grade: int = None) -> List[Dict]:
    """Query pattern memory"""
    memory = load_memory()
    results = []
    
    if query_type == "pattern" and ticker:
        # Find similar patterns for this ticker
        results = [p for p in memory["patterns"] if p["ticker"] == ticker]
    
    elif query_type == "grade_outcome" and min_grade:
        # Find outcomes for grades >= min_grade
        results = [o for o in memory["outcomes"] if o["grade_at_entry"] >= min_grade]
    
    elif query_type == "thesis" and ticker:
        # Find theses for this ticker
        results = [t for t in memory["theses"] if t["ticker"] == ticker]
    
    elif query_type == "recent":
        # Get recent patterns
        results = sorted(memory["patterns"], key=lambda x: x["timestamp"], reverse=True)[:10]
    
    return results


def analyze_patterns(ticker: str) -> Dict:
    """Analyze patterns for a ticker"""
    memory = load_memory()
    patterns = [p for p in memory["patterns"] if p["ticker"] == ticker]
    outcomes = [o for o in memory["outcomes"] if o["ticker"] == ticker]
    
    if not patterns and not outcomes:
        return {"message": f"No memory for {ticker} yet"}
    
    # Pattern summary
    pattern_types = {}
    for p in patterns:
        pt = p["type"]
        if pt not in pattern_types:
            pattern_types[pt] = []
        pattern_types[pt].append(p)
    
    # Outcome summary
    wins = [o for o in outcomes if o["was_correct"]]
    losses = [o for o in outcomes if not o["was_correct"]]
    
    avg_pnl = sum(o["pnl_pct"] for o in outcomes) / len(outcomes) if outcomes else 0
    
    return {
        "ticker": ticker,
        "patterns_count": len(patterns),
        "outcomes_count": len(outcomes),
        "win_rate": len(wins) / len(outcomes) if outcomes else 0,
        "avg_pnl": avg_pnl,
        "pattern_types": {k: len(v) for k, v in pattern_types.items()},
        "recent_patterns": patterns[-3:] if patterns else [],
        "recent_outcomes": outcomes[-3:] if outcomes else [],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Pattern Memory")
    subparsers = parser.add_subparsers(dest="command")
    
    # Add pattern
    add_pat = subparsers.add_parser("add-pattern", help="Add a pattern")
    add_pat.add_argument("--ticker", required=True)
    add_pat.add_argument("--type", required=True)
    add_pat.add_argument("--trigger", required=True)
    add_pat.add_argument("--outcome", required=True)
    add_pat.add_argument("--pnl", type=float)
    add_pat.add_argument("--days", type=int)
    add_pat.add_argument("--notes")
    
    # Query
    query = subparsers.add_parser("query", help="Query memory")
    query.add_argument("--type", required=True, choices=["pattern", "grade_outcome", "thesis", "recent"])
    query.add_argument("--ticker")
    query.add_argument("--min-grade", type=int)
    
    # Analyze
    analyze = subparsers.add_parser("analyze", help="Analyze ticker patterns")
    analyze.add_argument("--ticker", required=True)
    
    # Stats
    subparsers.add_parser("stats", help="Show memory stats")
    
    args = parser.parse_args()
    
    if args.command == "add-pattern":
        add_pattern(args.ticker, args.type, args.trigger, args.outcome, args.pnl, args.days, args.notes or "")
    
    elif args.command == "query":
        results = query_memory(args.type, args.ticker, args.min_grade)
        print(f"\nFound {len(results)} results:")
        for r in results[:10]:
            print(f"  {r.get('ticker', '')}: {r.get('trigger', r.get('thesis', ''))[:60]}...")
    
    elif args.command == "analyze":
        result = analyze_patterns(args.ticker)
        print(f"\n📊 {args.ticker} Pattern Analysis")
        print("=" * 50)
        for k, v in result.items():
            if k not in ["recent_patterns", "recent_outcomes"]:
                print(f"{k}: {v}")
    
    elif args.command == "stats":
        memory = load_memory()
        print(f"Patterns: {len(memory['patterns'])}")
        print(f"Theses: {len(memory['theses'])}")
        print(f"Outcomes: {len(memory['outcomes'])}")
        print(f"Regimes: {len(memory['regimes'])}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
