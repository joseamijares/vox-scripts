#!/usr/bin/env python3
"""
Trump / Policy Tweet Tracker — JOS-9
Tracks @realDonaldTrump tweets and classifies by market impact.
Uses X API v2 Bearer Token auth.
"""

import os
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta


def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    keys[key] = val
    return keys


def search_x_recent(query, max_results=10):
    """Search X API v2 for recent tweets."""
    env = load_env()
    bearer = env.get("X_BEARER_TOKEN", "")

    if not bearer:
        return {"error": "X_BEARER_TOKEN not set"}

    # URL encode query
    encoded_query = query.replace(" ", "%20").replace("#", "%23")
    url = f"https://api.twitter.com/2/tweets/search/recent?query={encoded_query}&max_results={max_results}&tweet.fields=created_at,public_metrics,author_id,context_annotations"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {bearer}",
        "User-Agent": "Vox-Finance/1.0"
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "details": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def classify_tweet(text):
    """Classify tweet by topic and market impact."""
    text_lower = text.lower()

    # Topic classification
    topics = []
    topic_keywords = {
        "tariffs": ["tariff", "tariffs", "trade war", "import tax", "duty"],
        "fed": ["fed", "federal reserve", "interest rate", "rates", "jerome powell", "powell"],
        "crypto": ["bitcoin", "btc", "crypto", "cryptocurrency", "blockchain", "digital asset"],
        "tech": ["ai", "artificial intelligence", "big tech", "silicon valley", "regulation"],
        "energy": ["oil", "gas", "energy", "drill", "opec", "pipeline"],
        "china": ["china", "chinese", "beijing", "xi"],
        "mexico": ["mexico", "mexican", "amlo", "border"],
        "defense": ["military", "defense", "war", "nato", "pentagon"],
        "inflation": ["inflation", "cpi", "prices", "cost of living"],
        "taxes": ["tax", "taxes", "tax cut", "tax reform"],
    }

    for topic, keywords in topic_keywords.items():
        if any(kw in text_lower for kw in keywords):
            topics.append(topic)

    # Market impact scoring
    impact_score = 0
    impact_keywords = {
        "high": ["emergency", "crisis", "war", "sanctions", "ban", "tariff", "major", "huge", "massive"],
        "medium": ["new", "plan", "policy", "announce", "sign", "order", "deal"],
        "low": ["thank", "great", "beautiful", "congratulations", "happy"],
    }

    for level, keywords in impact_keywords.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if level == "high":
            impact_score += count * 3
        elif level == "medium":
            impact_score += count * 1
        elif level == "low":
            impact_score -= count * 1

    # Cap score
    impact_score = max(0, min(10, impact_score))

    # Determine impact level
    if impact_score >= 7:
        impact_level = "🔴 HIGH"
    elif impact_score >= 4:
        impact_level = "🟡 MEDIUM"
    else:
        impact_level = "🟢 LOW"

    return {
        "topics": topics if topics else ["general"],
        "impact_score": impact_score,
        "impact_level": impact_level,
    }


def sector_impact(topics):
    """Map topics to affected sectors/tickers."""
    sector_map = {
        "tariffs": ["Manufacturing", "Retail", "Materials", "XLI", "XRT"],
        "china": ["Tech", "Manufacturing", "AAPL", "NVDA", "TSLA", "FXI"],
        "mexico": ["Auto", "Agriculture", "USMCA", "GM", "F"],
        "crypto": ["BTC", "COIN", "MSTR", "Crypto ETFs"],
        "fed": ["Banks", "REITs", "XLF", "VNQ", "TLT"],
        "energy": ["XLE", "XOM", "CVX", "OXY"],
        "defense": ["LMT", "NOC", "RTX", "GD"],
        "inflation": ["Gold", "GLD", "Commodities", "DBC"],
        "tech": ["QQQ", "XLK", "NVDA", "MSFT", "GOOGL"],
        "taxes": ["Small Caps", "IWM", "Consumer Discretionary", "XLY"],
    }

    affected = set()
    for topic in topics:
        if topic in sector_map:
            affected.update(sector_map[topic])

    return list(affected)


