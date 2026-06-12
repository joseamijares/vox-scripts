#!/usr/bin/env python3
"""
VOX Technical Analyst Agent
Analyzes charts, patterns, volume, support/resistance.
Reads Polygon technical data. Outputs BULLISH/BEARISH/NEUTRAL with conviction.

Usage:
    python3 technical_analyst.py analyze --ticker TSLA
    python3 technical_analyst.py analyze --ticker NVDA --full
    python3 technical_analyst.py batch --file portfolio_tickers.json
"""

import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Load API key
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

ENV = load_env()
POLYGON_KEY = ENV.get("POLYGON_API_KEY", "")

def polygon_get(path, params=""):
    """Make Polygon API request"""
    if not POLYGON_KEY:
        return {"error": "POLYGON_API_KEY not set"}
    url = f"https://api.polygon.io{path}?apiKey={POLYGON_KEY}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def get_daily_bars(ticker: str, days: int = 60) -> List[Dict]:
    """Get daily price bars"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        return []
    return result.get("results", [])

def calculate_ema(prices: List[float], period: int) -> float:
    """Calculate EMA"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI"""
    if len(prices) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_volume_trend(bars: List[Dict]) -> Dict:
    """Analyze volume trend"""
    if len(bars) < 20:
        return {"trend": "neutral", "ratio": 1.0}
    
    recent_vol = sum(b["v"] for b in bars[-5:]) / 5
    avg_vol = sum(b["v"] for b in bars[-20:]) / 20
    
    ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
    
    if ratio > 2.0:
        trend = "spike"
    elif ratio > 1.5:
        trend = "high"
    elif ratio < 0.5:
        trend = "low"
    else:
        trend = "normal"
    
    return {"trend": trend, "ratio": ratio}

def find_support_resistance(bars: List[Dict], lookback: int = 20) -> Dict:
    """Find support and resistance levels"""
    if len(bars) < lookback:
        return {"support": 0, "resistance": 0}
    
    recent = bars[-lookback:]
    highs = [b["h"] for b in recent]
    lows = [b["l"] for b in recent]
    
    # Simple: use recent high/low
    resistance = max(highs)
    support = min(lows)
    
    return {
        "support": support,
        "resistance": resistance,
        "range_pct": (resistance - support) / support * 100 if support > 0 else 0
    }

def analyze_trend(bars: List[Dict]) -> Dict:
    """Analyze price trend"""
    if len(bars) < 20:
        return {"trend": "neutral", "strength": 0}
    
    closes = [b["c"] for b in bars]
    
    # EMAs
    ema_9 = calculate_ema(closes, 9)
    ema_21 = calculate_ema(closes, 21)
    ema_50 = calculate_ema(closes, 50)
    
    current_price = closes[-1]
    
    # Trend direction
    if ema_9 > ema_21 > ema_50:
        trend = "strong_bullish"
        strength = 3
    elif ema_9 > ema_21:
        trend = "bullish"
        strength = 2
    elif ema_9 < ema_21 < ema_50:
        trend = "strong_bearish"
        strength = -3
    elif ema_9 < ema_21:
        trend = "bearish"
        strength = -2
    else:
        trend = "neutral"
        strength = 0
    
    # Price vs EMAs
    above_ema9 = current_price > ema_9
    above_ema21 = current_price > ema_21
    above_ema50 = current_price > ema_50
    
    return {
        "trend": trend,
        "strength": strength,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "ema_50": ema_50,
        "above_ema9": above_ema9,
        "above_ema21": above_ema21,
        "above_ema50": above_ema50,
    }

def analyze_momentum(bars: List[Dict]) -> Dict:
    """Analyze momentum indicators"""
    if len(bars) < 14:
        return {"rsi": 50, "momentum": "neutral"}
    
    closes = [b["c"] for b in bars]
    rsi = calculate_rsi(closes)
    
    # RSI interpretation
    if rsi > 70:
        momentum = "overbought"
    elif rsi > 60:
        momentum = "strong"
    elif rsi < 30:
        momentum = "oversold"
    elif rsi < 40:
        momentum = "weak"
    else:
        momentum = "neutral"
    
    return {
        "rsi": rsi,
        "momentum": momentum,
    }

