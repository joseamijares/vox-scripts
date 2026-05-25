#!/usr/bin/env python3
"""
Vox Portfolio Scanner — Grades all positions with smart caching
"""

import json
import urllib.request
import time
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
    """Get daily bars with retry for rate limits."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    
    for attempt in range(3):
        result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
        if "error" in result:
            if "exceeded" in result.get("error", "").lower() or "429" in result.get("error", ""):
                wait_time = 12 * (attempt + 1)
                print(f"    Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            return []
        return result.get("results", [])
    return []


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
    bars = get_daily_bars(ticker, days=60)
    if not bars:
        return None
    
    closes = [bar["c"] for bar in bars]
    current = closes[-1]
    
    score = 50
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


# Priority 1: Your actual holdings (from memory)
HOLDINGS = [
    "VOO", "AAPL", "MSFT", "0700.HK", "BRK.B",
    "TSLA", "CRWD", "AMD", "NVDA", "OKLO", "CEG", "DELL",
    "JPM", "BAC", "XOM", "CVX", "O",
    "INDA", "EWZ", "EWW", "FXI",
    "COIN", "SQ", "MSTR",
    "POET", "JMIA", "IONQ", "RKLB", "BE", "GEV", "SMCI",
    "XLK", "SMH", "XLE", "XLF", "XLI", "XLV", "XLU", "XLP", "XLB",
    "OSCR", "PLTR", "SHOP", "NET", "DDOG", "MDB", "S", "ZS",
    "FTNT", "NOW", "CRM", "META", "GOOGL", "NFLX", "UBER", "ABNB",
    "SNOW", "PANW", "LLY", "AMAT", "MU", "ANET", "VST", "COHR",
    "ALSEA.MX", "BIMBO.MX", "CEMEX.MX", "GMEXICO.MX",
    "BYND", "RBLX", "CFLT", "DOCN", "ESTC", "GTLB", "PATH",
    "AI", "TOST", "BILL", "LSPD", "MNDY", "ASAN",
    "KO", "PEP", "PG", "JNJ", "UNH", "PFE", "ABBV", "BMY",
    "VZ", "T", "CVS", "WBA", "MO", "PM",
]


def main():
    print("=" * 70)
    print("📊 VOX PORTFOLIO SCANNER")
    print("=" * 70)
    print(f"Scanning {len(HOLDINGS)} positions...")
    print("(Rate limited: ~2 seconds per ticker)")
    print()
    
    results = []
    errors = []
    
    for i, ticker in enumerate(HOLDINGS, 1):
        print(f"[{i:3}/{len(HOLDINGS)}] {ticker:10} ...", end=" ")
        time.sleep(0.3)  # Unlimited tier: minimal delay
        
        try:
            result = grade_ticker(ticker)
            if result:
                results.append(result)
                rsi_str = f"{result['rsi']:.1f}" if result['rsi'] is not None else "N/A"
                print(f"Grade: {result['grade']:2.0f} | ${result['price']:8.2f} | RSI: {rsi_str}")
            else:
                errors.append(ticker)
                print("NO DATA")
        except Exception as e:
            errors.append(ticker)
            print(f"ERROR: {e}")
    
    results.sort(key=lambda x: x["grade"], reverse=True)
    
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    
    strong = [r for r in results if r["grade"] >= 70]
    moderate = [r for r in results if 55 <= r["grade"] < 70]
    weak = [r for r in results if r["grade"] < 55]
    
    print(f"\n🟢 STRONG BUY (70+): {len(strong)}")
    for r in strong:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:10} | {r['grade']:5.1f} | ${r['price']:9.2f} | RSI {rsi_str}")
    
    print(f"\n🟡 MODERATE BUY (55-69): {len(moderate)}")
    for r in moderate:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:10} | {r['grade']:5.1f} | ${r['price']:9.2f} | RSI {rsi_str}")
    
    print(f"\n🔴 AVOID / CUT (<55): {len(weak)}")
    for r in weak:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:10} | {r['grade']:5.1f} | ${r['price']:9.2f} | RSI {rsi_str}")
    
    if errors:
        print(f"\n⚠️  ERRORS ({len(errors)}): {', '.join(errors[:15])}")
    
    # Save
    out_path = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(HOLDINGS),
            "graded": len(results),
            "errors": len(errors),
            "strong_buy": strong,
            "moderate_buy": moderate,
            "avoid": weak
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to portfolio_grades.json")
    print(f"\nSUMMARY: {len(strong)} strong | {len(moderate)} moderate | {len(weak)} weak | {len(errors)} errors")


if __name__ == "__main__":
    main()