def get_portfolio_tickers():
    """Load portfolio tickers from dashboard_positions.json."""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    tickers = set()
    if positions_file.exists():
        try:
            with open(positions_file) as f:
                data = json.load(f)
                # Handle both list and dict formats
                if isinstance(data, list):
                    positions = data
                elif isinstance(data, dict):
                    positions = data.get("positions", [])
                else:
                    positions = []
                for p in positions:
                    tickers.add(p.get("ticker", ""))
        except Exception as e:
            print(f"Warning: Could not load positions: {e}")
    return tickers


def generate_action_plan(tweet, portfolio_tickers):
    """Generate actionable plan based on tweet impact and portfolio overlap."""
    topics = tweet["classification"]["topics"]
    affected_sectors = tweet["affected_sectors"]
    impact_score = tweet["classification"]["impact_score"]
    
    # Find portfolio positions affected
    affected_positions = []
    sector_to_tickers = {
        "tariffs": ["AAPL", "NVDA", "TSLA", "AMD", "AVGO", "TSM", "WMT", "COST"],
        "china": ["AAPL", "NVDA", "TSLA", "AMD", "AVGO", "TSM", "BIDU", "0700.HK"],
        "mexico": ["GM", "F", "WMT", "COST"],
        "crypto": ["BTC", "ETH", "COIN", "ADA", "HBAR", "SOL", "XRP", "DOGE", "TRX", "BNB"],
        "fed": ["XLF", "VNQ", "TLT", "BIVI", "VOO", "VTI", "QQQ"],
        "energy": ["XLE", "CEG", "OKLO"],
        "defense": ["LMT", "NOC", "RTX", "GD"],
        "inflation": ["GLD", "BTC", "ETH"],
        "tech": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD", "AVGO", "TSM", "PLTR", "CRWD", "SNOW", "DDOG", "SHOP", "DASH", "SPOT", "APH"],
        "taxes": ["IWM", "XLY", "VOO", "VTI"],
    }
    
    # Map affected sectors to tickers
    at_risk_tickers = set()
    for topic in topics:
        if topic in sector_to_tickers:
            at_risk_tickers.update(sector_to_tickers[topic])
    
    # Check overlap with portfolio
    portfolio_overlap = at_risk_tickers & portfolio_tickers
    
    # Generate action items
    actions = []
    
    if impact_score >= 8:
        if portfolio_overlap:
            actions.append(f"🔴 URGENT: Review positions — {', '.join(sorted(portfolio_overlap))}")
            actions.append("→ Check stops on affected positions")
            actions.append("→ Consider trimming if thesis compromised")
        else:
            actions.append("🟡 MONITOR: No direct portfolio exposure")
            actions.append("→ Watch for sector contagion")
            
        # Add specific plays based on topic
        if "tariffs" in topics:
            actions.append("→ Short XLI (industrials) or buy GLD (hedge)")
        elif "china" in topics:
            actions.append("→ Trim AAPL/NVDA/TSM if held, watch for supply chain impact")
        elif "crypto" in topics:
            actions.append("→ BTC/ETH volatile — tighten stops, consider taking profits")
        elif "fed" in topics:
            actions.append("→ Rate sensitive: check REITs, banks, utilities")
        elif "energy" in topics:
            actions.append("→ XLE momentum play if policy bullish")
    elif impact_score >= 5:
        if portfolio_overlap:
            actions.append(f"🟡 WATCH: {', '.join(sorted(portfolio_overlap))} may be affected")
            actions.append("→ Set price alerts on these positions")
        else:
            actions.append("🟢 No action needed — no portfolio overlap")
    else:
        actions.append("🟢 Low impact — no action required")
    
    return {
        "portfolio_overlap": sorted(portfolio_overlap),
        "actions": actions,
        "risk_level": "HIGH" if impact_score >= 8 else "MEDIUM" if impact_score >= 5 else "LOW"
    }


