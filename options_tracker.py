#!/usr/bin/env python3
"""
Options Tracker — JOS-8 / JOS-20
Tracks options positions using free data sources:
- Polygon.io (free tier): contract reference, daily bars
- Yahoo Finance (scraping): basic options chains, premiums
- Manual input: Greeks, position sizing

Does NOT require paid Polygon options plan.
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


def polygon_request(endpoint):
    """Make request to Polygon API with rate limiting."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY")
    if not api_key:
        return None

    url = f"https://api.polygon.io{endpoint}{'&' if '?' in endpoint else '?'}apiKey={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("   ⚠️ Rate limited — wait 60s between Polygon calls")
        return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def get_options_contracts(underlying_ticker, expiration_gte=None, limit=50):
    """Fetch available options contracts for a ticker (FREE TIER)."""
    if not expiration_gte:
        expiration_gte = datetime.now().strftime("%Y-%m-%d")

    endpoint = f"/v3/reference/options/contracts?underlying_ticker={underlying_ticker}&expiration_date.gte={expiration_gte}&limit={limit}"
    data = polygon_request(endpoint)

    if not data:
        return []

    results = data.get("results", [])
    contracts = []
    for r in results:
        contracts.append({
            "ticker": r.get("ticker"),
            "strike": r.get("strike_price"),
            "type": r.get("contract_type"),  # call or put
            "expiration": r.get("expiration_date"),
            "shares_per_contract": r.get("shares_per_contract", 100),
            "exercise_style": r.get("exercise_style", "american"),
        })

    return contracts


def get_stock_bars(ticker, days=30):
    """Fetch daily price bars for technical analysis (FREE TIER)."""
    end = datetime.now()
    start = end - timedelta(days=days)

    endpoint = f"/v2/aggs/ticker/{ticker}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    data = polygon_request(endpoint)

    if not data:
        return []

    bars = []
    for r in data.get("results", []):
        bars.append({
            "date": datetime.fromtimestamp(r["t"] / 1000).strftime("%Y-%m-%d"),
            "open": r["o"],
            "high": r["h"],
            "low": r["l"],
            "close": r["c"],
            "volume": r["v"],
            "vwap": r.get("vw"),
        })

    return bars


def get_ticker_details(ticker):
    """Fetch ticker details including market cap (FREE TIER)."""
    endpoint = f"/v3/reference/tickers/{ticker}"
    data = polygon_request(endpoint)

    if not data or "results" not in data:
        return {}

    r = data["results"]
    return {
        "name": r.get("name"),
        "market_cap": r.get("market_cap"),
        "shares_outstanding": r.get("share_class_shares_outstanding"),
        "sector": r.get("sic_description"),
        "locale": r.get("locale"),
    }


def calculate_ema(prices, period):
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return None

    multiplier = 2 / (period + 1)
    ema = prices[0]

    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema

    return ema


def calculate_adtr(bars, period=14):
    """Calculate Average Daily True Range."""
    if len(bars) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i]["high"]
        low = bars[i]["low"]
        prev_close = bars[i - 1]["close"]

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)

        true_ranges.append(max(tr1, tr2, tr3))

    # Simple average of last N true ranges
    recent_tr = true_ranges[-period:]
    return sum(recent_tr) / len(recent_tr)


def calculate_adr(bars, period=14):
    """Calculate Average Daily Range (high - low) as % of price."""
    if len(bars) < period:
        return None

    ranges = []
    for bar in bars[-period:]:
        daily_range = bar["high"] - bar["low"]
        range_pct = (daily_range / bar["close"]) * 100
        ranges.append(range_pct)

    return sum(ranges) / len(ranges)


def screen_for_options_plays(tickers):
    """Screen stocks for potential options plays using free data."""
    print("=" * 70)
    print("OPTIONS PLAY SCREENER")
    print("=" * 70)
    print(f"{'Ticker':<8} {'Price':>8} {'EMA21':>8} {'EMA50':>8} {'ADR%':>6} {'Vol(K)':>8} {'Setup':<20}")
    print("-" * 70)

    candidates = []

    for ticker in tickers:
        # Get bars
        bars = get_stock_bars(ticker, days=60)
        if not bars or len(bars) < 50:
            continue

        closes = [b["close"] for b in bars]
        latest = bars[-1]
        price = latest["close"]
        volume = latest["volume"]

        # Calculate EMAs
        ema21 = calculate_ema(closes, 21)
        ema50 = calculate_ema(closes, 50)

        # Calculate ADR
        adr = calculate_adr(bars, 14)

        # Check criteria
        above_ema21 = price > ema21 if ema21 else False
        above_ema50 = price > ema50 if ema50 else False
        adr_ok = adr > 2.0 if adr else False
        volume_ok = volume > 500000
        price_ok = price > 3.0

        # Determine setup
        setup = ""
        if above_ema21 and above_ema50 and adr_ok and volume_ok and price_ok:
            # Check for bull flag (recent high volume move + consolidation)
            recent_volume = sum(b["volume"] for b in bars[-5:]) / 5
            avg_volume = sum(b["volume"] for b in bars[-20:]) / 20

            if recent_volume > avg_volume * 1.5:
                setup = "🔥 Momentum + Flag"
            else:
                setup = "✅ Trending"

            candidates.append({
                "ticker": ticker,
                "price": price,
                "ema21": ema21,
                "ema50": ema50,
                "adr": adr,
                "volume": volume,
                "setup": setup,
            })
        else:
            reasons = []
            if not above_ema21:
                reasons.append("below 21EMA")
            if not above_ema50:
                reasons.append("below 50EMA")
            if not adr_ok:
                reasons.append("low ADR")
            if not volume_ok:
                reasons.append("low vol")
            if not price_ok:
                reasons.append("price<3")
            setup = f"❌ {', '.join(reasons[:2])}"

        print(f"{ticker:<8} ${price:>7.2f} ${ema21:>7.2f} ${ema50:>7.2f} {adr:>5.2f}% {volume/1000:>7.0f}K {setup:<20}")

    print("-" * 70)
    print(f"Found {len(candidates)} candidates")
    return candidates


