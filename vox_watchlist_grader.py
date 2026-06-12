#!/usr/bin/env python3
"""
VOX Watchlist Grader + Entry Target Generator
Proactively grades all watchlist tickers and calculates entry/exit levels
"""

import json, os, sys, urllib.request, math
from datetime import datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")

def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v.strip('"').strip("'")
    return env

ENV = load_env()
POLYGON_KEY = ENV.get("POLYGON_API_KEY", "")

def polygon_api(endpoint):
    url = f"https://api.polygon.io{endpoint}&apiKey={POLYGON_KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_daily_bars(ticker, days=60):
    """Get daily OHLCV bars"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime("%Y-%m-%d")
    data = polygon_api(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?limit=5000")
    return data.get("results", [])

def get_snapshot(ticker):
    """Get current snapshot"""
    data = polygon_api(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
    return data.get("ticker", {})

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(bars, period=14):
    if len(bars) < period:
        return None
    trs = []
    for i in range(1, min(period + 1, len(bars))):
        high = bars[-i]["h"]
        low = bars[-i]["l"]
        prev_close = bars[-i-1]["c"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)

def grade_ticker(ticker, bars, snapshot):
    """Multi-factor grading with entry/exit targets"""
    if not bars or len(bars) < 30:
        return None
    
    closes = [b["c"] for b in bars]
    volumes = [b["v"] for b in bars]
    current_price = closes[-1]
    
    # Technical indicators
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes)
    atr = calculate_atr(bars)
    
    if not ema21 or not atr:
        return None
    
    # Volume analysis
    avg_volume = sum(volumes[-20:]) / 20
    latest_volume = volumes[-1]
    volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 1
    
    # Support/Resistance (last 20 days)
    recent_highs = [b["h"] for b in bars[-20:]]
    recent_lows = [b["l"] for b in bars[-20:]]
    resistance = max(recent_highs)
    support = min(recent_lows)
    
    # === GRADING ===
    # Trend score (0-30)
    trend_score = 15
    if ema50 and current_price > ema21 > ema50:
        trend_score = 30  # Strong uptrend
    elif current_price > ema21:
        trend_score = 24  # Above EMA21
    elif ema50 and current_price > ema50:
        trend_score = 18  # Above EMA50 but below EMA21
    elif ema50 and ema21 > ema50:
        trend_score = 12  # EMA crossover bearish
    else:
        trend_score = 6   # Below both EMAs
    
    # Momentum score (0-25)
    momentum_score = 12.5
    if rsi > 70:
        momentum_score = 20  # Overbought but strong
    elif rsi > 60:
        momentum_score = 25  # Sweet spot
    elif rsi > 50:
        momentum_score = 20
    elif rsi > 40:
        momentum_score = 15
    elif rsi > 30:
        momentum_score = 10
    else:
        momentum_score = 5   # Oversold
    
    # Volatility score (0-20)
    vol_pct = (atr / current_price) * 100
    if vol_pct < 2:
        volatility_score = 20  # Low vol = stable
    elif vol_pct < 4:
        volatility_score = 16
    elif vol_pct < 6:
        volatility_score = 12
    elif vol_pct < 10:
        volatility_score = 8
    else:
        volatility_score = 4   # High vol = risky
    
    # Volume score (0-15)
    if volume_ratio > 2.0:
        volume_score = 15  # Massive volume spike
    elif volume_ratio > 1.5:
        volume_score = 12
    elif volume_ratio > 1.2:
        volume_score = 9
    elif volume_ratio > 0.8:
        volume_score = 7
    else:
        volume_score = 4   # Low volume
    
    # Support/Resistance score (0-10)
    sr_score = 5
    if current_price > resistance * 0.98:
        sr_score = 10  # Breaking out
    elif current_price > support * 1.05:
        sr_score = 7   # Well above support
    elif current_price < support * 1.02:
        sr_score = 3   # Near support (risky)
    
    total_score = trend_score + momentum_score + volatility_score + volume_score + sr_score
    grade = min(100, max(0, int(total_score)))
    
    # === ENTRY/EXIT TARGETS ===
    # Buy zone: near support or pullback to EMA21
    if current_price > ema21:
        buy_zone = ema21 * 0.98  # Pullback to EMA21
    else:
        buy_zone = support * 1.01  # Near support
    
    # Stop loss: below support or ATR-based
    stop_loss = min(support * 0.97, current_price - (atr * 2))
    
    # Target 1: recent resistance
    target_1 = resistance * 1.02
    
    # Target 2: extended target (2R)
    risk = current_price - stop_loss
    target_2 = current_price + (risk * 3)
    
    # Position size suggestion (based on volatility)
    if vol_pct < 3:
        position_size = "Full"
    elif vol_pct < 5:
        position_size = "Standard"
    elif vol_pct < 8:
        position_size = "Half"
    else:
        position_size = "Quarter"
    
    # Signal
    if grade >= 70:
        signal = "STRONG_BUY"
    elif grade >= 60:
        signal = "BUY"
    elif grade >= 50:
        signal = "HOLD"
    elif grade >= 40:
        signal = "WEAK"
    elif grade >= 30:
        signal = "AVOID"
    else:
        signal = "SELL"
    
    return {
        "ticker": ticker,
        "price": round(current_price, 2),
        "grade": grade,
        "signal": signal,
        "rsi": round(rsi, 1),
        "ema21": round(ema21, 2),
        "ema50": round(ema50, 2) if ema50 else None,
        "atr": round(atr, 2),
        "volume_ratio": round(volume_ratio, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "buy_zone": round(buy_zone, 2),
        "stop_loss": round(stop_loss, 2),
        "target_1": round(target_1, 2),
        "target_2": round(target_2, 2),
        "risk_reward": round((target_1 - current_price) / (current_price - stop_loss), 2) if (current_price - stop_loss) > 0 else 0,
        "position_size": position_size,
        "scores": {
            "trend": round(trend_score, 1),
            "momentum": round(momentum_score, 1),
            "volatility": round(volatility_score, 1),
            "volume": round(volume_score, 1),
            "support_resistance": round(sr_score, 1)
        },
        "graded_at": datetime.now().isoformat()
    }

def main():
    print("=" * 60)
    print("VOX WATCHLIST GRADER + ENTRY TARGET GENERATOR")
    print("=" * 60)
    
    # Load watchlist
    watchlist_path = os.path.expanduser("~/.hermes/scripts/vox_watchlist.json")
    with open(watchlist_path) as f:
        data = json.load(f)
    
    watchlist = data.get("watchlist", [])
    print(f"\nGrading {len(watchlist)} watchlist tickers...")
    print("-" * 60)
    
    graded = []
    errors = []
    
    for i, item in enumerate(watchlist):
        ticker = item["ticker"]
        print(f"\n[{i+1}/{len(watchlist)}] {ticker}...", end=" ", flush=True)
        
        bars = get_daily_bars(ticker)
        if not bars or len(bars) < 30:
            print(f"ERROR: Insufficient data ({len(bars)} bars)")
            errors.append({"ticker": ticker, "error": "insufficient_data"})
            continue
        
        snapshot = get_snapshot(ticker)
        result = grade_ticker(ticker, bars, snapshot)
        if result:
            graded.append(result)
            print(f"GRADE={result['grade']} SIGNAL={result['signal']}")
            print(f"       Buy@${result['buy_zone']} → Target1=${result['target_1']} → Target2=${result['target_2']}")
            print(f"       Stop@${result['stop_loss']} R:R={result['risk_reward']}x Size={result['position_size']}")
        else:
            print("ERROR: Grading failed")
            errors.append({"ticker": ticker, "error": "grading_failed"})
    
    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "total": len(watchlist),
        "graded": len(graded),
        "errors": len(errors),
        "results": graded,
        "errors_detail": errors
    }
    
    output_path = os.path.expanduser("~/.hermes/scripts/vox_watchlist_graded.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {len(watchlist)}")
    print(f"Graded: {len(graded)}")
    print(f"Errors: {len(errors)}")
    
    if graded:
        strong_buy = [g for g in graded if g["signal"] == "STRONG_BUY"]
        buy = [g for g in graded if g["signal"] == "BUY"]
        hold = [g for g in graded if g["signal"] == "HOLD"]
        weak = [g for g in graded if g["signal"] == "WEAK"]
        avoid = [g for g in graded if g["signal"] == "AVOID"]
        
        print(f"\nSTRONG BUY: {len(strong_buy)}")
        for g in strong_buy:
            print(f"  {g['ticker']}: {g['grade']} @ ${g['price']} → Buy ${g['buy_zone']} → T1 ${g['target_1']}")
        
        print(f"\nBUY: {len(buy)}")
        for g in buy:
            print(f"  {g['ticker']}: {g['grade']} @ ${g['price']} → Buy ${g['buy_zone']} → T1 ${g['target_1']}")
        
        print(f"\nHOLD: {len(hold)}")
        for g in hold:
            print(f"  {g['ticker']}: {g['grade']} @ ${g['price']}")
        
        print(f"\nWEAK: {len(weak)}")
        for g in weak:
            print(f"  {g['ticker']}: {g['grade']} @ ${g['price']}")
        
        print(f"\nAVOID: {len(avoid)}")
        for g in avoid:
            print(f"  {g['ticker']}: {g['grade']} @ ${g['price']}")
    
    print(f"\nSaved to: {output_path}")
    return output

if __name__ == "__main__":
    main()
