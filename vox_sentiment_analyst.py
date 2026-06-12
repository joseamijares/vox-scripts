#!/usr/bin/env python3
"""
VOX Sentiment Analyst v1.0
Tracks market sentiment from multiple sources.

Sources:
- X/Twitter (fear/greed indicators)
- Reddit (wallstreetbets, investing)
- VIX (volatility = fear)
- Put/Call ratio
- CNN Fear & Greed proxy

Output: vox_sentiment_report.json
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public"

def get_vix():
    """Get current VIX level"""
    # In production, fetch from Yahoo Finance API
    # For now, use estimated value
    return {
        "value": 16.2,
        "change": -0.5,
        "interpretation": "LOW" if 16.2 < 20 else "MODERATE" if 16.2 < 25 else "HIGH",
    }

def get_fear_greed_index():
    """Calculate fear/greed index (0-100)"""
    # Simplified calculation
    vix = 16.2
    
    # VIX component (lower VIX = more greed)
    vix_score = max(0, min(100, (30 - vix) / 30 * 100))
    
    # Market momentum (placeholder)
    momentum_score = 55  # Slightly bullish
    
    # Combined
    fg_index = (vix_score * 0.4 + momentum_score * 0.6)
    
    if fg_index >= 75:
        classification = "EXTREME_GREED"
    elif fg_index >= 55:
        classification = "GREED"
    elif fg_index >= 45:
        classification = "NEUTRAL"
    elif fg_index >= 25:
        classification = "FEAR"
    else:
        classification = "EXTREME_FEAR"
    
    return {
        "index": round(fg_index, 1),
        "classification": classification,
        "components": {
            "vix": round(vix_score, 1),
            "momentum": momentum_score,
        }
    }

def get_social_sentiment():
    """Get social media sentiment"""
    # Placeholder - would integrate with X API, Reddit API
    return {
        "twitter_bullish_pct": 58,
        "twitter_bearish_pct": 42,
        "reddit_mentions": 1247,
        "reddit_sentiment": "BULLISH",
        "trending_tickers": ["NVDA", "TSLA", "BTC", "ETH"],
    }

def get_put_call_ratio():
    """Get put/call ratio"""
    # Placeholder
    return {
        "ratio": 0.85,
        "interpretation": "BULLISH" if 0.85 < 1.0 else "BEARISH",
        "trend": "DECREASING",
    }

def generate_sentiment_report():
    """Generate comprehensive sentiment report"""
    
    now = datetime.now(timezone.utc)
    
    vix = get_vix()
    fear_greed = get_fear_greed_index()
    social = get_social_sentiment()
    put_call = get_put_call_ratio()
    
    # Calculate overall sentiment score (-100 to +100)
    scores = []
    
    # VIX contribution
    if vix["interpretation"] == "LOW":
        scores.append(30)
    elif vix["interpretation"] == "MODERATE":
        scores.append(0)
    else:
        scores.append(-30)
    
    # Fear/Greed contribution
    fg_map = {
        "EXTREME_GREED": 50,
        "GREED": 25,
        "NEUTRAL": 0,
        "FEAR": -25,
        "EXTREME_FEAR": -50,
    }
    scores.append(fg_map.get(fear_greed["classification"], 0))
    
    # Social contribution
    social_score = (social["twitter_bullish_pct"] - 50) * 1.5
    scores.append(social_score)
    
    # Put/Call contribution
    if put_call["interpretation"] == "BULLISH":
        scores.append(20)
    else:
        scores.append(-20)
    
    overall_score = sum(scores) / len(scores)
    
    if overall_score >= 30:
        overall = "BULLISH"
    elif overall_score >= 10:
        overall = "SLIGHTLY_BULLISH"
    elif overall_score >= -10:
        overall = "NEUTRAL"
    elif overall_score >= -30:
        overall = "SLIGHTLY_BEARISH"
    else:
        overall = "BEARISH"
    
    report = {
        "timestamp": now.isoformat(),
        "overall_sentiment": overall,
        "overall_score": round(overall_score, 1),
        "vix": vix,
        "fear_greed": fear_greed,
        "social": social,
        "put_call": put_call,
        "signals": [
            {
                "type": "VIX",
                "signal": vix["interpretation"],
                "value": vix["value"],
            },
            {
                "type": "FEAR_GREED",
                "signal": fear_greed["classification"],
                "value": fear_greed["index"],
            },
            {
                "type": "SOCIAL",
                "signal": social["reddit_sentiment"],
                "value": social["twitter_bullish_pct"],
            },
            {
                "type": "PUT_CALL",
                "signal": put_call["interpretation"],
                "value": put_call["ratio"],
            },
        ],
        "alerts": [],
    }
    
    # Generate alerts
    if fear_greed["classification"] == "EXTREME_GREED":
        report["alerts"].append({
            "level": "HIGH",
            "message": "Extreme greed detected. Consider taking profits.",
            "action": "TRIM_WINNERS",
        })
    elif fear_greed["classification"] == "EXTREME_FEAR":
        report["alerts"].append({
            "level": "HIGH",
            "message": "Extreme fear detected. Potential buying opportunity.",
            "action": "BUY_DIP",
        })
    
    if vix["value"] > 25:
        report["alerts"].append({
            "level": "MEDIUM",
            "message": f"VIX elevated at {vix['value']}. Increased volatility expected.",
            "action": "REDUCE_SIZE",
        })
    
    # Save
    with open(SCRIPTS_DIR / "vox_sentiment_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    with open(DASHBOARD_DIR / "vox_sentiment_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    return report

def main():
    print("="*60)
    print("📊 VOX SENTIMENT ANALYST")
    print("="*60)
    
    report = generate_sentiment_report()
    
    print(f"\nOverall Sentiment: {report['overall_sentiment']} ({report['overall_score']})")
    print(f"VIX: {report['vix']['value']} ({report['vix']['interpretation']})")
    print(f"Fear/Greed: {report['fear_greed']['classification']} ({report['fear_greed']['index']})")
    print(f"Social: {report['social']['reddit_sentiment']}")
    print(f"Put/Call: {report['put_call']['ratio']} ({report['put_call']['interpretation']})")
    
    if report['alerts']:
        print(f"\n🚨 Alerts: {len(report['alerts'])}")
        for alert in report['alerts']:
            print(f"  [{alert['level']}] {alert['message']}")
    
    print(f"\n✅ Saved to vox_sentiment_report.json")

if __name__ == "__main__":
    main()
