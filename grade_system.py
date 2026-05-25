#!/usr/bin/env python3
"""
Vox Grade System v1 — JOS-10
Scores stocks 0-100 across 5 pillars.
Threshold: 85+ = Strong Buy, 70-84 = Moderate Buy, 55-69 = Neutral, <55 = Avoid
"""

import os
import json
import math
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


def get_daily_bars(ticker, days=60):
    """Get daily OHLCV bars."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        print(f"⚠️ Polygon error for {ticker}: {result['error']}")
        return []
    return result.get("results", [])


def get_ticker_details(ticker):
    """Get ticker details (market cap, etc)."""
    return polygon_get(f"/v3/reference/tickers/{ticker}")


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


def calculate_macd(closes):
    """Calculate MACD histogram."""
    if len(closes) < 35:
        return None, None, None

    ema12 = calculate_ema(closes[:12], 12) or closes[0]
    ema26 = calculate_ema(closes[:26], 26) or closes[0]

    # Proper EMA calculation
    def ema_series(data, period):
        ema = [data[0]]
        mult = 2 / (period + 1)
        for price in data[1:]:
            ema.append((price - ema[-1]) * mult + ema[-1])
        return ema

    e12 = ema_series(closes, 12)
    e26 = ema_series(closes, 26)
    macd_line = [e12[i] - e26[i] for i in range(len(e12))]
    signal_line = ema_series(macd_line, 9)

    histogram = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], histogram


def calculate_adr(bars, period=14):
    """Average Daily Range %."""
    if len(bars) < period:
        return None
    ranges = []
    for bar in bars[-period:]:
        high = bar.get("h", 0)
        low = bar.get("l", 0)
        if low > 0:
            ranges.append((high - low) / low * 100)
    return sum(ranges) / len(ranges) if ranges else None


def calculate_avg_volume(bars, period=20):
    """Average volume."""
    if len(bars) < period:
        return None
    volumes = [bar.get("v", 0) for bar in bars[-period:]]
    return sum(volumes) / len(volumes)


def score_fundamental(ticker, details):
    """Score fundamentals 0-25."""
    score = 12.5  # Neutral base
    reasons = ["Base neutral score"]

    # Market cap scoring
    market_cap = details.get("results", {}).get("market_cap", 0)
    if market_cap > 100_000_000_000:  # Large cap
        score += 5
        reasons.append("Large cap stability (+5)")
    elif market_cap > 10_000_000_000:  # Mid cap
        score += 3
        reasons.append("Mid cap (+3)")
    elif market_cap > 2_000_000_000:  # Small cap
        score += 1
        reasons.append("Small cap (+1)")
    else:
        score -= 3
        reasons.append("Micro cap risk (-3)")

    # We don't have full financials on free tier, so use heuristics
    # Check if it's an ETF
    type_ = details.get("results", {}).get("type", "")
    if type_ == "ETF":
        score += 3
        reasons.append("ETF diversification (+3)")

    # Cap
    score = max(0, min(25, score))
    return round(score, 1), reasons


def score_technical(bars):
    """Score technicals 0-25."""
    if len(bars) < 50:
        return 10, ["Insufficient data, neutral score"]

    closes = [bar["c"] for bar in bars]
    volumes = [bar["v"] for bar in bars]
    current_price = closes[-1]

    score = 12.5
    reasons = ["Base neutral score"]

    # EMA trend
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)

    if ema21 and ema50:
        if current_price > ema21 > ema50:
            score += 4
            reasons.append("Price > EMA21 > EMA50 bullish trend (+4)")
        elif current_price > ema21:
            score += 2
            reasons.append("Price > EMA21 short-term bullish (+2)")
        elif current_price < ema21 < ema50:
            score -= 4
            reasons.append("Price < EMA21 < EMA50 bearish trend (-4)")
        elif current_price < ema21:
            score -= 2
            reasons.append("Price < EMA21 short-term bearish (-2)")

    # RSI
    rsi = calculate_rsi(closes)
    if rsi:
        if 40 <= rsi <= 60:
            score += 2
            reasons.append(f"RSI {rsi:.1f} neutral zone (+2)")
        elif 30 <= rsi < 40:
            score += 4
            reasons.append(f"RSI {rsi:.1f} oversold bounce potential (+4)")
        elif rsi < 30:
            score += 3
            reasons.append(f"RSI {rsi:.1f} deeply oversold (+3)")
        elif 60 < rsi <= 70:
            score -= 1
            reasons.append(f"RSI {rsi:.1f} getting hot (-1)")
        elif rsi > 70:
            score -= 3
            reasons.append(f"RSI {rsi:.1f} overbought (-3)")

    # MACD
    macd, signal, hist = calculate_macd(closes)
    if hist is not None:
        if hist > 0 and macd > 0:
            score += 3
            reasons.append("MACD bullish momentum (+3)")
        elif hist > 0:
            score += 1
            reasons.append("MACD turning up (+1)")
        elif hist < 0 and macd < 0:
            score -= 3
            reasons.append("MACD bearish momentum (-3)")
        elif hist < 0:
            score -= 1
            reasons.append("MACD turning down (-1)")

    # Volume
    avg_vol = calculate_avg_volume(bars)
    recent_vol = volumes[-1] if volumes else 0
    if avg_vol and recent_vol > avg_vol * 1.5:
        score += 2
        reasons.append("Volume spike confirms move (+2)")
    elif avg_vol and recent_vol < avg_vol * 0.5:
        score -= 1
        reasons.append("Low volume, weak conviction (-1)")

    # ADR (volatility)
    adr = calculate_adr(bars)
    if adr:
        if adr > 3:
            score += 1
            reasons.append(f"ADR {adr:.1f}% good volatility for swings (+1)")
        elif adr < 1:
            score -= 1
            reasons.append(f"ADR {adr:.1f}% too flat (-1)")

    score = max(0, min(25, score))
    return round(score, 1), reasons


def score_sentiment(ticker):
    """Score sentiment 0-20."""
    score = 10
    reasons = ["Base neutral score"]

    # Check X momentum data if available
    momentum_path = Path.home() / ".hermes" / "scripts" / "x_momentum_results.json"
    if momentum_path.exists():
        try:
            with open(momentum_path) as f:
                data = json.load(f)
                for item in data.get("momentum", []):
                    if item.get("ticker") == ticker:
                        sentiment = item.get("sentiment", "neutral")
                        if sentiment == "bullish":
                            score += 3
                            reasons.append("X sentiment bullish (+3)")
                        elif sentiment == "bearish":
                            score -= 3
                            reasons.append("X sentiment bearish (-3)")
                        break
        except:
            pass

    # Check Trump tracker for policy impact
    trump_path = Path.home() / ".hermes" / "scripts" / "trump_tracker_results.json"
    if trump_path.exists():
        try:
            with open(trump_path) as f:
                data = json.load(f)
                for tweet in data.get("tweets", []):
                    sectors = tweet.get("affected_sectors", [])
                    if ticker in sectors or any(ticker in s for s in sectors):
                        impact = tweet["classification"]["impact_score"]
                        if impact >= 7:
                            score -= 4
                            reasons.append(f"High policy risk from Trump tweet (-4)")
                        elif impact >= 4:
                            score -= 2
                            reasons.append(f"Medium policy risk (-2)")
                        break
        except:
            pass

    score = max(0, min(20, score))
    return round(score, 1), reasons


def score_macro(ticker, bars):
    """Score macro/market context 0-15."""
    score = 7.5
    reasons = ["Base neutral score"]

    # SPY correlation proxy — check if stock is above recent range
    if len(bars) >= 20:
        closes = [b["c"] for b in bars]
        current = closes[-1]
        high_20 = max(b["h"] for b in bars[-20:])
        low_20 = min(b["l"] for b in bars[-20:])

        if current > high_20 * 0.98:
            score += 3
            reasons.append("Near 20-day highs, strong relative strength (+3)")
        elif current < low_20 * 1.02:
            score -= 3
            reasons.append("Near 20-day lows, weak relative strength (-3)")

    # Sector ETFs — simplified
    tech_tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "TSLA", "AMD", "INTC", "CRM", "ADBE"]
    finance_tickers = ["JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "AXP"]
    energy_tickers = ["XOM", "CVX", "COP", "EOG", "OXY", "MPC", "VLO"]

    if ticker in tech_tickers:
        score += 1
        reasons.append("Tech sector, generally strong trend (+1)")
    elif ticker in finance_tickers:
        # Check Fed policy from Trump tracker
        reasons.append("Finance sector, Fed-sensitive")
    elif ticker in energy_tickers:
        reasons.append("Energy sector, commodity-sensitive")

    score = max(0, min(15, score))
    return round(score, 1), reasons


def score_risk_reward(ticker, bars, portfolio_value=200000):
    """Score risk/reward fit 0-15."""
    score = 7.5
    reasons = ["Base neutral score"]

    if len(bars) < 20:
        return round(score, 1), reasons

    closes = [b["c"] for b in bars]
    current = closes[-1]
    atr = calculate_adr(bars)  # Using ADR as ATR proxy

    if atr:
        # Stop loss distance (2x ATR)
        stop_distance = atr * 2
        stop_pct = stop_distance / current * 100

        if stop_pct < 5:
            score += 2
            reasons.append(f"Tight stop possible ({stop_pct:.1f}%), good R/R (+2)")
        elif stop_pct > 10:
            score -= 2
            reasons.append(f"Wide stop needed ({stop_pct:.1f}%), poor R/R (-2)")

        # Position sizing
        risk_per_trade = portfolio_value * 0.01  # 1% risk
        shares = int(risk_per_trade / (current * stop_pct / 100))
        position_value = shares * current

        if position_value > 0:
            position_pct = position_pct = position_value / portfolio_value * 100
            if position_pct > 10:
                reasons.append(f"Position would be {position_pct:.1f}% of portfolio — consider smaller size")
            elif position_pct < 1:
                reasons.append(f"Position only {position_pct:.1f}% — may not be worth the commission")

    score = max(0, min(15, score))
    return round(score, 1), reasons


def grade_stock(ticker, portfolio_value=200000):
    """Main grading function. Returns 0-100 score with breakdown."""
    print(f"\n{'='*70}")
    print(f"📊 VOX GRADE: {ticker}")
    print(f"{'='*70}")
    print(f"Analysis time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Portfolio reference: ${portfolio_value:,.0f}")
    print()

    # Fetch data
    print("Fetching data...")
    bars = get_daily_bars(ticker, days=60)
    details = get_ticker_details(ticker)

    if not bars:
        print(f"❌ No price data for {ticker}")
        return None

    if "error" in details:
        print(f"⚠️ Ticker details error: {details['error']}")
        details = {"results": {}}

    current_price = bars[-1]["c"]
    print(f"Current price: ${current_price:.2f}")
    print(f"Data points: {len(bars)} days")
    print()

    # Score each pillar
    f_score, f_reasons = score_fundamental(ticker, details)
    t_score, t_reasons = score_technical(bars)
    s_score, s_reasons = score_sentiment(ticker)
    m_score, m_reasons = score_macro(ticker, bars)
    r_score, r_reasons = score_risk_reward(ticker, bars, portfolio_value)

    total = f_score + t_score + s_score + m_score + r_score

    # Display breakdown
    print(f"{'='*70}")
    print("GRADE BREAKDOWN")
    print(f"{'='*70}")

    pillars = [
        ("Fundamental", f_score, 25, f_reasons),
        ("Technical", t_score, 25, t_reasons),
        ("Sentiment", s_score, 20, s_reasons),
        ("Macro/Market", m_score, 15, m_reasons),
        ("Risk/Reward", r_score, 15, r_reasons),
    ]

    for name, score, max_score, reasons in pillars:
        pct = score / max_score * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\n{name:15} | {bar} | {score:.1f}/{max_score} ({pct:.0f}%)")
        for r in reasons:
            print(f"   → {r}")

    # Total
    print(f"\n{'='*70}")
    grade_bar = "█" * int(total / 5) + "░" * (20 - int(total / 5))
    print(f"TOTAL GRADE     | {grade_bar} | {total:.1f}/100")
    print(f"{'='*70}")

    # Recommendation
    if total >= 85:
        rec = "🟢 STRONG BUY"
        action = "Consider entry with proper position size"
    elif total >= 70:
        rec = "🟡 MODERATE BUY"
        action = "Add to watchlist, wait for optimal entry"
    elif total >= 55:
        rec = "⚪ NEUTRAL"
        action = "No action — monitor for setup improvement"
    else:
        rec = "🔴 AVOID"
        action = "Skip — fundamentals/technical not aligned"

    print(f"\nRecommendation: {rec}")
    print(f"Action: {action}")

    # Key levels
    if len(bars) >= 20:
        highs = [b["h"] for b in bars[-20:]]
        lows = [b["l"] for b in bars[-20:]]
        print(f"\nKey Levels:")
        print(f"   20-day high: ${max(highs):.2f}")
        print(f"   20-day low:  ${min(lows):.2f}")
        print(f"   Current:     ${current_price:.2f}")

    # Save result
    result = {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "price": current_price,
        "total_grade": round(total, 1),
        "recommendation": rec,
        "action": action,
        "breakdown": {
            "fundamental": {"score": f_score, "max": 25, "reasons": f_reasons},
            "technical": {"score": t_score, "max": 25, "reasons": t_reasons},
            "sentiment": {"score": s_score, "max": 20, "reasons": s_reasons},
            "macro": {"score": m_score, "max": 15, "reasons": m_reasons},
            "risk_reward": {"score": r_score, "max": 15, "reasons": r_reasons},
        },
    }

    out_path = Path.home() / ".hermes" / "scripts" / "grade_results.json"
    if out_path.exists():
        with open(out_path) as f:
            all_results = json.load(f)
    else:
        all_results = {"grades": []}

    all_results["grades"].append(result)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n💾 Saved to grade_results.json")

    return result


def main():
    import sys
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        portfolio = float(sys.argv[2]) if len(sys.argv) > 2 else 200000
        grade_stock(ticker, portfolio)
    else:
        print("Usage: python3 grade_system.py TICKER [PORTFOLIO_VALUE]")
        print("Example: python3 grade_system.py AAPL 195000")


if __name__ == "__main__":
    main()
