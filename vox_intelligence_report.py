#!/usr/bin/env python3
"""
VOX Intelligence Report
Aggregates volume, X, Reddit, news, sentiment, and Trump data
into a single cross-signal dashboard for portfolio positions.
"""

import json
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_json(filename):
    path = SCRIPT_DIR / filename
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def main():
    # Load all data sources
    x = load_json("snapshots/x_momentum_latest.json")
    live = load_json("dashboard_positions_live.json")
    reddit = load_json("vox_reddit_report.json")
    vol = load_json("vox_volume_scan.json")
    trump = load_json("trump_tracker_results.json")
    sentiment = load_json("vox_sentiment_report.json")

    portfolio_tickers = {p.get("ticker", "") for p in live.get("positions", [])}
    positions = {p["ticker"]: p for p in live.get("positions", [])}

    print("=" * 60)
    print("VOX INTELLIGENCE DASHBOARD")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}")
    print("=" * 60)

    # MARKET SENTIMENT
    print("\n📊 MARKET SENTIMENT")
    print("-" * 50)
    if sentiment:
        print(f"  VIX: {sentiment['vix']['value']} ({sentiment['vix']['interpretation']})")
        print(f"  Fear & Greed: {sentiment['fear_greed']['index']:.1f} ({sentiment['fear_greed']['classification']})")
        print(f"  Put/Call: {sentiment['put_call']['ratio']:.2f} ({sentiment['put_call']['interpretation']})")
        print(f"  X/Twitter: {sentiment['social']['twitter_bullish_pct']}% bullish")
        print(f"  Reddit: {sentiment['social']['reddit_sentiment']} ({sentiment['social']['reddit_mentions']} mentions)")
        print(f"  Overall: {sentiment['overall_sentiment']}")

    # X MOMENTUM (Portfolio overlap)
    print("\n🐦 X MOMENTUM — Portfolio Overlap")
    print("-" * 50)
    x_results = x.get("results", [])
    x_portfolio = [r for r in x_results if r["ticker"] in portfolio_tickers]
    print(f"Tracked: {len(x_results)} total | {len(x_portfolio)} in portfolio")
    for r in x_portfolio:
        t = r["ticker"]
        pos = positions.get(t, {})
        price = pos.get("live_price", 0)
        change = pos.get("price_change_pct", 0)
        bull = "BULLISH" in r["sentiment"]
        emoji = "🟢" if bull else "🔴"
        print(f"  {emoji} {t:6s} | {r['mentions']:3d} mentions | {r['sentiment']} | ${price:.2f} ({change:+.2f}%)")

    # REDDIT (Portfolio overlap)
    print("\n👽 REDDIT — Portfolio Overlap")
    print("-" * 50)
    noise = {"AI", "US", "IP", "EU", "OTC", "FAQ", "ATM", "DR", "TL", "CS", "MBA", "BS", "SCS", "LEO", "WSB", "FCC", "ARPU", "EOY", "CNBC", "DA", "EV", "CON", "TLDR", "AWS", "JV", "MNO", "YES", "FAA", "LOL", "AST", "AMT", "OP", "BBC", "CLI", "IN", "JUST", "ME", "VZ", "TMUS", "DUMP", "PUMP", "NEXT", "HAVE", "CASH", "SOLD", "YET", "THEN", "TODAY", "USD", "TAM", "TTM", "SEC", "LLM", "FDA"}
    reddit_mentions = {}
    for sub, data in reddit.get("subreddits", {}).items():
        for ticker, count in data.get("ticker_mentions", {}).items():
            if ticker in portfolio_tickers and ticker not in noise:
                reddit_mentions[ticker] = reddit_mentions.get(ticker, 0) + count

    reddit_sorted = sorted(reddit_mentions.items(), key=lambda x: x[1], reverse=True)[:10]
    for t, c in reddit_sorted:
        pos = positions.get(t, {})
        price = pos.get("live_price", 0)
        change = pos.get("price_change_pct", 0)
        print(f"  {t:6s} | {c:3d} mentions | ${price:.2f} ({change:+.2f}%)")

    # VOLUME
    print("\n📈 VOLUME — Portfolio")
    print("-" * 50)
    vol_results = vol.get("results", [])
    vol_portfolio = [r for r in vol_results if r["ticker"] in portfolio_tickers]
    vol_sorted = sorted(vol_portfolio, key=lambda x: x.get("volume_ratio", 0), reverse=True)[:10]
    for r in vol_sorted:
        t = r["ticker"]
        ratio = r.get("volume_ratio", 0)
        change = r.get("price_change_pct", 0)
        alert = r.get("alert", "NONE")
        flag = "⚠️ " if alert != "NONE" else "  "
        print(f"{flag}{t:6s} | Vol: {ratio:.2f}x avg | {change:+.2f}% | {alert}")

    # TRUMP
    print("\n🇺🇸 TRUMP TRACKER")
    print("-" * 50)
    high_impact = [t for t in trump.get("tweets", []) if t.get("classification", {}).get("impact_score", 0) >= 8]
    print(f"Tweets: {trump.get('tweets_found', 0)} | High impact: {len(high_impact)}")
    if high_impact:
        for t in high_impact:
            impact = t["classification"]["impact_score"]
            text = t["text"][:60]
            print(f"  [{impact}/10] {text}...")
    else:
        print("  No high-impact tweets today")

    # CROSS-SIGNAL ANALYSIS
    print("\n🔥 CROSS-SIGNAL ALERTS")
    print("-" * 50)
    multi_signal = {}
    
    for r in x_results:
        t = r["ticker"]
        if t in portfolio_tickers:
            sig = "X_BULLISH" if "Bull" in r["sentiment"] else "X_BEARISH"
            multi_signal[t] = multi_signal.get(t, []) + [sig]
    
    for t, c in reddit_mentions.items():
        if c >= 3:
            multi_signal[t] = multi_signal.get(t, []) + ["REDDIT_HOT"]
    
    for r in vol_sorted:
        if r.get("volume_ratio", 0) > 1.5:
            t = r["ticker"]
            multi_signal[t] = multi_signal.get(t, []) + ["HIGH_VOLUME"]
    
    found = False
    for t, signals in sorted(multi_signal.items(), key=lambda x: len(x[1]), reverse=True):
        if len(signals) >= 2:
            found = True
            pos = positions.get(t, {})
            price = pos.get("live_price", 0)
            change = pos.get("price_change_pct", 0)
            value = pos.get("live_value", 0)
            sig_str = ", ".join(signals)
            print(f"  {t:6s} | {sig_str} | ${price:.2f} ({change:+.2f}%) | ${value:,.0f}")
    
    if not found:
        print("  No multi-signal alerts today")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