def get_available_options(underlying_ticker, min_dte=7, max_dte=45):
    """Get available options contracts filtered by DTE range."""
    today = datetime.now()
    min_exp = (today + timedelta(days=min_dte)).strftime("%Y-%m-%d")
    max_exp = (today + timedelta(days=max_dte)).strftime("%Y-%m-%d")

    contracts = get_options_contracts(underlying_ticker, expiration_gte=min_exp, limit=100)

    # Filter by max expiration
    filtered = [c for c in contracts if c["expiration"] <= max_exp]

    # Group by expiration
    by_expiration = {}
    for c in filtered:
        exp = c["expiration"]
        if exp not in by_expiration:
            by_expiration[exp] = []
        by_expiration[exp].append(c)

    return by_expiration


def suggest_options_strategy(underlying_ticker, current_price, outlook="bullish"):
    """Suggest simple options strategies based on outlook."""
    print(f"\n{'='*70}")
    print(f"OPTIONS STRATEGY SUGGESTIONS: {underlying_ticker} @ ${current_price:.2f}")
    print(f"{'='*70}")

    # Get available options
    options = get_available_options(underlying_ticker)

    if not options:
        print("No options found")
        return

    # Show nearest expiration
    nearest_exp = min(options.keys())
    nearest_contracts = options[nearest_exp]

    print(f"\nNearest expiration: {nearest_exp} ({(datetime.strptime(nearest_exp, '%Y-%m-%d') - datetime.now()).days} DTE)")

    # Find ATM strikes
    calls = [c for c in nearest_contracts if c["type"] == "call"]
    puts = [c for c in nearest_contracts if c["type"] == "put"]

    calls.sort(key=lambda x: abs(x["strike"] - current_price))
    puts.sort(key=lambda x: abs(x["strike"] - current_price))

    if outlook == "bullish":
        print("\n📈 BULLISH STRATEGIES:")
        print("\n1. Long Call (ATM):")
        if calls:
            atm_call = calls[0]
            print(f"   Buy {atm_call['ticker']}")
            print(f"   Strike: ${atm_call['strike']}")
            print(f"   Exp: {atm_call['expiration']}")
            print(f"   Max Risk: Premium paid (unknown without quotes)")
            print(f"   Max Reward: Unlimited")

        print("\n2. Bull Call Spread:")
        if len(calls) >= 2:
            buy_call = calls[0]
            sell_call = calls[3] if len(calls) > 3 else calls[-1]
            print(f"   Buy  {buy_call['ticker']} @ ${buy_call['strike']}")
            print(f"   Sell {sell_call['ticker']} @ ${sell_call['strike']}")
            print(f"   Max Profit: ${sell_call['strike'] - buy_call['strike']} - net premium")
            print(f"   Max Risk: Net premium paid")

    elif outlook == "bearish":
        print("\n📉 BEARISH STRATEGIES:")
        print("\n1. Long Put (ATM):")
        if puts:
            atm_put = puts[0]
            print(f"   Buy {atm_put['ticker']}")
            print(f"   Strike: ${atm_put['strike']}")

    print("\n⚠️  NOTE: Greeks and premiums require real-time quotes.")
    print("   Use your broker platform for exact pricing before trading.")


def main():
    print("Vox Options Tracker")
    print("=" * 70)

    # Test with watchlist
    watchlist = ["AAPL", "NVDA", "CEG", "VST", "RKLB", "TSLA", "PLTR", "AMD"]

    # Screen for options plays
    candidates = screen_for_options_plays(watchlist)

    # Show available options for top candidates
    if candidates:
        print(f"\n{'='*70}")
        print("AVAILABLE OPTIONS FOR TOP CANDIDATES")
        print(f"{'='*70}")

        for c in candidates[:3]:
            ticker = c["ticker"]
            price = c["price"]

            # Get options
            options = get_available_options(ticker, min_dte=7, max_dte=30)

            if options:
                print(f"\n{ticker} @ ${price:.2f}:")
                for exp, contracts in sorted(options.items())[:2]:
                    calls = len([x for x in contracts if x["type"] == "call"])
                    puts = len([x for x in contracts if x["type"] == "put"])
                    dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                    print(f"   {exp} ({dte} DTE): {calls} calls, {puts} puts")

    # Save results
    output = {
        "date": datetime.now().isoformat(),
        "candidates": candidates,
    }
    out_path = Path.home() / ".hermes" / "scripts" / "options_screen_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Results saved to: {out_path}")


if __name__ == "__main__":
    main()
