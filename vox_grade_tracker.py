#!/usr/bin/env python3
"""
VOX Grade Accuracy Tracker v1.0
Track if grades were right. Learn which signals work.

For every graded position, record:
- Grade given
- Price at grading
- Price 7/14/30 days later
- Was the grade directionally correct?

Outputs:
- Win rate per grade bucket
- Win rate per signal type
- Grade accuracy trend over time
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request

# Files
GRADES_FILE = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
TRACKER_FILE = Path.home() / ".hermes" / "scripts" / "vox_grade_tracker.json"
DASHBOARD_FILE = Path.home() / "dev" / "vox-dashboard" / "public" / "vox_grade_tracker.json"
HISTORY_DIR = Path.home() / ".hermes" / "scripts" / "grade_history"

# Ensure history dir exists
HISTORY_DIR.mkdir(exist_ok=True)


def load_tracker():
    """Load grade tracker"""
    if TRACKER_FILE.exists():
        with open(TRACKER_FILE) as f:
            return json.load(f)
    return {
        "snapshots": [],
        "accuracy": {
            "grade_70_plus": {"correct": 0, "total": 0},
            "grade_60_69": {"correct": 0, "total": 0},
            "grade_50_59": {"correct": 0, "total": 0},
            "grade_below_50": {"correct": 0, "total": 0},
        },
        "signal_accuracy": {},
        "last_updated": None,
    }


def save_tracker(data):
    """Save grade tracker"""
    with open(TRACKER_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    if DASHBOARD_FILE.parent.exists():
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def get_price(ticker):
    """Get current price from Polygon"""
    api_key = None
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, val = line.strip().split('=', 1)
                    if key == 'POLYGON_API_KEY':
                        api_key = val.strip().strip('"').strip("'")
                        break
    
    if not api_key:
        return None
    
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get('results'):
                return data['results'][0].get('c')
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
    
    return None


def take_snapshot():
    """Take a snapshot of current grades and prices"""
    print("📸 Taking grade snapshot...")
    
    if not GRADES_FILE.exists():
        print("❌ No grades file found")
        return
    
    with open(GRADES_FILE) as f:
        grades = json.load(f)
    
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions": [],
    }
    
    all_graded = []
    for cat in ['strong_buy', 'moderate_buy', 'avoid']:
        for item in grades.get(cat, []):
            all_graded.append(item)
    
    print(f"   Checking {len(all_graded)} graded positions...")
    
    for item in all_graded[:20]:  # Limit API calls
        ticker = item['ticker']
        grade = item['grade']
        price = get_price(ticker)
        
        if price:
            snapshot["positions"].append({
                "ticker": ticker,
                "grade": grade,
                "price_at_grade": item.get('price', price),
                "current_price": price,
                "change_pct": round((price - item.get('price', price)) / item.get('price', price) * 100, 2) if item.get('price') else None,
            })
            print(f"   {ticker}: Grade {grade}, Price ${price:.2f}")
    
    # Save snapshot
    snapshot_file = HISTORY_DIR / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(snapshot_file, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    # Update tracker
    tracker = load_tracker()
    tracker["snapshots"].append({
        "timestamp": snapshot["timestamp"],
        "file": str(snapshot_file),
        "count": len(snapshot["positions"]),
    })
    tracker["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_tracker(tracker)
    
    print(f"\n✅ Snapshot saved: {snapshot_file}")
    print(f"   Tracked: {len(snapshot['positions'])} positions")


def analyze_accuracy():
    """Analyze grade accuracy from historical snapshots"""
    print("📊 Analyzing grade accuracy...")
    
    tracker = load_tracker()
    
    # Find snapshots from 7+ days ago
    old_snapshots = []
    for snap in tracker["snapshots"]:
        snap_time = datetime.fromisoformat(snap["timestamp"])
        if datetime.now(timezone.utc) - snap_time > timedelta(days=7):
            old_snapshots.append(snap)
    
    if not old_snapshots:
        print("   No old snapshots to analyze (need 7+ days)")
        return
    
    print(f"   Found {len(old_snapshots)} snapshots to analyze")
    
    # For each old snapshot, compare with current
    for snap in old_snapshots[-5:]:  # Last 5
        with open(snap["file"]) as f:
            old_data = json.load(f)
        
        print(f"\n   Snapshot from {snap['timestamp'][:10]}:")
        
        for pos in old_data["positions"]:
            ticker = pos["ticker"]
            old_grade = pos["grade"]
            old_price = pos["current_price"]
            
            current_price = get_price(ticker)
            if not current_price:
                continue
            
            change_pct = (current_price - old_price) / old_price * 100
            
            # Was the grade directionally correct?
            # Grade 70+ = should go up
            # Grade <50 = should go down
            if old_grade >= 70:
                correct = change_pct > 0
                bucket = "grade_70_plus"
            elif old_grade >= 60:
                correct = change_pct > -5  # Some tolerance
                bucket = "grade_60_69"
            elif old_grade >= 50:
                correct = abs(change_pct) < 10  # Hold = don't move much
                bucket = "grade_50_59"
            else:
                correct = change_pct < 0  # Should go down
                bucket = "grade_below_50"
            
            tracker["accuracy"][bucket]["total"] += 1
            if correct:
                tracker["accuracy"][bucket]["correct"] += 1
            
            print(f"     {ticker}: Grade {old_grade} → {change_pct:+.1f}% ({'✅' if correct else '❌'})")
    
    # Print summary
    print("\n📈 GRADE ACCURACY SUMMARY")
    print("=" * 50)
    for bucket, stats in tracker["accuracy"].items():
        if stats["total"] > 0:
            rate = stats["correct"] / stats["total"]
            print(f"{bucket:20} | {rate:.1%} ({stats['correct']}/{stats['total']})")
    
    save_tracker(tracker)
    print(f"\n✅ Tracker updated")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Grade Tracker")
    parser.add_argument("command", choices=["snapshot", "analyze", "stats"])
    args = parser.parse_args()
    
    if args.command == "snapshot":
        take_snapshot()
    elif args.command == "analyze":
        analyze_accuracy()
    elif args.command == "stats":
        tracker = load_tracker()
        print(f"Snapshots: {len(tracker['snapshots'])}")
        print(f"Last updated: {tracker['last_updated']}")
        for bucket, stats in tracker["accuracy"].items():
            if stats["total"] > 0:
                rate = stats["correct"] / stats["total"]
                print(f"{bucket}: {rate:.1%}")


if __name__ == "__main__":
    main()
