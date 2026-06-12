#!/usr/bin/env python3
"""
VOX Grade Weighting System v1.0
Dynamically weight grades based on historical accuracy.

- Track grade predictions vs outcomes
- Weight future grades by accuracy
- Kill signals that don't work
- Boost signals that do

Usage:
    python3 vox_grade_weighting.py update
    python3 vox_grade_weighting.py stats
    python3 vox_grade_weighting.py weight --ticker TSLA
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

WEIGHTS_FILE = Path.home() / ".hermes" / "scripts" / "vox_grade_weights.json"
GRADES_FILE = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
SNAPSHOTS_FILE = Path.home() / ".hermes" / "scripts" / "vox_grade_snapshots.json"


def load_weights() -> Dict:
    """Load current grade weights"""
    if WEIGHTS_FILE.exists():
        with open(WEIGHTS_FILE) as f:
            return json.load(f)
    return {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "grade_buckets": {
            "90-100": {"predictions": 0, "correct": 0, "weight": 1.0},
            "80-89": {"predictions": 0, "correct": 0, "weight": 1.0},
            "70-79": {"predictions": 0, "correct": 0, "weight": 1.0},
            "60-69": {"predictions": 0, "correct": 0, "weight": 1.0},
            "50-59": {"predictions": 0, "correct": 0, "weight": 1.0},
            "40-49": {"predictions": 0, "correct": 0, "weight": 1.0},
            "30-39": {"predictions": 0, "correct": 0, "weight": 1.0},
            "0-29": {"predictions": 0, "correct": 0, "weight": 1.0},
        },
        "ticker_accuracy": {},
    }


def save_weights(weights: Dict):
    """Save grade weights"""
    weights["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(WEIGHTS_FILE, 'w') as f:
        json.dump(weights, f, indent=2)


def get_grade_bucket(grade: int) -> str:
    """Get grade bucket"""
    if grade >= 90:
        return "90-100"
    elif grade >= 80:
        return "80-89"
    elif grade >= 70:
        return "70-79"
    elif grade >= 60:
        return "60-69"
    elif grade >= 50:
        return "50-59"
    elif grade >= 40:
        return "40-49"
    elif grade >= 30:
        return "30-39"
    else:
        return "0-29"


def calculate_accuracy(predictions: int, correct: int) -> float:
    """Calculate accuracy with smoothing"""
    if predictions == 0:
        return 0.5  # Neutral prior
    return (correct + 1) / (predictions + 2)  # Laplace smoothing


def update_weights():
    """Update grade weights based on historical accuracy"""
    weights = load_weights()
    
    # Load snapshots (grade history)
    if not SNAPSHOTS_FILE.exists():
        print("❌ No grade snapshots found. Run grade tracker first.")
        return
    
    with open(SNAPSHOTS_FILE) as f:
        snapshots = json.load(f)
    
    print("📊 Updating grade weights...")
    
    # Reset counters
    for bucket in weights["grade_buckets"]:
        weights["grade_buckets"][bucket]["predictions"] = 0
        weights["grade_buckets"][bucket]["correct"] = 0
    
    # Analyze each snapshot
    for snapshot in snapshots.get("snapshots", []):
        for ticker_data in snapshot.get("tickers", []):
            ticker = ticker_data["ticker"]
            grade = ticker_data["grade"]
            price_change = ticker_data.get("price_change_7d", 0)
            
            bucket = get_grade_bucket(grade)
            weights["grade_buckets"][bucket]["predictions"] += 1
            
            # Correct if: high grade + positive return, or low grade + negative return
            if grade >= 70 and price_change > 0:
                weights["grade_buckets"][bucket]["correct"] += 1
            elif grade < 50 and price_change < 0:
                weights["grade_buckets"][bucket]["correct"] += 1
            elif 50 <= grade < 70 and abs(price_change) < 5:
                weights["grade_buckets"][bucket]["correct"] += 1
    
    # Calculate weights
    for bucket, data in weights["grade_buckets"].items():
        accuracy = calculate_accuracy(data["predictions"], data["correct"])
        # Weight = 2 * accuracy - 1 (range: -1 to 1, then scale to 0.5 to 1.5)
        data["weight"] = round(0.5 + accuracy, 2)
        data["accuracy"] = round(accuracy, 3)
    
    save_weights(weights)
    
    print("\n✅ Weights updated:")
    for bucket, data in weights["grade_buckets"].items():
        if data["predictions"] > 0:
            print(f"   {bucket:8} | Accuracy: {data['accuracy']:.1%} | Weight: {data['weight']:.2f}x | Samples: {data['predictions']}")


def get_weighted_grade(ticker: str, grade: int) -> Dict:
    """Get weighted grade for a ticker"""
    weights = load_weights()
    bucket = get_grade_bucket(grade)
    weight = weights["grade_buckets"][bucket]["weight"]
    
    weighted_grade = grade * weight
    
    return {
        "ticker": ticker,
        "original_grade": grade,
        "bucket": bucket,
        "weight": weight,
        "weighted_grade": round(weighted_grade, 1),
        "confidence": "high" if weight > 1.2 else "medium" if weight > 0.8 else "low",
    }


def show_stats():
    """Show current weight stats"""
    weights = load_weights()
    
    print("\n📊 GRADE WEIGHT STATS")
    print("=" * 60)
    print(f"Last updated: {weights['last_updated']}")
    print()
    
    for bucket, data in weights["grade_buckets"].items():
        bar = "█" * int(data["weight"] * 10)
        print(f"   {bucket:8} | Weight: {data['weight']:.2f}x | {bar}")
    
    # Ticker accuracy
    if weights.get("ticker_accuracy"):
        print(f"\n🏆 Top Performing Tickers:")
        sorted_tickers = sorted(
            weights["ticker_accuracy"].items(),
            key=lambda x: x[1].get("accuracy", 0),
            reverse=True
        )[:5]
        for ticker, data in sorted_tickers:
            print(f"   {ticker}: {data.get('accuracy', 0):.1%} accuracy")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Grade Weighting")
    parser.add_argument("command", choices=["update", "stats", "weight"])
    parser.add_argument("--ticker", help="Ticker to weight")
    parser.add_argument("--grade", type=int, help="Grade to weight")
    
    args = parser.parse_args()
    
    if args.command == "update":
        update_weights()
    elif args.command == "stats":
        show_stats()
    elif args.command == "weight":
        if args.ticker and args.grade:
            result = get_weighted_grade(args.ticker, args.grade)
            print(json.dumps(result, indent=2))
        else:
            print("❌ Need --ticker and --grade")


if __name__ == "__main__":
    main()
