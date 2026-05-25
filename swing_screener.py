#!/usr/bin/env python3
"""
Swing Trading Screener — JOS-21
Top-down approach: Market → Sector → Industry → Stock
Uses Polygon.io free tier data.
"""

import os
import json
import time
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


def polygon_get(path, params=""):
    """Polygon.io API GET with rate limit handling."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {"error": "POLYGON_API_KEY not set"}

    url = f"https://api.polygon.io{path}?apiKey={api_key}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "details": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def get_daily_bars(ticker, days=50):
    """Get daily OHLCV bars."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    return result.get("results", [])


def calculate_ema(prices, period):
    """Calculate EMA."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_rsi(closes, period=14):
    """Calculate RSI."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calculate_adr(bars, period=14):
    """Average Daily Range %."""
    if len(bars) < period:
        return None
    ranges = []
    for bar in bars[-period:]:
        high, low = bar.get("h", 0), bar.get("l", 0)
        if low > 0:
            ranges.append((high - low) / low * 100)
    return sum(ranges) / len(ranges) if ranges else None


def screen_stock(ticker):
    """Screen a single stock against swing criteria."""
    bars = get_daily_bars(ticker, days=60)
    if len(bars) < 50:
        return None

    closes = [b["c"] for b in bars]
    volumes = [b["v"] for b in bars]
    current_price = closes[-1]

    # Criteria from your friend's video + your specs
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes)
    adr = calculate_adr(bars)
    avg_volume = sum(volumes[-20:]) / 20

    # Market cap check (simplified - would need ticker details)
    # For now, skip if price < $3
    if current_price < 3:
        return None

    # Score the setup
    score = 0
    reasons = []

    # Trend: Price > EMA21 > EMA50
    if current_price > ema21 > ema50:
        score += 3
        reasons.append("Price > EMA21 > EMA50")
    elif current_price > ema21:
        score += 1
        reasons.append("Price > EMA21")

    # RSI between 40-70 (not overbought, not oversold)
    if rsi and 40 <= rsi <= 70:
        score += 2
        reasons.append(f"RSI {rsi:.1f} in sweet spot")
    elif rsi and 30 <= rsi < 40:
        score += 1
        reasons.append(f"RSI {rsi:.1f} oversold bounce")

    # Volume > 500K average
    if avg_volume > 500000:
        score += 2
        reasons.append(f"Volume {avg_volume/1e6:.1f}M > 500K")

    # ADR > 2%
    if adr and adr > 2:
        score += 2
        reasons.append(f"ADR {adr:.1f}% > 2%")

    # Recent momentum (price above 20-day high * 0.98)
    high_20 = max(b["h"] for b in bars[-20:])
    if current_price > high_20 * 0.98:
        score += 1
        reasons.append("Near 20-day highs")

    return {
        "ticker": ticker,
        "price": current_price,
        "score": score,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi,
        "adr": adr,
        "avg_volume": avg_volume,
        "reasons": reasons,
        "setup_quality": "STRONG" if score >= 7 else "MODERATE" if score >= 5 else "WEAK",
    }


def run_screener(watchlist=None):
    """Run screener on watchlist or default list."""
    if watchlist is None:
        # Default watchlist — mix of sectors
        watchlist = [
            # Tech
            "AAPL", "MSFT", "GOOGL", "NVDA", "META", "AMD", "CRM", "ADBE",
            # Finance
            "JPM", "BAC", "GS", "MS", "BLK",
            # Energy
            "XOM", "CVX", "COP", "OXY",
            # Healthcare
            "JNJ", "PFE", "UNH", "LLY",
            # Consumer
            "AMZN", "TSLA", "HD", "NKE",
            # Meme/Momentum
            "PLTR", "GME", "AMC", "BB",
            # Mexican exposure
            "Cemex", "TV", "AMX",
            # AI/Memory plays you mentioned
            "WDC", "STX", "MU", "SNOW", "NET",
        ]

    print("=" * 80)
    print("📈 VOX SWING SCREENER")
    print("=" * 80)
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Stocks: {len(watchlist)}")
    print(f"Criteria: Price >$3 | EMA21/50 < Price | Volume >500K | ADR >2%")
    print()

    results = []
    for i, ticker in enumerate(watchlist, 1):
        print(f"Scanning {i}/{len(watchlist)}: {ticker}...", end=" ")
        try:
            result = screen_stock(ticker)
            if result and result["score"] >= 5:
                results.append(result)
                print(f"✅ Score: {result['score']}/10 — {result['setup_quality']}")
            elif result:
                print(f"⚪ Score: {result['score']}/10 — weak")
            else:
                print("❌ No data")
        except Exception as e:
            print(f"❌ Error: {e}")

        # Rate limit: 5 calls/minute on free tier
        time.sleep(12)

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)

    if not results:
        print("No strong setups found.")
        return []

    for r in results:
        emoji = "🟢" if r["setup_quality"] == "STRONG" else "🟡"
        print(f"\n{emoji} {r['ticker']} — ${r['price']:.2f} | Score: {r['score']}/10")
        print(f"   EMA21: ${r['ema21']:.2f} | EMA50: ${r['ema50']:.2f} | RSI: {r['rsi']:.1f}")
        print(f"   ADR: {r['adr']:.1f}% | Volume: {r['avg_volume']/1e6:.1f}M")
        print(f"   Reasons: {', '.join(r['reasons'])}")

    # Save results
    out_path = Path.home() / ".hermes" / "scripts" / "screener_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "scan_time": datetime.now().isoformat(),
            "stocks_scanned": len(watchlist),
            "strong_setups": len([r for r in results if r["setup_quality"] == "STRONG"]),
            "results": results,
        }, f, indent=2)

    print(f"\n💾 Saved to: {out_path}")
    return results


def main():
    import sys
    if len(sys.argv) > 1:
        # Screen specific tickers
        tickers = [t.upper() for t in sys.argv[1:]]
        run_screener(tickers)
    else:
        run_screener()


if __name__ == "__main__":
    main()