def track_trump_tweets():
    """Main tracker function."""
    print("=" * 70)
    print("🦅 TRUMP / POLICY TWEET TRACKER")
    print("=" * 70)
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load portfolio
    portfolio_tickers = get_portfolio_tickers()
    print(f"Portfolio: {len(portfolio_tickers)} tickers tracked")
    print()

    # Search for Trump tweets
    queries = [
        "from:realDonaldTrump",
        "from:POTUS",
    ]

    all_tweets = []
    for query in queries:
        result = search_x_recent(query, max_results=10)
        if "error" in result:
            print(f"❌ Query '{query}': {result['error']}")
            continue

        tweets = result.get("data", [])
        print(f"✅ Query '{query}': {len(tweets)} tweets found")
        all_tweets.extend(tweets)

    if not all_tweets:
        print("\n⚠️ No tweets found. Check X_BEARER_TOKEN or rate limits.")
        return []

    # Process tweets
    print(f"\n{'='*70}")
    print("TWEET ANALYSIS")
    print(f"{'='*70}")

    processed = []
    for tweet in all_tweets:
        text = tweet.get("text", "")
        tweet_id = tweet.get("id", "")
        created_at = tweet.get("created_at", "")
        metrics = tweet.get("public_metrics", {})

        # Classify
        classification = classify_tweet(text)
        affected_sectors = sector_impact(classification["topics"])
        
        # Generate action plan
        action_plan = generate_action_plan(
            {"classification": classification, "affected_sectors": affected_sectors},
            portfolio_tickers
        )

        # Build result
        result = {
            "id": tweet_id,
            "text": text,
            "created_at": created_at,
            "url": f"https://x.com/i/web/status/{tweet_id}",
            "metrics": metrics,
            "classification": classification,
            "affected_sectors": affected_sectors,
            "action_plan": action_plan,
        }
        processed.append(result)

        # Display
        print(f"\n📝 Tweet ({created_at[:10]}):")
        print(f"   {text[:120]}{'...' if len(text) > 120 else ''}")
        print(f"   Topics: {', '.join(classification['topics'])}")
        print(f"   Impact: {classification['impact_level']} (score: {classification['impact_score']}/10)")
        if affected_sectors:
            print(f"   Sectors: {', '.join(affected_sectors)}")
        if action_plan["portfolio_overlap"]:
            print(f"   🔴 PORTFOLIO OVERLAP: {', '.join(action_plan['portfolio_overlap'])}")
        print(f"   ❤️ {metrics.get('like_count', 0)}  🔁 {metrics.get('retweet_count', 0)}  💬 {metrics.get('reply_count', 0)}")

    # High impact alerts with action plans
    high_impact = [t for t in processed if t["classification"]["impact_score"] >= 7]
    if high_impact:
        print(f"\n{'='*70}")
        print("🔴 HIGH IMPACT ALERTS — ACTION REQUIRED")
        print(f"{'='*70}")
        for t in high_impact:
            print(f"\n⚠️ HIGH IMPACT:")
            print(f"   {t['text'][:150]}{'...' if len(t['text']) > 150 else ''}")
            print(f"   Sectors affected: {', '.join(t['affected_sectors'])}")
            print(f"   URL: {t['url']}")
            print(f"\n   📋 ACTION PLAN:")
            for action in t['action_plan']['actions']:
                print(f"      {action}")

    # Save results
    output = {
        "scan_time": datetime.now().isoformat(),
        "tweets_found": len(all_tweets),
        "tweets": processed,
        "high_impact_count": len(high_impact),
    }

    out_path = Path.home() / ".hermes" / "scripts" / "trump_tracker_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Results saved to: {out_path}")

    return processed


def main():
    track_trump_tweets()


if __name__ == "__main__":
    main()
