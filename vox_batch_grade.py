#!/usr/bin/env python3
"""
Vox Batch Grade v2.0 — Proper multi-factor grading for portfolio positions.
Factors: trend, momentum, volatility, volume, support/resistance.
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
import time


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
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_daily_bars(ticker, days=90):
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


def calculate_atr(bars, period=14):
    """Average True Range for volatility scoring."""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        high = bars[i]["h"]
        low = bars[i]["l"]
        prev_close = bars[i-1]["c"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period


def grade_ticker(ticker):
    """Comprehensive grade a single ticker."""
    bars = get_daily_bars(ticker, days=90)
    if not bars or len(bars) < 50:
        return None
    
    closes = [bar["c"] for bar in bars]
    volumes = [bar["v"] for bar in bars]
    current = closes[-1]
    prev_close = closes[-2]
    
    # ─── TREND SCORE (0-30) ──────────────────────────────────────────
    trend_score = 15  # Neutral base
    
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    
    if ema21 and ema50:
        if current > ema21 > ema50:
            trend_score = 28  # Strong uptrend
        elif current > ema21:
            trend_score = 22  # Above short EMA
        elif current < ema21 < ema50:
            trend_score = 5   # Strong downtrend
        elif current < ema21:
            trend_score = 10  # Below short EMA
    
    # Trend strength: distance from EMA50
    if ema50:
        pct_from_50 = (current - ema50) / ema50 * 100
        if pct_from_50 > 10:
            trend_score += 2
        elif pct_from_50 < -10:
            trend_score -= 2
    
    # Longer-term trend (200-day EMA if available)
    if len(closes) >= 200:
        ema200 = calculate_ema(closes, 200)
        if ema200:
            if current > ema200:
                trend_score += 3  # Above long-term trend
            else:
                trend_score -= 3  # Below long-term trend
    elif len(closes) >= 100:
        ema100 = calculate_ema(closes, 100)
        if ema100:
            if current > ema100:
                trend_score += 2
            else:
                trend_score -= 2
    
    # Recent price action (last 5 days)
    if len(closes) >= 5:
        recent_return = (closes[-1] - closes[-5]) / closes[-5] * 100
        if recent_return > 5:
            trend_score += 3  # Strong recent bounce
        elif recent_return > 2:
            trend_score += 1
        elif recent_return < -5:
            trend_score -= 3  # Recent breakdown
        elif recent_return < -2:
            trend_score -= 1
    
    trend_score = max(0, min(30, trend_score))
    
    # ─── MOMENTUM SCORE (0-25) ───────────────────────────────────────
    momentum_score = 12  # Neutral
    
    rsi = calculate_rsi(closes)
    if rsi:
        if 50 <= rsi <= 60:
            momentum_score = 20  # Healthy momentum
        elif 40 <= rsi < 50:
            momentum_score = 15  # Mild weakness
        elif 30 <= rsi < 40:
            momentum_score = 10  # Oversold but not extreme
        elif rsi < 30:
            momentum_score = 18  # Deep oversold - mean reversion potential
        elif 60 < rsi <= 70:
            momentum_score = 15  # Getting extended
        elif rsi > 70:
            momentum_score = 8   # Overbought
    
    # Price vs 20-day high/low — REWARD mean reversion from lows
    if len(bars) >= 20:
        high_20 = max(b["h"] for b in bars[-20:])
        low_20 = min(b["l"] for b in bars[-20:])
        range_20 = high_20 - low_20
        if range_20 > 0:
            position_in_range = (current - low_20) / range_20
            if position_in_range > 0.8:
                momentum_score += 3  # Near highs
            elif position_in_range < 0.2:
                momentum_score += 5  # Near lows = bounce potential
            elif position_in_range > 0.5:
                momentum_score += 2  # Above midpoint
    
    momentum_score = max(0, min(25, momentum_score))
    
    # ─── VOLATILITY SCORE (0-20) ─────────────────────────────────────
    vol_score = 10  # Neutral
    
    atr = calculate_atr(bars)
    if atr and current > 0:
        atr_pct = atr / current * 100
        if atr_pct < 2:
            vol_score = 15  # Low vol = stable
        elif atr_pct < 4:
            vol_score = 12  # Normal vol
        elif atr_pct < 7:
            vol_score = 8   # Elevated
        else:
            vol_score = 5   # High vol = risky
    
    # Recent volatility trend
    if len(closes) >= 20:
        recent_vol = sum(abs(closes[i] - closes[i-1]) for i in range(-10, 0)) / 10
        older_vol = sum(abs(closes[i] - closes[i-1]) for i in range(-20, -10)) / 10
        if older_vol > 0:
            vol_trend = recent_vol / older_vol
            if vol_trend < 0.8:
                vol_score += 3  # Volatility contracting = good
            elif vol_trend > 1.5:
                vol_score -= 3  # Volatility expanding = risky
    
    vol_score = max(0, min(20, vol_score))
    
    # ─── VOLUME SCORE (0-15) ─────────────────────────────────────────
    volume_score = 8  # Neutral
    
    if len(volumes) >= 20:
        avg_vol_20 = sum(volumes[-20:]) / 20
        avg_vol_50 = sum(volumes[-50:]) / 50 if len(volumes) >= 50 else avg_vol_20
        today_vol = volumes[-1]
        
        if avg_vol_20 > 0:
            vol_ratio = today_vol / avg_vol_20
            if vol_ratio > 2:
                volume_score = 14  # Heavy volume = conviction
            elif vol_ratio > 1.5:
                volume_score = 12
            elif vol_ratio > 1:
                volume_score = 10
            elif vol_ratio < 0.5:
                volume_score = 5   # Low volume = no interest
        
        # Volume trend
        if avg_vol_50 > 0:
            vol_trend = avg_vol_20 / avg_vol_50
            if vol_trend > 1.3:
                volume_score += 1  # Increasing volume
    
    volume_score = max(0, min(15, volume_score))
    
    # ─── SUPPORT/RESISTANCE SCORE (0-10) ─────────────────────────────
    sr_score = 5  # Neutral
    
    if len(bars) >= 20:
        # Bounce off 20-day low = support
        low_20 = min(b["l"] for b in bars[-20:])
        high_20 = max(b["h"] for b in bars[-20:])
        
        if current < low_20 * 1.03:
            sr_score = 3  # Near support but weak
        elif current > high_20 * 0.97:
            sr_score = 7  # Near resistance but strong
        
        # 50-day context
        if len(bars) >= 50:
            low_50 = min(b["l"] for b in bars[-50:])
            high_50 = max(b["h"] for b in bars[-50:])
            if current > low_50 * 1.2 and current < high_50 * 0.8:
                sr_score = 6  # Middle of range = neutral
    
    sr_score = max(0, min(10, sr_score))
    
    # ─── COMPOSITE GRADE ──────────────────────────────────────────────
    total_score = trend_score + momentum_score + vol_score + volume_score + sr_score
    
    # Normalize to 0-100 (max possible is 30+25+20+15+10 = 100)
    grade = int(total_score)
    
    # Apply position-size bonus for smaller positions
    # Small speculative positions get +5 to grade (more lenient)
    # This reflects that small positions can ride out pullbacks
    # Note: This is applied at alert level, not grade level
    
    return {
        "ticker": ticker,
        "grade": grade,
        "price": current,
        "rsi": rsi,
        "ema21": ema21,
        "ema50": ema50,
        "atr": atr,
        "scores": {
            "trend": trend_score,
            "momentum": momentum_score,
            "volatility": vol_score,
            "volume": volume_score,
            "support_resistance": sr_score
        }
    }


def main():
    # Load portfolio from dashboard_positions.json
    dashboard_path = Path.home() / ".hermes" / "scripts" / "dashboard_positions.json"
    with open(dashboard_path) as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    
    # Extract unique tickers
    tickers = sorted(set(p["ticker"] for p in positions))
    
    print("=" * 70)
    print("📊 VOX BATCH PORTFOLIO GRADE v2.0")
    print("=" * 70)
    print(f"Scanning {len(tickers)} unique tickers...")
    print("Scoring: Trend(30) + Momentum(25) + Volatility(20) + Volume(15) + S/R(10)")
    print()
    
    results = []
    errors = []
    
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Grading {ticker}...", end=" ")
        time.sleep(0.3)  # Rate limit
        
        try:
            result = grade_ticker(ticker)
            if result:
                results.append(result)
                scores = result['scores']
                print(f"✅ Grade: {result['grade']:3d} | T:{scores['trend']:2d} M:{scores['momentum']:2d} V:{scores['volatility']:2d} Vol:{scores['volume']:2d} SR:{scores['support_resistance']:2d}")
            else:
                errors.append(ticker)
                print("❌ No data")
        except Exception as e:
            errors.append(ticker)
            print(f"❌ Error: {e}")
    
    # Sort by grade
    results.sort(key=lambda x: x["grade"], reverse=True)
    
    print("\n" + "=" * 70)
    print("📊 FULL PORTFOLIO GRADES")
    print("=" * 70)
    
    strong = [r for r in results if r["grade"] >= 70]
    moderate = [r for r in results if 50 <= r["grade"] < 70]
    weak = [r for r in results if r["grade"] < 50]
    
    print(f"\n🟢 STRONG — Grade 70+ ({len(strong)}):")
    for r in strong[:15]:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:8} | {r['grade']:3d} | ${r['price']:8.2f} | RSI {rsi_str:>5}")
    
    print(f"\n🟡 MODERATE — Grade 50-69 ({len(moderate)}):")
    for r in moderate[:20]:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:8} | {r['grade']:3d} | ${r['price']:8.2f} | RSI {rsi_str:>5}")
    
    print(f"\n🔴 WEAK — Grade <50 ({len(weak)}):")
    for r in weak[:15]:
        rsi_str = f"{r['rsi']:.1f}" if r['rsi'] is not None else "N/A"
        print(f"   {r['ticker']:8} | {r['grade']:3d} | ${r['price']:8.2f} | RSI {rsi_str:>5}")
    
    if errors:
        print(f"\n⚠️ Errors ({len(errors)}): {', '.join(errors[:20])}")
    
    # Save
    out_path = Path.home() / ".hermes" / "scripts" / "portfolio_grades.json"
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(tickers),
            "graded": len(results),
            "errors": len(errors),
            "strong_buy": strong,
            "moderate_buy": moderate,
            "avoid": weak
        }, f, indent=2, default=str)
    
    print(f"\n💾 Saved to portfolio_grades.json")
    
    # Also copy to dashboard
    dashboard_public = Path.home() / "dev" / "vox-dashboard" / "public" / "portfolio_grades.json"
    if dashboard_public.parent.exists():
        import shutil
        shutil.copy(out_path, dashboard_public)
        print(f"💾 Copied to dashboard public/")


if __name__ == "__main__":
    main()
