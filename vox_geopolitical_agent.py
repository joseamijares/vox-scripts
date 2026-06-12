#!/usr/bin/env python3
"""
VOX Geopolitical Risk Agent
Monitors: War, sanctions, trade disputes, shipping disruptions, nuclear threats
Sources: Free news RSS feeds, web scraping
Impacts: Energy (XOM, CVX), Defense (RTX, LMT), Shipping, Emerging markets
"""

import json, urllib.request, re
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Portfolio tickers sensitive to geopolitical risk
GEOPOL_SENSITIVE = {
    "XOM": "oil", "CVX": "oil", "COP": "oil", "OXY": "oil",
    "RTX": "defense", "LMT": "defense", "NOC": "defense", "GD": "defense",
    "CEG": "nuclear", "CCJ": "uranium", "URA": "uranium",
    "BABA": "china", "PDD": "china", "TSM": "taiwan", "JD": "china",
    "COIN": "crypto_regulation", "MSTR": "crypto_regulation",
    "GLD": "gold_safe_haven", "SLV": "silver_safe_haven",
    "UNG": "natgas_europe", "LNG": "lng_shipping",
    "ZIM": "shipping", "MATX": "shipping", "DAC": "shipping",
}

# Risk keywords mapped to severity
RISK_KEYWORDS = {
    "CRITICAL": [
        "nuclear strike", "nuclear attack", "invasion", "war declared",
        "embargo", "blockade", "strait of hormuz closed", "taiwan blockade",
        "article 5", "mutual defense", "chemical weapons", "biological weapons"
    ],
    "HIGH": [
        "airstrike", "missile attack", "sanctions", "trade war", "tariff",
        "evacuation", "embassy closed", "military exercise", "drill",
        "iran", "russia", "china", "taiwan", "ukraine", "israel", "gaza",
        "houthi", "red sea", "suez canal", "strait of hormuz"
    ],
    "MEDIUM": [
        "tension", "escalation", "provocation", "diplomatic crisis",
        "protest", "unrest", "coup", "election dispute", "border clash"
    ]
}

# Free RSS feeds for geopolitical news
RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/hotnews",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL=F,GC=F,NG=F",
]

def fetch_rss(url):
    """Fetch and parse RSS feed."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            root = ET.fromstring(content)
            items = []
            for item in root.findall(".//item")[:10]:
                title = item.find("title")
                desc = item.find("description")
                pub = item.find("pubDate")
                items.append({
                    "title": title.text if title is not None else "",
                    "description": desc.text if desc is not None else "",
                    "published": pub.text if pub is not None else ""
                })
            return items
    except Exception as e:
        return []

def score_geopolitical_risk(headline):
    """Score headline for geopolitical risk."""
    text = headline.lower()
    score = 0
    matched_keywords = []
    
    for level, keywords in RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                if level == "CRITICAL":
                    score += 50
                elif level == "HIGH":
                    score += 20
                else:
                    score += 10
                matched_keywords.append(kw)
    
    # Check for portfolio ticker mentions
    affected = []
    for ticker, sector in GEOPOL_SENSITIVE.items():
        if ticker.lower() in text or sector in text:
            score += 15
            affected.append(ticker)
    
    return min(100, score), list(set(matched_keywords)), list(set(affected))

def run_geopolitical_agent():
    """Main geopolitical tracking loop."""
    all_headlines = []
    
    for feed in RSS_FEEDS:
        items = fetch_rss(feed)
        all_headlines.extend(items)
    
    # Score and filter
    alerts = []
    for item in all_headlines:
        text = item["title"] + " " + item.get("description", "")
        score, keywords, affected = score_geopolitical_risk(text)
        
        if score >= 30:  # Only keep significant risks
            alerts.append({
                "headline": item["title"],
                "score": score,
                "keywords": keywords,
                "affected_tickers": affected,
                "published": item.get("published", ""),
                "priority": "CRITICAL" if score >= 70 else "HIGH" if score >= 50 else "MEDIUM"
            })
    
    # Sort by score
    alerts.sort(key=lambda x: x["score"], reverse=True)
    
    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "headlines_checked": len(all_headlines),
        "alerts": alerts[:10],
        "critical_count": len([a for a in alerts if a["priority"] == "CRITICAL"]),
        "high_count": len([a for a in alerts if a["priority"] == "HIGH"])
    }
    
    with open(SCRIPT_DIR / "vox_geopolitical_analysis.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Only print if there are alerts
    if alerts:
        critical = [a for a in alerts if a["priority"] == "CRITICAL"]
        high = [a for a in alerts if a["priority"] == "HIGH"]
        
        if critical:
            print(f"🌍 GEOPOL CRITICAL — {len(critical)} alerts")
            for a in critical[:3]:
                print(f"   🚨 {a['headline'][:80]}...")
                if a['affected_tickers']:
                    print(f"      Tickers: {', '.join(a['affected_tickers'])}")
        
        if high and not critical:
            print(f"🌍 GEOPOL HIGH — {len(high)} alerts")
            for a in high[:3]:
                print(f"   ⚠️ {a['headline'][:80]}...")
                if a['affected_tickers']:
                    print(f"      Tickers: {', '.join(a['affected_tickers'])}")
    
    return output

if __name__ == "__main__":
    run_geopolitical_agent()