def analyze_ticker(ticker: str, full: bool = False) -> Dict:
    """Full technical analysis of a ticker"""
    print(f"\n📊 Analyzing {ticker}...")
    
    bars = get_daily_bars(ticker)
    if not bars:
        return {"error": f"No data for {ticker}"}
    
    closes = [b["c"] for b in bars]
    current_price = closes[-1]
    
    # Run all analyses
    trend = analyze_trend(bars)
    momentum = analyze_momentum(bars)
    volume = calculate_volume_trend(bars)
    levels = find_support_resistance(bars)
    
    # Calculate conviction score (-100 to +100)
    conviction = 0
    
    # Trend contribution
    conviction += trend["strength"] * 15  # ±45
    
    # RSI contribution
    if momentum["rsi"] > 70:
        conviction -= 20  # Overbought = bearish
    elif momentum["rsi"] > 60:
        conviction += 10
    elif momentum["rsi"] < 30:
        conviction += 20  # Oversold = bullish
    elif momentum["rsi"] < 40:
        conviction -= 10
    
    # Volume contribution
    if volume["trend"] == "spike":
        if trend["strength"] > 0:
            conviction += 15  # Volume confirming uptrend
        else:
            conviction -= 15  # Volume confirming downtrend
    elif volume["trend"] == "high":
        conviction += 5 if trend["strength"] > 0 else -5
    
    # Price vs support/resistance
    if current_price > levels["resistance"] * 0.98:
        conviction += 10  # Breaking resistance
    elif current_price < levels["support"] * 1.02:
        conviction -= 10  # Breaking support
    
    # Clamp
    conviction = max(-100, min(100, conviction))
    
    # Determine signal
    if conviction > 50:
        signal = "BULLISH"
        action = "BUY"
    elif conviction > 20:
        signal = "MODERATELY_BULLISH"
        action = "BUY"
    elif conviction < -50:
        signal = "BEARISH"
        action = "SELL"
    elif conviction < -20:
        signal = "MODERATELY_BEARISH"
        action = "SELL"
    else:
        signal = "NEUTRAL"
        action = "HOLD"
    
    result = {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "price": current_price,
        "signal": signal,
        "action": action,
        "conviction": conviction,
        "trend": trend,
        "momentum": momentum,
        "volume": volume,
        "levels": levels,
    }
    
    # Print summary
    emoji = "🟢" if conviction > 20 else "🔴" if conviction < -20 else "⚪"
    print(f"   {emoji} {signal} (conviction: {conviction:+.0f})")
    print(f"   Price: ${current_price:.2f}")
    print(f"   RSI: {momentum['rsi']:.1f} ({momentum['momentum']})")
    print(f"   Volume: {volume['trend']} ({volume['ratio']:.1f}x)")
    print(f"   Trend: {trend['trend']}")
    if full:
        print(f"   Support: ${levels['support']:.2f}")
        print(f"   Resistance: ${levels['resistance']:.2f}")
        print(f"   EMA9: ${trend['ema_9']:.2f}")
        print(f"   EMA21: ${trend['ema_21']:.2f}")
        print(f"   EMA50: ${trend['ema_50']:.2f}")
    
    return result

def analyze_portfolio():
    """Analyze all portfolio positions"""
    positions_file = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    
    if not positions_file.exists():
        print("❌ No portfolio data found")
        return
    
    with open(positions_file) as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    tickers = list(set(p["ticker"] for p in positions))
    
    print(f"\n🔍 Analyzing {len(tickers)} tickers...")
    
    results = []
    for ticker in tickers[:20]:  # Limit API calls
        result = analyze_ticker(ticker)
        if "error" not in result:
            results.append(result)
    
    # Summary
    bullish = [r for r in results if r["conviction"] > 20]
    bearish = [r for r in results if r["conviction"] < -20]
    neutral = [r for r in results if -20 <= r["conviction"] <= 20]
    
    print(f"\n📈 SUMMARY")
    print(f"   Bullish: {len(bullish)}")
    print(f"   Bearish: {len(bearish)}")
    print(f"   Neutral: {len(neutral)}")
    
    if bullish:
        print(f"\n🟢 Top Bullish:")
        for r in sorted(bullish, key=lambda x: x["conviction"], reverse=True)[:5]:
            print(f"      {r['ticker']}: {r['conviction']:+.0f} ({r['signal']})")
    
    if bearish:
        print(f"\n🔴 Top Bearish:")
        for r in sorted(bearish, key=lambda x: x["conviction"])[:5]:
            print(f"      {r['ticker']}: {r['conviction']:+.0f} ({r['signal']})")
    
    # Save results
    output_file = Path.home() / ".hermes" / "scripts" / "vox_technical_analysis.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "summary": {
                "bullish": len(bullish),
                "bearish": len(bearish),
                "neutral": len(neutral),
            }
        }, f, indent=2)
    
    print(f"\n✅ Saved to {output_file}")
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Technical Analyst")
    subparsers = parser.add_subparsers(dest="command")
    
    analyze_cmd = subparsers.add_parser("analyze", help="Analyze a ticker")
    analyze_cmd.add_argument("--ticker", required=True)
    analyze_cmd.add_argument("--full", action="store_true")
    
    batch_cmd = subparsers.add_parser("batch", help="Analyze portfolio")
    
    args = parser.parse_args()
    
    if args.command == "analyze":
        analyze_ticker(args.ticker, args.full)
    elif args.command == "batch":
        analyze_portfolio()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
