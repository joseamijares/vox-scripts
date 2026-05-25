#!/usr/bin/env python3
"""
Vox Batch Grade — Fast parallel grading for full portfolio
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


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
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {"error": "POLYGON_API_KEY not set"}
    url = f"https://api.polygon.io{path}?apiKey={api_key}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_daily_bars(ticker, days=60):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        return []
    return result.get("results", [])


def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def grade_ticker(ticker):
    """Fast grade a single ticker."""
    bars = get_daily_bars(ticker, days=60)
    if not bars:
        return None
    
    closes = [bar["c"] for bar in bars]
    current = closes[-1]
    
    # Technical score (simplified)
    score = 50  # Base
    
    # EMA trend
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    if ema21 and ema50:
        if current > ema21 > ema50:
            score += 15
        elif current > ema21:
            score += 5
        elif current < ema21 < ema50:
            score -= 15
        else:
            score -= 5
    
    # RSI
    rsi = calculate_rsi(closes)
    if rsi:
        if 40 <= rsi <= 60:
            score += 5
        elif 30 <= rsi < 40:
            score += 10
        elif rsi < 30:
            score += 5
        elif rsi > 70:
            score -= 10
        elif rsi > 60:
            score -= 5
    
    # Near highs/lows
    if len(bars) >= 20:
        high_20 = max(b["h"] for b in bars[-20:])
        low_20 = min(b["l"] for b in bars[-20:])
        if current > high_20 * 0.98:
            score += 5
        elif current < low_20 * 1.02:
            score -= 5
    
    return {
        "ticker": ticker,
        "grade": max(0, min(100, score)),
        "price": current,
        "rsi": rsi,
        "ema21": ema21,
        "ema50": ema50
    }


# Your full portfolio
PORTFOLIO = [
    # Core
    "VOO", "AAPL", "MSFT", "0700.HK", "BRK.B",
    # Growth
    "TSLA", "CRWD", "AMD", "NVDA", "OKLO", "CEG", "DELL",
    # Value
    "JPM", "BAC", "XOM", "CVX", "O",
    # International
    "INDA", "EWZ", "EWW", "FXI",
    # Crypto-adjacent
    "COIN", "SQ", "MSTR",
    # Small Cap/Spec
    "POET", "JMIA", "IONQ", "RKLB", "BE", "GEV", "SMCI",
    # Sector ETFs
    "XLK", "SMH", "XLE", "XLF", "XLI", "XLV", "XLU", "XLP", "XLB",
    # Other
    "OSCR", "PLTR", "SHOP", "NET", "DDOG", "MDB", "S", "ZS",
    "FTNT", "NOW", "CRM", "META", "GOOGL", "NFLX", "UBER", "ABNB",
    "SNOW", "PANW", "LLY", "AMAT", "MU", "ANET", "VST", "COHR",
    # Mexican
    "ALSEA.MX", "BIMBO.MX", "CEMEX.MX", "GMEXICO.MX",
    # More growth
    "BYND", "RBLX", "DOCN", "CFLT", "ESTC", "GTLB", "PATH",
    "AI", " sound", "LSPD", "TOST", "BILL", "ASAN", "MNDY",
    # Dividend
    "KO", "PEP", "PG", "JNJ", "UNH", "PFE", "ABBV", "BMY",
    "VZ", "T", "CVS", "WBA", "MO", "PM",
]


def main():
    print("=" * 70)
    print("📊 VOX BATCH PORTFOLIO GRADE")
    print("=" * 70)
    print(f"Scanning {len(PORTFOLIO)} positions in parallel...")
    print()
    
    results = []
    errors = []
    
    for i, ticker in enumerate(PORTFOLIO, 1):
        print(f"[{i}/{len(PORTFOLIO)}] Grading {ticker}...")
        time.sleep(0.5)  # Rate limit: 2 requests per second max
        
        try:
            result = grade_ticker(ticker)
            if result:
                results.append(result)
                rsi_str = f"{result['rsi']:.1f}" if result['rsi'] is not None else "N/A"
                print(f"  ✅ Grade: {result['grade']:.0f} | Price: ${result['price']:.2f} | RSI: {rsi_str}")
            else:
                errors.append(ticker)
                print(f"  ❌ No data")
        except Exception as e:
            errors.append(ticker)
            print(f"  ❌ Error: {e}")
    
    # Sort by grade
    results.sort(key=lambda x: x["grade"], reverse=True)
    
    print("\n" + "=" * 70)
    print("📊 FULL PORTFOLIO GRADES")
    print("=" * 70)
    
    strong = [r for r in results if r["grade"] >= 70]
    moderate = [r for r in results if 55 <= r["grade"] < 70]
    weak = [r for r in results if r["grade"] < 55]
    
    print(f"\n🟢 STRONG ({len(strong)}):")
    for r in strong[:10]:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:8} | {r['grade']:5.1f} | ${r['price']:8.2f} | RSI {rsi_str}")
    
    print(f"\n🟡 MODERATE ({len(moderate)}):")
    for r in moderate[:15]:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:8} | {r['grade']:5.1f} | ${r['price']:8.2f} | RSI {rsi_str}")
    
    print(f"\n🔴 WEAK ({len(weak)}):")
    for r in weak[:10]:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:8} | {r['grade']:5.1f} | ${r['price']:8.2f} | RSI {rsi_str}")
    
    if errors:
        print(f"\n⚠️ Errors ({len(errors)}): {', '.join(errors[:10])}")
    
    # Save
    out_path = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(PORTFOLIO),
            "graded": len(results),
            "errors": len(errors),
            "strong_buy": strong,
            "moderate_buy": moderate,
            "avoid": weak
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to portfolio_grades.json")


if __name__ == "__main__":
    main()
